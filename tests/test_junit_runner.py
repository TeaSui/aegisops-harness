"""tests/junit_runner.py writes a report the lifecycle engine can read (this repository's pinned verify command)."""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / 'plugins' / 'aegisops-harness'
RUNNER = ROOT / 'tests' / 'junit_runner.py'
SPEC = importlib.util.spec_from_file_location('junit_runner_aidlc', PLUGIN / 'scripts' / 'aidlc.py')
aidlc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aidlc)

CASES = '''
    import unittest


    class Sample(unittest.TestCase):
        def test_eta_1_passes(self):
            self.assertTrue(True)

        def test_eta_2_fails(self):
            self.assertEqual(1, 2)

        @unittest.skip('later')
        def test_eta_3_is_skipped(self):
            pass

        def test_eta_4_subtest_fails(self):
            for value in (1, 2):
                with self.subTest(value=value):
                    self.assertEqual(value, 1)
'''


class JunitRunnerTest(unittest.TestCase):
    def run_runner(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text))
        result = subprocess.run([sys.executable, str(RUNNER), '-s', 'tests', '-o', 'out/junit.xml'], cwd=root,
                                capture_output=True, text=True, timeout=60,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        return result, root

    def test_report_is_read_by_the_engine_story_by_story(self):
        result, root = self.run_runner({'tests/test_sample.py': CASES})
        self.assertEqual(result.returncode, 1, result.stderr)
        ids = ['ETA-1', 'ETA-2', 'ETA-3', 'ETA-4']
        summary, problems = aidlc.parse_junit([root / 'out' / 'junit.xml'], ids, aidlc.Repo(root))
        self.assertEqual(problems, [])
        self.assertEqual(summary['req_pass'], ['ETA-1'])           # skipped is not passed
        self.assertEqual(summary['req_fail'], ['ETA-2', 'ETA-4'])
        self.assertEqual((summary['passed'], summary['failed']), (1, 2))

    def test_all_green_exits_zero_and_a_broken_module_is_an_error(self):
        result, root = self.run_runner({'tests/test_ok.py': 'import unittest\n\n\nclass T(unittest.TestCase):\n'
                                                            '    def test_fine(self):\n        pass\n'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('testcase', (root / 'out' / 'junit.xml').read_text())
        result, root = self.run_runner({'tests/test_broken.py': 'import nothing_like_this\n'})
        self.assertEqual(result.returncode, 1)
        summary, _ = aidlc.parse_junit([root / 'out' / 'junit.xml'], [], aidlc.Repo(root))
        self.assertEqual(summary['failed'], 1)

    def test_no_test_at_all_is_not_a_green_run(self):
        result, _ = self.run_runner({'tests/helper.py': 'x = 1\n'})
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
