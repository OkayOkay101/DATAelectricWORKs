"""Self-tests use a disposable synthetic repository, never production bugs."""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / '.github' / 'quality'
if not ADAPTER.is_dir():
    ADAPTER = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('quality_runner', ADAPTER / 'runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def test_mutation_changes_source_without_execution(self):
        source = 'def plus(a, b):\n return a + b\n'
        self.assertTrue(any('a - b' in value for value in runner.mutations(source)))

    def test_import_error_does_not_prove_red(self):
        green = {'exit_code': 0, 'test_count': 1, 'test_ids': ['test'], 'skipped_count': 0, 'errors': 0}
        red = {**green, 'exit_code': 1, 'errors': 1, 'failures': 0}
        self.assertEqual(runner.assess('bug', red, green, None)['status'], 'BLOCKED')

    def test_target_report_is_not_accepted_as_phase_output(self):
        self.assertEqual(runner.read_phase_output('{"status":"PASSED"}', 0)['test_count'], 0)

    def test_container_has_no_host_report_mount(self):
        command = runner.container_command('image', Path('/snapshot'), Path('/driver.py'), [])
        self.assertNotIn('quality-report.json', ' '.join(command))
        self.assertIn('--network=none', command)

    @unittest.skipUnless(shutil.which('docker'), 'Docker required: verify on GitHub CI before activation')
    def test_real_container_red_green_and_report_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL).decode().strip()
            git('init')
            (repo / 'calc.py').write_text('def plus(a,b):\n return a - b\n')
            (repo / 'requirements-test.txt').write_text('')
            git('add', '.')
            git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'base')
            base = git('rev-parse', 'HEAD')
            (repo / 'calc.py').write_text('def plus(a,b):\n return a + b\n')
            (repo / 'tests').mkdir()
            (repo / 'tests/test_calc.py').write_text('import unittest, os\nfrom pathlib import Path\nfrom calc import plus\n'
                'class Case(unittest.TestCase):\n def test_add(self):\n  self.assertEqual(plus(2,3),5)\n'
                ' def test_host_report_and_credentials_are_inaccessible(self):\n'
                '  self.assertNotIn("GITHUB_TOKEN", os.environ)\n'
                '  self.assertNotIn("QUALITY_REQUEST", os.environ)\n'
                '  with self.assertRaises(OSError): Path("/reports/quality-report.json").write_text("forged")\n'
                '  with self.assertRaises(OSError): Path("/workspace/quality-report.json").write_text("forged")\n')
            git('add', '.')
            git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'candidate')
            head = git('rev-parse', 'HEAD')
            request = {'repository_id': 1, 'task_id': 'fixture', 'attempt_id': 'one', 'operation': 'fixture',
                'base_sha': base, 'subject_head_sha': head, 'workflow_revision': head,
                'profile_version': 'python-unittest-v2',
                'members': [{'task_id': 'fixture', 'kind': 'bug', 'paths': ['calc.py', 'tests/test_calc.py']}]}
            profile = json.loads((ADAPTER / 'profile.json').read_text())
            results, _ = runner.execute(repo, request, profile)
            self.assertEqual(results[0]['status'], 'PASSED')
            self.assertEqual(results[0]['red_exit_code'], 1)
            self.assertEqual(results[0]['green_exit_code'], 0)
            # Test-only work must kill a mutation, then re-run restored source.
            request['members'][0]['kind'] = 'test'
            results, _ = runner.execute(repo, request, profile)
            self.assertEqual(results[0]['sensitivity_result'], 'killed')
            self.assertTrue(results[0]['mutation_restored'])
            self.assertFalse((repo / 'quality-report.json').exists())


if __name__ == '__main__':
    unittest.main()
