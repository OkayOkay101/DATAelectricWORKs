import unittest
from pathlib import Path


DOC = Path(__file__).resolve().parents[1] / 'docs' / 'FUNCTIONAL_TESTS_TH.md'


class FunctionalTestDocumentationTests(unittest.TestCase):
    def test_does_not_claim_unconfigured_ci_workflow_runs(self):
        documentation = DOC.read_text(encoding='utf-8')

        self.assertIn('ยังไม่มี workflow CI', documentation)
        self.assertNotIn(
            'CI ชื่อ `python-functional` รันบน push/pull_request',
            documentation,
        )


if __name__ == '__main__':
    unittest.main()
