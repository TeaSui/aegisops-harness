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
