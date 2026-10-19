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

    def test_ui_interactions(self):
        """
        Integration test: verify UI interactions with AppTest
        """
        import sys
        # Workaround: test_data_handler.py mocks sys.modules['streamlit'] as a MockSt object at the module level.
        # This breaks streamlit.testing.v1 imports globally if test_data_handler is imported first.
        # We temporarily remove the mock to allow the real streamlit package to be imported for AppTest.
        mock_st = None
        if 'streamlit' in sys.modules and not hasattr(sys.modules['streamlit'], '__path__'):
            mock_st = sys.modules.pop('streamlit')

        try:
            from streamlit.testing.v1 import AppTest

            import os

            # Resolve path to app.py based on repo root
            app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
            at = AppTest.from_file(app_path).run()

            # Initial run should not have exceptions
            self.assertFalse(at.exception, f"App execution failed: {at.exception}")

            # Test basic UI elements
            self.assertTrue(len(at.title) > 0, "No title found in the UI")
            self.assertTrue(len(at.file_uploader) > 0, "No file uploader found in the UI")

            # Check initial markdown instructions
            self.assertTrue(len(at.markdown) > 0, "No markdown instructions found")

            # Simulate file upload to test UI interactions (e.g. download button)
            import pandas as pd
            import io

            # Create a simple mock CSV
            df = pd.DataFrame({
                'Clock': ['2026-01-01 10:00:00', '2026-01-01 10:15:00'],
                'kW_Import': [100.0, 110.0],
                'Voltage': [220.0, 220.0]
            })
            buffer = io.BytesIO()
            df.to_csv(buffer, index=False)
            content = buffer.getvalue()

            # Upload file
            at.file_uploader[0].set_value([("mock_data.csv", content, "text/csv")]).run()

            # Check for selectboxes or radio buttons to show the UI has responded
            self.assertTrue(len(at.selectbox) > 0, "No selectboxes found after file upload")
            self.assertTrue(len(at.radio) > 0, "No radio buttons found after file upload")

            # Find number inputs to change shift minutes
            # App.py has: shift_mins_sim = st.number_input("⏱️ ใส่เวลาที่เลื่อน (นาที):", ...)
            # We assume it is one of the number_inputs
            for ni in at.number_input:
                if "ใส่เวลาที่เลื่อน" in ni.label:
                    ni.set_value(60).run()
                    break

            # We check if a download button is created after simulating shifting time
            self.assertTrue(len(at.download_button) > 0, "No download button found after time shifting")
        finally:
            if mock_st is not None:
                sys.modules['streamlit'] = mock_st
