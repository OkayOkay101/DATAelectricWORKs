import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
import sys
from unittest.mock import MagicMock

class MockSt:
    def cache_data(self, func=None, **kwargs):
        if func is None:
            return lambda f: f
        return func

    def warning(self, msg):
        pass

sys.modules['streamlit'] = MockSt()

import pandas as pd
import numpy as np
from data_handler import parse_text_lines, parse_excel_df, preprocess_data, get_usage_snapshots

class TestDataHandler(unittest.TestCase):

    def test_parse_text_lines_basic(self):
        lines = [
            "Company XYZ",
            "Clock, kW_Import, Voltage",
            "01/01/2023 00:15, 100.5, 220",
            "01/01/2023 00:30, 110.2, 221",
            "01/01/2023 00:45, NaN, 220",  # Test invalid values might be parsed as string
            "total, p, op" # Should be skipped or handled gracefully
        ]
        df = parse_text_lines(lines, delimiter=',')

        self.assertIsNotNone(df)
        self.assertEqual(list(df.columns), ['Clock', 'kW_Import', 'Voltage'])
        # The last line should be skipped because of "total" in clock column
        self.assertEqual(len(df), 3)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2023 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], "100.5")
        self.assertEqual(df.iloc[0]['Voltage'], "220")

    def test_parse_text_lines_tab_separated(self):
        lines = [
            "เวลา\tพลังงาน\tแรงดัน",
            "01/01/2023 00:15\t50.0\t230"
        ]
        df = parse_text_lines(lines, delimiter='\t')
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2023 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], "50.0")

    def test_parse_excel_df_basic(self):
        df_raw = pd.DataFrame([
            ["Metadata row 1", None, None],
            ["Clock", "Import kW", "Voltage"],
            ["01/01/2023 00:15", 200, 225],
            ["total", 0, 0] # Should be skipped
        ])
        df = parse_excel_df(df_raw)
        self.assertIsNotNone(df)
        self.assertEqual(list(df.columns), ['Clock', 'kW_Import', 'Voltage'])
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2023 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], 200)

    def test_parse_excel_df_non_string_headers(self):
        # DataFrame with integer or float headers in metadata rows
        df_raw = pd.DataFrame([
            [123, 456.78, None],
            ["Clock", "Import kW", "Voltage"],
            ["01/01/2023 00:15", 200, 225],
        ])
        df = parse_excel_df(df_raw)
        self.assertIsNotNone(df)
        self.assertEqual(list(df.columns), ['Clock', 'kW_Import', 'Voltage'])
        self.assertEqual(len(df), 1)

    def test_preprocess_data(self):
        # Initial DataFrame mimicking output of parse_text_lines / parse_excel_df
        data = {
            'Clock': ["01/01/2023 00:15", "01/01/2023 00:30", "02/01/2023 00:15", "01/01/2023 00:15"], # Includes duplicate
            'kW_Import': ["100.5", "110", "120.5", "100.5"],
            'Voltage': ["220", "225", "230", "220"]
        }
        df_in = pd.DataFrame(data)

        df_out = preprocess_data(df_in)

        self.assertFalse(df_out.empty)
        # Check columns
        expected_cols = ['Clock', 'kW_Import', 'Voltage', 'Date', 'Month', 'Time_Str', 'kWh_15min']
        for col in expected_cols:
            self.assertIn(col, df_out.columns)

        # Check deduplication
        self.assertEqual(len(df_out), 3) # 4 original - 1 duplicate = 3

        # Check data types
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df_out['Clock']))
        self.assertTrue(pd.api.types.is_numeric_dtype(df_out['kW_Import']))
        self.assertTrue(pd.api.types.is_numeric_dtype(df_out['Voltage']))

        # Check specific values
        self.assertEqual(df_out.iloc[0]['kW_Import'], 100.5)
        self.assertEqual(df_out.iloc[0]['kWh_15min'], 100.5 / 4.0)
        self.assertEqual(df_out.iloc[0]['Time_Str'], "00:15")
        self.assertEqual(df_out.iloc[0]['Month'], "2023-01")

    def test_preprocess_data_error_handling(self):
        # Testing missing values and outliers
        data = {
            'Clock': ["invalid_date", "01/01/2023 00:30", "01/01/2023 00:45"],
            'kW_Import': ["100.5", "abc", 3000000], # Outlier (>=2,000,000)
            'Voltage': ["220", "225", "230"]
        }
        df_in = pd.DataFrame(data)

        df_out = preprocess_data(df_in)

        # invalid_date is dropped, abc becomes 0 or handled, outlier is kept
        # row 0: dropped (NaT Clock)
        # row 1: kW_Import 'abc' -> becomes 0
        # row 2: kW_Import 3000000 -> kept (Outlier now generates a warning instead of dropping)
        self.assertEqual(len(df_out), 2)
        self.assertEqual(df_out.iloc[0]['kW_Import'], 0) # "abc" -> 0
        self.assertEqual(df_out.iloc[1]['kW_Import'], 3000000) # outlier kept

    def test_get_usage_snapshots(self):
        data = {
            'Clock': pd.to_datetime([
                "2023-01-01 00:00:00",
                "2023-01-01 00:15:00",
                "2023-01-01 00:30:00",
                "2023-01-01 00:45:00",
                "2023-01-01 01:00:00",
                "2023-01-01 01:15:00",
            ]),
            'kW_Import': [0, 100, 150, 0, 50, 0]
        }
        df = pd.DataFrame(data)
        snapshots = get_usage_snapshots(df)
        self.assertEqual(len(snapshots), 2)

        self.assertEqual(snapshots[0]['start_idx'], 0) # previous index (0)
        self.assertEqual(snapshots[0]['end_idx'], 3) # ends at index 3

        self.assertEqual(snapshots[1]['start_idx'], 3)
        self.assertEqual(snapshots[1]['end_idx'], 5)

    def test_get_usage_snapshots_empty(self):
        df = pd.DataFrame()
        snapshots = get_usage_snapshots(df)
        self.assertEqual(len(snapshots), 0)

    def test_get_usage_snapshots_no_usage(self):
        data = {
            'Clock': pd.to_datetime(["2023-01-01 00:00:00", "2023-01-01 00:15:00"]),
            'kW_Import': [0, 0]
        }
        df = pd.DataFrame(data)
        snapshots = get_usage_snapshots(df)
        self.assertEqual(len(snapshots), 0)

    def test_fast_parse_datetime_parity(self):
        from data_handler import fast_parse_datetime
        # Test that fast_parse_datetime produces exact parity with pd.to_datetime(..., format='mixed')
        dates = pd.date_range("2024-01-01", periods=100, freq="15min")
        test_series = [
            pd.Series(dates.strftime("%d/%m/%Y %H:%M")),
            pd.Series(dates.strftime("%Y-%m-%d %H:%M:%S")),
            pd.Series(list(dates[:50].strftime("%d/%m/%Y %H:%M")) + [None, "invalid_date", ""] + list(dates[50:97].strftime("%d/%m/%Y %H:%M"))),
            pd.Series(list(dates[:80].strftime("%d/%m/%Y %H:%M")) + list(dates[80:100].strftime("%Y-%m-%d %H:%M:%S"))),
        ]
        for s in test_series:
            expected = pd.to_datetime(s, dayfirst=True, errors='coerce', format='mixed')
            actual = fast_parse_datetime(s, dayfirst=True)
            pd.testing.assert_series_equal(actual, expected)

        # Test preprocess_data parity on a realistic DataFrame
        df_input = pd.DataFrame({
            'Clock': list(dates[:50].strftime("%d/%m/%Y %H:%M")) + ['invalid'] + list(dates[51:100].strftime("%d/%m/%Y %H:%M")),
            'kW_Import': ['100.5'] * 100,
            'Voltage': ['220.0'] * 100
        })
        # Baseline using format='mixed'
        df_baseline = df_input.copy()
        df_baseline['kW_Import'] = pd.to_numeric(df_baseline['kW_Import'], errors='coerce').fillna(0)
        df_baseline['Voltage'] = pd.to_numeric(df_baseline['Voltage'], errors='coerce').fillna(220.0)
        df_baseline['Clock'] = pd.to_datetime(df_baseline['Clock'], dayfirst=True, errors='coerce', format='mixed')
        df_baseline = df_baseline.dropna(subset=['Clock']).reset_index(drop=True)
        df_baseline = df_baseline.sort_values(['Clock', 'kW_Import'], ascending=[True, False]).drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
        df_baseline['Date'] = df_baseline['Clock'].dt.normalize()
        clock_str = df_baseline['Clock'].astype(str)
        df_baseline['Month'] = clock_str.str.slice(0, 7)
        df_baseline['Time_Str'] = clock_str.str.slice(11, 16).replace('', '00:00')
        df_baseline['kWh_15min'] = df_baseline['kW_Import'] / 4.0

        df_optimized = preprocess_data(df_input)
        pd.testing.assert_frame_equal(df_optimized, df_baseline)

    def test_load_file_unsupported_extension_rejected(self):
        import io
        from data_handler import load_file
        buffer = io.BytesIO(b"Clock,kW_Import,Voltage\n01/01/2026 00:00,100,220\n")
        with self.assertRaises(ValueError) as ctx:
            load_file(buffer, "exe")
        self.assertIn("ไม่อนุญาต", str(ctx.exception))

    def test_load_file_empty_or_invalid_extension_rejected(self):
        import io
        from data_handler import load_file
        buffer = io.BytesIO(b"Clock,kW_Import,Voltage\n01/01/2026 00:00,100,220\n")
        with self.assertRaises(ValueError):
            load_file(buffer, "")
        with self.assertRaises(ValueError):
            load_file(buffer, None)

    def test_load_file_oversized_file_rejected(self):
        import io
        from data_handler import load_file
        class OversizedFile(io.BytesIO):
            def __init__(self):
                super().__init__(b"Clock,kW_Import,Voltage\n01/01/2026 00:00,100,220\n")
                self.size = 51 * 1024 * 1024
        with self.assertRaises(ValueError) as ctx:
            load_file(OversizedFile(), "csv")
        self.assertIn("ขนาดไฟล์เกินกำหนด", str(ctx.exception))

    def test_load_file_valid_csv_accepted(self):
        import io
        from data_handler import load_file
        buffer = io.BytesIO(b"Clock,kW_Import,Voltage\n01/01/2026 00:00,100,220\n")
        df = load_file(buffer, "csv")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 1)

    def test_app_file_uploader_specifies_type(self):
        import ast
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        found_uploader_with_type = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == 'file_uploader':
                for kw in node.keywords:
                    if kw.arg == 'type':
                        found_uploader_with_type = True
        self.assertTrue(found_uploader_with_type, "st.file_uploader must specify allowed 'type' parameter")

    def test_is_header_row_patterns(self):
        from data_handler import is_header_row
        # Must recognize standard English date and time combinations
        self.assertTrue(is_header_row("Date, Time, kW_Import, Voltage"))
        self.assertTrue(is_header_row("Date, Time, kW, Voltage"))
        self.assertTrue(is_header_row("Datetime, kW_Import, Voltage"))
        self.assertTrue(is_header_row("Datetime, Import kW, Voltage"))
        self.assertTrue(is_header_row("Time, kW, Voltage"))
        self.assertTrue(is_header_row("PEA NO 1234 Datetime kW"))

        # Must recognize standard Thai combinations
        self.assertTrue(is_header_row("วันที่, เวลา, กำลังไฟฟ้า (kW), แรงดัน"))
        self.assertTrue(is_header_row("เวลา, พลังงาน, แรงดัน"))
        self.assertTrue(is_header_row("เวลา, kW, Voltage"))

        # Must reject metadata and empty / invalid rows
        self.assertFalse(is_header_row("Company XYZ - Electricity Billing Report"))
        self.assertFalse(is_header_row("Location: Bangkok Substation 1"))
        self.assertFalse(is_header_row("Total Energy: 500 kWh"))
        self.assertFalse(is_header_row(""))
        self.assertFalse(is_header_row(None))
        self.assertFalse(is_header_row(12345))

    def test_parse_text_lines_space_delimiter(self):
        lines = [
            "Date Clock kW_Import Voltage",
            "01/01/2023 00:15 100.5 220",
            "01/01/2023 00:30 110.2 221"
        ]
        df = parse_text_lines(lines, delimiter='space')
        self.assertIsNotNone(df)
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2023 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], "100.5")
        self.assertEqual(df.iloc[0]['Voltage'], "220")

    def test_parse_text_lines_date_and_time_columns_missing_voltage(self):
        # File with separate Date and Time columns and omitted Voltage
        lines = [
            "Date, Time, kW_Import",
            "01/01/2026, 00:15, 100.5",
            "01/01/2026, 00:30, 110.2"
        ]
        df = parse_text_lines(lines, delimiter=',')
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], "100.5")
        self.assertEqual(df.iloc[0]['Voltage'], "220")

    def test_parse_excel_df_date_and_time_columns(self):
        # Excel DataFrame with separate Date and Time columns
        df_raw = pd.DataFrame([
            ["Metadata Title", None, None],
            ["Date", "Time", "kW_Import"],
            ["01/01/2026", "00:15", 100.5],
        ])
        df = parse_excel_df(df_raw)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], 100.5)
        self.assertEqual(df.iloc[0]['Voltage'], 220.0)

    def test_preprocess_data_leap_year_february(self):
        # Leap year Feb 29 (2024 is leap year, 2026 is not)
        df_in = pd.DataFrame({
            'Clock': ["29/02/2024 12:00", "29/02/2026 12:00"],
            'kW_Import': ["150.0", "150.0"],
            'Voltage': ["220.0", "220.0"]
        })
        df_out = preprocess_data(df_in)
        # 29/02/2024 should be valid and retained; 29/02/2026 should be NaT and dropped
        self.assertEqual(len(df_out), 1)
        self.assertEqual(df_out.iloc[0]['Clock'], pd.Timestamp('2024-02-29 12:00:00'))
        self.assertEqual(df_out.iloc[0]['Month'], "2024-02")
        self.assertEqual(df_out.iloc[0]['Time_Str'], "12:00")
        self.assertEqual(df_out.iloc[0]['kWh_15min'], 150.0 / 4.0)

    def test_load_file_csv_optimization_and_parity(self):
        import io
        from data_handler import load_file
        # 1. Test standard CSV parity: header=None fast path vs names=range(50) baseline
        csv_content = (
            "Date,Clock,kW_Import,Voltage\n"
            "01/01/2026,00:15,100.5,220.0\n"
            "01/01/2026,00:30,110.2,221.0\n"
            "01/01/2026,00:45,120.0,220.5\n"
        )
        buf_baseline = io.BytesIO(csv_content.encode('utf-8-sig'))
        df_baseline_raw = pd.read_csv(buf_baseline, encoding='utf-8-sig', names=range(50), dtype=str, low_memory=False)
        expected_df = parse_excel_df(df_baseline_raw)

        buf_test = io.BytesIO(csv_content.encode('utf-8-sig'))
        with unittest.mock.patch('pandas.read_csv', side_effect=pd.read_csv) as mock_csv:
            actual_df = load_file(buf_test, 'csv')
            first_kwargs = mock_csv.call_args_list[0][1]
            self.assertEqual(first_kwargs.get('header'), None)
            self.assertNotIn('names', first_kwargs)

        pd.testing.assert_frame_equal(actual_df, expected_df)

        # 2. Test ragged CSV with metadata rows: fallback to names=range(50) must work and preserve parity
        ragged_content = (
            "Factory Electricity Report - Metadata Line 1\n"
            "Station 02, Meter 4\n"
            "Date,Clock,kW_Import,Voltage\n"
            "01/01/2026,00:15,100.5,220.0\n"
            "01/01/2026,00:30,110.2,221.0\n"
        )
        buf_ragged_baseline = io.BytesIO(ragged_content.encode('utf-8-sig'))
        df_ragged_raw = pd.read_csv(buf_ragged_baseline, encoding='utf-8-sig', names=range(50), dtype=str, low_memory=False)
        expected_ragged_df = parse_excel_df(df_ragged_raw)

        buf_ragged_test = io.BytesIO(ragged_content.encode('utf-8-sig'))
        actual_ragged_df = load_file(buf_ragged_test, 'csv')
        pd.testing.assert_frame_equal(actual_ragged_df, expected_ragged_df)

    def test_sanitize_csv_cell_formula_injection_prefixes(self):
        from data_handler import sanitize_csv_cell
        self.assertEqual(sanitize_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(sanitize_csv_cell("=cmd|'/C calc'!A0"), "'=cmd|'/C calc'!A0")
        self.assertEqual(sanitize_csv_cell("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(sanitize_csv_cell("+cmd"), "'+cmd")
        self.assertEqual(sanitize_csv_cell("-calc"), "'-calc")
        self.assertEqual(sanitize_csv_cell("  =formula_with_leading_space"), "'  =formula_with_leading_space")
        self.assertEqual(sanitize_csv_cell("\t=tab_formula"), "'\t=tab_formula")
        self.assertEqual(sanitize_csv_cell("\r=cr_formula"), "'\r=cr_formula")

    def test_sanitize_csv_cell_preserves_safe_values(self):
        from data_handler import sanitize_csv_cell
        self.assertEqual(sanitize_csv_cell("-100.5"), "-100.5")
        self.assertEqual(sanitize_csv_cell("+25.0"), "+25.0")
        self.assertEqual(sanitize_csv_cell("0"), "0")
        self.assertEqual(sanitize_csv_cell("Off-Peak"), "Off-Peak")
        self.assertEqual(sanitize_csv_cell("On-Peak"), "On-Peak")
        self.assertEqual(sanitize_csv_cell(""), "")
        self.assertEqual(sanitize_csv_cell(100.5), 100.5)
        self.assertIsNone(sanitize_csv_cell(None))

    def test_sanitize_dataframe_for_csv_neutralizes_headers_and_cells(self):
        from data_handler import sanitize_dataframe_for_csv
        df = pd.DataFrame({
            "=HeaderFormula": ["=2+5", "@evil", "Normal"],
            "+NonNumHeader": ["+calc", "-exec", "Normal"],
            "NumericLoad": [-100.5, 200.0, 0.0]
        })
        sanitized = sanitize_dataframe_for_csv(df)

        self.assertIn("'=HeaderFormula", sanitized.columns)
        self.assertIn("'+NonNumHeader", sanitized.columns)
        self.assertIn("NumericLoad", sanitized.columns)

        self.assertEqual(sanitized["'=HeaderFormula"].iloc[0], "'=2+5")
        self.assertEqual(sanitized["'=HeaderFormula"].iloc[1], "'@evil")
        self.assertEqual(sanitized["'=HeaderFormula"].iloc[2], "Normal")
        self.assertEqual(sanitized["'+NonNumHeader"].iloc[0], "'+calc")
        self.assertEqual(sanitized["'+NonNumHeader"].iloc[1], "'-exec")

        self.assertEqual(sanitized["NumericLoad"].iloc[0], -100.5)
        self.assertEqual(sanitized["NumericLoad"].iloc[1], 200.0)

    def test_parse_text_lines_preserves_12hr_pm_records(self):
        # 12-hour AM/PM timestamps must not be falsely dropped by unanchored 'p' filter
        lines = [
            "Date, Time, kW_Import, Voltage",
            "01/01/2026, 09:00 AM, 100.0, 220",
            "01/01/2026, 01:00 PM, 150.0, 225",
            "01/01/2026, 06:30 PM, 200.0, 220",
            "01/01/2026, 11:45 PM, 80.0, 219",
            "Total, , 530.0, 220"
        ]
        df = parse_text_lines(lines, delimiter=',')
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 4, "Expected all 4 AM and PM records to be retained, skipping only 'Total'")
        self.assertEqual(df.iloc[1]['Clock'], "01/01/2026 01:00 PM")
        self.assertEqual(df.iloc[2]['Clock'], "01/01/2026 06:30 PM")
        self.assertEqual(df.iloc[3]['Clock'], "01/01/2026 11:45 PM")
        self.assertEqual(df.iloc[1]['kW_Import'], "150.0")

    def test_parse_text_lines_preserves_month_names_with_p_or_h(self):
        # Dates with month names containing 'p' or 'h' (Sep, Apr, March) must not be dropped
        lines = [
            "Date, Clock, kW_Import, Voltage",
            "15-Sep-2026, 09:00, 100.0, 220",
            "10-Apr-2026, 09:00, 120.0, 220",
            "05-March-2026, 09:00, 110.0, 220",
            "total, 0, 330.0, 220"
        ]
        df = parse_text_lines(lines, delimiter=',')
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 3, "Expected all 3 month records (Sep, Apr, March) to be retained")
        self.assertEqual(df.iloc[0]['Clock'], "15-Sep-2026 09:00")
        self.assertEqual(df.iloc[1]['Clock'], "10-Apr-2026 09:00")
        self.assertEqual(df.iloc[2]['Clock'], "05-March-2026 09:00")

    def test_parse_text_lines_preserves_time_with_h_character(self):
        # Formats with 'h' in time string (e.g. 14h00, 14h15) must not be dropped by 'h' filter
        lines = [
            "Date Clock kW_Import Voltage",
            "01/01/2026 14h00 100.0 220",
            "01/01/2026 14h15 105.0 220"
        ]
        df = parse_text_lines(lines, delimiter='space')
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 14h00")
        self.assertEqual(df.iloc[1]['Clock'], "01/01/2026 14h15")

    def test_parse_text_lines_filters_actual_summary_footers(self):
        # Footer summary rows should be filtered out accurately
        for footer in ["Total, , 1000, 220", "P, , 500, 220", "OP, , 500, 220", "H, , 0, 220", "kWh, , 1000, 220", "NaN, , 0, 220", "dnv/err, , 0, 220"]:
            lines = [
                "Clock, kW_Import, Voltage",
                "01/01/2026 00:15, 100.0, 220",
                footer
            ]
            df = parse_text_lines(lines, delimiter=',')
            self.assertIsNotNone(df)
            self.assertEqual(len(df), 1, f"Failed to filter footer row: {footer}")
            self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 00:15")

    def test_get_usage_snapshots_selective_formatting_performance_and_parity(self):
        # 1. Parity test: compare with baseline reference implementation
        n = 1000
        dates = pd.date_range("2026-01-01", periods=n, freq="15min")
        kw = np.zeros(n)
        for i in range(5):
            start = i * 150 + 20
            kw[start:start + 40] = 75.5
        df_test = pd.DataFrame({'Clock': dates, 'kW_Import': kw})

        # Baseline calculation
        kw_array = df_test['kW_Import'].to_numpy()
        is_pos = kw_array > 0
        diff = np.diff(np.concatenate(([False], is_pos, [False])).astype(np.int8))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        pad_s = np.maximum(0, starts - 1)
        pad_e = np.minimum(len(df_test) - 1, np.where(ends < len(df_test), ends, len(df_test) - 1))
        c_str = df_test['Clock'].astype(str)
        fmt = c_str.str.slice(8, 10) + '/' + c_str.str.slice(5, 7) + '/' + c_str.str.slice(2, 4) + ' ' + c_str.str.slice(11, 16)
        expected = [
            {
                'label': f"⚡ รอบที่ {i+1}: {fmt.iloc[pad_s[i]]} ถึง {fmt.iloc[pad_e[i]]}",
                'start_idx': int(pad_s[i]),
                'end_idx': int(pad_e[i])
            }
            for i in range(len(starts))
        ]

        actual = get_usage_snapshots(df_test)
        self.assertEqual(actual, expected)
        pd.testing.assert_frame_equal(pd.DataFrame(actual), pd.DataFrame(expected))

        # 2. Performance benchmark: 100,000 rows must run in under 0.06s (previously ~0.16s)
        n_large = 100000
        dates_large = pd.date_range("2026-01-01", periods=n_large, freq="15min")
        kw_large = np.zeros(n_large)
        for i in range(10):
            s = i * 8000 + 100
            kw_large[s:s + 300] = 120.0
        df_large = pd.DataFrame({'Clock': dates_large, 'kW_Import': kw_large})

        import time
        t0 = time.perf_counter()
        large_actual = get_usage_snapshots(df_large)
        elapsed = time.perf_counter() - t0
        self.assertEqual(len(large_actual), 10)
        self.assertLess(elapsed, 0.06, f"Expected elapsed < 0.06s, took {elapsed:.4f}s")

    def test_get_usage_snapshots_midnight_boundary_formatting(self):
        # Boundary timestamps at midnight (00:00) must retain the '00:00' time component in snapshot labels
        df_midnight = pd.DataFrame({
            'Clock': pd.to_datetime(['2026-01-01 00:00:00', '2026-01-02 00:00:00']),
            'kW_Import': [100.0, 0.0]
        })
        snapshots = get_usage_snapshots(df_midnight)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['label'], "⚡ รอบที่ 1: 01/01/26 00:00 ถึง 02/01/26 00:00")

    def test_get_usage_snapshots_single_row_active(self):
        # A single active load row must produce a valid snapshot with complete timestamp formatting
        df_single = pd.DataFrame({
            'Clock': pd.to_datetime(['2026-01-01 00:00:00']),
            'kW_Import': [50.0]
        })
        snapshots = get_usage_snapshots(df_single)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['start_idx'], 0)
        self.assertEqual(snapshots[0]['end_idx'], 0)
        self.assertEqual(snapshots[0]['label'], "⚡ รอบที่ 1: 01/01/26 00:00 ถึง 01/01/26 00:00")

    def test_get_usage_snapshots_string_clock_at_midnight(self):
        # String clock values at midnight boundaries must be parsed and formatted with full time component
        df_str = pd.DataFrame({
            'Clock': ['01/01/2026 00:00', '02/01/2026 00:00'],
            'kW_Import': [100.0, 0.0]
        })
        snapshots = get_usage_snapshots(df_str)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['label'], "⚡ รอบที่ 1: 01/01/26 00:00 ถึง 02/01/26 00:00")

    def test_preprocess_data_no_full_clock_astype_str(self):
        # AST test: ensure preprocess_data does not convert entire df['Clock'] to str via astype
        import ast
        with open('data_handler.py', 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_clock_astype = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'preprocess_data':
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == 'astype':
                        if isinstance(child.func.value, ast.Subscript):
                            sub = child.func.value
                            if getattr(sub.value, 'id', '') == 'df' and getattr(sub.slice, 'value', '') == 'Clock':
                                found_clock_astype = True

        self.assertFalse(found_clock_astype, "preprocess_data should not convert entire df['Clock'] to str via astype(str)")

    def test_preprocess_data_month_time_str_fast_mapping_parity(self):
        # Parity test: verify fast numeric mapping produces exact parity with legacy string slicing
        dates = pd.date_range("2023-12-31 23:00", "2024-03-01 01:00", freq="15min")
        df_in = pd.DataFrame({
            'Clock': dates.strftime('%d/%m/%Y %H:%M'),
            'kW_Import': ['100.5'] * len(dates),
            'Voltage': ['220.0'] * len(dates)
        })

        from data_handler import fast_parse_datetime
        df_expected = df_in.copy()
        df_expected['kW_Import'] = pd.to_numeric(df_expected['kW_Import'], errors='coerce').fillna(0)
        df_expected['Voltage'] = pd.to_numeric(df_expected['Voltage'], errors='coerce').fillna(220.0)
        df_expected['Clock'] = fast_parse_datetime(df_expected['Clock'], dayfirst=True)
        df_expected = df_expected.dropna(subset=['Clock']).reset_index(drop=True)
        df_expected = df_expected.sort_values(['Clock', 'kW_Import'], ascending=[True, False]).drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
        df_expected['Date'] = df_expected['Clock'].dt.normalize()
        legacy_clock_str = df_expected['Clock'].astype(str)
        df_expected['Month'] = legacy_clock_str.str.slice(0, 7)
        df_expected['Time_Str'] = legacy_clock_str.str.slice(11, 16).replace('', '00:00')
        df_expected['kWh_15min'] = df_expected['kW_Import'] / 4.0

        actual = preprocess_data(df_in)
        pd.testing.assert_frame_equal(actual, df_expected)

        # Verify midnight values
        midnight_rows = actual[actual['Clock'].dt.hour == 0]
        self.assertGreater(len(midnight_rows), 0)
        self.assertTrue((midnight_rows['Time_Str'].str.slice(0, 2) == '00').all())

    def test_sanitize_filename_path_traversal(self):
        from data_handler import sanitize_filename
        self.assertEqual(sanitize_filename("../../../../etc/passwd.csv"), "passwd.csv")
        self.assertEqual(sanitize_filename("..\\..\\Windows\\System32\\cmd.exe.csv"), "cmd.exe.csv")
        self.assertEqual(sanitize_filename("....//....//secret.xlsx"), "secret.xlsx")
        self.assertEqual(sanitize_filename(".."), "unnamed_file")
        self.assertEqual(sanitize_filename("../../.."), "unnamed_file")

    def test_sanitize_filename_markdown_and_html_injection(self):
        from data_handler import sanitize_filename
        self.assertEqual(sanitize_filename("[คลิกที่นี่](https://phishing.site/login).csv"), "login.csv")
        self.assertEqual(sanitize_filename("[คลิกที่นี่](phishing).csv"), "คลิกที่นี่phishing.csv")
        self.assertEqual(sanitize_filename("<script>alert(1)</script>.csv"), "script.csv")
        self.assertEqual(sanitize_filename("`code`~strike~.csv"), "codestrike.csv")

    def test_sanitize_filename_crlf_and_control_chars(self):
        from data_handler import sanitize_filename
        self.assertEqual(sanitize_filename("report\r\nERROR: Fake log.csv"), "reportERROR: Fake log.csv")
        self.assertEqual(sanitize_filename("null\x00byte.csv"), "nullbyte.csv")

    def test_sanitize_filename_preserves_legitimate_names(self):
        from data_handler import sanitize_filename
        self.assertEqual(sanitize_filename("load_profile_2026.csv"), "load_profile_2026.csv")
        self.assertEqual(sanitize_filename("ข้อมูลการใช้ไฟฟ้า มกราคม 2567.xlsx"), "ข้อมูลการใช้ไฟฟ้า มกราคม 2567.xlsx")
        self.assertEqual(sanitize_filename(""), "unnamed_file")
        self.assertEqual(sanitize_filename(None), "unnamed_file")

    def test_app_uses_sanitize_filename_for_upload(self):
        import ast
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        found_import = False
        found_usage = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'data_handler':
                if any(alias.name == 'sanitize_filename' for alias in node.names):
                    found_import = True
            if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'sanitize_filename':
                found_usage = True
        self.assertTrue(found_import, "app.py must import sanitize_filename from data_handler")
        self.assertTrue(found_usage, "app.py must call sanitize_filename on uploaded files")

if __name__ == '__main__':
    unittest.main()
