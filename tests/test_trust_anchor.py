"""Evidence trust anchor (docs/specs/evidence-trust-anchor): the proofs of the 2026-11-26 assessment as regression tests.

Proof A: every gate up to `shipped` passed on red tests (`verify --cmd true`, a story ID in a comment, a typed review).
Proof B: four text files and the 12 hex characters the gate printed passed the merge gate.
Each test names the story it proves (ETA-n). Same isolation as test_aidlc.py: scratch HOME, no global git config, no gh.
Run: python3 -m unittest tests.test_trust_anchor -v
"""
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_aidlc import Base, aidlc, REVIEW, SHIP  # noqa: E402  (Base carries no test of its own)

RED = sys.executable + ' -c "import sys; sys.exit(1)"'
# A stand-in test runner: runs nothing, writes the JUnit report it is told to.
REPORT = sys.executable + ' -c "import pathlib,sys; pathlib.Path(sys.argv[1]).parent.mkdir(parents=True, exist_ok=True); ' \
                          'pathlib.Path(sys.argv[1]).write_text(sys.argv[2])" ignored/junit.xml '


def junit(*cases):
    """A JUnit report; each case is (name, 'pass' | 'fail' | 'skip')."""
    body = ''
    for name, state in cases:
        inner = {'pass': '', 'fail': '<failure message="x"/>', 'skip': '<skipped/>'}[state]
        body += '<testcase classname="t" name="%s">%s</testcase>' % (name, inner)
    return "'<testsuite>%s</testsuite>'" % body


class ConfigCase(Base):
    """Helpers for a repository whose default branch (main) already carries the config: the onboarded state."""

    def config_on_main(self, cmd='true', junit='none — fixture has no JUnit writer', **top):
        """Commit .aidlc.json on main. Call before building() leaves main."""
        self.assertEqual(self.git('rev-parse', '--abbrev-ref', 'HEAD'), 'main')
        self.pin(cmd, junit, **top)
        self.commit('config')

    def repin_main(self, cmd, junit='none — fixture has no JUnit writer', **top):
        """Give main a new .aidlc.json without leaving the current branch (a commit built on main's tree)."""
        self.pin(cmd, junit, **top)
        text = (self.repo / '.aidlc.json').read_text()
        self.git('checkout', '--', '.aidlc.json') if self.git('ls-files', '.aidlc.json') else (self.repo / '.aidlc.json').unlink()
        env = dict(os.environ, GIT_INDEX_FILE=str(self.base / 'main.index'))
        run = lambda *args, **kw: subprocess.run(['git', *args], cwd=self.repo, env=env, check=True,  # noqa: E731
                                                 capture_output=True, text=True, **kw).stdout.strip()
        blob = run('hash-object', '-w', '--stdin', input=text)
        run('read-tree', 'main')
        run('update-index', '--add', '--cacheinfo', '100644,%s,.aidlc.json' % blob)
        commit = run('commit-tree', run('write-tree'), '-p', 'main', '-m', 'config on main')
        self.git('update-ref', 'refs/heads/main', commit)

    def last(self, kind):
        events, findings = aidlc.parse_ledger(self.ledger(), 'ledger.md')
        self.assertEqual(findings, [])
        return [e for e in events if e['kind'] == kind][-1]

    def warns(self, findings):
        return [m for level, m in findings if level == 'WARN']


class PinnedVerifyTest(ConfigCase):
    """ETA-1: the session that is gated does not choose the command that gates it."""

    def test_eta_1_verify_without_a_config_is_refused(self):
        self.building()
        code, out, err = self.cli('verify', 'refunds')
        self.assertEqual(code, 2, out + err)
        self.assertIn('.aidlc.json', err)
        self.assertIn('config init', err)
        self.assertNotIn('verify', self.ledger())

    def test_eta_1_proof_a_true_is_not_a_test_run(self):
        # The assessment's proof A: `aidlc verify --cmd true` logged a green run over a red suite.
        self.config_on_main(RED)
        self.verified_ready(verify=False)
        code, out, err = self.cli('verify', 'refunds', '--cmd', 'true')
        self.assertEqual(code, 2, out + err)
        self.assertIn('pinned', err)
        self.assertNotIn(' verify ', self.ledger())
        self.assertEqual(self.cli('verify', 'refunds')[0], 1)        # the pinned command runs, and it is red
        self.assertEqual(self.last('verify')['exit'], 1)
        self.assertFails(aidlc.check(self.spec, 'verified'), 'exited 1')

    def test_eta_1_the_pinned_command_may_be_named(self):
        self.config_on_main('true')
        self.building()
        self.assertEqual(self.cli('verify', 'refunds', '--cmd', 'true')[0], 0)
        event = self.last('verify')
        self.assertEqual((event['cmd'], event['pinned']), ('true', 'base'))

    def test_eta_1_a_branch_cannot_rewrite_the_config(self):
        self.config_on_main(RED)
        self.building()
        self.pin('true')                                              # the feature branch swaps the exam ...
        self.commit('swap the test command')
        code, out, _ = self.cli('verify', 'refunds')
        self.assertEqual(code, 1, out)                                # ... and still sits main's
        self.assertEqual(self.last('verify')['cmd'], RED)
        self.assertIn('differs', out)

    def test_eta_1_a_branch_cannot_delete_the_config(self):
        self.config_on_main(RED)
        self.building()
        (self.repo / '.aidlc.json').unlink()
        self.commit('drop the config')
        self.assertEqual(self.cli('verify', 'refunds')[0], 1)
        self.assertEqual(self.last('verify')['cmd'], RED)

    def test_eta_1_first_config_on_a_branch_is_onboarding_and_says_so(self):
        self.building()
        self.pin('true')
        code, out, _ = self.cli('verify', 'refunds')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.last('verify')['pinned'], 'onboarding')
        self.assertIn('onboarding', out)
        self.assertTrue(any('onboarding' in w for w in self.warns(aidlc.check(self.spec, 'verified'))))

    def test_eta_1_the_remote_default_branch_wins_over_the_local_one(self):
        # A session can commit to its local main; it cannot move origin/main without pushing.
        self.config_on_main(RED)
        origin = self.base / 'origin.git'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(origin)], check=True)
        self.git('remote', 'add', 'origin', str(origin))
        self.git('push', '-q', '-u', 'origin', 'main')
        self.pin('true')
        self.commit('local main says true')
        self.building()
        self.assertEqual(self.cli('verify', 'refunds')[0], 1)
        self.assertEqual(self.last('verify')['cmd'], RED)

    def test_eta_1_a_ledger_line_without_the_pin_does_not_count(self):
        # What a 5.x ledger holds, and what a hand-written line looked like in proof B.
        self.config_on_main('true')
        self.verified_ready(verify=False)
        with open(self.spec / 'ledger.md', 'a') as ledger:
            ledger.write('- 2026-11-26T00:00:00Z verify exit=0 fingerprint=%s cmd="true"\n' % aidlc.fingerprint(self.repo))
        self.assertFails(aidlc.check(self.spec, 'verified'), 'pinned command')

    def test_eta_1_a_changed_pin_needs_a_new_verify(self):
        self.building()
        self.verified_ready_here()
        self.assertPasses(aidlc.check(self.spec, 'verified'))
        self.pin('echo other')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'pinned command')

    def verified_ready_here(self):
        self.write('tests/test_refunds.py', '# RFD-1\n')
        self.pin()
        for task in ('T1', 'T2'):
            self.assertEqual(self.cli('task-done', 'refunds', task, '--cmd', 'true')[0], 0)
        self.assertEqual(self.cli('verify', 'refunds')[0], 0)

    def test_eta_1_config_problems_are_findings(self):
        self.building()
        cases = (('{not json', 'not valid JSON'),
                 (json.dumps({'schema': 1, 'verify': {'junit': 'none — x'}}), 'verify.cmd'),
                 (json.dumps({'schema': 1, 'verify': {'cmd': 'true'}}), 'verify.junit'),
                 (json.dumps({'schema': 1, 'verify': {'cmd': 'true', 'junit': 'none'}}), 'needs a reason'),
                 (json.dumps({'verify': {'cmd': 'true', 'junit': 'none — x'}}), 'schema'),
                 (json.dumps({'schema': 2, 'verify': {'cmd': 'true', 'junit': 'none — x'}}), 'newer'),
                 (json.dumps({'schema': 1, 'verify': {'cmd': 'true', 'junit': 'none — x'}, 'ci': 'off'}), '"ci"'))
        for text, needle in cases:
            self.write('.aidlc.json', text)
            code, out, err = self.cli('verify', 'refunds')
            self.assertEqual(code, 1, (text, out, err))
            self.assertIn(needle, out, text)
        self.assertNotIn(' verify ', self.ledger())

    def test_eta_1_a_service_config_is_used_in_its_own_folder(self):
        service = self.repo / 'services' / 'pay'
        spec = service / 'docs' / 'specs' / 'payouts'
        self.assertEqual(self.cli('init', str(spec), '--key', 'PAY')[0], 0)
        self.write('services/pay/.aidlc.json', json.dumps({'schema': 1, 'verify': {
            'cmd': 'pwd > ignored/where.log', 'junit': 'none — fixture', 'revert_check': False}}))
        (service / 'ignored').mkdir()
        self.write('.aidlc.json', json.dumps({'schema': 1, 'verify': {'cmd': RED, 'junit': 'none — fixture'}}))
        code, out, err = self.cli('verify', str(spec))
        self.assertEqual(code, 0, out + err)
        self.assertEqual((service / 'ignored' / 'where.log').read_text().strip(), str(service))

    def test_config_init_writes_a_valid_file_once(self):
        code, out, err = self.cli('config', 'init', '--cmd', 'npm test', '--junit', 'reports/*.xml')
        self.assertEqual(code, 0, out + err)
        data = json.loads((self.repo / '.aidlc.json').read_text())
        self.assertEqual((data['schema'], data['verify']['cmd'], data['verify']['junit']), (1, 'npm test', 'reports/*.xml'))
        self.assertEqual(self.cli('config', 'init', '--cmd', 'true', '--junit', 'none — x')[0], 2)
        code, out, _ = self.cli('config', 'show')
        self.assertEqual(code, 0, out)
        self.assertIn('npm test', out)
        self.assertIn('onboarding', out)


class DynamicTraceabilityTest(ConfigCase):
    """ETA-2: a story is traced by a test that ran and passed, not by its ID appearing in a file."""

    def ready(self, report):
        self.config_on_main(REPORT + report, junit='ignored/*.xml')
        self.verified_ready(verify=False)

    def test_eta_2_proof_a_an_id_in_a_comment_is_not_traceability(self):
        # tests/test_refunds.py holds "# RFD-1: ..." (a comment). The run reports one passing test without the ID.
        self.ready(junit(('refund works', 'pass')))
        self.assertEqual(self.cli('verify', 'refunds')[0], 0)
        self.assertFails(aidlc.check(self.spec, 'verified'), 'RFD-1 has no passing test in the JUnit results')

    def test_eta_2_a_passing_test_that_names_the_story_traces_it(self):
        self.ready(junit(('RFD-1 refunds a captured payment', 'pass')))
        self.assertEqual(self.cli('verify', 'refunds')[0], 0)
        self.assertEqual(self.last('verify')['req_pass'], ['RFD-1'])
        self.assertPasses(aidlc.check(self.spec, 'verified'))

    def test_eta_2_a_skipped_or_failed_story_test_does_not_trace_it(self):
        self.ready(junit(('RFD-1 refunds', 'skip')))
        self.assertEqual(self.cli('verify', 'refunds')[0], 0)
        self.assertFails(aidlc.check(self.spec, 'verified'), 'RFD-1 has no passing test')
        self.repin_main(REPORT + junit(('RFD-1 refunds', 'fail')), junit='ignored/*.xml')
        self.assertEqual(self.cli('verify', 'refunds')[0], 1)
        self.assertFails(aidlc.check(self.spec, 'verified'), 'RFD-1')

    def test_eta_2_a_run_without_its_report_fails_the_gate(self):
        self.config_on_main('true', junit='ignored/*.xml')            # the runner writes nothing
        self.verified_ready(verify=False)
        code, out, _ = self.cli('verify', 'refunds')
        self.assertEqual(code, 1, out)
        self.assertFails(aidlc.check(self.spec, 'verified'), 'JUnit')

    def test_eta_2_the_waiver_is_visible_and_needs_no_report(self):
        self.config_on_main('true', junit='none — the runner cannot write JUnit')
        self.verified_ready(verify=False)
        self.assertEqual(self.cli('verify', 'refunds')[0], 0)
        findings = aidlc.check(self.spec, 'verified')
        self.assertPasses(findings)
        self.assertTrue(any('the runner cannot write JUnit' in w for w in self.warns(findings)), findings)


if __name__ == '__main__':
    import unittest
    unittest.main()


ROOT = pathlib.Path(__file__).resolve().parent.parent
QUIET = 'PYTHONDONTWRITEBYTECODE=1 '
UNITTEST = QUIET + sys.executable + ' -m unittest discover -s tests -q'
JUNIT_RUN = QUIET + '%s %s -s tests -o ignored/junit.xml' % (sys.executable, ROOT / 'tests' / 'junit_runner.py')
MODEL = 'def refund(amount):\n    return amount\n'
REAL_TEST = '''import sys
import unittest

sys.path.insert(0, 'src')
from refunds.model import refund  # noqa: E402


class RefundTest(unittest.TestCase):
    def test_rfd_1_refund_returns_the_amount(self):
        self.assertEqual(refund(5), 5)
'''
VACUOUS_TEST = '''import unittest


class RefundTest(unittest.TestCase):
    def test_rfd_1_refund_returns_the_amount(self):
        self.assertTrue(True)  # carries the story ID, exercises nothing
'''
EXISTING_TEST = '''import sys
import unittest

sys.path.insert(0, 'src')
import app  # noqa: E402


class ExistingTest(unittest.TestCase):
    def test_rfd_3_existing_value_is_kept(self):
        self.assertEqual(app.x, 1)
'''
REQS_TWO_TESTED = '''# Requirements

### RFD-1: Refund a captured payment
Acceptance:
- A full refund returns the amount.
Verify: test

### RFD-2: Refunds are visible to support staff
Acceptance:
- p95 visibility delay <= 60 s.
Verify: check — k6 run load/refund-visibility.js

### RFD-3: Existing settings keep their value
Acceptance:
- The existing value is unchanged.
Verify: test
'''


class RevertCheckTest(ConfigCase):
    """ETA-3: the suite goes red when the production change is taken out, or the tests prove nothing about it."""

    def ready(self, test_text, cmd=UNITTEST, junit='none — plain unittest writes no JUnit', commit=True):
        self.config_on_main(cmd, junit, revert_check=True)
        self.building()
        self.write('src/refunds/model.py', MODEL)
        self.write('tests/test_refunds.py', test_text)
        if commit:
            self.commit('code')
        for task in ('T1', 'T2'):
            self.assertEqual(self.cli('task-done', 'refunds', task, '--cmd', 'true')[0], 0)

    def code_status(self):
        return self.git('status', '--porcelain', '--', 'src', 'tests', '.aidlc.json')

    def test_eta_3_a_real_test_goes_red_without_the_change_and_the_tree_is_restored(self):
        self.ready(REAL_TEST)
        before = aidlc.fingerprint(self.repo)
        code, out, err = self.cli('verify', 'refunds')
        self.assertEqual(code, 0, out + err)
        check = self.last('revert-check')
        self.assertFalse(check['skipped'])
        self.assertNotEqual(check['exit'], 0)
        self.assertEqual(check['files'], '1')
        kinds = [line.split()[2] for line in self.ledger().splitlines() if line.startswith('- ')]
        self.assertEqual(kinds[-2:], ['revert-check', 'verify'])   # red first: the tree ends on the real code's run
        self.assertEqual((self.repo / 'src' / 'refunds' / 'model.py').read_text(), MODEL)
        self.assertEqual(self.code_status(), '')
        self.assertEqual(aidlc.fingerprint(self.repo), before)
        self.assertFalse((pathlib.Path(self.git('rev-parse', '--absolute-git-dir')) / 'aidlc-revert-check.json').exists())
        self.assertPasses(aidlc.check(self.spec, 'verified'))

    def test_eta_3_a_vacuous_test_fails_the_revert_check(self):
        # Proof A again: a test that names the story and exercises nothing is green with or without the change.
        self.ready(VACUOUS_TEST)
        code, out, _ = self.cli('verify', 'refunds')
        self.assertEqual(code, 1, out)
        self.assertIn('still passes without the production change', out)
        self.assertEqual(self.last('revert-check')['exit'], 0)
        self.assertNotIn(' verify ', self.ledger())                 # no green run is recorded on top of it
        self.assertEqual(self.code_status(), '')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'without the production change')

    def test_eta_3_modified_deleted_and_added_files_are_put_back_as_they_were(self):
        self.write('src/legacy.py', 'old = True\n')
        self.config_on_main(UNITTEST, 'none — plain unittest writes no JUnit', revert_check=True)
        self.building()
        self.write('src/app.py', 'x = 2\n')                          # modified
        (self.repo / 'src' / 'legacy.py').unlink()                   # deleted
        self.write('src/refunds/model.py', MODEL)                    # added
        self.write('tests/test_refunds.py', REAL_TEST + '\n\nclass AppTest(unittest.TestCase):\n'
                   '    def test_app_value(self):\n        import app\n        self.assertEqual(app.x, 2)\n')
        self.commit('code')
        for task in ('T1', 'T2'):
            self.cli('task-done', 'refunds', task, '--cmd', 'true')
        code, out, err = self.cli('verify', 'refunds')
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.last('revert-check')['files'], '3')
        self.assertEqual((self.repo / 'src' / 'app.py').read_text(), 'x = 2\n')
        self.assertFalse((self.repo / 'src' / 'legacy.py').exists())
        self.assertEqual((self.repo / 'src' / 'refunds' / 'model.py').read_text(), MODEL)
        self.assertEqual(self.code_status(), '')

    def test_eta_3_uncommitted_code_is_refused_before_anything_runs(self):
        self.ready(REAL_TEST, commit=False)
        code, out, _ = self.cli('verify', 'refunds')
        self.assertEqual(code, 1, out)
        self.assertIn('commit', out)
        self.assertNotIn('revert-check', self.ledger())
        self.assertNotIn(' verify ', self.ledger())
        self.assertEqual((self.repo / 'src' / 'refunds' / 'model.py').read_text(), MODEL)

    def test_eta_3_a_change_without_production_source_is_skipped_with_its_reason(self):
        self.config_on_main(UNITTEST, 'none — plain unittest writes no JUnit', revert_check=True)
        self.building()
        self.write('tests/test_refunds.py', EXISTING_TEST.replace('rfd_3', 'rfd_1'))
        self.commit('a test for existing behaviour')
        for task in ('T1', 'T2'):
            self.cli('task-done', 'refunds', task, '--cmd', 'true')
        code, out, err = self.cli('verify', 'refunds')
        self.assertEqual(code, 0, out + err)
        check = self.last('revert-check')
        self.assertTrue(check['skipped'])
        self.assertIn('no production source', check['reason'])
        findings = aidlc.check(self.spec, 'verified')
        self.assertPasses(findings)
        self.assertTrue(any('no production source' in w for w in self.warns(findings)))

    def building_with(self, requirements, covers):
        self.config_on_main(JUNIT_RUN, 'ignored/*.xml', revert_check=True)
        self.accepted_ready()
        self.spec_file('requirements.md', requirements)
        self.assertEqual(self.cli('advance', 'refunds', 'accepted')[0], 0)
        self.spec_file('plan.md', '- [ ] T1: Refund model\n  - covers: %s\n  - depends: none\n  - owner: main\n'
                                  '  - files: src/refunds/model.py (new)\n' % covers)
        self.assertEqual(self.cli('advance', 'refunds', 'planned')[0], 0)
        self.git('checkout', '-q', '-b', 'feat/refunds')
        self.assertEqual(self.cli('advance', 'refunds', 'building')[0], 0)

    def test_eta_3_stories_whose_tests_pass_without_the_change_are_listed(self):
        self.building_with(REQS_TWO_TESTED, 'RFD-1, RFD-2, RFD-3')
        self.write('src/refunds/model.py', MODEL)
        self.write('tests/test_refunds.py', REAL_TEST)
        self.write('tests/test_existing.py', EXISTING_TEST)
        self.commit('code')
        self.assertEqual(self.cli('task-done', 'refunds', 'T1', '--cmd', 'true')[0], 0)
        code, out, err = self.cli('verify', 'refunds')
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.last('revert-check')['still_green'], ['RFD-3'])
        self.assertEqual(self.last('verify')['req_pass'], ['RFD-1', 'RFD-3'])
        findings = aidlc.check(self.spec, 'verified')
        self.assertPasses(findings)
        self.assertTrue(any('RFD-3' in w and 'without the production change' in w for w in self.warns(findings)))

    def test_eta_3_a_red_suite_does_not_count_when_no_story_test_depends_on_the_change(self):
        # The suite goes red for another reason (an unrelated test needs the reverted file); the story's own test
        # is vacuous. With JUnit the check is per story, so this does not pass.
        self.building_with(REQS_TWO_TESTED.split('### RFD-3')[0], 'RFD-1, RFD-2')
        self.write('src/refunds/model.py', MODEL)
        self.write('tests/test_refunds.py', VACUOUS_TEST)
        self.write('tests/test_other.py', REAL_TEST.replace('test_rfd_1_refund_returns_the_amount', 'test_unrelated'))
        self.commit('code')
        self.assertEqual(self.cli('task-done', 'refunds', 'T1', '--cmd', 'true')[0], 0)
        code, out, _ = self.cli('verify', 'refunds')
        self.assertEqual(code, 1, out)
        self.assertIn('every story test of this spec still passes', out)
        self.assertFails(aidlc.check(self.spec, 'verified'), 'every story test of this spec still passes')

    def test_eta_3_an_interrupted_check_is_healed_by_the_next_command(self):
        self.ready(REAL_TEST)
        git_dir = pathlib.Path(self.git('rev-parse', '--absolute-git-dir'))
        (self.repo / 'src' / 'refunds' / 'model.py').unlink()        # as a killed revert check leaves the tree
        (git_dir / 'aidlc-revert-check.json').write_text(json.dumps({'changes': [['A', 'src/refunds/model.py']]}))
        code, out, err = self.cli('status')
        self.assertEqual(code, 0, out + err)
        self.assertIn('restored', err)
        self.assertEqual((self.repo / 'src' / 'refunds' / 'model.py').read_text(), MODEL)
        self.assertFalse((git_dir / 'aidlc-revert-check.json').exists())

    def test_eta_3_the_gate_needs_a_revert_check_of_this_code(self):
        self.ready(REAL_TEST)
        self.assertEqual(self.cli('verify', 'refunds')[0], 0)
        ledger = self.spec / 'ledger.md'
        kept = [line for line in ledger.read_text().splitlines() if 'revert-check' not in line]
        ledger.write_text('\n'.join(kept) + '\n')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'no revert check')
        with open(ledger, 'a') as handle:
            handle.write('- 2026-11-26T00:00:00Z revert-check exit=124 fingerprint=%s base=abc files=1\n'
                         % aidlc.fingerprint(self.repo))
        self.assertFails(aidlc.check(self.spec, 'verified'), 'timed out')
        with open(ledger, 'a') as handle:
            handle.write('- 2026-11-26T00:00:01Z revert-check exit=1 fingerprint=%s base=abc files=1\n' % ('0' * 64))
        self.assertFails(aidlc.check(self.spec, 'verified'), 'code changed since the revert check')
