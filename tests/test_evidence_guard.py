"""hooks/evidence-guard.py: the model does not write the evidence that gates it (ETA-6, ETA-7).

The guard is a guard rail for the default path, not a lock: it reads the session transcript the way the question gate
does, and a session that sets out to get round it can. Enforcement is `aidlc ci` behind branch protection.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARD = ROOT / 'hooks' / 'evidence-guard.py'
AIDLC = 'python3 "/plugins/aegisops-harness/scripts/aidlc.py"'


def command(name, args):
    text = (f'<command-message>aegisops-harness:{name}</command-message>\n'
            f'<command-name>/aegisops-harness:{name}</command-name>\n<command-args>{args}</command-args>')
    return {'type': 'user', 'message': {'role': 'user', 'content': text}}


class GuardCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = pathlib.Path(tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('AEGISOPS_HARNESS_')}
        self.env['HOME'] = str(self.base)

    def run_guard(self, tool, tool_input, entries=None, env=None):
        payload = {'session_id': 's1', 'tool_name': tool, 'tool_input': tool_input, 'cwd': str(self.base)}
        if entries is not None:
            transcript = self.base / 'transcript.jsonl'
            transcript.write_text('\n'.join(json.dumps(e) for e in entries) + '\n')
            payload['transcript_path'] = str(transcript)
        result = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload), capture_output=True,
                                text=True, env=dict(self.env, **(env or {})), timeout=20)
        return result.returncode, result.stderr

    def bash(self, text, entries=None, env=None):
        return self.run_guard('Bash', {'command': text}, entries, env)


class ApprovalGuardTest(GuardCase):
    def test_eta_6_the_model_cannot_record_a_persons_approval(self):
        entries = [command('aidlc', 'Add refunds to the wallet.')]
        code, err = self.bash(AIDLC + ' approve refunds', entries)
        self.assertEqual(code, 2)
        self.assertIn('/aegisops-harness:approve refunds', err)
        self.assertEqual(self.bash(AIDLC + ' approve refunds --by "Tea"', entries)[0], 2)
        self.assertEqual(self.bash('cd repo && ' + AIDLC + ' approve docs/specs/refunds', entries)[0], 2)

    def test_eta_6_a_shell_wrapper_does_not_hide_the_call(self):
        entries = [command('aidlc', 'Add refunds to the wallet.')]
        for text in ('bash -c \'' + AIDLC + ' approve refunds\'', 'sh -c "' + AIDLC + ' approve refunds"',
                     'eval "' + AIDLC + ' approve refunds"', 'sudo -u me ' + AIDLC + ' approve refunds',
                     'env X=1 ' + AIDLC + ' approve refunds', 'python3 /p/scripts/aidlc.py --repo . approve refunds',
                     'python3 /p/scripts/aidlc.py approve \\\n refunds', 'ls && (cd x; ' + AIDLC + ' approve refunds)',
                     'bash <<EOF\n' + AIDLC + ' approve refunds\nEOF', 'python3 /p/scripts/aidlc.py attest refunds'):
            self.assertEqual(self.bash(text, entries)[0], 2, text)
        self.assertEqual(self.bash('echo "aidlc.py approve refunds"', entries)[0], 0)

    def test_eta_6_the_users_own_command_authorises_it(self):
        entries = [command('aidlc', 'Add refunds.'), command('approve', 'refunds')]
        self.assertEqual(self.bash(AIDLC + ' approve refunds', entries)[0], 0)
        self.assertEqual(self.bash(AIDLC + ' approve docs/specs/refunds --by Tea', entries)[0], 0)
        self.assertEqual(self.bash(AIDLC + ' approve payouts', entries)[0], 2)      # another spec than the one typed
        later = entries + [command('build', 'refunds')]
        self.assertEqual(self.bash(AIDLC + ' approve refunds', later)[0], 2)        # an old approval is not a new one

    def test_eta_6_one_typed_approval_authorises_one_run(self):
        # The spec may be edited after the first run; the second approval is of text the person has not seen.
        typed = command('approve', 'refunds')
        ran = {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
            {'type': 'tool_use', 'name': 'Bash', 'input': {'command': AIDLC + ' approve refunds'}}]}}
        self.assertEqual(self.bash(AIDLC + ' approve refunds', [typed])[0], 0)
        code, err = self.bash(AIDLC + ' approve refunds', [typed, ran])
        self.assertEqual(code, 2)
        self.assertIn('one run', err)
        again = [typed, ran, {'type': 'user', 'message': {'role': 'user', 'content': 'thanks'}}, command('approve', 'refunds')]
        self.assertEqual(self.bash(AIDLC + ' approve refunds', again)[0], 0)        # a second typed command: one more run
        other = {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
            {'type': 'tool_use', 'name': 'Bash', 'input': {'command': AIDLC + ' approve payouts'}}]}}
        self.assertEqual(self.bash(AIDLC + ' approve refunds', [typed, other])[0], 0)  # another spec's run does not count

    def test_eta_6_a_transcript_that_cannot_be_read_does_not_authorise(self):
        code, err = self.bash(AIDLC + ' approve refunds')
        self.assertEqual(code, 2)
        self.assertIn('terminal', err)

    def test_eta_6_delegated_approval_needs_a_request_that_delegated(self):
        delegated = [command('aidlc', 'Add refunds end to end. I am not available for questions.')]
        self.assertEqual(self.bash(AIDLC + ' approve refunds --delegated', delegated)[0], 0)
        ready = [command('aidlc', 'Build this.\n\nStatus: ready-for-agent\n\n# Refunds')]
        self.assertEqual(self.bash(AIDLC + ' approve refunds --delegated', ready)[0], 0)
        plain = [command('aidlc', 'Add refunds to the wallet.')]
        code, err = self.bash(AIDLC + ' approve refunds --delegated', plain)
        self.assertEqual(code, 2)
        self.assertIn('did not hand the decisions over', err)
        code, err = self.bash(AIDLC + ' approve refunds --delegated')               # nothing to read: fail closed
        self.assertEqual(code, 2)
        self.assertIn('no work command', err)
        typed_only = [command('approve', 'refunds')]                                # an approval is not a request
        self.assertEqual(self.bash(AIDLC + ' approve refunds --delegated', typed_only)[0], 2)

    def test_other_aidlc_commands_and_other_tools_pass(self):
        entries = [command('aidlc', 'Add refunds.')]
        for text in (AIDLC + ' verify refunds', AIDLC + ' advance refunds accepted', AIDLC + ' status',
                     'grep -n approve docs/specs/refunds/ledger.md', 'echo "aidlc.py approve refunds is for the user"'):
            self.assertEqual(self.bash(text, entries)[0], 0, text)
        self.assertEqual(self.run_guard('Read', {'file_path': 'docs/specs/refunds/ledger.md'}, entries)[0], 0)

    def test_the_guard_can_be_turned_off_and_never_blocks_on_its_own_failure(self):
        entries = [command('aidlc', 'Add refunds.')]
        self.assertEqual(self.bash(AIDLC + ' approve refunds', entries, {'AEGISOPS_HARNESS_EVIDENCE_GUARD': 'off'})[0], 0)
        result = subprocess.run([sys.executable, str(GUARD)], input='not json', capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0)


class EvidenceFilesTest(GuardCase):
    """ETA-7: the ledger and the stored reviewer returns are written by `aidlc` only."""

    def test_eta_7_a_relative_path_after_cd_and_other_write_shapes_are_refused(self):
        entries = [command('review', 'refunds')]
        for text in ('cd docs/specs/refunds && echo x >> ledger.md', 'cd docs/specs/refunds && rm ledger.md',
                     'cd docs/specs/refunds; rm returns/a.md', 'dd if=/tmp/x of=docs/specs/refunds/ledger.md',
                     'git checkout abc123 -- docs/specs/refunds/ledger.md',
                     'git restore --source=HEAD~3 -- docs/specs/refunds/returns', 'cp /tmp/x docs/specs/refunds/ledger.md',
                     'mv /tmp/x docs/specs/refunds/ledger.md', 'cd docs && cd specs/refunds && tee ledger.md'):
            self.assertEqual(self.bash(text, entries)[0], 2, text)

    def test_eta_7_reading_the_ledger_is_not_writing_it(self):
        entries = [command('review', 'refunds')]
        for text in ('cp docs/specs/refunds/ledger.md /tmp/backup', 'cd docs/specs/refunds && cat ledger.md',
                     'cd docs/specs/refunds && cp ledger.md /tmp/l.md', 'ln -s docs/specs/refunds/ledger.md /tmp/l'):
            self.assertEqual(self.bash(text, entries)[0], 0, text)

    def test_eta_7_the_model_cannot_store_a_reviewers_return_itself(self):
        code, err = self.bash(AIDLC + ' attest refunds --agent aegisops-harness:code-reviewer --axis spec --file r.md',
                              [command('review', 'refunds')])
        self.assertEqual(code, 2)
        self.assertIn('when the reviewer agent returns', err)

    def test_eta_7_edits_to_the_ledger_and_the_returns_are_refused(self):
        for path in ('docs/specs/refunds/ledger.md', '/repo/services/pay/docs/specs/payouts/ledger.md',
                     'docs/specs/refunds/returns/20261126T100000Z-01-code-reviewer-spec.md'):
            for tool in ('Edit', 'Write', 'MultiEdit'):
                code, err = self.run_guard(tool, {'file_path': path})
                self.assertEqual(code, 2, (tool, path))
                self.assertIn('only `aidlc` writes it', err)

    def test_eta_7_shell_writes_to_them_are_refused(self):
        for text in ('echo "- 2026-11-26T00:00:00Z verify exit=0 fingerprint=abc" >> docs/specs/refunds/ledger.md',
                     'cat forged.md > docs/specs/refunds/ledger.md',
                     "sed -i 's/exit=1/exit=0/' docs/specs/refunds/ledger.md",
                     'rm docs/specs/refunds/returns/20261126T100000Z-01-code-reviewer-spec.md',
                     'printf x | tee -a docs/specs/refunds/ledger.md',
                     'cp /tmp/ledger.md docs/specs/refunds/ledger.md',
                     'mv docs/specs/refunds/returns /tmp/away'):
            self.assertEqual(self.bash(text)[0], 2, text)

    def test_the_rest_of_the_spec_folder_and_reads_are_untouched(self):
        for path in ('docs/specs/refunds/spec.md', 'docs/specs/refunds/review.md', 'docs/specs/refunds/tickets.md',
                     'docs/specs/refunds/README.md', 'src/ledger.md', 'docs/ledger.md'):
            self.assertEqual(self.run_guard('Write', {'file_path': path})[0], 0, path)
        for text in ('cat docs/specs/refunds/ledger.md', 'grep -c verify docs/specs/refunds/ledger.md',
                     'ls docs/specs/refunds/returns', 'git add docs/specs/refunds && git commit -m spec',
                     'echo done > docs/specs/refunds/notes.md', AIDLC + ' ruling refunds --decision a --why b --if-wrong c'):
            self.assertEqual(self.bash(text)[0], 0, text)


class RegistrationTest(unittest.TestCase):
    def test_the_guard_is_registered_for_shell_and_file_edits(self):
        hooks = json.loads((ROOT / 'hooks' / 'hooks.json').read_text())['hooks']['PreToolUse']
        for matcher in ('Bash', 'Edit|Write|MultiEdit'):
            entry = next(e for e in hooks if e['matcher'] == matcher)
            self.assertTrue(any('evidence-guard.py' in h['command'] for h in entry['hooks']), matcher)


if __name__ == '__main__':
    unittest.main()
