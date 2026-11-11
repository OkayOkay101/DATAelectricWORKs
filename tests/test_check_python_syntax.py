import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'check_python_syntax.py'
spec = importlib.util.spec_from_file_location('check_python_syntax', SCRIPT)
syntax_checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(syntax_checker)


class CheckPythonSyntaxTests(unittest.TestCase):
    def test_parses_only_git_tracked_python_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'tracked.py').write_text('value = 1\n')
            (root / 'untracked.py').write_text('this is not valid python!\n')
            output = io.StringIO()
            with patch.object(syntax_checker.subprocess, 'check_output',
                              return_value=b'tracked.py\0') as check_output, \
                    contextlib.redirect_stdout(output):
                old_directory = os.getcwd()
                try:
                    os.chdir(root)
                    syntax_checker.main()
                finally:
                    os.chdir(old_directory)

        self.assertEqual(output.getvalue(), 'Syntax passed: 1 Python files.\n')
        check_output.assert_called_once_with(
            ['git', 'ls-files', '-z', '--', '*.py'])

    def test_rejects_invalid_tracked_python_syntax(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'broken.py').write_text('def incomplete(:\n')
            with patch.object(syntax_checker.subprocess, 'check_output',
                              return_value=b'broken.py\0'):
                old_directory = os.getcwd()
                try:
                    os.chdir(root)
                    with self.assertRaises(SyntaxError):
                        syntax_checker.main()
                finally:
                    os.chdir(old_directory)


if __name__ == '__main__':
    unittest.main()
