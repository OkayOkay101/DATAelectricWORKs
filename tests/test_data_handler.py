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

if __name__ == '__main__':
    unittest.main()
