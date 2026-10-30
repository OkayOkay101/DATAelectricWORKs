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

if __name__ == '__main__':
    unittest.main()
