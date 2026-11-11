import os
import re
import sys
import unittest
from zipfile import ZipFile
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from generate_mock_data import generate_mock_data


class TestMockDataTimestamps(unittest.TestCase):
    timestamp_pattern = re.compile(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_mock_csv_and_text_use_iso_8601_timestamps(self):
        for filename in ("mock_dataset.csv", "mock_dataset.txt"):
            with self.subTest(filename=filename):
                dataset = pd.read_csv(os.path.join("mock_data", filename))
                self.assertTrue(
                    dataset["Clock"].str.fullmatch(
                        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
                    ).all()
                )

    def test_mock_spreadsheets_use_iso_8601_timestamps(self):
        with ZipFile(os.path.join("mock_data", "mock_dataset.xlsx")) as workbook:
            sheet = workbook.read("xl/worksheets/sheet1.xml")
        self.assertEqual(len(self.timestamp_pattern.findall(sheet)), 192)

    @patch("pandas.DataFrame.to_csv", autospec=True)
    @patch("pandas.DataFrame.to_excel", autospec=True)
    @patch("os.makedirs")
    def test_generated_datasets_use_iso_8601_timestamps(
        self, _mock_makedirs, _mock_to_excel, mock_to_csv
    ):
        generated_frames = []
        mock_to_csv.side_effect = lambda frame, *args, **kwargs: generated_frames.append(frame.copy())

        generate_mock_data()

        self.assertEqual(len(generated_frames), 2)
        for frame in generated_frames:
            self.assertTrue(
                frame["Clock"].str.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
                ).all()
            )


if __name__ == "__main__":
    unittest.main()
