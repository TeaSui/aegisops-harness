"""The harder lifecycle eval cases (ETA-11): brownfield fee, storage migration, concurrent transfers.

A hidden check is only worth its name when it tells right from wrong, so for every case:
  * the fixture ships green (its own tests pass) and FAILS the hidden check as shipped;
  * a reference solution (tests/eval_reference/<variant>/, copied over the fixture) passes every hidden check and
    keeps the tests green;
  * plausible wrong solutions fail the check that names their defect.
Needs node (no npm, no model call). Run: python3 -m unittest tests.test_eval_cases -v
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEADLESS = ROOT / 'evals' / 'headless'
SUITE = HEADLESS / 'suites' / 'lifecycle'
REFERENCE = pathlib.Path(__file__).resolve().parent / 'eval_reference'
NODE = shutil.which('node')
sys.path[:0] = [str(HEADLESS), str(HEADLESS / 'fixtures')]
GIT_ENV = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com'}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = load(SUITE / 'fixture.py', 'eval_cases_lifecycle_fixture')
aidlc = load(ROOT / 'scripts' / 'aidlc.py', 'eval_cases_aidlc')
CASES = {case['id']: case for case in (json.loads(line) for line in (SUITE / 'cases.jsonl').read_text().splitlines()
                                       if line.startswith('{'))}
HARDER = {'L4-brownfield-fee': 'brownfield', 'L5-storage-migration': 'migration', 'L6-concurrent-transfers': 'concurrency'}

# Wrong solutions a session could plausibly hand in: (text in the reference file, replacement, the check that must fail).
WRONG = {
    'brownfield': [
        ('src/fees.js', 'Math.floor((cents + 50) / 100)', 'Math.floor(cents / 100)', 'fee_quote'),              # rounds down
        ('src/wallet.js', 'balanceOf(from) < cents + fee', 'balanceOf(from) < cents', 'insufficient_is_atomic'),  # overdraws by the fee
        ('src/wallet.js', "kind: 'fee', ref: id", "kind: 'transfer-out', ref: id", 'statement_has_fee_line'),    # fee hidden in the amount
    ],
    'migration': [
        ('src/store.js', 'Math.round(amount * 100)', 'Math.floor(amount * 100)', 'migrates_v1'),                  # 19.99 -> 1998
        ('src/store.js', 'if (!existsSync(backup)) writeFileSync(backup, text);', '', 'backup_kept'),            # no way back
        ('src/store.js', "throw coded('UNSUPPORTED_VERSION', String(raw.version));", 'return { version: 2, balances: {} };',
         'rejects_future_version'),                                                                               # wipes a newer file
    ],
    'concurrency': [
        ('src/wallet.js', 'const ordered = [...new Set(keys)].sort();', 'const ordered = [...new Set(keys)];', 'no_deadlock'),
        ('src/wallet.js', 'const ordered = [...new Set(keys)].sort();', "const ordered = ['*'];", 'independent_wallets_overlap'),
        ('src/wallet.js', 'return withLocks([user], async () => {', 'return (async () => {', 'no_lost_deposit'),
    ],
}


class CaseFilesTest(unittest.TestCase):
    def test_every_case_names_its_hidden_script_checks_and_fixture(self):
        for case in CASES.values():
            self.assertTrue((SUITE / case.get('hidden', 'hidden_refund.mjs')).is_file(), case['id'])
            if case.get('fixture'):
                self.assertTrue((HEADLESS / 'fixtures' / 'shop' / case['fixture'] / 'src').is_dir(), case['id'])
        for case_id, variant in HARDER.items():
            case = CASES[case_id]
            self.assertEqual(case['fixture'], variant)
            self.assertGreaterEqual(len(case['hidden_checks']), 5, case_id)
            self.assertTrue((REFERENCE / variant).is_dir(), variant)

    def test_handed_over_specs_meet_the_plugins_own_standard(self):
        # Each harder case hands over a spec: it must pass `aidlc lint`, the check prompt-builder holds users to.
        for case_id in HARDER:
            prompt = CASES[case_id]['prompt']
            self.assertTrue(prompt.startswith('/aegisops-harness:aidlc '), case_id)
            self.assertIn('I am not available for questions', prompt)
            spec = prompt[prompt.index('Status: ready-for-agent'):]
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / 'spec.md'
                path.write_text(spec)
                stories, findings = aidlc.parse_spec(spec, 'spec.md', 'KEY')
                findings = findings + aidlc.spec_findings(spec, 'spec.md', stories)
            self.assertEqual([m for level, m in findings if level == 'FAIL'], [], case_id)
            self.assertTrue(aidlc.spec_security(spec), case_id + ': no security decisions')
            self.assertGreaterEqual(len(stories), 5, case_id)


class OnboardedFixtureTest(unittest.TestCase):
    """ETA-1: the gates need a pinned verify command, so the fixture a session works in ships one on main."""

    def build(self, tmp, case_id):
        repo = pathlib.Path(tmp).resolve() / 'repo'
        with mock.patch.dict(os.environ, GIT_ENV):
            fixture.build(repo, CASES[case_id])
        return repo

    def test_eta_1_fixture_pins_its_verify_command_on_main(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, GIT_ENV):
            repo = self.build(tmp, 'L1-refund')
            config = aidlc.load_config(aidlc.Repo(repo), [repo])
            self.assertEqual(config['source'], 'base')
            self.assertEqual([m for level, m in config['findings'] if level != 'OK'], [])
            self.assertEqual(config['junit'], 'reports/*.xml')
            self.assertTrue(config['revert_check'])
            self.assertIsNone(config['ci_waiver'])  # the fixture's gh reports real checks
            ignored = subprocess.run(['git', 'check-ignore', '-q', 'reports/junit.xml'], cwd=repo)
            self.assertEqual(ignored.returncode, 0, 'the JUnit report must be git-ignored or every run changes the code')

    @unittest.skipUnless(NODE and shutil.which('npm'), 'needs node and npm')
    def test_eta_2_pinned_command_writes_a_report_the_engine_reads(self):
        for case_id in ('L1-refund',) + tuple(HARDER):
            with self.subTest(case=case_id), tempfile.TemporaryDirectory() as tmp:
                repo = self.build(tmp, case_id)
                with mock.patch.dict(os.environ, GIT_ENV):
                    root = aidlc.Repo(repo)
                    config = aidlc.load_config(root, [repo])
                    before = root.fingerprint
                    code, tail = aidlc.run_command(config['cmd'], repo, 120)
                    self.assertEqual(code, 0, tail)
                    self.assertEqual(aidlc.Repo(repo).fingerprint, before)  # the run changed no code file
                reports = sorted(repo.glob(config['junit']))
                self.assertTrue(reports, 'no JUnit report at ' + config['junit'])
                summary, problems = aidlc.parse_junit(reports, [], aidlc.Repo(repo))
                self.assertEqual(problems, [])
                self.assertGreaterEqual(summary['passed'], 3)
                self.assertEqual(summary['failed'], 0)


@unittest.skipUnless(NODE, 'needs node')
class HiddenCheckTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = pathlib.Path(tmp.name).resolve()
        self.env = dict(os.environ, **GIT_ENV)
        self.env.pop('WALLET_FILE', None)

    def build(self, case_id):
        repo = self.base / case_id / 'repo'
        with mock.patch.dict(os.environ, GIT_ENV):
            fixture.build(repo, CASES[case_id])
        return repo

    def node_tests(self, repo):
        return subprocess.run([NODE, '--test'], cwd=repo, env=self.env, capture_output=True, text=True, timeout=120)

    def hidden(self, repo, case_id):
        case = CASES[case_id]
        result = subprocess.run([NODE, str(SUITE / case['hidden']), str(repo)], env=self.env, capture_output=True,
                                text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        return {name: report.get(name) is True for name in case['hidden_checks']}, report

    def apply_reference(self, repo, variant, wrong=None):
        shutil.copytree(REFERENCE / variant, repo, dirs_exist_ok=True)
        if wrong:
            rel, old, new, _ = wrong
            text = (repo / rel).read_text()
            self.assertEqual(text.count(old), 1, '%s: %r is not in the reference once' % (rel, old))
            (repo / rel).write_text(text.replace(old, new))

    def test_eta_11_fixture_is_green_and_fails_the_hidden_check_as_shipped(self):
        for case_id in HARDER:
            with self.subTest(case=case_id):
                repo = self.build(case_id)
                tests = self.node_tests(repo)
                self.assertEqual(tests.returncode, 0, tests.stdout[-1500:])
                checks, _ = self.hidden(repo, case_id)
                self.assertIn(False, checks.values(), 'the unchanged fixture passes every hidden check')

    def test_eta_11_reference_solution_passes_every_hidden_check(self):
        for case_id, variant in HARDER.items():
            with self.subTest(case=case_id):
                repo = self.build(case_id)
                self.apply_reference(repo, variant)
                tests = self.node_tests(repo)
                self.assertEqual(tests.returncode, 0, tests.stdout[-1500:])
                checks, report = self.hidden(repo, case_id)
                self.assertEqual([name for name, ok in checks.items() if not ok], [], report)

    def test_eta_11_plausible_wrong_solutions_fail_the_check_that_names_the_defect(self):
        for case_id, variant in HARDER.items():
            for wrong in WRONG[variant]:
                with self.subTest(case=case_id, defect=wrong[3]):
                    repo = self.build(case_id)
                    self.apply_reference(repo, variant, wrong)
                    checks, report = self.hidden(repo, case_id)
                    self.assertFalse(checks[wrong[3]], report)
                    shutil.rmtree(repo.parent)

    @unittest.skipUnless(shutil.which('npm'), 'needs npm')
    def test_eta_11_judge_scores_the_reference_as_working_and_the_fixture_as_not(self):
        harness = load(HEADLESS / 'harness.py', 'harness')
        sys.modules.setdefault('harness', harness)
        judge = load(SUITE / 'judge.py', 'eval_cases_lifecycle_judge')
        for case_id, variant in HARDER.items():
            with self.subTest(case=case_id):
                repo = self.build(case_id)
                with mock.patch.dict(os.environ, self.env, clear=True):
                    before = judge.outcome(CASES[case_id], harness.parse_stream([]), repo)
                    self.apply_reference(repo, variant)
                    after = judge.outcome(CASES[case_id], harness.parse_stream([]), repo)
                self.assertFalse(before['outcome_pass'], before['summary'])
                self.assertTrue(after['outcome_pass'], after['summary'])


if __name__ == '__main__':
    unittest.main()
