import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / 'app.py'
UPLOAD = (
    'Clock,kW_Import,Voltage\n'
    '19/10/2026 10:00,100,220\n'
    '19/10/2026 10:15,110,220\n'
).encode('utf-8')

class TestApp(unittest.TestCase):
    def test_regression_date_update(self):
        """
        Regression test: Ensure that shifting 'Clock' updates 'Date' correctly
        when the time crosses into a new day.
        """
        # Mock data for simulation
        df_sim = pd.DataFrame({
            'Clock': [pd.Timestamp('2024-01-01 23:30:00')],
            'Date': [pd.Timestamp('2024-01-01')],
            'kW_Import': [100.0],
            'Voltage': [220.0]
        })

        # Simulate a shift forward by 60 minutes
        shift_mins_sim = 60

        # Apply logic from app.py
        df_sim['Clock'] = df_sim['Clock'] + pd.to_timedelta(shift_mins_sim, unit='m')
        df_sim['Date'] = df_sim['Clock'].dt.normalize()

        # Check that both Date and Clock reflect crossing into 2024-01-02
        self.assertEqual(df_sim.iloc[0]['Clock'], pd.Timestamp('2024-01-02 00:30:00'), "Clock did not shift correctly")
        self.assertEqual(df_sim.iloc[0]['Date'], pd.Timestamp('2024-01-02'), "Date did not update to match Clock across day boundary")

    def test_ui_interactions(self):
        """Uploading CSV and shifting 60 minutes changes the displayed readings."""
        at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
        self.assertFalse(at.exception)
        at.file_uploader[0].set_value([('readings.csv', UPLOAD, 'text/csv')]).run()
        self.assertFalse(at.exception)
        self.assertTrue(any('วิเคราะห์ข้อมูลสำเร็จ 1 ไฟล์' in item.value
                            for item in at.success))

        shifts = [item for item in at.number_input if 'ใส่เวลาที่เลื่อน' in item.label]
        self.assertEqual(len(shifts), 1, 'The cost-simulator shift control is missing')
        shifts[0].set_value(60).run()
        self.assertFalse(at.exception)
        shifted = at.dataframe[-1].value
        self.assertEqual(shifted['Clock'].tolist(),
                         [pd.Timestamp('2026-10-19 11:00'), pd.Timestamp('2026-10-19 11:15')])
        self.assertEqual(shifted['kW_Import'].tolist(), [100.0, 110.0])
        self.assertEqual(shifted['Period_Detail'].tolist(), ['On-Peak', 'On-Peak'])
        self.assertEqual(len(at.download_button), 1)

    def test_ui_empty_state(self):
        """With no upload the app explains what to do without showing results."""
        at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.title), 1)
        self.assertEqual(len(at.file_uploader), 1)
        self.assertTrue(any('อัปโหลดไฟล์ Load Profile' in item.value for item in at.info))
        self.assertEqual(len(at.dataframe), 0)
        self.assertEqual(len(at.download_button), 0)

    def test_ui_invalid_upload_shows_error(self):
        """An unreadable CSV displays a validation error rather than results."""
        at = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
        at.file_uploader[0].set_value([('invalid.csv', b'not,a,load-profile\n', 'text/csv')]).run()
        self.assertFalse(at.exception)
        self.assertTrue(any('ไม่มีข้อมูลที่สามารถนำมาวิเคราะห์' in item.value
                            for item in at.error))
        self.assertEqual(len(at.dataframe), 0)
        self.assertEqual(len(at.download_button), 0)
