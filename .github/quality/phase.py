"""Runs only inside the disposable target container; stdout is untrusted data."""
import hashlib
import importlib.util
import json
import sys
import unittest


def main():
    selectors = json.loads(sys.argv[1])
    sys.path.insert(0, '/workspace')
    suite = unittest.TestSuite()
    for entry in selectors:
        name = 'quality_' + hashlib.sha256(entry['path'].encode()).hexdigest()[:12]
        spec = importlib.util.spec_from_file_location(name, '/workspace/' + entry['path'])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(entry['selector'], module))
    ids = []
    def collect(tests):
        for test in tests:
            if isinstance(test, unittest.TestSuite):
                collect(test)
            else:
                ids.append(test.id())
    collect(suite)
    # Docker multiplexes stdout/stderr and can splice progress into the JSON
    # marker (FQUALITY_RESULT=...). Keep ordered runner output on one stream.
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
    print('QUALITY_RESULT=' + json.dumps({'test_ids': ids, 'test_count': result.testsRun,
        'skipped_count': len(result.skipped), 'failures': len(result.failures), 'errors': len(result.errors)}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        # Import/setup errors never become a red behavioral proof.
        print('QUALITY_RESULT=' + json.dumps({'test_ids': [], 'test_count': 0, 'skipped_count': 0,
                                              'failures': 0, 'errors': 1}))
        sys.exit(2)
