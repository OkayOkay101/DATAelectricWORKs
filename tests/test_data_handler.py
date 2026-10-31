import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
import sys
from unittest.mock import MagicMock, patch

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

    def test_load_file_rejects_xlsx_decompression_bomb(self):
        import io
        import struct
        import zipfile
        from unittest import mock
        from data_handler import load_file, MAX_EXCEL_UNCOMPRESSED_BYTES

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('xl/worksheets/sheet1.xml', '<worksheet/>')
        payload = bytearray(buffer.getvalue())

        # Forge the declared uncompressed size in both local and central headers
        # so the archive looks like a multi-hundred-MB bomb without allocating it.
        forged_size = MAX_EXCEL_UNCOMPRESSED_BYTES + 1
        struct.pack_into('<I', payload, 22, forged_size)
        central_dir = payload.find(b'PK\x01\x02')
        self.assertNotEqual(central_dir, -1)
        struct.pack_into('<I', payload, central_dir + 24, forged_size)

        with mock.patch('pandas.read_excel') as read_excel_mock:
            with self.assertRaises(ValueError) as ctx:
                load_file(io.BytesIO(bytes(payload)), 'xlsx')
            read_excel_mock.assert_not_called()
        self.assertIn("แตกไฟล์เกินกำหนด", str(ctx.exception))

    def test_validate_excel_archive_allows_small_zip_and_non_zip(self):
        import io
        import zipfile
        from data_handler import validate_excel_archive

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('xl/worksheets/sheet1.xml', '<worksheet/>')
        buffer.seek(0)
        validate_excel_archive(buffer)

        # HTML renamed to .xlsx is handled by the existing read_html fallback.
        validate_excel_archive(io.BytesIO(b"<html><body><table></table></body></html>"))

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

    def test_validate_upload_batch_rejects_too_many_files(self):
        from data_handler import validate_upload_batch, UploadValidationError, MAX_UPLOAD_FILES

        class FakeFile:
            def __init__(self, size):
                self.size = size

        files = [FakeFile(1) for _ in range(MAX_UPLOAD_FILES + 1)]
        with self.assertRaises(UploadValidationError) as ctx:
            validate_upload_batch(files)
        self.assertIn("ไฟล์ต่อครั้ง", str(ctx.exception))

    def test_validate_upload_batch_rejects_aggregate_size_over_limit(self):
        from data_handler import validate_upload_batch, UploadValidationError, MAX_TOTAL_UPLOAD_BYTES

        class FakeFile:
            def __init__(self, size):
                self.size = size

        # Each file individually passes the per-file limit but the batch does not.
        per_file = MAX_TOTAL_UPLOAD_BYTES // 4 + 1
        files = [FakeFile(per_file) for _ in range(4)]
        with self.assertRaises(UploadValidationError) as ctx:
            validate_upload_batch(files)
        self.assertIn("ขนาดไฟล์รวมเกินกำหนด", str(ctx.exception))

    def test_validate_upload_batch_allows_batch_within_limits(self):
        from data_handler import validate_upload_batch, MAX_TOTAL_UPLOAD_BYTES

        class FakeFile:
            def __init__(self, size):
                self.size = size

        files = [FakeFile(1024), FakeFile(2048)]
        total = validate_upload_batch(files)
        self.assertEqual(total, 3072)
        self.assertLess(total, MAX_TOTAL_UPLOAD_BYTES)

    def test_validate_upload_batch_uses_getbuffer_when_size_missing(self):
        import io
        from data_handler import validate_upload_batch

        buffer = io.BytesIO(b"x" * 10)
        self.assertEqual(validate_upload_batch([buffer]), 10)

    def test_get_upload_size_uses_seek_and_tell_when_size_and_getbuffer_missing(self):
        import io
        from data_handler import get_upload_size

        class MockSeekableStream(io.BytesIO):
            def __getattribute__(self, name):
                if name in ('size', 'getbuffer'):
                    raise AttributeError(f"No {name}")
                return super().__getattribute__(name)

        stream = MockSeekableStream(b"A" * 2048)
        stream.seek(15)
        self.assertEqual(get_upload_size(stream), 2048)
        self.assertEqual(stream.tell(), 15, "Stream position must be preserved after size calculation")

    def test_validate_upload_batch_rejects_oversized_seekable_streams(self):
        import io
        from data_handler import validate_upload_batch, UploadValidationError, MAX_TOTAL_UPLOAD_BYTES

        class MockSeekableStream(io.BytesIO):
            def __init__(self, virtual_size):
                super().__init__(b"sample")
                self.virtual_size = virtual_size
                self._virtual_pos = None

            def __getattribute__(self, name):
                if name in ('size', 'getbuffer'):
                    raise AttributeError(f"No {name}")
                return super().__getattribute__(name)

            def seek(self, offset, whence=io.SEEK_SET):
                if whence == io.SEEK_END and self.virtual_size is not None:
                    self._virtual_pos = self.virtual_size + offset
                    return self._virtual_pos
                self._virtual_pos = None
                return super().seek(offset, whence)

            def tell(self):
                if getattr(self, '_virtual_pos', None) is not None:
                    return self._virtual_pos
                return super().tell()

        per_file = MAX_TOTAL_UPLOAD_BYTES // 4 + 1024
        files = [MockSeekableStream(virtual_size=per_file) for _ in range(4)]
        with self.assertRaises(UploadValidationError) as ctx:
            validate_upload_batch(files)
        self.assertIn("ขนาดไฟล์รวมเกินกำหนด", str(ctx.exception))

    def test_load_file_rejects_oversized_seekable_stream(self):
        import io
        from data_handler import load_file, UploadValidationError, MAX_FILE_SIZE_BYTES

        class MockSeekableStream(io.BytesIO):
            def __init__(self, content, virtual_size):
                super().__init__(content)
                self.virtual_size = virtual_size
                self._virtual_pos = None

            def __getattribute__(self, name):
                if name in ('size', 'getbuffer'):
                    raise AttributeError(f"No {name}")
                return super().__getattribute__(name)

            def seek(self, offset, whence=io.SEEK_SET):
                if whence == io.SEEK_END and self.virtual_size is not None:
                    self._virtual_pos = self.virtual_size + offset
                    return self._virtual_pos
                self._virtual_pos = None
                return super().seek(offset, whence)

            def tell(self):
                if getattr(self, '_virtual_pos', None) is not None:
                    return self._virtual_pos
                return super().tell()

        oversized_stream = MockSeekableStream(
            b"Clock,kW_Import,Voltage\n01/01/2026 00:00,100,220\n",
            virtual_size=MAX_FILE_SIZE_BYTES + 1024
        )
        with self.assertRaises(UploadValidationError) as ctx:
            load_file(oversized_stream, "csv")
        self.assertIn("ขนาดไฟล์เกินกำหนด", str(ctx.exception))

    def test_get_upload_size_ignores_negative_size_and_falls_back_to_stream(self):
        import io
        from data_handler import get_upload_size

        # 1. Fallback to getbuffer() when size is negative
        stream = io.BytesIO(b"X" * 1024)
        stream.size = -1
        self.assertEqual(get_upload_size(stream), 1024)

        # 2. Fallback to seek/tell when size is negative and getbuffer is absent
        class MockSeekableNegativeStream(io.BytesIO):
            def __init__(self, nbytes):
                super().__init__(b"sample")
                self.virtual_size = nbytes
                self.size = -1
                self._virtual_pos = None

            def __getattribute__(self, name):
                if name == 'getbuffer':
                    raise AttributeError("No getbuffer")
                return super().__getattribute__(name)

            def seek(self, offset, whence=io.SEEK_SET):
                if whence == io.SEEK_END:
                    self._virtual_pos = self.virtual_size + offset
                    return self._virtual_pos
                self._virtual_pos = None
                return super().seek(offset, whence)

            def tell(self):
                if getattr(self, '_virtual_pos', None) is not None:
                    return self._virtual_pos
                return super().tell()

        self.assertEqual(get_upload_size(MockSeekableNegativeStream(4096)), 4096)

        # 3. Unseekable negative stream returns None
        class MockUnseekableNegativeStream:
            size = -1

        self.assertIsNone(get_upload_size(MockUnseekableNegativeStream()))

    def test_load_file_rejects_oversized_file_with_negative_size_attribute(self):
        import io
        from data_handler import load_file, UploadValidationError, MAX_FILE_SIZE_BYTES

        class MockOversizedNegativeStream(io.BytesIO):
            def __init__(self, content, virtual_size):
                super().__init__(content)
                self.virtual_size = virtual_size
                self.size = -1
                self._virtual_pos = None

            def __getattribute__(self, name):
                if name == 'getbuffer':
                    raise AttributeError("No getbuffer")
                return super().__getattribute__(name)

            def seek(self, offset, whence=io.SEEK_SET):
                if whence == io.SEEK_END and self.virtual_size is not None:
                    self._virtual_pos = self.virtual_size + offset
                    return self._virtual_pos
                self._virtual_pos = None
                return super().seek(offset, whence)

            def tell(self):
                if getattr(self, '_virtual_pos', None) is not None:
                    return self._virtual_pos
                return super().tell()

        oversized_stream = MockOversizedNegativeStream(
            b"Clock,kW_Import,Voltage\n01/01/2026 00:00,100,220\n",
            virtual_size=MAX_FILE_SIZE_BYTES + 2048
        )
        with self.assertRaises(UploadValidationError) as ctx:
            load_file(oversized_stream, "csv")
        self.assertIn("ขนาดไฟล์เกินกำหนด", str(ctx.exception))

    def test_validate_upload_batch_does_not_allow_negative_size_to_reduce_total_or_bypass(self):
        import io
        from data_handler import validate_upload_batch, UploadValidationError, MAX_TOTAL_UPLOAD_BYTES

        class MockStream(io.BytesIO):
            def __init__(self, size_attr, virtual_size):
                super().__init__(b"Clock,kW_Import,Voltage\n01/01/2026 00:00,100,220\n")
                self.size = size_attr
                self.virtual_size = virtual_size
                self._virtual_pos = None

            def __getattribute__(self, name):
                if name == 'getbuffer':
                    raise AttributeError("No getbuffer")
                return super().__getattribute__(name)

            def seek(self, offset, whence=io.SEEK_SET):
                if whence == io.SEEK_END and self.virtual_size is not None:
                    self._virtual_pos = self.virtual_size + offset
                    return self._virtual_pos
                self._virtual_pos = None
                return super().seek(offset, whence)

            def tell(self):
                if getattr(self, '_virtual_pos', None) is not None:
                    return self._virtual_pos
                return super().tell()

        per_file = MAX_TOTAL_UPLOAD_BYTES // 4 + 1024
        files = [MockStream(size_attr=-1, virtual_size=per_file) for _ in range(4)]
        with self.assertRaises(UploadValidationError) as ctx:
            validate_upload_batch(files)
        self.assertIn("ขนาดไฟล์รวมเกินกำหนด", str(ctx.exception))

    def test_app_enforces_upload_batch_limits(self):
        import ast
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        imported = any(
            isinstance(node, ast.ImportFrom) and node.module == 'data_handler'
            and any(alias.name == 'validate_upload_batch' for alias in node.names)
            for node in ast.walk(tree)
        )
        self.assertTrue(imported, "app.py must import validate_upload_batch from data_handler")

        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'validate_upload_batch'
        ]
        self.assertTrue(calls, "app.py must call validate_upload_batch before processing uploads")

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

    def test_parse_text_lines_prefers_kw_over_kwh_column(self):
        # A cumulative kWh column contains "kw" as a substring and often has a
        # larger sum, but it must never be selected as the instantaneous kW value.
        lines = [
            "Clock, Import kWh, Import kW, Voltage",
            "01/01/2026 00:15, 400.0, 100.0, 220",
            "01/01/2026 00:30, 440.0, 110.0, 221",
        ]
        df = parse_text_lines(lines, delimiter=',')
        self.assertIsNotNone(df)
        self.assertEqual(df['kW_Import'].tolist(), ['100.0', '110.0'])
        self.assertEqual(df['Voltage'].tolist(), ['220', '221'])

    def test_parse_excel_df_prefers_kw_over_kwh_column(self):
        df_raw = pd.DataFrame([
            ["Clock", "Import kWh", "Import kW", "Voltage"],
            ["01/01/2026 00:15", 400.0, 100.0, 220],
            ["01/01/2026 00:30", 440.0, 110.0, 221],
        ])
        df = parse_excel_df(df_raw)
        self.assertIsNotNone(df)
        self.assertEqual(df['kW_Import'].tolist(), [100.0, 110.0])
        self.assertEqual(df['Voltage'].tolist(), [220.0, 221.0])

    def test_parse_text_lines_energy_only_column_is_not_power(self):
        lines = [
            "Clock, Import kWh, Voltage",
            "01/01/2026 00:15, 400.0, 220",
        ]
        self.assertIsNone(parse_text_lines(lines, delimiter=','))

    def test_parse_excel_df_filters_footer_in_time_column_and_empty_time(self):
        # Excel files with separate Date and Time columns must filter footers in Time (e.g. Total, P, OP, H, empty)
        df_raw = pd.DataFrame([
            ["Date", "Time", "kW_Import", "Voltage"],
            ["01/01/2026", "00:00", "10.0", "220"],
            ["01/01/2026", "00:15", "20.0", "220"],
            ["01/01/2026", "Total", "500.0", "220"],
            ["01/01/2026", "P", "250.0", "220"],
            ["01/01/2026", "OP", "250.0", "220"],
            ["01/01/2026", "H", "0.0", "220"],
            ["01/01/2026", "kWh", "125.0", "220"],
            ["01/01/2026", "dnv/err", "0.0", "220"],
            ["01/01/2026", "", "5000.0", "220"],
            ["01/01/2026", None, "5000.0", "220"],
            ["Total", "", "5000.0", "220"],
        ])
        df = parse_excel_df(df_raw)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2, "Only 2 actual time readings should be retained")
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 00:00")
        self.assertEqual(df.iloc[1]['Clock'], "01/01/2026 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], "10.0")
        self.assertEqual(df.iloc[1]['kW_Import'], "20.0")

    def test_parse_excel_df_filters_clock_summary_footers(self):
        # Single Clock column must filter footers matching total.* and dnv/err
        df_raw = pd.DataFrame([
            ["Clock", "kW_Import", "Voltage"],
            ["01/01/2026 00:15", "100.0", "220"],
            ["Total Energy", "1000.0", "220"],
            ["Total Demand (kW)", "500.0", "220"],
            ["dnv/err", "0.0", "220"],
            ["kWh", "1000.0", "220"],
        ])
        df = parse_excel_df(df_raw)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 1, "Only 1 valid row should be retained, skipping summary footers")
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], "100.0")

    def test_parse_excel_df_preserves_12hr_pm_and_month_names(self):
        # Formats with 12hr PM and month names (Sep, March) must not be falsely dropped by footer filters
        df_raw = pd.DataFrame([
            ["Date", "Time", "kW_Import"],
            ["01/01/2026", "01:00 PM", "100.0"],
            ["15-Sep-2026", "09:00", "120.0"],
            ["10-March-2026", "09:00", "110.0"],
            ["Total", "", "330.0"],
        ])
        df = parse_excel_df(df_raw)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 3, "Expected 3 valid records, skipping only the Total footer")
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 01:00 PM")
        self.assertEqual(df.iloc[1]['Clock'], "15-Sep-2026 09:00")
        self.assertEqual(df.iloc[2]['Clock'], "10-March-2026 09:00")

    def test_parse_excel_df_skips_clock_unique_scan(self):
        # ⚡ Bolt: high-cardinality Clock columns must not pay for a full Series.unique() probe.
        # The first-byte validation gate must produce the same footer filtering without the scan.
        df_raw = pd.DataFrame([
            ["Clock", "kW_Import", "Voltage"],
            ["01/01/2026 00:15", "100.0", "220"],
            ["01/01/2026 00:30", "110.0", "221"],
            ["Total Energy", "1000.0", "220"],
            ["dnv/err", "0.0", "220"],
        ])
        expected = pd.DataFrame({
            "Clock": ["01/01/2026 00:15", "01/01/2026 00:30"],
            "kW_Import": ["100.0", "110.0"],
            "Voltage": ["220", "221"],
        })

        original_unique = pd.Series.unique

        def guarded_unique(series):
            if isinstance(series.name, str) and series.name.lower() == "clock":
                raise AssertionError("parse_excel_df must not scan Clock with Series.unique()")
            return original_unique(series)

        with patch.object(pd.Series, "unique", guarded_unique):
            actual = parse_excel_df(df_raw)

        pd.testing.assert_frame_equal(actual, expected)

    def test_parse_excel_df_none_or_empty_returns_none(self):
        self.assertIsNone(parse_excel_df(None))
        self.assertIsNone(parse_excel_df(pd.DataFrame()))

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

    def test_sanitize_csv_cell_pipe_and_percent_prefixes(self):
        from data_handler import sanitize_csv_cell
        self.assertEqual(sanitize_csv_cell("|cmd|'/C calc'!A0"), "'|cmd|'/C calc'!A0")
        self.assertEqual(sanitize_csv_cell("|calc"), "'|calc")
        self.assertEqual(sanitize_csv_cell("%calc"), "'%calc")
        self.assertEqual(sanitize_csv_cell("  |formula_with_leading_space"), "'  |formula_with_leading_space")
        self.assertEqual(sanitize_csv_cell("  %formula_with_leading_space"), "'  %formula_with_leading_space")

    def test_sanitize_dataframe_for_csv_neutralizes_index_and_index_name(self):
        from data_handler import sanitize_dataframe_for_csv
        df = pd.DataFrame(
            {"Load": [10.5, 20.0, 30.0]},
            index=["=cmd|calc", "@danger", "+non_num"]
        )
        df.index.name = "=IndexHeader"
        sanitized = sanitize_dataframe_for_csv(df)

        self.assertEqual(sanitized.index[0], "'=cmd|calc")
        self.assertEqual(sanitized.index[1], "'@danger")
        self.assertEqual(sanitized.index[2], "'+non_num")
        self.assertEqual(sanitized.index.name, "'=IndexHeader")
        self.assertEqual(sanitized["Load"].iloc[0], 10.5)

    def test_sanitize_dataframe_for_csv_multiindex_support(self):
        from data_handler import sanitize_dataframe_for_csv
        mi_index = pd.MultiIndex.from_tuples(
            [("=calc", "group1"), ("@danger", "group2")],
            names=["=Level1", "Level2"]
        )
        df = pd.DataFrame({"Val": [1, 2]}, index=mi_index)
        sanitized = sanitize_dataframe_for_csv(df)

        self.assertEqual(sanitized.index[0], ("'=calc", "group1"))
        self.assertEqual(sanitized.index[1], ("'@danger", "group2"))
        self.assertEqual(sanitized.index.names, ["'=Level1", "Level2"])

    def test_sanitize_dataframe_for_csv_preserves_numeric_and_datetime_index(self):
        from data_handler import sanitize_dataframe_for_csv
        df_num = pd.DataFrame({"Val": [10, 20]}, index=[1, 2])
        sanitized_num = sanitize_dataframe_for_csv(df_num)
        self.assertEqual(list(sanitized_num.index), [1, 2])

        dt_idx = pd.date_range("2026-01-01", periods=2, freq="15min")
        df_dt = pd.DataFrame({"Val": [10, 20]}, index=dt_idx)
        sanitized_dt = sanitize_dataframe_for_csv(df_dt)
        pd.testing.assert_index_equal(sanitized_dt.index, dt_idx)

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

    def test_preprocess_data_integer_epoch_datetime_fields_parity(self):
        # ⚡ Bolt: Date/Month/Time_Str must match the legacy .dt accessor derivation exactly,
        # including pre-1970 dates, century leap-year rules and year/month boundaries.
        from data_handler import fast_parse_datetime

        dates = pd.to_datetime([
            '1900-02-28 23:45', '1900-03-01 00:00',
            '1969-12-31 23:45', '1970-01-01 00:00',
            '2000-02-29 12:30', '2024-02-29 23:45',
            '2024-03-01 00:00', '2026-12-31 23:45', '2027-01-01 00:00',
        ])
        df_in = pd.DataFrame({
            'Clock': dates.strftime('%d/%m/%Y %H:%M'),
            'kW_Import': [f"{100 + i:.1f}" for i in range(len(dates))],
            'Voltage': ['220.0'] * len(dates),
        }, index=range(100, 100 + len(dates)))

        expected = df_in.copy()
        expected['kW_Import'] = pd.to_numeric(expected['kW_Import'], errors='coerce').fillna(0)
        expected['Voltage'] = pd.to_numeric(expected['Voltage'], errors='coerce').fillna(220.0)
        expected['Clock'] = fast_parse_datetime(expected['Clock'], dayfirst=True)
        expected = expected.reset_index(drop=True)
        expected['Date'] = expected['Clock'].dt.normalize()
        c_dt = expected['Clock'].dt
        ym = c_dt.year * 100 + c_dt.month
        ym_dict = {v: f'{v // 100:04d}-{v % 100:02d}' for v in ym.unique()}
        expected['Month'] = ym.map(ym_dict)
        hm = c_dt.hour * 60 + c_dt.minute
        hm_dict = {v: f'{v // 60:02d}:{v % 60:02d}' for v in hm.unique()}
        expected['Time_Str'] = hm.map(hm_dict)
        expected['kWh_15min'] = expected['kW_Import'] / 4.0

        pd.testing.assert_frame_equal(preprocess_data(df_in), expected)

    def test_preprocess_data_uses_integer_datetime_field_derivation(self):
        # AST check: ensure the fast integer epoch path (iNaT detection + civil-from-days) exists.
        import ast
        handler_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data_handler.py'))
        with open(handler_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_iinfo = False
        found_civil_constant = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'preprocess_data':
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute) and child.attr == 'iinfo':
                        found_iinfo = True
                    if isinstance(child, ast.Constant) and child.value == 146097:
                        found_civil_constant = True
        self.assertTrue(found_iinfo, "preprocess_data should detect NaT via the int64 iNaT sentinel")
        self.assertTrue(found_civil_constant, "preprocess_data should use civil-from-days integer arithmetic")

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

    def test_sanitize_dataframe_for_csv_unique_mapping_optimization(self):
        import data_handler
        from pandas.testing import assert_frame_equal

        df = pd.DataFrame({
            "Period": ["On-Peak", "Off-Peak", "Holiday"] * 100,
            "Anomaly": ["ปกติ", "ไฟตก (Low)", "=malicious"] * 100,
            "kW": [10.5, 20.0, 30.5] * 100
        })

        call_count = 0
        real_sanitize_cell = data_handler.sanitize_csv_cell

        def counting_sanitize(val):
            nonlocal call_count
            call_count += 1
            return real_sanitize_cell(val)

        orig_func = data_handler.sanitize_csv_cell
        data_handler.sanitize_csv_cell = counting_sanitize
        try:
            sanitized = data_handler.sanitize_dataframe_for_csv(df)
        finally:
            data_handler.sanitize_csv_cell = orig_func

        # Headers: 3 columns. Unique cells in Period: 3. Unique cells in Anomaly: 3.
        # Total sanitize_csv_cell calls must not exceed headers + unique values (3 + 3 + 3 = 9).
        # In naive element-by-element mapping, this would be 3 + 300 + 300 = 603 calls.
        self.assertLessEqual(call_count, 15, f"Expected unique-value mapping (<= 15 calls), got {call_count}")

        expected_anomaly = ["ปกติ", "ไฟตก (Low)", "'=malicious"] * 100
        expected_df = pd.DataFrame({
            "Period": ["On-Peak", "Off-Peak", "Holiday"] * 100,
            "Anomaly": expected_anomaly,
            "kW": [10.5, 20.0, 30.5] * 100
        })
        assert_frame_equal(sanitized, expected_df)

    def test_preprocess_data_missing_voltage_column(self):
        # When Voltage column is omitted from input, preprocess_data must default to 220.0 without KeyError
        df_in = pd.DataFrame({
            'Clock': ["01/01/2026 00:15", "01/01/2026 00:30"],
            'kW_Import': ["100.5", "120.0"]
        })
        df_out = preprocess_data(df_in)
        self.assertEqual(len(df_out), 2)
        self.assertIn('Voltage', df_out.columns)
        self.assertTrue((df_out['Voltage'] == 220.0).all())
        self.assertEqual(df_out.iloc[0]['kW_Import'], 100.5)

    def test_preprocess_data_missing_kw_import_column(self):
        # When kW_Import column is omitted, preprocess_data must default kW_Import and kWh_15min to 0.0
        df_in = pd.DataFrame({
            'Clock': ["01/01/2026 00:15"],
            'Voltage': ["230.0"]
        })
        df_out = preprocess_data(df_in)
        self.assertEqual(len(df_out), 1)
        self.assertIn('kW_Import', df_out.columns)
        self.assertIn('kWh_15min', df_out.columns)
        self.assertEqual(df_out.iloc[0]['kW_Import'], 0.0)
        self.assertEqual(df_out.iloc[0]['kWh_15min'], 0.0)
        self.assertEqual(df_out.iloc[0]['Voltage'], 230.0)

    def test_preprocess_data_missing_clock_column(self):
        # When Clock column is omitted, preprocess_data must return an empty DataFrame with standard columns
        df_in = pd.DataFrame({
            'kW_Import': ["100.5"],
            'Voltage': ["220.0"]
        })
        df_out = preprocess_data(df_in)
        self.assertTrue(df_out.empty)
        expected_cols = ['Clock', 'kW_Import', 'Voltage', 'Date', 'Month', 'Time_Str', 'kWh_15min']
        for col in expected_cols:
            self.assertIn(col, df_out.columns)

    def test_preprocess_data_empty_input_returns_standard_columns(self):
        # Empty inputs (None, pd.DataFrame(), or empty with partial cols) must return standard schema
        expected_cols = ['Clock', 'kW_Import', 'Voltage', 'Date', 'Month', 'Time_Str', 'kWh_15min']
        for empty_input in [
            None,
            pd.DataFrame(),
            pd.DataFrame(columns=['Clock', 'kW_Import', 'Voltage']),
            pd.DataFrame(columns=['Clock']),
        ]:
            with self.subTest(inp=type(empty_input).__name__):
                res = preprocess_data(empty_input)
                self.assertTrue(res.empty)
                for col in expected_cols:
                    self.assertIn(col, res.columns)
                self.assertTrue(pd.api.types.is_datetime64_any_dtype(res['Clock']))
                self.assertTrue(pd.api.types.is_numeric_dtype(res['kW_Import']))
                self.assertTrue(pd.api.types.is_numeric_dtype(res['Voltage']))
                self.assertTrue(pd.api.types.is_datetime64_any_dtype(res['Date']))
                self.assertTrue(pd.api.types.is_numeric_dtype(res['kWh_15min']))

    def test_preprocess_data_all_invalid_clock_returns_standard_columns(self):
        # When all Clock rows are invalid or missing, resulting empty DataFrame must have standard schema
        df_in = pd.DataFrame({
            'Clock': ["invalid_date_1", "", None],
            'kW_Import': ["10.0", "20.0", "30.0"],
            'Voltage': ["220", "220", "220"]
        })
        df_out = preprocess_data(df_in)
        self.assertTrue(df_out.empty)
        expected_cols = ['Clock', 'kW_Import', 'Voltage', 'Date', 'Month', 'Time_Str', 'kWh_15min']
        for col in expected_cols:
            self.assertIn(col, df_out.columns)

    def test_preprocess_data_single_row(self):
        # Single row input must correctly compute all derived fields
        df_in = pd.DataFrame({
            'Clock': ["15/05/2026 14:30"],
            'kW_Import': ["80.0"],
            'Voltage': ["225.0"]
        })
        df_out = preprocess_data(df_in)
        self.assertEqual(len(df_out), 1)
        self.assertEqual(df_out.iloc[0]['Clock'], pd.Timestamp('2026-05-15 14:30:00'))
        self.assertEqual(df_out.iloc[0]['Date'], pd.Timestamp('2026-05-15'))
        self.assertEqual(df_out.iloc[0]['Month'], "2026-05")
        self.assertEqual(df_out.iloc[0]['Time_Str'], "14:30")
        self.assertEqual(df_out.iloc[0]['kW_Import'], 80.0)
        self.assertEqual(df_out.iloc[0]['kWh_15min'], 20.0)
        self.assertEqual(df_out.iloc[0]['Voltage'], 225.0)

    def test_get_usage_snapshots_missing_columns(self):
        # Incomplete DataFrame (missing kW_Import or Clock) must return empty list without KeyError
        self.assertEqual(get_usage_snapshots(pd.DataFrame({'Clock': [pd.Timestamp('2026-01-01')]})), [])
        self.assertEqual(get_usage_snapshots(pd.DataFrame({'kW_Import': [100.0]})), [])
        self.assertEqual(get_usage_snapshots(pd.DataFrame({'Voltage': [220.0]})), [])

    def test_parse_excel_df_unique_mapping_optimization_and_parity(self):
        # 1. AST check: ensure parse_excel_df uses unique() mapping optimization
        import ast
        handler_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data_handler.py'))
        with open(handler_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_unique_in_parse = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'parse_excel_df':
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == 'unique':
                        found_unique_in_parse = True
        self.assertTrue(found_unique_in_parse, "parse_excel_df must use unique() mapping optimization for candidate columns")

        # 2. Functional & Parity check: compare output with expected result using assert_frame_equal
        dates = pd.date_range("2026-01-01", periods=200, freq="15min")
        df_raw = pd.DataFrame([
            ["Meter Metadata Report", None, None, None],
            ["Date", "Time", "kW", "Voltage"],
        ] + [
            [d.strftime("%d/%m/%Y"), d.strftime("%H:%M"), "150.25", "220.0"] for d in dates
        ] + [
            ["01/01/2026", "Total", "50000.0", "220.0"],
            ["01/01/2026", "dnv/err", "0.0", "220.0"],
            ["Total", "", "50000.0", "220.0"],
        ])

        actual = parse_excel_df(df_raw)
        self.assertEqual(len(actual), 200)

        expected = pd.DataFrame({
            'Clock': [d.strftime("%d/%m/%Y %H:%M") for d in dates],
            'kW_Import': ["150.25"] * 200,
            'Voltage': ["220.0"] * 200
        })
        pd.testing.assert_frame_equal(actual, expected)

    def test_parse_text_lines_unique_mapping_optimization_and_parity(self):
        # 1. AST check: ensure parse_text_lines uses unique() mapping optimization
        import ast
        handler_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data_handler.py'))
        with open(handler_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_unique_in_parse = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'parse_text_lines':
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == 'unique':
                        found_unique_in_parse = True
        self.assertTrue(found_unique_in_parse, "parse_text_lines must use unique() mapping optimization for candidate columns")

        # 2. Functional & Parity check: compare output with expected result using assert_frame_equal
        dates = pd.date_range("2026-01-01", periods=200, freq="15min")
        lines = [
            "Meter Metadata Report\n",
            "Date,Time,kW,Voltage\n",
        ] + [
            f"{d.strftime('%d/%m/%Y')},{d.strftime('%H:%M')},150.25,220.0\n" for d in dates
        ] + [
            "01/01/2026,Total,50000.0,220.0\n",
            "01/01/2026,dnv/err,0.0,220.0\n",
            "Total,,50000.0,220.0\n",
        ]

        actual = parse_text_lines(iter(lines), delimiter=',')
        self.assertIsNotNone(actual)
        self.assertEqual(len(actual), 200)

        expected = pd.DataFrame({
            'Clock': [d.strftime("%d/%m/%Y %H:%M") for d in dates],
            'kW_Import': ["150.25"] * 200,
            'Voltage': ["220.0"] * 200
        })
        pd.testing.assert_frame_equal(actual, expected)

    def test_parse_excel_df_rejects_identical_clock_and_kw_columns(self):
        # A 1-column DataFrame where Clock and kW match the same unseparated text header must return None
        df_raw = pd.DataFrame([
            ["Date Clock kW_Import Voltage"],
            ["01/01/2026 00:15 100.5 220"]
        ])
        self.assertIsNone(parse_excel_df(df_raw), "parse_excel_df must return None when Clock and kW columns are identical")

    def test_parse_text_lines_rejects_identical_clock_and_kw_indices(self):
        # Text line where Clock and kW match the same single column must return None
        lines = [
            "Clock_kW_Import",
            "01/01/2026 00:15 100.5"
        ]
        self.assertIsNone(parse_text_lines(lines), "parse_text_lines must return None when Clock and kW resolve to same index")

    def test_load_file_tab_separated_txt_parsed_successfully(self):
        import io
        from data_handler import load_file
        content = b"Date\tClock\tkW_Import\tVoltage\n01/01/2026\t00:15\t100.5\t220.0\n01/01/2026\t00:30\t110.2\t221.0\n"
        buffer = io.BytesIO(content)
        df = load_file(buffer, "txt")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], "100.5")
        self.assertEqual(df.iloc[0]['Voltage'], "220.0")

        # Verify it successfully preprocesses into valid datetime load profile
        df_preprocessed = preprocess_data(df)
        self.assertEqual(len(df_preprocessed), 2)
        self.assertEqual(df_preprocessed.iloc[0]['Clock'], pd.Timestamp('2026-01-01 00:15:00'))
        self.assertEqual(df_preprocessed.iloc[0]['kW_Import'], 100.5)

    def test_load_file_space_separated_txt_parsed_successfully(self):
        import io
        from data_handler import load_file
        content = b"Date Clock kW_Import Voltage\n01/01/2026 00:15 100.5 220.0\n01/01/2026 00:30 110.2 221.0\n"
        buffer = io.BytesIO(content)
        df = load_file(buffer, "txt")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], "100.5")

        df_preprocessed = preprocess_data(df)
        self.assertEqual(len(df_preprocessed), 2)
        self.assertEqual(df_preprocessed.iloc[0]['Clock'], pd.Timestamp('2026-01-01 00:15:00'))

    def test_load_file_semicolon_separated_csv_parsed_successfully(self):
        import io
        from data_handler import load_file
        content = b"Date;Clock;kW_Import;Voltage\n01/01/2026;00:15;100.5;220.0\n01/01/2026;00:30;110.2;221.0\n"
        buffer = io.BytesIO(content)
        df = load_file(buffer, "csv")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 00:15")
        self.assertEqual(df.iloc[0]['kW_Import'], "100.5")

        df_preprocessed = preprocess_data(df)
        self.assertEqual(len(df_preprocessed), 2)
        self.assertEqual(df_preprocessed.iloc[0]['Clock'], pd.Timestamp('2026-01-01 00:15:00'))

    def test_load_file_tab_separated_csv_parsed_successfully(self):
        import io
        from data_handler import load_file
        content = b"Date\tClock\tkW_Import\tVoltage\n01/01/2026\t00:15\t100.5\t220.0\n01/01/2026\t00:30\t110.2\t221.0\n"
        buffer = io.BytesIO(content)
        df = load_file(buffer, "csv")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "01/01/2026 00:15")

        df_preprocessed = preprocess_data(df)
        self.assertEqual(len(df_preprocessed), 2)
        self.assertEqual(df_preprocessed.iloc[0]['Clock'], pd.Timestamp('2026-01-01 00:15:00'))


    def test_parse_excel_df_descriptive_date_column_preserves_multi_day_data(self):
        # When column header specifies date format like 'Date (DD/MM/YYYY)',
        # parse_excel_df must recognize it as the date column so multi-day data
        # is merged with time and not dropped by drop_duplicates in preprocess_data.
        df_raw = pd.DataFrame([
            ['Date (DD/MM/YYYY)', 'Time', 'kW', 'Voltage'],
            ['01/01/2026', '10:00', '100.0', '220.0'],
            ['01/01/2026', '10:15', '110.0', '220.0'],
            ['02/01/2026', '10:00', '120.0', '220.0'],
            ['02/01/2026', '10:15', '130.0', '220.0'],
            ['03/01/2026', '10:00', '140.0', '220.0'],
            ['03/01/2026', '10:15', '150.0', '220.0'],
        ])
        parsed = parse_excel_df(df_raw)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['Clock'].tolist(), [
            '01/01/2026 10:00', '01/01/2026 10:15',
            '02/01/2026 10:00', '02/01/2026 10:15',
            '03/01/2026 10:00', '03/01/2026 10:15'
        ])
        preprocessed = preprocess_data(parsed)
        self.assertEqual(len(preprocessed), 6, "All 6 readings across 3 distinct days must be preserved")
        self.assertEqual(preprocessed.iloc[0]['Clock'], pd.Timestamp('2026-01-01 10:00:00'))
        self.assertEqual(preprocessed.iloc[2]['Clock'], pd.Timestamp('2026-01-02 10:00:00'))
        self.assertEqual(preprocessed.iloc[4]['Clock'], pd.Timestamp('2026-01-03 10:00:00'))

    def test_parse_text_lines_descriptive_date_column_preserves_multi_day_data(self):
        # Verify parse_text_lines also handles 'Date (YYYY-MM-DD)' or 'Record Date'
        lines = [
            'Date (YYYY-MM-DD),Time,kW,Voltage',
            '2026-01-01,10:00,100.0,220.0',
            '2026-01-01,10:15,110.0,220.0',
            '2026-01-02,10:00,120.0,220.0',
            '2026-01-02,10:15,130.0,220.0',
        ]
        parsed = parse_text_lines(lines)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['Clock'].tolist(), [
            '2026-01-01 10:00', '2026-01-01 10:15',
            '2026-01-02 10:00', '2026-01-02 10:15'
        ])
        preprocessed = preprocess_data(parsed)
        self.assertEqual(len(preprocessed), 4)
        self.assertEqual(preprocessed.iloc[0]['Clock'], pd.Timestamp('2026-01-01 10:00:00'))
        self.assertEqual(preprocessed.iloc[2]['Clock'], pd.Timestamp('2026-01-02 10:00:00'))

    def test_parse_excel_df_thai_descriptive_date_column(self):
        # Thai header with date description: 'วันที่ (วว/ดด/ปปปป)'
        df_raw = pd.DataFrame([
            ['วันที่ (วว/ดด/ปปปป)', 'เวลา', 'กำลังไฟฟ้า (kW)', 'แรงดัน (V)'],
            ['01/01/2026', '10:00', '100.0', '220.0'],
            ['02/01/2026', '10:00', '120.0', '220.0'],
        ])
        parsed = parse_excel_df(df_raw)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['Clock'].tolist(), ['01/01/2026 10:00', '02/01/2026 10:00'])
        preprocessed = preprocess_data(parsed)
        self.assertEqual(len(preprocessed), 2)
        self.assertEqual(preprocessed.iloc[0]['Clock'], pd.Timestamp('2026-01-01 10:00:00'))
        self.assertEqual(preprocessed.iloc[1]['Clock'], pd.Timestamp('2026-01-02 10:00:00'))

    def test_parse_excel_df_datetime_combined_not_mistaken_for_date_only(self):
        # 'Date/Time' or 'DateTime' has both date and time, so it must map to clock_col, not date_col
        df_raw = pd.DataFrame([
            ['Date/Time', 'Active Power', 'Voltage'],
            ['2026-01-01 10:00', '100.0', '220.0'],
            ['2026-01-02 10:00', '120.0', '220.0'],
        ])
        parsed = parse_excel_df(df_raw)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['Clock'].tolist(), ['2026-01-01 10:00', '2026-01-02 10:00'])
        preprocessed = preprocess_data(parsed)
        self.assertEqual(len(preprocessed), 2)

    def test_load_file_csv_with_descriptive_date_header(self):
        import io
        from data_handler import load_file
        content = (
            b"Date (DD/MM/YYYY),Time,kW_Import,Voltage\n"
            b"01/01/2026,10:00,100.0,220.0\n"
            b"02/01/2026,10:00,120.0,220.0\n"
        )
        buffer = io.BytesIO(content)
        df = load_file(buffer, "csv")
        self.assertIsNotNone(df)
        self.assertEqual(df['Clock'].tolist(), ['01/01/2026 10:00', '02/01/2026 10:00'])
        preprocessed = preprocess_data(df)
        self.assertEqual(len(preprocessed), 2)
        self.assertEqual(preprocessed.iloc[0]['Clock'], pd.Timestamp('2026-01-01 10:00:00'))
        self.assertEqual(preprocessed.iloc[1]['Clock'], pd.Timestamp('2026-01-02 10:00:00'))


    def test_preprocess_data_fast_monotonic_sorting_optimization_and_parity(self):
        # 1. AST check: ensure preprocess_data checks strictly increasing order via np.diff or diff
        import ast
        handler_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data_handler.py'))
        with open(handler_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_diff_optimization = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'preprocess_data':
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute) and child.attr == 'diff':
                        found_diff_optimization = True
                        break
        self.assertTrue(
            found_diff_optimization,
            "preprocess_data must use fast diff check to bypass redundant lexsort on chronological data"
        )

        # 2. Functional & Parity checks across multiple datasets
        import data_handler
        def baseline_preprocess(df_in):
            df = df_in.copy()
            if df.empty:
                return data_handler._empty_preprocessed_df(df)
            if 'Clock' not in df.columns:
                return data_handler._empty_preprocessed_df(df)
            if 'kW_Import' not in df.columns:
                df['kW_Import'] = 0.0
            if 'Voltage' not in df.columns:
                df['Voltage'] = 220.0
            num_kw = pd.to_numeric(df['kW_Import'], errors='coerce')
            mask_kw = num_kw.isna()
            if mask_kw.any():
                clean_str_kw = df.loc[mask_kw, 'kW_Import'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
                num_kw.loc[mask_kw] = pd.to_numeric(clean_str_kw, errors='coerce')
            df['kW_Import'] = num_kw.fillna(0)
            num_v = pd.to_numeric(df['Voltage'], errors='coerce')
            mask_v = num_v.isna()
            if mask_v.any():
                clean_str_v = df.loc[mask_v, 'Voltage'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
                num_v.loc[mask_v] = pd.to_numeric(clean_str_v, errors='coerce')
            df['Voltage'] = num_v.fillna(220.0)
            df['Clock'] = data_handler.fast_parse_datetime(df['Clock'], dayfirst=True)
            df = df.dropna(subset=['Clock']).reset_index(drop=True)
            df = df.sort_values(['Clock', 'kW_Import'], ascending=[True, False])
            df = df.drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
            if df.empty:
                return data_handler._empty_preprocessed_df(df)
            df['Date'] = df['Clock'].dt.normalize()
            clock_dt = df['Clock'].dt
            ym = clock_dt.year * 100 + clock_dt.month
            ym_dict = {v: f'{v // 100:04d}-{v % 100:02d}' for v in ym.unique()}
            df['Month'] = ym.map(ym_dict)
            hm = clock_dt.hour * 60 + clock_dt.minute
            hm_dict = {v: f'{v // 60:02d}:{v % 60:02d}' for v in hm.unique()}
            df['Time_Str'] = hm.map(hm_dict)
            df['kWh_15min'] = df['kW_Import'] / 4.0
            return df

        np.random.seed(42)
        dates_a = pd.date_range("2026-01-01", periods=1000, freq="15min")
        df_a = pd.DataFrame({
            'Clock': dates_a,
            'kW_Import': np.random.uniform(10, 200, size=len(dates_a)).round(2),
            'Voltage': np.random.uniform(218, 222, size=len(dates_a)).round(1)
        })
        pd.testing.assert_frame_equal(preprocess_data(df_a), baseline_preprocess(df_a))

        df_b = df_a.sample(frac=1.0, random_state=42).reset_index(drop=True)
        pd.testing.assert_frame_equal(preprocess_data(df_b), baseline_preprocess(df_b))

        df_c = pd.DataFrame({
            'Clock': [
                pd.Timestamp('2026-01-01 00:00:00'),
                pd.Timestamp('2026-01-01 00:00:00'),
                pd.Timestamp('2026-01-01 00:15:00'),
                pd.Timestamp('2026-01-01 00:15:00'),
                pd.Timestamp('2026-01-01 00:30:00')
            ],
            'kW_Import': [10.0, 50.0, 100.0, 20.0, 30.0],
            'Voltage': [220.0, 221.0, 220.0, 220.0, 220.0]
        })
        pd.testing.assert_frame_equal(preprocess_data(df_c), baseline_preprocess(df_c))

        df_d = pd.DataFrame({
            'Clock': [d.strftime("%d/%m/%Y %H:%M") for d in dates_a[:100]],
            'kW_Import': ["150.5"] * 100,
            'Voltage': ["220.0"] * 100
        })
        pd.testing.assert_frame_equal(preprocess_data(df_d), baseline_preprocess(df_d))

    def test_sort_and_deduplicate_by_clock_fast_path_and_parity(self):
        import data_handler
        from unittest.mock import patch
        from pandas.testing import assert_frame_equal

        def baseline(df_in):
            return (
                df_in.sort_values(['Clock', 'kW_Import'], ascending=[True, False])
                .drop_duplicates(subset=['Clock'], keep='first')
                .reset_index(drop=True)
            )

        dates = pd.date_range('2026-01-01 00:00', periods=200, freq='15min')
        rng = np.random.default_rng(42)
        df_sorted = pd.DataFrame({
            'Clock': dates,
            'kW_Import': rng.uniform(10, 200, len(dates)),
            'Voltage': 220.0,
            'Month': dates.strftime('%Y-%m'),
        })

        expected_sorted = baseline(df_sorted)
        with patch.object(
            pd.DataFrame,
            'sort_values',
            side_effect=AssertionError('chronological data must bypass sort_values'),
        ):
            result_sorted = data_handler.sort_and_deduplicate_by_clock(df_sorted)
        assert_frame_equal(result_sorted, expected_sorted)

        df_unsorted = df_sorted.sample(frac=1.0, random_state=1).reset_index(drop=True)
        assert_frame_equal(
            data_handler.sort_and_deduplicate_by_clock(df_unsorted),
            baseline(df_unsorted),
        )

        df_duplicates = pd.DataFrame({
            'Clock': [dates[0], dates[0], dates[1], dates[1], dates[2]],
            'kW_Import': [10.0, 50.0, 100.0, 20.0, 30.0],
            'Voltage': [220.0, 221.0, 220.0, 220.0, 220.0],
        })
        assert_frame_equal(
            data_handler.sort_and_deduplicate_by_clock(df_duplicates),
            baseline(df_duplicates),
        )

        df_nat = pd.DataFrame({
            'Clock': [dates[0], dates[1], pd.NaT],
            'kW_Import': [10.0, 20.0, 30.0],
        })
        assert_frame_equal(
            data_handler.sort_and_deduplicate_by_clock(df_nat),
            baseline(df_nat),
        )

        df_non_range_index = df_sorted.iloc[::2]
        assert_frame_equal(
            data_handler.sort_and_deduplicate_by_clock(df_non_range_index),
            baseline(df_non_range_index),
        )

        df_string_clock = pd.DataFrame({
            'Clock': dates.strftime('%Y-%m-%d %H:%M:%S'),
            'kW_Import': np.arange(len(dates), dtype='float64'),
        })
        assert_frame_equal(
            data_handler.sort_and_deduplicate_by_clock(df_string_clock),
            baseline(df_string_clock),
        )

        df_single = df_sorted.iloc[[0]]
        assert_frame_equal(
            data_handler.sort_and_deduplicate_by_clock(df_single),
            baseline(df_single),
        )

        df_empty = pd.DataFrame(columns=['Clock', 'kW_Import'])
        assert_frame_equal(
            data_handler.sort_and_deduplicate_by_clock(df_empty),
            baseline(df_empty),
        )

    def test_fast_byte_reordering_datetime_parser_parity(self):
        """⚡ Bolt: Verify fast vectorized byte-reordering datetime parser matches pd.to_datetime exact parity."""
        from data_handler import fast_parse_datetime, preprocess_data

        dates = pd.date_range("2026-01-01 00:00", periods=200, freq="15min")

        # 1. 16-char DMY with slash and hyphen
        s_slash_16 = pd.Series([d.strftime("%d/%m/%Y %H:%M") for d in dates])
        s_hyphen_16 = pd.Series([d.strftime("%d-%m-%Y %H:%M") for d in dates])
        pd.testing.assert_series_equal(
            fast_parse_datetime(s_slash_16, dayfirst=True),
            pd.to_datetime(s_slash_16, format="%d/%m/%Y %H:%M", errors="coerce")
        )
        pd.testing.assert_series_equal(
            fast_parse_datetime(s_hyphen_16, dayfirst=True),
            pd.to_datetime(s_hyphen_16, format="%d-%m-%Y %H:%M", errors="coerce")
        )

        # 2. 19-char DMY with seconds
        s_slash_19 = pd.Series([d.strftime("%d/%m/%Y %H:%M:%S") for d in dates])
        s_hyphen_19 = pd.Series([d.strftime("%d-%m-%Y %H:%M:%S") for d in dates])
        pd.testing.assert_series_equal(
            fast_parse_datetime(s_slash_19, dayfirst=True),
            pd.to_datetime(s_slash_19, format="%d/%m/%Y %H:%M:%S", errors="coerce")
        )
        pd.testing.assert_series_equal(
            fast_parse_datetime(s_hyphen_19, dayfirst=True),
            pd.to_datetime(s_hyphen_19, format="%d-%m-%Y %H:%M:%S", errors="coerce")
        )

        # 3. Missing, null, and malformed entries
        s_mixed = pd.Series([
            "01/01/2026 00:00",
            None,
            "",
            "   ",
            np.nan,
            "corrupted_text",
            "31/02/2026 00:00",
            "01/01/2026 00:15",
            "01/01/2026 00:30"
        ], index=[10, 10, 20, 30, 40, 50, 60, 70, 80])
        expected_mixed = pd.to_datetime(s_mixed, dayfirst=True, errors="coerce", format="mixed")
        actual_mixed = fast_parse_datetime(s_mixed, dayfirst=True)
        pd.testing.assert_series_equal(actual_mixed, expected_mixed)

        # 4. Full DataFrame comparison through preprocess_data
        df_input = pd.DataFrame({
            'Clock': [d.strftime("%d/%m/%Y %H:%M") for d in dates[:50]] + ["invalid", None] + [d.strftime("%d/%m/%Y %H:%M") for d in dates[52:100]],
            'kW_Import': [f"{100 + i * 0.5:.2f}" for i in range(100)],
            'Voltage': ["220.0"] * 100
        })
        # Baseline using standard format='mixed'
        df_base = df_input.copy()
        df_base['kW_Import'] = pd.to_numeric(df_base['kW_Import'], errors='coerce').fillna(0.0)
        df_base['Voltage'] = pd.to_numeric(df_base['Voltage'], errors='coerce').fillna(220.0)
        df_base['Clock'] = pd.to_datetime(df_base['Clock'], dayfirst=True, errors='coerce', format='mixed')
        df_base = df_base.dropna(subset=['Clock']).reset_index(drop=True)
        df_base['Date'] = df_base['Clock'].dt.normalize()
        c_dt = df_base['Clock'].dt
        ym = c_dt.year * 100 + c_dt.month
        ym_dict = {v: f'{v // 100:04d}-{v % 100:02d}' for v in ym.unique()}
        df_base['Month'] = ym.map(ym_dict)
        hm = c_dt.hour * 60 + c_dt.minute
        hm_dict = {v: f'{v // 60:02d}:{v % 60:02d}' for v in hm.unique()}
        df_base['Time_Str'] = hm.map(hm_dict)
        df_base['kWh_15min'] = df_base['kW_Import'] / 4.0

        df_out = preprocess_data(df_input)
        pd.testing.assert_frame_equal(df_out, df_base)


    def test_fast_parse_datetime_leading_empty_and_null_samples(self):
        # ⚡ Bolt: first-format detection must skip empty/whitespace/null leading values
        # after replacing the full-Series dropna() copy with a notna() count.
        from data_handler import fast_parse_datetime

        s = pd.Series([
            "", "   ", None, np.nan,
            "01/01/2026 00:00", "01/01/2026 00:15", "invalid", None,
            "01/01/2026 00:45",
        ])
        expected = pd.to_datetime(s, dayfirst=True, errors='coerce', format='mixed')
        actual = fast_parse_datetime(s, dayfirst=True)
        pd.testing.assert_series_equal(actual, expected)

    def test_fast_parse_datetime_dayfirst_false_parity(self):
        """Ensure fast_parse_datetime respects dayfirst=False for MM/DD/YYYY formats without month-day transposition."""
        from data_handler import fast_parse_datetime

        # 1. 16-char MM/DD/YYYY and MM-DD-YYYY
        s_slash_16 = pd.Series(['03/05/2026 10:00', '12/01/2026 23:45'])
        expected_slash_16 = pd.to_datetime(s_slash_16, format='%m/%d/%Y %H:%M', errors='coerce')
        actual_slash_16 = fast_parse_datetime(s_slash_16, dayfirst=False)
        self.assertEqual(actual_slash_16.iloc[0], pd.Timestamp('2026-03-05 10:00:00'))
        self.assertEqual(actual_slash_16.iloc[1], pd.Timestamp('2026-12-01 23:45:00'))
        pd.testing.assert_series_equal(actual_slash_16, expected_slash_16)

        s_hyphen_16 = pd.Series(['03-05-2026 10:00', '12-01-2026 23:45'])
        expected_hyphen_16 = pd.to_datetime(s_hyphen_16, format='%m-%d-%Y %H:%M', errors='coerce')
        actual_hyphen_16 = fast_parse_datetime(s_hyphen_16, dayfirst=False)
        self.assertEqual(actual_hyphen_16.iloc[0], pd.Timestamp('2026-03-05 10:00:00'))
        self.assertEqual(actual_hyphen_16.iloc[1], pd.Timestamp('2026-12-01 23:45:00'))
        pd.testing.assert_series_equal(actual_hyphen_16, expected_hyphen_16)

        # 2. 19-char MM/DD/YYYY and MM-DD-YYYY with seconds
        s_slash_19 = pd.Series(['03/05/2026 10:00:00', '12/01/2026 23:45:30'])
        expected_slash_19 = pd.to_datetime(s_slash_19, format='%m/%d/%Y %H:%M:%S', errors='coerce')
        actual_slash_19 = fast_parse_datetime(s_slash_19, dayfirst=False)
        self.assertEqual(actual_slash_19.iloc[0], pd.Timestamp('2026-03-05 10:00:00'))
        pd.testing.assert_series_equal(actual_slash_19, expected_slash_19)

        s_hyphen_19 = pd.Series(['03-05-2026 10:00:00', '12-01-2026 23:45:30'])
        expected_hyphen_19 = pd.to_datetime(s_hyphen_19, format='%m-%d-%Y %H:%M:%S', errors='coerce')
        actual_hyphen_19 = fast_parse_datetime(s_hyphen_19, dayfirst=False)
        self.assertEqual(actual_hyphen_19.iloc[0], pd.Timestamp('2026-03-05 10:00:00'))
        pd.testing.assert_series_equal(actual_hyphen_19, expected_hyphen_19)

        # 3. Date-only candidate path (e.g. MM/DD/YYYY without time)
        s_date_only = pd.Series(['03/05/2026', '12/01/2026'])
        expected_date_only = pd.to_datetime(s_date_only, format='%m/%d/%Y', errors='coerce')
        actual_date_only = fast_parse_datetime(s_date_only, dayfirst=False)
        self.assertEqual(actual_date_only.iloc[0], pd.Timestamp('2026-03-05'))
        pd.testing.assert_series_equal(actual_date_only, expected_date_only)

        # 4. Mixed valid, invalid, and missing values with dayfirst=False
        s_mixed = pd.Series(['03/05/2026 10:00', None, '', 'invalid_text', '12/01/2026 23:45'])
        expected_mixed = pd.to_datetime(s_mixed, dayfirst=False, errors='coerce', format='mixed')
        actual_mixed = fast_parse_datetime(s_mixed, dayfirst=False)
        pd.testing.assert_series_equal(actual_mixed, expected_mixed)

    def test_fast_parse_datetime_mixed_second_precision_preserves_seconds(self):
        """Mixed 16-char (no seconds) and 19/23-char (seconds/fraction) rows must not be truncated."""
        from data_handler import fast_parse_datetime

        s_no_seconds_first = pd.Series([
            '01/02/2023 00:15',
            '01/02/2023 00:15:30',
            '01/02/2023 00:15:30.500',
            '01/02/2023 00:30',
        ])
        for dayfirst in (True, False):
            with self.subTest(dayfirst=dayfirst, case='16-first'):
                expected = pd.to_datetime(s_no_seconds_first, dayfirst=dayfirst, errors='coerce', format='mixed')
                actual = fast_parse_datetime(s_no_seconds_first, dayfirst=dayfirst)
                pd.testing.assert_series_equal(actual, expected)

        s_seconds_first = pd.Series([
            '01/02/2023 00:15:30',
            '01/02/2023 00:15:30.500',
            '01/02/2023 00:15',
            '01/02/2023 00:30:45',
        ])
        for dayfirst in (True, False):
            with self.subTest(dayfirst=dayfirst, case='19-first'):
                expected = pd.to_datetime(s_seconds_first, dayfirst=dayfirst, errors='coerce', format='mixed')
                actual = fast_parse_datetime(s_seconds_first, dayfirst=dayfirst)
                pd.testing.assert_series_equal(actual, expected)

    def test_preprocess_data_mixed_second_precision_does_not_drop_rows(self):
        """Rows from the same minute with and without seconds must stay distinct (no silent dedup/data loss)."""
        df_in = pd.DataFrame({
            'Clock': ['01/02/2023 00:15', '01/02/2023 00:15:30', '01/02/2023 00:30'],
            'kW_Import': ['100', '150', '200'],
            'Voltage': ['220', '220', '220'],
        })

        df_out = preprocess_data(df_in)

        self.assertEqual(len(df_out), 3, 'distinct timestamps must not collapse into one row')
        self.assertEqual(
            df_out['Clock'].tolist(),
            [pd.Timestamp('2023-02-01 00:15:00'),
             pd.Timestamp('2023-02-01 00:15:30'),
             pd.Timestamp('2023-02-01 00:30:00')]
        )


    def test_parse_excel_df_high_cardinality_clock_first_byte_gating_parity(self):
        """⚡ Bolt: high-cardinality clock columns must validate via a first-byte gate, not full-series regex."""
        import ast
        handler_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data_handler.py'))
        with open(handler_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_byte_gate = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'parse_excel_df':
                has_view = any(
                    isinstance(child, ast.Attribute) and child.attr == 'view'
                    for child in ast.walk(node)
                )
                has_s19 = any(
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == 'to_numpy'
                    and any(
                        kw.arg == 'dtype'
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value == 'S19'
                        for kw in child.keywords
                    )
                    for child in ast.walk(node)
                )
                if has_view and has_s19:
                    found_byte_gate = True
        self.assertTrue(
            found_byte_gate,
            "parse_excel_df must use a vectorized first-byte gate for high-cardinality clock columns"
        )

        # High-cardinality clock column (every timestamp unique) mixed with footer/summary rows.
        valid_clocks = [f"01/01/2026 {h:02d}:{m:02d}:{s:02d}" for h in range(24) for m in range(0, 60, 2) for s in (0, 30)]
        valid_clocks = valid_clocks[:1000]
        rows = [[c, "100.5", "220.0"] for c in valid_clocks]
        invalid_rows = [
            ["TOTAL 5", "1", "220"],
            ["p", "1", "220"],
            ["OP", "1", "220"],
            ["h", "1", "220"],
            ["kWh", "1", "220"],
            ["NaN", "1", "220"],
            ["DNV/ERR", "1", "220"],
            ["   total 9", "1", "220"],
            ["", "1", "220"],
            [None, "1", "220"],
        ]
        # Non-ASCII text and letter-prefixed text do not match the footer regex and stay valid.
        extra_valid = [["ปกติ", "1", "220"], ["ABC123", "1", "220"]]

        raw_rows = rows + invalid_rows + extra_valid
        df_raw = pd.DataFrame([["Clock", "kW_Import", "Voltage"]] + raw_rows)

        actual = parse_excel_df(df_raw)
        expected = pd.DataFrame({
            'Clock': valid_clocks + ["ปกติ", "ABC123"],
            'kW_Import': ["100.5"] * len(valid_clocks) + ["1", "1"],
            'Voltage': ["220.0"] * len(valid_clocks) + ["220", "220"],
        })
        pd.testing.assert_frame_equal(actual, expected)


class TestSafeErrorReason(unittest.TestCase):
    """UI ต้องแสดงเฉพาะข้อความที่เราควบคุมเอง ไม่ใช่ str(e) ดิบของ exception ภายนอก"""

    def test_upload_validation_error_keeps_our_own_message(self):
        from data_handler import UploadValidationError, safe_error_reason
        # ยังคงเป็น ValueError เพื่อความเข้ากันได้กับผู้เรียกเดิม
        exc = UploadValidationError("ขนาดไฟล์เกินกำหนด (สูงสุด 50 MB)")
        self.assertIsInstance(exc, ValueError)
        self.assertEqual(safe_error_reason(exc), "ขนาดไฟล์เกินกำหนด (สูงสุด 50 MB)")

    def test_external_exception_text_is_never_revealed(self):
        from data_handler import safe_error_reason, GENERIC_LOAD_ERROR_REASON
        leaked = ValueError("Failed to read C:\\Users\\admin\\secret\\payroll.xlsx\nTraceback (most recent call last)")
        reason = safe_error_reason(leaked)
        self.assertEqual(reason, GENERIC_LOAD_ERROR_REASON)
        self.assertNotIn("secret", reason)
        self.assertNotIn("Traceback", reason)

        # exception ที่ไม่ใช่ ValueError ก็ต้องถูกปิดเช่นกัน
        reason = safe_error_reason(OSError("/srv/app/internal/config.ini"))
        self.assertEqual(reason, GENERIC_LOAD_ERROR_REASON)
        self.assertNotIn("/srv", reason)

    def test_empty_upload_validation_message_falls_back_to_generic(self):
        from data_handler import UploadValidationError, safe_error_reason, GENERIC_LOAD_ERROR_REASON
        self.assertEqual(safe_error_reason(UploadValidationError("   ")), GENERIC_LOAD_ERROR_REASON)
        self.assertEqual(safe_error_reason(None), GENERIC_LOAD_ERROR_REASON)

    def test_upload_validation_message_is_length_bounded(self):
        from data_handler import UploadValidationError, safe_error_reason, MAX_ERROR_REASON_LENGTH
        reason = safe_error_reason(UploadValidationError("x" * 5000))
        self.assertEqual(len(reason), MAX_ERROR_REASON_LENGTH)

    def test_load_file_validation_failures_use_upload_validation_error(self):
        import io
        from data_handler import load_file, UploadValidationError

        with self.assertRaises(UploadValidationError):
            load_file(io.BytesIO(b"Clock,kW_Import,Voltage\n01/01/2026 00:00,100,220\n"), "exe")

        with self.assertRaises(UploadValidationError):
            load_file(io.BytesIO(b"hello,world\nfoo,bar\nbaz,qux\n"), "csv")

        class OversizedFile(io.BytesIO):
            def __init__(self):
                super().__init__(b"Clock,kW_Import,Voltage\n01/01/2026 00:00,100,220\n")
                self.size = 51 * 1024 * 1024

        with self.assertRaises(UploadValidationError):
            load_file(OversizedFile(), "csv")


class TestDataHandlerEdgeCases(unittest.TestCase):

    def test_sort_and_deduplicate_by_clock_none_and_empty(self):
        """sort_and_deduplicate_by_clock must handle None and empty DataFrame safely without raising."""
        from data_handler import sort_and_deduplicate_by_clock
        self.assertIsNone(sort_and_deduplicate_by_clock(None))

        empty_df = pd.DataFrame()
        res_empty = sort_and_deduplicate_by_clock(empty_df)
        self.assertIsInstance(res_empty, pd.DataFrame)
        self.assertTrue(res_empty.empty)

    def test_sort_and_deduplicate_by_clock_missing_columns(self):
        """sort_and_deduplicate_by_clock must handle missing Clock or kW_Import columns gracefully."""
        from data_handler import sort_and_deduplicate_by_clock
        # Missing kW_Import: sort and deduplicate by Clock only
        dates = pd.to_datetime(['2026-01-01 00:15', '2026-01-01 00:00', '2026-01-01 00:15'])
        df_clock_only = pd.DataFrame({'Clock': dates, 'Voltage': [220, 221, 222]})
        res_clock_only = sort_and_deduplicate_by_clock(df_clock_only)
        self.assertEqual(len(res_clock_only), 2)
        self.assertEqual(res_clock_only['Clock'].tolist(), [pd.Timestamp('2026-01-01 00:00'), pd.Timestamp('2026-01-01 00:15')])

        # Missing Clock: cannot sort/deduplicate by Clock, return copy without KeyError
        df_no_clock = pd.DataFrame({'kW_Import': [10.0, 20.0]})
        res_no_clock = sort_and_deduplicate_by_clock(df_no_clock)
        self.assertEqual(len(res_no_clock), 2)
        self.assertNotIn('Clock', res_no_clock.columns)

    def test_get_usage_snapshots_string_and_non_numeric_kw(self):
        """get_usage_snapshots must handle string or object kW_Import without raising TypeError."""
        df_str_kw = pd.DataFrame({
            'Clock': pd.date_range('2026-01-01 00:00', periods=5, freq='15min'),
            'kW_Import': ['0.0', '15.5', '20.0', '0.0', '0.0']
        })
        snapshots = get_usage_snapshots(df_str_kw)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['start_idx'], 0)
        self.assertEqual(snapshots[0]['end_idx'], 3)

    def test_get_usage_snapshots_nat_clock_formatting(self):
        """get_usage_snapshots must format NaT timestamps as 'NaT' instead of corrupted '//T 00:00'."""
        df_nat = pd.DataFrame({
            'Clock': [pd.NaT, pd.NaT],
            'kW_Import': [10.0, 0.0]
        })
        snapshots = get_usage_snapshots(df_nat)
        self.assertEqual(len(snapshots), 1)
        self.assertNotIn('//T', snapshots[0]['label'])
        self.assertIn('NaT', snapshots[0]['label'])


    def test_parse_text_lines_tab_separated_with_comma_in_header(self):
        """parse_text_lines must correctly detect tab delimiter when column header contains comma."""
        lines = [
            "Date\tTime\tActive Power, kW\tVoltage\n",
            "2026-01-01\t10:00\t150.5\t220.0\n",
            "2026-01-01\t10:15\t160.0\t220.0\n",
        ]
        df = parse_text_lines(lines)
        self.assertIsNotNone(df, "parse_text_lines should not return None for tab-separated data with comma in header")
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "2026-01-01 10:00")
        self.assertEqual(df.iloc[0]['kW_Import'], "150.5")

    def test_parse_text_lines_semicolon_separated_with_comma_in_header(self):
        """parse_text_lines must correctly detect semicolon delimiter when column header contains comma."""
        lines = [
            "Date;Time;Active Power, kW;Voltage\n",
            "2026-01-01;10:00;150.5;220.0\n",
            "2026-01-01;10:15;160.0;220.0\n",
        ]
        df = parse_text_lines(lines)
        self.assertIsNotNone(df, "parse_text_lines should not return None for semicolon-separated data with comma in header")
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "2026-01-01 10:00")
        self.assertEqual(df.iloc[0]['kW_Import'], "150.5")

    def test_load_file_tab_separated_with_comma_in_header_succeeds(self):
        """load_file must successfully parse tab-separated txt/csv files when header contains commas."""
        import io
        from data_handler import load_file
        content = b"Date\tTime\tActive Power, kW\tVoltage\n2026-01-01\t10:00\t150.5\t220.0\n2026-01-01\t10:15\t160.0\t220.0\n"
        df = load_file(io.BytesIO(content), "txt")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "2026-01-01 10:00")

    def test_load_file_semicolon_separated_with_comma_in_header_succeeds(self):
        """load_file must successfully parse semicolon-separated csv files when header contains commas."""
        import io
        from data_handler import load_file
        content = b"Date;Time;Active Power, kW;Voltage\n2026-01-01;10:00;150.5;220.0\n2026-01-01;10:15;160.0;220.0\n"
        df = load_file(io.BytesIO(content), "csv")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['Clock'], "2026-01-01 10:00")


if __name__ == '__main__':
    unittest.main()
