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


class RevertFixture(ConfigCase):
    """A branch with production code and a real test runner pinned on main, revert check on."""

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


class RevertCheckTest(RevertFixture):
    """ETA-3: the suite goes red when the production change is taken out, or the tests prove nothing about it."""

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


class CumulativeGateTest(ConfigCase):
    """ETA-5: a later gate re-checks the earlier ones, and `shipped` needs a result from CI, not a sentence."""

    def test_eta_5_proof_b_four_text_files_do_not_reach_shipped(self):
        # The assessment's proof B, with the forger already adapted to the pinned-command rule.
        self.pin()
        self.git('checkout', '-q', '-b', 'feat/x')
        self.commit('ship it')
        folder = self.repo / 'docs' / 'specs' / 'x'
        current = aidlc.fingerprint(self.repo)
        self.spec_file('README.md', '---\nstatus: reviewed\nkey: ZZ\nbranch: feat/x\n---\n# x\n', folder)
        self.spec_file('ship.md', SHIP, folder)
        self.spec_file('review.md', '---\nfingerprint: %s\n---\n' % current[:12], folder)
        self.spec_file('ledger.md', '- 2026-11-26T00:00:00Z verify exit=0 fingerprint=%s cmd="true" pinned=onboarding\n'
                       % current[:12], folder)
        findings = aidlc.check(folder, 'shipped')
        for needle in ('spec.md: missing', 'accepted_by', 'tickets.md', 'no "## Spec" section'):
            self.assertFails(findings, needle)
        code, out, _ = self.cli('check', 'x', '--to', 'shipped')
        self.assertEqual(code, 1, out)

    def test_eta_5_a_hand_set_stage_grants_nothing(self):
        self.building()
        self.pin()
        self.commit('code')
        readme = self.spec / 'README.md'
        readme.write_text(readme.read_text().replace('status: building', 'status: reviewed'))
        self.spec_file('review.md', REVIEW.format(fp=aidlc.fingerprint(self.repo)))
        self.spec_file('ship.md', SHIP)
        with open(self.spec / 'ledger.md', 'a') as ledger:
            ledger.write('- 2026-11-26T00:00:00Z verify exit=0 fingerprint=%s cmd="true" pinned=onboarding\n'
                         % aidlc.fingerprint(self.repo))
        findings = aidlc.check(self.spec, 'shipped')
        self.assertFails(findings, 'T1 is not done')
        self.assertFails(findings, 'RFD-1 (Verify: test) is not referenced')
        self.assertEqual(self.cli('advance', 'refunds', 'shipped')[0], 1)

    def test_eta_5_planned_includes_accepted(self):
        self.planned_ready()
        self.assertPasses(aidlc.check(self.spec, 'planned'))
        self.readme(status='accepted', accepted_by='')
        self.assertFails(aidlc.check(self.spec, 'planned'), 'accepted_by')

    def test_eta_5_reviewed_includes_verified(self):
        self.reviewed_ready()
        self.assertPasses(aidlc.check(self.spec, 'reviewed'))
        plan = self.spec / 'plan.md'
        plan.write_text(plan.read_text() + '- [ ] T3: slipped in after the verify\n  - covers: RFD-1\n'
                        '  - depends: none\n  - owner: main\n  - files: src/late.py\n')
        self.assertFails(aidlc.check(self.spec, 'reviewed'), 'T3 is not done')

    def test_eta_5_shipped_includes_the_review(self):
        self.shipped_ready()
        self.assertPasses(aidlc.check(self.spec, 'shipped'))
        review = self.spec / 'review.md'
        review.write_text(review.read_text().replace('## QA', '- [ ] S9 (must): found after the stamp\n## QA'))
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'open finding S9')

    def strict_ci(self):
        self.shipped_ready()
        self.pin(ci='required')
        self.commit('CI is required')
        self.assertEqual(self.verify(ci='required')[0], 0)
        self.assertEqual(self.cli('stamp', 'refunds', 'review')[0], 0)

    def test_eta_5_proof_a_a_typed_ci_green_is_not_a_ci_result(self):
        self.strict_ci()                                              # ship.md says "CI: green"; no gh, no PR
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'no CI result')
        self.fake_gh('build\tpass\t1m\thttps://ci/1\n')
        self.assertPasses(aidlc.check(self.spec, 'shipped'))
        self.fake_gh('build\tfail\t1m\thttps://ci/1\n')
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'CI is not green')

    def test_eta_5_the_ci_waiver_is_a_visible_decision(self):
        self.shipped_ready()                                          # the fixture config waives CI
        findings = aidlc.check(self.spec, 'shipped')
        self.assertPasses(findings)
        self.assertTrue(any('CI is waived' in w and 'the fixture has no CI' in w for w in self.warns(findings)))

    def test_eta_5_fast_status_does_not_call_missing_ci_a_blocker(self):
        self.strict_ci()
        row = next(item for item in aidlc.status(self.repo, fast=True) if item['slug'] == 'refunds')
        self.assertFalse(any('no CI result' in blocker for blocker in row['blockers']), row['blockers'])


class CiCommandTest(RevertFixture):
    """ETA-4: `aidlc ci` recomputes the evidence on the head with the base's config. It never reads a verify or
    revert line from the ledger and never writes to the spec folder."""

    def reviewed(self, test_text=REAL_TEST, model=MODEL):
        """A branch taken to `reviewed` the honest way, everything committed."""
        self.ready(test_text)
        self.assertEqual(self.cli('verify', 'refunds')[0], 0)
        self.assertEqual(self.cli('advance', 'refunds', 'verified')[0], 0)
        self.spec_file('review.md', REVIEW.format(fp='pending'))
        self.assertEqual(self.cli('stamp', 'refunds', 'review')[0], 0)
        code, out, err = self.cli('advance', 'refunds', 'reviewed')
        self.assertEqual(code, 0, out + err)
        self.commit('spec files')

    def ci(self, *extra):
        return self.cli('ci', '--base', 'main', '--branch', 'feat/refunds', *extra)

    def snapshot(self):
        files = {p.relative_to(self.repo).as_posix(): p.read_bytes() for p in sorted(self.spec.rglob('*')) if p.is_file()}
        return files, self.git('status', '--porcelain')

    def test_eta_4_an_honest_branch_passes_and_nothing_is_written(self):
        self.reviewed()
        before = self.snapshot()
        code, out, err = self.ci()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.snapshot(), before)
        self.assertIn('gate reviewed passes', out)

    def test_eta_4_proof_a_a_forged_green_ledger_over_red_tests_fails(self):
        # Everything the local gates read says green; the suite is red. CI runs the suite.
        self.reviewed()
        self.write('src/refunds/model.py', 'def refund(amount):\n    return 0\n')
        self.commit('break the refund')
        current = aidlc.fingerprint(self.repo)
        review = self.spec / 'review.md'
        review.write_text(REVIEW.format(fp=current))
        with open(self.spec / 'ledger.md', 'a') as ledger:
            ledger.write('- 2026-11-26T00:00:00Z revert-check exit=1 fingerprint=%s base=abc files=1\n' % current)
            ledger.write('- 2026-11-26T00:00:01Z verify exit=0 fingerprint=%s cmd=%s pinned=base\n'
                         % (current, json.dumps(UNITTEST)))
        self.commit('forged evidence')
        self.assertPasses(aidlc.check(self.spec, 'reviewed'))        # the local gate is fooled ...
        code, out, _ = self.ci()
        self.assertEqual(code, 1, out)                                # ... CI is not
        self.assertIn('the pinned command exited 1', out)

    def test_eta_4_the_base_config_is_used_not_the_heads(self):
        self.reviewed()
        self.write('src/refunds/model.py', 'def refund(amount):\n    return 0\n')
        self.pin('true')                                              # the head swaps the exam
        self.commit('swap the test command and break the refund')
        code, out, _ = self.ci()
        self.assertEqual(code, 1, out)
        self.assertIn('the pinned command exited 1', out)

    def test_eta_4_the_review_must_be_stamped_on_this_code(self):
        self.reviewed()
        self.write('src/refunds/model.py', MODEL + '\n\ndef extra():\n    return 1\n')
        self.commit('slipped in after the review')
        code, out, _ = self.ci()
        self.assertEqual(code, 1, out)
        self.assertIn('code changed since the review was stamped', out)

    def test_eta_4_a_vacuous_test_fails_ci_too(self):
        self.ready(VACUOUS_TEST)
        code, out, _ = self.ci('--require', 'none')
        self.assertEqual(code, 1, out)
        self.assertIn('still passes without the production change', out)

    def test_eta_4_a_spec_below_the_required_stage_fails(self):
        self.ready(REAL_TEST)                                         # stage: building, suite green
        code, out, _ = self.ci()
        self.assertEqual(code, 1, out)
        self.assertIn('needs it at reviewed', out)
        code, out, err = self.ci('--require', 'none')
        self.assertEqual(code, 0, out + err)

    def test_eta_4_the_base_must_be_a_commit_here(self):
        self.reviewed()
        code, out, err = self.cli('ci', '--base', 'origin/nope', '--branch', 'feat/refunds')
        self.assertEqual(code, 2, out + err)
        self.assertIn('fetch', err)

    def test_eta_4_a_detached_checkout_works_with_the_branch_named(self):
        self.reviewed()
        self.git('checkout', '-q', '--detach')
        code, out, err = self.ci()
        self.assertEqual(code, 0, out + err)

    def test_eta_4_a_branch_without_a_spec_still_runs_the_pinned_suite(self):
        self.config_on_main(UNITTEST, 'none — plain unittest writes no JUnit', revert_check=True)
        self.git('checkout', '-q', '-b', 'chore/tidy')
        self.write('tests/test_app.py', EXISTING_TEST)
        self.commit('a test')
        code, out, err = self.cli('ci', '--base', 'main', '--branch', 'chore/tidy')
        self.assertEqual(code, 0, out + err)
        self.assertIn('no spec is bound to chore/tidy', out)
        self.write('tests/test_app.py', EXISTING_TEST.replace('app.x, 1', 'app.x, 2'))
        self.commit('a red test')
        self.assertEqual(self.cli('ci', '--base', 'main', '--branch', 'chore/tidy')[0], 1)

    def test_eta_4_no_config_anywhere_fails(self):
        self.git('checkout', '-q', '-b', 'chore/tidy')
        code, out, _ = self.cli('ci', '--base', 'main', '--branch', 'chore/tidy')
        self.assertEqual(code, 1, out)
        self.assertIn('.aidlc.json', out)

    def test_eta_4_the_summary_lists_what_ci_cannot_check(self):
        self.reviewed()
        summary = self.base / 'summary.md'
        self.assertEqual(self.ci('--summary', str(summary))[0], 0)
        text = summary.read_text()
        for needle in ('Lifecycle gate', 'PASS', 'feat/refunds', 'accepted_by: Tea (2026-11-19)', 'reviewers:',
                       'CI is waived', 'reviewer returns are waived'):
            self.assertIn(needle, text)

    def test_eta_4_onboarding_is_said_out_loud(self):
        self.building()                                               # main has no config
        self.pin(UNITTEST, revert_check=True)
        self.write('src/refunds/model.py', MODEL)
        self.write('tests/test_refunds.py', REAL_TEST)
        self.commit('code and the first config')
        summary = self.base / 'summary.md'
        code, out, err = self.ci('--require', 'none', '--summary', str(summary))
        self.assertEqual(code, 0, out + err)
        self.assertIn('ONBOARDING', summary.read_text())


class CiPackagingTest(Base):
    def test_eta_4_the_action_runs_the_ci_command(self):
        action = (ROOT / '.github' / 'actions' / 'aidlc-gate' / 'action.yml').read_text()
        self.assertIn('using: composite', action)
        self.assertIn('scripts/aidlc.py" ci', action)
        self.assertIn('GITHUB_STEP_SUMMARY', action)

    def test_eta_15_this_repository_runs_its_own_gate_on_pull_requests(self):
        workflow = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text()
        self.assertIn('uses: ./.github/actions/aidlc-gate', workflow)
        self.assertIn('fetch-depth: 0', workflow)
        self.assertIn('github.event.pull_request.head.sha', workflow)
        config = json.loads((ROOT / '.aidlc.json').read_text())
        self.assertEqual(config['schema'], 1)
        self.assertIn('junit_runner.py', config['verify']['cmd'])
        self.assertNotIn('none', config['verify']['junit'])           # this repository does not waive its own rule
        self.assertNotIn('ci', config)
