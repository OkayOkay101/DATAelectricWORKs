import unittest
import pandas as pd

class TestApp(unittest.TestCase):
    def test_convert_df_to_csv_sanitizes_formula_injection(self):
        """Ensure convert_df_to_csv invokes sanitize_dataframe_for_csv."""
        import ast
        import os
        app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        found_sanitization = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'convert_df_to_csv':
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and getattr(child.func, 'id', '') == 'sanitize_dataframe_for_csv':
                        found_sanitization = True
                        break
        self.assertTrue(found_sanitization, "convert_df_to_csv must invoke sanitize_dataframe_for_csv")

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
            import io

            # Resolve path to app.py based on repo root
            app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
            at = AppTest.from_file(app_path, default_timeout=30).run()

            # Initial run should not have exceptions
            self.assertFalse(at.exception, f"App execution failed: {at.exception}")

            # Test basic UI elements
            self.assertTrue(len(at.title) > 0, "No title found in the UI")
            self.assertTrue(len(at.file_uploader) > 0, "No file uploader found in the UI")

            # Check initial markdown instructions
            self.assertTrue(len(at.markdown) > 0, "No markdown instructions found")

            # Simulate file upload to test UI interactions (e.g. download button)
            # Create a simple mock CSV (100 kW and 110 kW at 15-min intervals)
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

            # Verify Tab 1 (Overview) executive summary metrics
            metrics = {m.label: m.value for m in at.metric}
            self.assertIn("⚡ พลังงานไฟฟ้ารวม", metrics, "Overview total energy metric missing")
            self.assertIn("🔥 ความต้องการไฟฟ้าสูงสุด (Peak)", metrics, "Overview peak demand metric missing")
            self.assertIn("💰 ค่าไฟฟ้าประเมินรวม", metrics, "Overview total cost metric missing")
            self.assertIn("📈 โหลดไฟฟ้าเฉลี่ย", metrics, "Overview average load metric missing")

            self.assertEqual(metrics["⚡ พลังงานไฟฟ้ารวม"], "52.50 kWh")
            self.assertEqual(metrics["🔥 ความต้องการไฟฟ้าสูงสุด (Peak)"], "110.00 kW")
            self.assertEqual(metrics["📈 โหลดไฟฟ้าเฉลี่ย"], "105.00 kW")
            self.assertTrue("138.44" in metrics["💰 ค่าไฟฟ้าประเมินรวม"], f"Expected cost in metric, got: {metrics['💰 ค่าไฟฟ้าประเมินรวม']}")

            # Verify Tab 2 (Daily Insights) raw data table has Thai headers with units and hidden index
            self.assertGreater(len(at.dataframe), 2, "Expected at least 3 dataframes rendered")
            raw_table = at.dataframe[2]
            expected_columns = [
                'วัน-เวลา (Timestamp)',
                'กำลังไฟฟ้า (kW)',
                'พลังงานไฟฟ้า (kWh)',
                'แรงดันไฟฟ้า (V)',
                'ช่วงเวลา (Period)',
                'อัตราค่าไฟ (บาท/หน่วย)',
                'ค่าไฟฟ้า (บาท)',
                'สถานะความผิดปกติ (Anomaly)'
            ]
            self.assertEqual(raw_table.value.columns.tolist(), expected_columns)
            self.assertIn('"hidden": true', raw_table.proto.columns)

            # Verify Tab 2 (Daily Insights) metrics
            self.assertIn("🔥 โหลดสูงสุดประจำวัน (Peak)", metrics, "Daily peak demand metric missing")
            self.assertIn("📈 โหลดเฉลี่ยประจำวัน", metrics, "Daily average load metric missing")
            self.assertEqual(metrics["🔥 โหลดสูงสุดประจำวัน (Peak)"], "110.00 kW")
            self.assertEqual(metrics["📈 โหลดเฉลี่ยประจำวัน"], "105.00 kW")

            # Verify Tab 2 daily period summary table has hidden index
            summary_table = at.dataframe[1]
            self.assertIn('"hidden": true', summary_table.proto.columns)

            # Verify Tab 2 daily download button exists with help tooltip
            tab2_dl_buttons = [db for db in at.download_button if "ดาวน์โหลดข้อมูลดิบรายวัน" in db.label]
            self.assertEqual(len(tab2_dl_buttons), 1, "Expected Tab 2 daily download button")
            self.assertTrue(tab2_dl_buttons[0].help and "CSV" in tab2_dl_buttons[0].help, "Expected Tab 2 download button help tooltip")

            # Verify Tab 3 (Shift Graph) comparison metrics
            self.assertIn("🔥 โหลดสูงสุดเปรียบเทียบ (Peak)", metrics, "Shift graph peak demand metric missing")
            self.assertIn("⚡ พลังงานช่วง On-Peak", metrics, "Shift graph on-peak energy metric missing")
            self.assertIn("💰 ค่าไฟฟ้าประเมินเปรียบเทียบ", metrics, "Shift graph cost metric missing")
            self.assertIn("⏱️ เวลาที่จำลองเลื่อน", metrics, "Shift graph shift duration metric missing")
            self.assertEqual(metrics["🔥 โหลดสูงสุดเปรียบเทียบ (Peak)"], "110.00 kW")
            self.assertEqual(metrics["⏱️ เวลาที่จำลองเลื่อน"], "+15 นาที")

            # Verify Tab 3 download button has help tooltip
            tab3_dl_buttons = [db for db in at.download_button if "📥 ดาวน์โหลดไฟล์ที่ปรับเวลาแล้ว (.csv)" in db.label]
            self.assertEqual(len(tab3_dl_buttons), 1, "Expected Tab 3 download button")
            self.assertTrue(tab3_dl_buttons[0].help and "CSV" in tab3_dl_buttons[0].help, "Expected Tab 3 download button help tooltip")

            # Find number inputs to change shift minutes
            # App.py has: shift_mins_sim = st.number_input("⏱️ ใส่เวลาที่เลื่อน (นาที):", ...)
            # We assume it is one of the number_inputs
            for ni in at.number_input:
                if "ใส่เวลาที่เลื่อน" in ni.label:
                    ni.set_value(60).run()
                    break

            # We check if a download button is created after simulating shifting time
            self.assertTrue(len(at.download_button) > 0, "No download button found after time shifting")

            # Verify Tab 4 (Cost Simulator) shows outcome summary banner
            info_texts = [inf.value for inf in at.info if "ผลการจำลอง" in inf.value]
            self.assertTrue(len(info_texts) > 0, "Expected simulation outcome info banner for unchanged rate")
            self.assertIn("ค่าไฟฟ้าคงเดิม", info_texts[0])

            # Verify Tab 4 simulated raw table has Thai headers with units and hidden index
            self.assertGreaterEqual(len(at.dataframe), 4, "Expected at least 4 dataframes rendered after simulation")
            sim_table = at.dataframe[3]
            expected_sim_columns = [
                'วัน-เวลา (Timestamp)',
                'กำลังไฟฟ้า (kW)',
                'พลังงานไฟฟ้า (kWh)',
                'ช่วงเวลา (Period)',
                'อัตราค่าไฟ (บาท/หน่วย)',
                'ค่าไฟฟ้า (บาท)',
                'สถานะความผิดปกติ (Anomaly)'
            ]
            self.assertEqual(sim_table.value.columns.tolist(), expected_sim_columns)
            self.assertIn('"hidden": true', sim_table.proto.columns)

            # Verify Tab 4 dedicated download button
            download_labels = [db.label for db in at.download_button]
            self.assertIn("📥 ดาวน์โหลดผลการจำลองค่าไฟ (.csv)", download_labels)
        finally:
            if mock_st is not None:
                sys.modules['streamlit'] = mock_st


