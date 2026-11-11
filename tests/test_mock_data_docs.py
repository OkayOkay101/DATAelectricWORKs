import unittest
from pathlib import Path


DOC = Path(__file__).resolve().parents[1] / 'docs' / 'GETTING_STARTED_TH.md'


class MockDataDocumentationTests(unittest.TestCase):
    def test_quickstart_lists_only_generated_formats(self):
        documentation = DOC.read_text(encoding='utf-8')

        self.assertIn('`.csv`, `.xlsx`, และ `.txt`', documentation)
        self.assertNotIn('`.xls`', documentation)


if __name__ == '__main__':
    unittest.main()
