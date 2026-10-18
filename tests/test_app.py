import unittest
import pandas as pd

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
