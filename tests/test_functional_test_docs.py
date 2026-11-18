import unittest
from pathlib import Path


DOC = Path(__file__).resolve().parents[1] / 'docs' / 'FUNCTIONAL_TESTS_TH.md'


class FunctionalTestDocumentationTests(unittest.TestCase):
    def test_documents_existing_python_functional_workflow(self):
        documentation = DOC.read_text(encoding='utf-8')

        self.assertNotIn('ยังไม่มี workflow CI', documentation)
        self.assertIn('`.github/workflows/python-functional.yml`', documentation)
        self.assertIn('push', documentation)
        self.assertIn('pull_request', documentation)


if __name__ == '__main__':
    unittest.main()
