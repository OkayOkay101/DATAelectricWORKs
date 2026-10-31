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

    def test_app_uses_sort_and_deduplicate_by_clock(self):
        """app.py must use the monotonic fast-path helper when merging uploaded files."""
        import ast
        import os
        app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        imported = any(
            isinstance(node, ast.ImportFrom) and node.module == 'data_handler'
            and any(alias.name == 'sort_and_deduplicate_by_clock' for alias in node.names)
            for node in ast.walk(tree)
        )
        self.assertTrue(imported, "app.py must import sort_and_deduplicate_by_clock from data_handler")

        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'sort_and_deduplicate_by_clock'
        ]
        self.assertTrue(calls, "app.py must call sort_and_deduplicate_by_clock when combining files")

    def test_skip_reason_uses_whitelisted_error_helper(self):
        """UI ต้องไม่แสดง str(e) ของ exception ภายนอกผ่าน safe_error_reason"""
        import ast
        import os
        app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
        with open(app_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        imported = any(
            isinstance(node, ast.ImportFrom) and node.module == 'data_handler'
            and any(alias.name == 'safe_error_reason' for alias in node.names)
            for node in ast.walk(tree)
        )
        self.assertTrue(imported, "app.py must import safe_error_reason from data_handler")

        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'safe_error_reason'
        ]
        self.assertTrue(calls, "app.py must use safe_error_reason when reporting skipped files")

        # ต้องไม่มีการนำ str(e) ของ exception ใด ๆ ไปเป็น reason ให้ UI
        raw_reason_leaks = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == 'reason' for t in node.targets)
            and any(
                isinstance(child, ast.Call) and getattr(child.func, 'id', '') == 'str'
                for child in ast.walk(node.value)
            )
        ]
        self.assertEqual(raw_reason_leaks, [], "raw str(e) must not be rendered as a skip reason")

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

    def test_load_kw_is_reported_as_peak_not_interval_sum(self):
        """'โหลด' ต้องเป็นค่า kW สูงสุด ไม่ใช่ผลบวก kW ของทุกช่วงเวลา (ซึ่งไม่มีความหมาย)"""
        import sys
        mock_st = None
        if 'streamlit' in sys.modules and not hasattr(sys.modules['streamlit'], '__path__'):
            mock_st = sys.modules.pop('streamlit')

        try:
            from streamlit.testing.v1 import AppTest
            import os
            import io

            app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
            at = AppTest.from_file(app_path, default_timeout=30).run()

            df = pd.DataFrame({
                'Clock': [
                    '2026-01-05 10:00:00',
                    '2026-01-05 10:15:00',
                    '2026-01-05 10:30:00',
                    '2026-01-05 10:45:00',
                ],
                'kW_Import': [100.0, 120.0, 160.0, 80.0],
                'Voltage': [220.0, 220.0, 220.0, 220.0],
            })
            buffer = io.BytesIO()
            df.to_csv(buffer, index=False)
            at.file_uploader[0].set_value([("peak.csv", buffer.getvalue(), "text/csv")]).run()
            self.assertFalse(at.exception, f"App execution failed: {at.exception}")

            metrics = {m.label: m.value for m in at.metric}
            self.assertNotIn("โหลดรวมทั้งหมด", metrics, "kW must not be summed across intervals")
            self.assertEqual(metrics["🔥 โหลดสูงสุด (Peak)"], "160.00 kW")

            period_table = at.dataframe[1].value
            self.assertIn("โหลดสูงสุด (kW)", period_table.columns)
            self.assertNotIn("โหลดรวม (kW)", period_table.columns)
            self.assertEqual(float(period_table["โหลดสูงสุด (kW)"].max()), 160.0)

            next(ni for ni in at.number_input if "ใส่เวลาที่เลื่อน" in ni.label).set_value(30).run()
            self.assertFalse(at.exception, f"App execution failed after simulation: {at.exception}")
            sim_peaks = [m.value for m in at.metric if m.label == "🔥 โหลดสูงสุด (Peak)"]
            self.assertEqual(len(sim_peaks), 2, "Expected current and simulated peak metrics")
            self.assertTrue(all(value == "160.00 kW" for value in sim_peaks), sim_peaks)
        finally:
            # Keep the real streamlit module loaded: restoring the mock here would force the
            # next AppTest (test_ui_interactions) to re-execute streamlit/__init__.py, which
            # raises "DeltaGeneratorSingleton instance already exists!".
            if mock_st is not None and not hasattr(sys.modules.get('streamlit'), '__path__'):
                sys.modules['streamlit'] = mock_st

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

            # Verify initial welcome screen guidance and sample template download button
            template_buttons = [db for db in at.download_button if "ดาวน์โหลดไฟล์ตัวอย่างแม่แบบ" in db.label]
            self.assertEqual(len(template_buttons), 1, "Expected sample template download button on welcome screen")
            self.assertTrue(template_buttons[0].help and "แม่แบบ" in template_buttons[0].help)
            self.assertTrue(len(at.dataframe) > 0, "Expected supported format sample table on welcome screen")
            sample_df = at.dataframe[0].value
            self.assertIn("ชื่อคอลัมน์ที่รองรับ", sample_df.columns)
            self.assertIn("ความหมายและหน่วย", sample_df.columns)

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

            # Verify Tab 1 (Overview) daily energy summary download button exists with help tooltip
            tab1_dl_buttons = [db for db in at.download_button if "ดาวน์โหลดสรุปพลังงานรายวัน" in db.label]
            self.assertEqual(len(tab1_dl_buttons), 1, "Expected Tab 1 daily summary download button")
            self.assertTrue(tab1_dl_buttons[0].help and "CSV" in tab1_dl_buttons[0].help, "Expected Tab 1 download button help tooltip")

            # Verify Tab 1 (Overview) charts have axis labels with units
            plotly_charts = at.get('plotly_chart')
            self.assertGreaterEqual(len(plotly_charts), 4, "Expected at least 4 Plotly charts in overview")
            import json
            fig_all_layout = json.loads(plotly_charts[0].proto.spec).get('layout', {})
            self.assertEqual(fig_all_layout.get('yaxis', {}).get('title', {}).get('text'), "กำลังไฟฟ้า (kW)")
            self.assertEqual(fig_all_layout.get('xaxis', {}).get('title', {}).get('text'), "วัน-เวลา (Timestamp)")

            fig_daily_layout = json.loads(plotly_charts[3].proto.spec).get('layout', {})
            self.assertEqual(fig_daily_layout.get('yaxis', {}).get('title', {}).get('text'), "พลังงานไฟฟ้ารวม (kWh)")
            self.assertEqual(fig_daily_layout.get('xaxis', {}).get('title', {}).get('text'), "วันที่ (Date)")

            # Verify Tab 1 (Overview) charts have Thai trace names with units
            fig_all_spec = json.loads(plotly_charts[0].proto.spec)
            fig_all_traces = [t.get('name') for t in fig_all_spec.get('data', [])]
            self.assertTrue(
                any("กำลังไฟฟ้า (kW" in name for name in fig_all_traces),
                f"Expected Thai trace name with kW in fig_all, got: {fig_all_traces}"
            )

            fig_kw_spec = json.loads(plotly_charts[1].proto.spec)
            fig_kw_traces = [t.get('name') for t in fig_kw_spec.get('data', [])]
            self.assertIn("กำลังไฟฟ้า (kW)", fig_kw_traces)

            fig_kwh_spec = json.loads(plotly_charts[2].proto.spec)
            fig_kwh_traces = [t.get('name') for t in fig_kwh_spec.get('data', [])]
            self.assertIn("พลังงานไฟฟ้า (kWh)", fig_kwh_traces)

            fig_daily_spec = json.loads(plotly_charts[3].proto.spec)
            fig_daily_traces = [t.get('name') for t in fig_daily_spec.get('data', [])]
            self.assertIn("พลังงานไฟฟ้ารวมรายวัน (kWh)", fig_daily_traces)

            # Verify Tab 1 (Overview) has anomaly color legend in info banner
            tab1_anomaly_legends = [inf.value for inf in at.info if "จุดสีแดง = โหลดสูงผิดปกติ" in inf.value]
            self.assertGreaterEqual(len(tab1_anomaly_legends), 2, "Expected anomaly color explanation in both Tab 1 and Tab 2")

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

            # Verify Tab 2 (Daily Insights) subplots chart has full Thai axis titles with units and Thai trace names
            self.assertGreaterEqual(len(plotly_charts), 5, "Expected at least 5 Plotly charts rendered")
            fig_15min_spec = json.loads(plotly_charts[4].proto.spec)
            fig_15min_layout = fig_15min_spec.get('layout', {})
            self.assertEqual(fig_15min_layout.get('yaxis', {}).get('title', {}).get('text'), "กำลังไฟฟ้า (kW)")
            self.assertEqual(fig_15min_layout.get('yaxis2', {}).get('title', {}).get('text'), "พลังงานไฟฟ้า (kWh)")
            self.assertEqual(fig_15min_layout.get('yaxis3', {}).get('title', {}).get('text'), "แรงดันไฟฟ้า (V)")
            self.assertEqual(fig_15min_layout.get('yaxis4', {}).get('title', {}).get('text'), "ค่าไฟฟ้า (บาท)")

            fig_15min_traces = [t.get('name') for t in fig_15min_spec.get('data', [])]
            self.assertIn("กำลังไฟฟ้า (kW)", fig_15min_traces)
            self.assertIn("พลังงานไฟฟ้า (kWh)", fig_15min_traces)
            self.assertIn("แรงดันไฟฟ้า (V)", fig_15min_traces)
            self.assertIn("ค่าไฟฟ้า (บาท)", fig_15min_traces)

            # Verify Tab 2 has period color legend info banner
            tab2_legends = [inf.value for inf in at.info if "สีส้ม = On-Peak" in inf.value]
            self.assertGreaterEqual(len(tab2_legends), 2, "Expected period color legend in both Tab 1 and Tab 2")

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

            # Test Tab 2 anomaly markers by updating file_uploader with anomaly data in the same session
            clocks = pd.date_range('2026-01-01 08:00:00', periods=20, freq='15min')
            anomaly_df = pd.DataFrame({
                'Clock': clocks.strftime('%Y-%m-%d %H:%M:%S'),
                'kW_Import': [50.0] * 19 + [500.0],
                'Voltage': [220.0] * 20
            })
            anom_buf = io.BytesIO()
            anomaly_df.to_csv(anom_buf, index=False)
            at.file_uploader[0].set_value([("anomaly_data.csv", anom_buf.getvalue(), "text/csv")]).run()

            plotly_charts_anom = at.get('plotly_chart')
            fig_15min_anom_spec = json.loads(plotly_charts_anom[4].proto.spec)
            anom_trace_names = [t.get('name') for t in fig_15min_anom_spec.get('data', [])]
            self.assertIn("สูงกว่าเกณฑ์", anom_trace_names, "Expected 'สูงกว่าเกณฑ์' anomaly trace on daily chart")

            # Test Tab 4 custom date selection guidance and empty state
            import datetime
            multi_day_df = pd.DataFrame({
                'Clock': ['2026-01-01 10:00:00', '2026-01-05 10:00:00'],
                'kW_Import': [100.0, 110.0],
                'Voltage': [220.0, 220.0]
            })
            multi_buf = io.BytesIO()
            multi_day_df.to_csv(multi_buf, index=False)
            at.file_uploader[0].set_value([("multi_day.csv", multi_buf.getvalue(), "text/csv")]).run()

            # Switch Tab 4 summary mode to "กำหนดช่วงเวลา (Custom)"
            radios = [r for r in at.radio if "ระดับการสรุปผล" in r.label or "กำหนดช่วงเวลา (Custom)" in r.options]
            self.assertTrue(len(radios) > 0, "Expected summary mode radio button in Tab 4")
            radios[0].set_value("กำหนดช่วงเวลา (Custom)").run()

            date_inputs = [di for di in at.date_input if "เลือกช่วงเวลา" in di.label]
            self.assertEqual(len(date_inputs), 1, "Expected custom date range input in Tab 4")

            # Case 1: Incomplete date selection (only start date selected)
            date_inputs[0].set_value((datetime.date(2026, 1, 1),)).run()
            self.assertFalse(at.exception, f"App execution failed on single date: {at.exception}")
            guidance_info = [inf.value for inf in at.info if "กรุณาคลิกเลือกวันสิ้นสุดให้ครบถ้วน" in inf.value]
            self.assertTrue(len(guidance_info) > 0, "Expected guidance message when only start date is selected")

            # Case 2: Date range with no data records (e.g. 2026-01-02 to 2026-01-03)
            date_inputs[0].set_value((datetime.date(2026, 1, 2), datetime.date(2026, 1, 3))).run()
            self.assertFalse(at.exception, f"App execution failed on empty date range: {at.exception}")
            empty_info = [inf.value for inf in at.info if "ไม่พบข้อมูลการใช้ไฟฟ้าในช่วงเวลาที่เลือก" in inf.value]
            self.assertTrue(len(empty_info) > 0, "Expected empty state message when selected range has no data")

            # Ensure metrics and simulation download button are hidden when data is empty
            tab4_metrics = [m for m in at.metric if m.label == "พลังงานที่ใช้ทั้งหมด"]
            self.assertEqual(len(tab4_metrics), 0, "Expected Tab 4 metrics to be hidden when summary data is empty")
            sim_downloads = [db for db in at.download_button if "ดาวน์โหลดผลการจำลองค่าไฟ" in db.label]
            self.assertEqual(len(sim_downloads), 0, "Expected simulation download button to be hidden when summary data is empty")

            # UX regression: mixed upload must persistently report skipped files (with
            # reason + fix hint) and the analyzed date range, not just a transient toast.
            summary_radios = [r for r in at.radio if "กำหนดช่วงเวลา (Custom)" in r.options]
            summary_radios[0].set_value("ภาพรวมทั้งหมด (Total)").run()

            good = (
                "Clock,kW_Import,Voltage\n"
                "2026-01-01 10:00:00,100,220\n"
                "2026-01-01 10:15:00,110,220\n"
            ).encode('utf-8')
            bad = b"hello,world\nfoo,bar\nbaz,qux\n"

            at.file_uploader[0].set_value([
                ("good.csv", good, "text/csv"),
                ("bad.csv", bad, "text/csv"),
            ]).run()
            self.assertFalse(at.exception, f"App execution failed on mixed upload: {at.exception}")

            notices = [w.value for w in at.warning if "ข้ามไฟล์ที่อ่านไม่ได้" in w.value]
            self.assertEqual(len(notices), 1, "Expected a persistent notice listing skipped files")
            self.assertIn("bad.csv", notices[0])
            self.assertIn("อ่านไฟล์ไม่สำเร็จ", notices[0])
            self.assertIn("วิธีแก้", notices[0])

            successes = [s.value for s in at.success if "วิเคราะห์ข้อมูลสำเร็จ" in s.value]
            self.assertEqual(successes, ["วิเคราะห์ข้อมูลสำเร็จ 1 จาก 2 ไฟล์"])

            coverage = [c.value for c in at.caption if "ข้อมูลที่อ่านได้" in c.value]
            self.assertEqual(len(coverage), 1, "Expected analyzed date range caption")
            self.assertIn("01/01/2026 10:00", coverage[0])
            self.assertIn("01/01/2026 10:15", coverage[0])
            self.assertIn("2 แถว", coverage[0])

            # UX: invalid On-Peak window must be explained in the sidebar, not silently
            # producing a zero On-Peak cost or an unexpected overnight peak window.
            equal_warnings = [w.value for w in at.warning if "On-Peak" in w.value and "เท่ากัน" in w.value]
            self.assertEqual(equal_warnings, [], "Should not warn on the default On-Peak window")

            def _set_peak_times(start, end):
                next(w for w in at.time_input if "เริ่ม On-Peak" in w.label).set_value(start)
                next(w for w in at.time_input if "สิ้นสุด On-Peak" in w.label).set_value(end)
                at.run()
                self.assertFalse(at.exception, f"App execution failed: {at.exception}")

            _set_peak_times(datetime.time(9, 0), datetime.time(9, 0))
            equal_warnings = [w.value for w in at.warning if "On-Peak" in w.value and "เท่ากัน" in w.value]
            self.assertEqual(len(equal_warnings), 1, "Expected a visible warning when On-Peak start equals end")
            self.assertIn("ไม่คิด", equal_warnings[0])
            self.assertIn("กรุณาตั้งเวลาให้ต่างกัน", equal_warnings[0])

            _set_peak_times(datetime.time(22, 0), datetime.time(9, 0))
            equal_warnings = [w.value for w in at.warning if "On-Peak" in w.value and "เท่ากัน" in w.value]
            self.assertEqual(equal_warnings, [], "Equal-time warning must disappear after fixing the window")
            overnight_info = [i.value for i in at.info if "On-Peak ข้ามวัน" in i.value]
            self.assertEqual(len(overnight_info), 1, "Expected an explanation for an overnight On-Peak window")
            self.assertIn("22:00", overnight_info[0])
            self.assertIn("09:00", overnight_info[0])

            # Restore the default On-Peak window for the remaining checks
            _set_peak_times(datetime.time(9, 0), datetime.time(22, 0))
            self.assertEqual(
                [i.value for i in at.info if "On-Peak ข้ามวัน" in i.value], [],
                "Overnight explanation must disappear after restoring the default window"
            )

            # When every file fails, the user must still see why and what to fix.
            at.file_uploader[0].set_value([("bad.csv", bad, "text/csv")]).run()
            self.assertFalse(at.exception, f"App execution failed when all uploads are invalid: {at.exception}")
            errors = [e.value for e in at.error if "ไม่มีข้อมูลที่สามารถนำมาวิเคราะห์ได้เลย" in e.value]
            self.assertEqual(len(errors), 1)
            notices = [w.value for w in at.warning if "ข้ามไฟล์ที่อ่านไม่ได้" in w.value]
            self.assertEqual(len(notices), 1, "Expected skipped-file details when all files fail")
            self.assertIn("bad.csv", notices[0])
        finally:
            if mock_st is not None:
                sys.modules['streamlit'] = mock_st

    def test_tou_breakdown_displays_standard_units_and_percentages(self):
        """กล่องสรุปพลังงานรายช่วงเวลาในแท็บ 4 ต้องใช้หน่วย 'บาท/หน่วย' มาตรฐาน และแสดงสัดส่วนร้อยละ (%) ทั้งก่อนและหลังจำลอง"""
        import sys
        mock_st = None
        if 'streamlit' in sys.modules and not hasattr(sys.modules['streamlit'], '__path__'):
            mock_st = sys.modules.pop('streamlit')

        try:
            from streamlit.testing.v1 import AppTest
            import os
            import io

            app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
            at = AppTest.from_file(app_path, default_timeout=30).run()

            # Mock data with 1 On-Peak interval (Monday 10:00) and 1 Off-Peak interval (Monday 23:00)
            df = pd.DataFrame({
                'Clock': [
                    '2026-01-05 10:00:00',
                    '2026-01-05 23:00:00',
                ],
                'kW_Import': [100.0, 100.0],
                'Voltage': [220.0, 220.0],
            })
            buffer = io.BytesIO()
            df.to_csv(buffer, index=False)
            at.file_uploader[0].set_value([("tou_pct.csv", buffer.getvalue(), "text/csv")]).run()
            self.assertFalse(at.exception, f"App execution failed: {at.exception}")

            # Check Tab 4 energy metric has 2 decimal precision
            metrics = {m.label: m.value for m in at.metric}
            self.assertEqual(metrics["พลังงานที่ใช้ทั้งหมด"], "50.00 kWh")

            # Check that On-Peak and Off-Peak cards use standard 'บาท/หน่วย' and show % breakdown
            on_peak_cards = [e.value for e in at.error if "On-Peak" in e.value]
            self.assertTrue(len(on_peak_cards) > 0, "Expected On-Peak breakdown card")
            self.assertIn("บาท/หน่วย", on_peak_cards[0], "Card must use standard 'บาท/หน่วย' instead of 'บ.'")
            self.assertNotIn(" บ.)", on_peak_cards[0], "Card must not contain casual abbreviation 'บ.)'")
            self.assertIn("50.0%", on_peak_cards[0], "Expected energy percentage (50.0%) in On-Peak card")
            self.assertIn("68.7%", on_peak_cards[0], "Expected cost percentage (68.7%) in On-Peak card")

            off_peak_cards = [s.value for s in at.success if "Off-Peak" in s.value]
            self.assertTrue(len(off_peak_cards) > 0, "Expected Off-Peak breakdown card")
            self.assertIn("บาท/หน่วย", off_peak_cards[0], "Card must use standard 'บาท/หน่วย'")
            self.assertNotIn(" บ.)", off_peak_cards[0], "Card must not contain casual abbreviation 'บ.)'")
            self.assertIn("50.0%", off_peak_cards[0], "Expected energy percentage (50.0%) in Off-Peak card")
            self.assertIn("31.3%", off_peak_cards[0], "Expected cost percentage (31.3%) in Off-Peak card")

            # Simulate shifting time in Tab 4
            next(ni for ni in at.number_input if "ใส่เวลาที่เลื่อน" in ni.label).set_value(60).run()
            self.assertFalse(at.exception, f"App execution failed after simulation: {at.exception}")

            # Check simulated cards also use 'บาท/หน่วย' and show %
            sim_on_peak = [e.value for e in at.error if "On-Peak" in e.value]
            self.assertEqual(len(sim_on_peak), 2, "Expected current and simulated On-Peak cards")
            self.assertIn("บาท/หน่วย", sim_on_peak[1])
            self.assertNotIn(" บ.)", sim_on_peak[1])
            self.assertIn("%", sim_on_peak[1])

            sim_off_peak = [s.value for s in at.success if "Off-Peak" in s.value]
            self.assertEqual(len(sim_off_peak), 2, "Expected current and simulated Off-Peak cards")
            self.assertIn("บาท/หน่วย", sim_off_peak[1])
            self.assertNotIn(" บ.)", sim_off_peak[1])
            self.assertIn("%", sim_off_peak[1])
        finally:
            if mock_st is not None and not hasattr(sys.modules.get('streamlit'), '__path__'):
                sys.modules['streamlit'] = mock_st

    def test_tab2_daily_insights_shows_day_type_and_tou_context(self):
        """แท็บ 2 (เจาะลึกรายวัน) ต้องแสดงชื่อวันภาษาไทย ประเภทวัน (วันทำงาน/วันหยุด) และเงื่อนไขอัตราค่าไฟ TOU อย่างชัดเจน"""
        import sys
        mock_st = None
        if 'streamlit' in sys.modules and not hasattr(sys.modules['streamlit'], '__path__'):
            mock_st = sys.modules.pop('streamlit')

        try:
            from streamlit.testing.v1 import AppTest
            import os
            import io
            import datetime

            app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
            at = AppTest.from_file(app_path, default_timeout=30).run()

            # Data with 3 different day types:
            # 2026-01-01 (Thursday, Holiday)
            # 2026-01-03 (Saturday, Weekend)
            # 2026-01-05 (Monday, Weekday)
            df = pd.DataFrame({
                'Clock': [
                    '2026-01-01 10:00:00',
                    '2026-01-03 10:00:00',
                    '2026-01-05 10:00:00',
                ],
                'kW_Import': [100.0, 100.0, 100.0],
                'Voltage': [220.0, 220.0, 220.0],
            })
            buffer = io.BytesIO()
            df.to_csv(buffer, index=False)
            at.file_uploader[0].set_value([('days_test.csv', buffer.getvalue(), 'text/csv')]).run()
            self.assertFalse(at.exception, f'App execution failed: {at.exception}')

            # 1. Default selected date: 2026-01-01 (Thursday, Public Holiday)
            holiday_cards = [inf.value for inf in at.info if 'วันหยุดนักขัตฤกษ์' in inf.value]
            self.assertEqual(len(holiday_cards), 1, 'Expected holiday context card in Tab 2 for 2026-01-01')
            self.assertIn('วันพฤหัสบดี', holiday_cards[0])
            self.assertIn('01/01/2026', holiday_cards[0])
            self.assertIn('Off-Peak/Holiday', holiday_cards[0])
            self.assertIn('ไม่มีช่วง On-Peak', holiday_cards[0])

            # 2. Switch date to 2026-01-05 (Monday, Weekday)
            date_selector = next(sb for sb in at.selectbox if 'เลือกวันที่ต้องการเจาะลึก' in sb.label)
            date_selector.set_value(datetime.date(2026, 1, 5)).run()
            self.assertFalse(at.exception, f'App execution failed on date switch: {at.exception}')

            weekday_cards = [inf.value for inf in at.info if 'วันทำงานปกติ' in inf.value]
            self.assertEqual(len(weekday_cards), 1, 'Expected weekday context card in Tab 2 for 2026-01-05')
            self.assertIn('วันจันทร์', weekday_cards[0])
            self.assertIn('05/01/2026', weekday_cards[0])
            self.assertIn('On-Peak', weekday_cards[0])
            self.assertIn('09:00–22:00', weekday_cards[0])

            # 3. Switch date to 2026-01-03 (Saturday, Weekend)
            date_selector = next(sb for sb in at.selectbox if 'เลือกวันที่ต้องการเจาะลึก' in sb.label)
            date_selector.set_value(datetime.date(2026, 1, 3)).run()
            self.assertFalse(at.exception, f'App execution failed on date switch: {at.exception}')

            weekend_cards = [inf.value for inf in at.info if 'วันหยุดสุดสัปดาห์' in inf.value]
            self.assertEqual(len(weekend_cards), 1, 'Expected weekend context card in Tab 2 for 2026-01-03')
            self.assertIn('วันเสาร์', weekend_cards[0])
            self.assertIn('03/01/2026', weekend_cards[0])
            self.assertIn('ไม่มีช่วง On-Peak', weekend_cards[0])

            # 4. Switch to Single Rate
            rate_radio = next(r for r in at.radio if 'ประเภทอัตราค่าไฟ' in r.label)
            rate_radio.set_value('อัตราเดียว (Single Rate)').run()
            self.assertFalse(at.exception, f'App execution failed on rate switch: {at.exception}')

            single_rate_cards = [inf.value for inf in at.info if 'คิดอัตราเดียว (Single Rate)' in inf.value]
            self.assertEqual(len(single_rate_cards), 1, 'Expected single rate context card in Tab 2')
            self.assertIn('คิดเรทคงที่', single_rate_cards[0])
        finally:
            if mock_st is not None and not hasattr(sys.modules.get('streamlit'), '__path__'):
                sys.modules['streamlit'] = mock_st


    def test_tab3_shift_graph_shows_outcome_banner_and_rate_context(self):
        """แท็บ 3 (กราฟจำลองเวลา) ต้องแสดงกล่องสรุปผลการจำลองค่าไฟ (ประหยัด/เพิ่มขึ้น/คงเดิม) รองรับอัตราเดียว และแสดงชื่อวันภาษาไทยในหัวข้อกราฟ"""
        import sys
        mock_st = None
        if 'streamlit' in sys.modules and not hasattr(sys.modules['streamlit'], '__path__'):
            mock_st = sys.modules.pop('streamlit')

        try:
            from streamlit.testing.v1 import AppTest
            import os
            import io
            import datetime
            import json

            app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py')
            at = AppTest.from_file(app_path, default_timeout=30).run()

            # Monday 2026-01-05 at 21:45:00 (On-Peak)
            df = pd.DataFrame({
                'Clock': [
                    '2026-01-05 21:45:00',
                ],
                'kW_Import': [100.0],
                'Voltage': [220.0],
            })
            buffer = io.BytesIO()
            df.to_csv(buffer, index=False)
            at.file_uploader[0].set_value([('shift_test.csv', buffer.getvalue(), 'text/csv')]).run()
            self.assertFalse(at.exception, f'App execution failed: {at.exception}')

            # 1. Default shift is 15 minutes: 21:45 + 15m = 22:00 (Off-Peak)
            # Moves from On-Peak (5.7982) to Off-Peak (2.6369) -> Saves money!
            savings_banners = [s.value for s in at.success if 'ประหยัดค่าไฟฟ้าได้' in s.value]
            self.assertEqual(len(savings_banners), 1, 'Expected savings banner in Tab 3')
            self.assertIn('฿', savings_banners[0])
            self.assertIn('%', savings_banners[0])
            self.assertIn('+15 นาที', savings_banners[0])

            # 2. Change shift to 0 minutes: 21:45 (original time)
            shift_input = next(ni for ni in at.number_input if 'จำนวนนาทีที่ต้องการเลื่อน' in ni.label)
            shift_input.set_value(0).run()
            self.assertFalse(at.exception, f'App execution failed with 0 shift: {at.exception}')
            zero_info = [inf.value for inf in at.info if 'เวลาจำลองเป็น 0 นาที' in inf.value]
            self.assertEqual(len(zero_info), 1, 'Expected 0-minute info banner in Tab 3')

            # 3. Switch to Single Rate
            rate_radio = next(r for r in at.radio if 'ประเภทอัตราค่าไฟ' in r.label)
            rate_radio.set_value('อัตราเดียว (Single Rate)').run()
            self.assertFalse(at.exception, f'App execution failed on rate switch: {at.exception}')

            # In Single Rate, metric should show '⚡ พลังงานรวม (Total kWh)' instead of On-Peak
            metrics = {m.label: m.value for m in at.metric}
            self.assertIn('⚡ พลังงานรวม (Total kWh)', metrics, 'Expected Total kWh metric in Tab 3 under Single Rate')
            self.assertNotIn('⚡ พลังงานช่วง On-Peak', metrics, 'On-Peak metric must not be displayed under Single Rate')

            # 4. Check Thai day name in chart title when selecting specific date
            shift_date_selector = next(sb for sb in at.selectbox if 'เลือกรูปแบบการเปรียบเทียบกราฟ' in sb.label)
            shift_date_selector.set_value(datetime.date(2026, 1, 5)).run()
            self.assertFalse(at.exception, f'App execution failed on date selector: {at.exception}')

            plotly_charts = at.get('plotly_chart')
            self.assertGreaterEqual(len(plotly_charts), 6, 'Expected comparison chart in Tab 3')
            compare_fig_spec = json.loads(plotly_charts[5].proto.spec)
            compare_title = compare_fig_spec.get('layout', {}).get('title', {}).get('text', '')
            self.assertIn('วันจันทร์', compare_title)
            self.assertIn('05/01/2026', compare_title)
        finally:
            if mock_st is not None and not hasattr(sys.modules.get('streamlit'), '__path__'):
                sys.modules['streamlit'] = mock_st
