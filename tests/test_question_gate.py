import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / 'plugins' / 'aegisops-harness'
GATE = PLUGIN / 'hooks' / 'question-gate.py'


def command(name, args, uuid):
    text = (f'<command-message>aegisops-harness:{name}</command-message>\n<command-name>/aegisops-harness:{name}</command-name>\n'
            f'<command-args>{args}</command-args>')
    return {'type': 'user', 'uuid': uuid, 'message': {'role': 'user', 'content': text}}


def tool(name):
    return {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
        {'type': 'tool_use', 'id': 'x', 'name': name, 'input': {}}]}}


class QuestionGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(self.base))
        self.env.pop('AEGISOPS_HARNESS_QUESTION_GATE', None)

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self, entries, session='s1', tool_name='AskUserQuestion', env=None):
        transcript = self.base / 'transcript.jsonl'
        transcript.write_text('\n'.join(json.dumps(e) for e in entries) + '\n')
        payload = {'session_id': session, 'tool_name': tool_name, 'tool_input': {'questions': []},
                   'transcript_path': str(transcript)}
        result = subprocess.run([sys.executable, str(GATE)], input=json.dumps(payload), capture_output=True,
                                text=True, env=dict(self.env, **(env or {})))
        return result.returncode, result.stderr

    def test_plain_sessions_and_grilling_are_untouched(self):
        self.assertEqual(self.ask([{'type': 'user', 'message': {'content': 'add refunds'}}])[0], 0)
        self.assertEqual(self.ask([command('grilling', 'login rules', 'u1')])[0], 0)

    def test_delegated_input_blocks_every_question(self):
        for args in ('Build this. End to end, do not ask.', 'I am not available for questions.',
                     'Build it.\n\nStatus: ready-for-agent\n\n# Login'):
            entries = [command('aidlc', args, 'u1'), tool('mcp__plugin_operations_atlassian__search')]
            for _ in range(2):
                code, err = self.ask(entries)
                self.assertEqual(code, 2, args)
                self.assertIn('RISK-ACCEPTANCE NEEDED', err)

    def test_first_question_before_rovo_is_sent_back_once_per_command(self):
        entries = [command('aidlc', 'I approve all your assumptions: Login', 'u1'), tool('Read')]
        code, err = self.ask(entries)
        self.assertEqual(code, 2)
        self.assertIn('Rovo', err)
        self.assertEqual(self.ask(entries)[0], 0)  # retry passes: never stuck without Rovo
        entries.append(command('aidlc', 'login, next run', 'u2'))
        self.assertEqual(self.ask(entries)[0], 2)  # a new command run is checked again

    def test_question_after_rovo_passes(self):
        entries = [command('spec', 'Login', 'u1'), tool('mcp__claude_ai_Atlassian__searchConfluenceUsingCql')]
        self.assertEqual(self.ask(entries)[0], 0)

    def test_rovo_call_before_the_command_does_not_count(self):
        entries = [tool('mcp__plugin_operations_atlassian__search'), command('fix', 'bug', 'u1')]
        self.assertEqual(self.ask(entries)[0], 2)

    def test_off_switch_other_tools_and_bad_input_pass(self):
        entries = [command('aidlc', 'do not ask', 'u1')]
        self.assertEqual(self.ask(entries, env={'AEGISOPS_HARNESS_QUESTION_GATE': 'off'})[0], 0)
        self.assertEqual(self.ask(entries, tool_name='Bash')[0], 0)
        result = subprocess.run([sys.executable, str(GATE)], input='not json', capture_output=True, text=True,
                                env=self.env)
        self.assertEqual(result.returncode, 0)
        payload = {'session_id': 's', 'tool_name': 'AskUserQuestion', 'transcript_path': str(self.base / 'none')}
        result = subprocess.run([sys.executable, str(GATE)], input=json.dumps(payload), capture_output=True,
                                text=True, env=self.env)
        self.assertEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
