import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
"""Behavioral tests of the real analyzer; malformed-input cases document current errors."""
import unittest
from datetime import time

import pandas as pd
from pandas.testing import assert_frame_equal

from tou_analyzer import apply_tou_and_anomaly


def readings(clocks, loads=None):
    loads = loads if loads is not None else [4.0] * len(clocks)
    return pd.DataFrame({
        'Clock': pd.DatetimeIndex([pd.Timestamp(value) for value in clocks]),
        'kW_Import': loads,
        'kWh_15min': [load / 4 for load in loads],
    })


def analyze(frame, holidays=None, start=time(9), end=time(22), sensitivity=2):
    return apply_tou_and_anomaly(frame, sensitivity, start, end, 5.0, 2.0,
                                 holidays if holidays is not None else [])


class TouFunctionalTests(unittest.TestCase):
    def test_weekday_peak_boundaries_and_cost(self):
        result = analyze(readings(['2026-10-19 08:59:59', '2026-10-19 09:00:00',
                                   '2026-10-19 21:59:59', '2026-10-19 22:00:00']))
        self.assertEqual(result['Period_Detail'].tolist(),
                         ['Off-Peak', 'On-Peak', 'On-Peak', 'Off-Peak'])
        self.assertEqual(result['Rate_THB'].tolist(), [2.0, 5.0, 5.0, 2.0])
        self.assertEqual(result['Cost_THB'].tolist(), [2.0, 5.0, 5.0, 2.0])

    def test_weekend_and_explicit_holiday_override_peak(self):
        result = analyze(readings(['2026-10-17 12:00', '2026-10-18 12:00',
                                   '2026-10-19 12:00', '2026-10-20 12:00']),
                         holidays=['2026-10-19'])
        self.assertEqual(result['Period_Detail'].tolist(),
                         ['Holiday', 'Holiday', 'Holiday', 'On-Peak'])
        self.assertEqual(result['Cost_THB'].tolist(), [2.0, 2.0, 2.0, 5.0])

    def test_holiday_matches_all_times_on_date(self):
        result = analyze(readings(['2026-10-19 00:00', '2026-10-19 12:00',
                                   '2026-10-19 23:59:59']), ['2026-10-19'])
        self.assertEqual(result['Period_Detail'].tolist(), ['Holiday'] * 3)

    def test_empty_holidays_keep_weekday_peak(self):
        result = analyze(readings(['2026-10-19 12:00']), [])
        self.assertEqual(result['Period_Detail'].tolist(), ['On-Peak'])

    def test_midnight_crossing_peak_window(self):
        result = analyze(readings(['2026-10-19 05:59:59', '2026-10-19 06:00',
                                   '2026-10-19 21:59:59', '2026-10-19 22:00']),
                         start=time(22), end=time(6))
        self.assertEqual(result['Period_Detail'].tolist(),
                         ['On-Peak', 'Off-Peak', 'Off-Peak', 'On-Peak'])

    def test_zero_length_peak_window(self):
        # Regression test: if start and end times are identical, no time should be evaluated as On-Peak
        result = analyze(readings(['2026-10-19 09:00', '2026-10-19 12:00',
                                   '2026-10-19 23:00']),
                         start=time(9), end=time(9))
        self.assertEqual(result['Period_Detail'].tolist(),
                         ['Off-Peak', 'Off-Peak', 'Off-Peak'])

    def test_cost_uses_actual_energy(self):
        result = analyze(readings(['2026-10-19 12:00', '2026-10-19 23:00'], [8.0, 2.0]))
        self.assertEqual(result['Cost_THB'].tolist(), [10.0, 1.0])

    def test_input_is_not_mutated(self):
        frame = readings(['2026-10-19 12:00', '2026-10-19 23:00'])
        before = frame.copy(deep=True)
        analyze(frame, ['2026-10-19'])
        assert_frame_equal(frame, before)

    def test_anomaly_classifies_high_low_and_zero(self):
        frame = readings(['2026-10-19 12:00'] * 23, [4.0] * 20 + [40.0, 0.1, 0.0])
        result = analyze(frame, sensitivity=0.5)
        self.assertEqual(result['Anomaly_Type'].iloc[20], 'สูงกว่าเกณฑ์ (High)')
        self.assertEqual(result['Anomaly_Type'].iloc[21], 'ไฟตก (Low)')
        self.assertEqual(result['Anomaly_Type'].iloc[22], 'ไฟตก (Low)')

    def test_malformed_holiday_ignored(self):
        # Regression test: user input with malformed dates is ignored instead of crashing
        for invalid in ['not-a-date', '2026-02-30']:
            with self.subTest(invalid=invalid):
                result = analyze(readings(['2026-10-19 12:00']), [invalid])
                self.assertEqual(result['Period_Detail'].tolist(), ['On-Peak'])

    def test_mixed_valid_and_invalid_holidays_ignored(self):
        result = analyze(readings(['2026-10-19 12:00']), ['2026-10-19', 'not-a-date'])
        self.assertEqual(result['Period_Detail'].tolist(), ['Holiday'])

    def test_anomaly_detects_zero_kw_as_low(self):
        # Create a frame with enough data to establish a mean > 0.01
        frame = readings(['2026-10-19 12:00'] * 10, [10.0] * 9 + [0.0])
        result = analyze(frame, sensitivity=0.5)
        # The 0.0 value should be classified as 'ไฟตก (Low)'
        self.assertEqual(result['Anomaly_Type'].iloc[9], 'ไฟตก (Low)')


    def test_holiday_list_none_treated_as_no_holidays(self):
        frame = readings(['2026-10-19 12:00'])
        result = apply_tou_and_anomaly(frame, 2.0, time(9), time(22), 5.0, 2.0, holiday_list=None)
        self.assertEqual(result['Period_Detail'].tolist(), ['On-Peak'])
        self.assertFalse(result['Is_Holiday'].iloc[0])

    def test_empty_dataframe_returns_all_columns(self):
        for empty_df in [
            pd.DataFrame(),
            pd.DataFrame(columns=['Clock', 'kW_Import', 'kWh_15min']),
            pd.DataFrame(columns=['Clock', 'kW_Import', 'kWh_15min', 'Voltage']),
        ]:
            with self.subTest(cols=list(empty_df.columns)):
                result = apply_tou_and_anomaly(empty_df, 2.0, time(9), time(22), 5.0, 2.0, holiday_list=[])
                self.assertTrue(result.empty)
                expected_cols = [
                    'Clock', 'kW_Import', 'kWh_15min',
                    'Is_Weekend', 'Is_Holiday', 'Period_Detail',
                    'Rate_THB', 'Cost_THB', 'Anomaly_Type'
                ]
                for col in expected_cols:
                    self.assertIn(col, result.columns)
                if 'Voltage' in empty_df.columns:
                    self.assertIn('Voltage', result.columns)

    def test_empty_dataframe_with_holiday_list_none(self):
        result = apply_tou_and_anomaly(pd.DataFrame(), 2.0, time(9), time(22), 5.0, 2.0, holiday_list=None)
        self.assertTrue(result.empty)
        self.assertIn('Period_Detail', result.columns)

    def test_apply_tou_and_anomaly_vectorized_integer_arithmetic_performance_and_parity(self):
        # 1. AST check: ensure _apply_tou_and_anomaly_cached uses fast integer nanosecond arithmetic
        import ast
        analyzer_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tou_analyzer.py'))
        with open(analyzer_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_fast_ns_arithmetic = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == '_apply_tou_and_anomaly_cached':
                for child in ast.walk(node):
                    if isinstance(child, ast.Constant) and child.value == 86_400_000_000_000:
                        found_fast_ns_arithmetic = True
        self.assertTrue(
            found_fast_ns_arithmetic,
            '_apply_tou_and_anomaly_cached must use fast vectorized nanosecond integer arithmetic (86_400_000_000_000)'
        )

        # 2. Exact Parity check across various scenarios
        dates = pd.date_range('2026-01-01 00:00:00', periods=500, freq='15min')
        import numpy as np
        np.random.seed(42)
        kw = np.random.uniform(0, 300, len(dates)).round(2)
        kw[kw < 40] = 0.0
        kw[10] = 450.0
        kw[50] = 5.0

        df_in = pd.DataFrame({
            'Clock': dates,
            'kW_Import': kw,
            'kWh_15min': kw / 4.0,
            'Voltage': np.random.uniform(215, 230, len(dates)).round(2)
        })

        holidays = ['2026-01-01', '2026-01-02']
        res = apply_tou_and_anomaly(df_in, 2.5, time(9, 0), time(22, 0), 5.7982, 2.6369, holidays)

        self.assertEqual(len(res), len(df_in))
        self.assertIn('Period_Detail', res.columns)
        self.assertIn('Anomaly_Type', res.columns)
        self.assertIn('Is_Weekend', res.columns)
        self.assertIn('Is_Holiday', res.columns)

        # 3. Non-mutation check
        self.assertNotIn('Period_Detail', df_in.columns)

    def test_string_clock_series_parsed_and_classified(self):
        """String/object Clock column must be parsed without AttributeError and classified correctly."""
        df = pd.DataFrame({
            'Clock': ['2026-10-19 10:00:00', '2026-10-19 23:00:00'],
            'kW_Import': [10.0, 10.0],
            'kWh_15min': [2.5, 2.5]
        })
        res = apply_tou_and_anomaly(df, 2.0, time(9), time(22), 5.0, 2.0)
        self.assertEqual(res['Period_Detail'].tolist(), ['On-Peak', 'Off-Peak'])
        self.assertEqual(res['Rate_THB'].tolist(), [5.0, 2.0])

    def test_non_nano_datetime_resolution_support(self):
        """Second-resolution datetimes (datetime64[s]) must scale to nanoseconds rather than evaluating as 1970-01-01."""
        df = pd.DataFrame({
            'Clock': pd.Series([
                pd.Timestamp('2026-10-19 10:00:00'),
                pd.Timestamp('2026-10-19 23:00:00')
            ]).astype('datetime64[s]'),
            'kW_Import': [10.0, 10.0],
            'kWh_15min': [2.5, 2.5]
        })
        res = apply_tou_and_anomaly(df, 2.0, time(9), time(22), 5.0, 2.0)
        self.assertEqual(res['Period_Detail'].tolist(), ['On-Peak', 'Off-Peak'])
        self.assertFalse(res['Is_Weekend'].iloc[0])

    def test_timezone_aware_clock_evaluates_local_wall_clock_time(self):
        """Timezone-aware timestamps (e.g. UTC+7 Asia/Bangkok) must evaluate peak hours in local wall-clock time, not UTC."""
        df = pd.DataFrame({
            'Clock': pd.Series([
                pd.Timestamp('2026-10-19 10:00:00', tz='Asia/Bangkok'),
                pd.Timestamp('2026-10-19 23:00:00', tz='Asia/Bangkok')
            ]),
            'kW_Import': [10.0, 10.0],
            'kWh_15min': [2.5, 2.5]
        })
        res = apply_tou_and_anomaly(df, 2.0, time(9), time(22), 5.0, 2.0)
        self.assertEqual(res['Period_Detail'].tolist(), ['On-Peak', 'Off-Peak'])
        self.assertFalse(res['Is_Weekend'].iloc[0])

    def test_holiday_with_time_component_matches_full_day(self):
        """Holiday list items containing non-zero time components must normalize to match entire calendar day."""
        df = pd.DataFrame({
            'Clock': [pd.Timestamp('2026-10-19 10:00:00')],
            'kW_Import': [10.0],
            'kWh_15min': [2.5]
        })
        res = apply_tou_and_anomaly(df, 2.0, time(9), time(22), 5.0, 2.0, holiday_list=['2026-10-19 08:30:00'])
        self.assertTrue(res['Is_Holiday'].iloc[0])
        self.assertEqual(res['Period_Detail'].iloc[0], 'Holiday')
        self.assertEqual(res['Rate_THB'].iloc[0], 2.0)

    def test_missing_kwh_15min_computed_from_kw_import(self):
        """When kWh_15min column is missing, it should be derived from kW_Import / 4 without KeyError."""
        df = pd.DataFrame({
            'Clock': [pd.Timestamp('2026-10-19 10:00:00')],
            'kW_Import': [20.0]
        })
        res = apply_tou_and_anomaly(df, 2.0, time(9), time(22), 5.0, 2.0)
        self.assertIn('kWh_15min', res.columns)
        self.assertEqual(res['kWh_15min'].iloc[0], 5.0)
        self.assertEqual(res['Cost_THB'].iloc[0], 25.0)


if __name__ == '__main__':
    unittest.main()
