import unittest
from pathlib import Path


DOC = Path(__file__).resolve().parents[1] / '.jules' / 'bolt.md'


class BoltMonotonicCheckDocumentationTests(unittest.TestCase):
    def test_monotonic_check_example_uses_numpy_all(self):
        documentation = DOC.read_text(encoding='utf-8')

        self.assertIn('np.all(np.diff(ns) > 0)', documentation)
        self.assertNotRegex(documentation, r'\bp\.all\(np\.diff\(ns\) > 0\)')


if __name__ == '__main__':
    unittest.main()
