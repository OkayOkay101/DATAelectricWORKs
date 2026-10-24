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

    def test_single_row_anomaly_std_nan(self):
        import datetime
        df = pd.DataFrame({
            'Clock': [pd.Timestamp('2026-10-19 12:00')],
            'kW_Import': [10.0],
            'kWh_15min': [2.5]
        })
        res = apply_tou_and_anomaly(df, sensitivity=1.0, p_start=datetime.time(9, 0), p_end=datetime.time(22, 0), p_rate=4.0, op_rate=2.0, holiday_list=[])
        self.assertEqual(res['Anomaly_Type'].iloc[0], 'ปกติ')


if __name__ == '__main__':
    unittest.main()
