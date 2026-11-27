"""hooks/record-returns.py stores what the review-stage reviewers returned (ETA-7). The session that was reviewed does
not write these files: the plugin does, when the reviewer agent returns."""
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_aidlc import Base, aidlc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOK = ROOT / 'hooks' / 'record-returns.py'
RETURN = '### Findings\n- [ ] S1 (must): RFD-1 — not rejected at src/x.py:3 (confidence: high)\n### Assessment\nStatus: BLOCKED\n'


class RecordReturnsTest(Base):
    def setUp(self):
        super().setUp()
        self.verified_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'verified')[0], 0)

    def returned(self, agent='aegisops-harness:code-reviewer', prompt='Review this change on axis spec.', response=None,
                 tool='Agent', env=None):
        if response is None:
            response = {'status': 'completed', 'agentId': 'a1', 'content': [{'type': 'text', 'text': RETURN}]}
        payload = {'session_id': 's1', 'cwd': str(self.repo), 'tool_name': tool,
                   'tool_input': {'subagent_type': agent, 'prompt': prompt, 'description': 'review'},
                   'tool_response': response}
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                              timeout=30, env=dict(os.environ, **(env or {})))

    def stored(self):
        folder = self.spec / 'returns'
        return sorted(folder.iterdir()) if folder.is_dir() else []

    def test_eta_7_a_reviewers_return_is_stored_verbatim_with_its_axis(self):
        result = self.returned()
        self.assertEqual(result.returncode, 0, result.stderr)
        (path,) = self.stored()
        meta, start = aidlc.parse_frontmatter(path.read_text())
        self.assertEqual((meta['agent'], meta['axis']), ('aegisops-harness:code-reviewer', 'spec'))
        self.assertEqual('\n'.join(path.read_text().split('\n')[start:]), RETURN)
        self.assertIn('returns/', json.loads(result.stdout)['hookSpecificOutput']['additionalContext'])

    def test_eta_7_axis_comes_from_the_dispatch_and_qa_is_its_own(self):
        self.returned(prompt='AXIS: standards\nReview the diff.')
        self.returned(prompt='Review this change on axis both (diff-only re-review).', response='plain text return\n')
        self.returned(agent='aegisops-harness:qa-subagent', prompt='QA the change.', response={'content': 'Verdict: GO\n'})
        self.returned(prompt='No axis named.', response={'content': [{'type': 'text', 'text': 'another return\n'}]},
                      tool='Task')
        axes = [aidlc.parse_frontmatter(p.read_text())[0]['axis'] for p in self.stored()]
        self.assertEqual(sorted(axes), ['both', 'both', 'qa', 'standards'])

    def test_other_agents_background_dispatches_and_other_stages_store_nothing(self):
        self.returned(agent='aegisops-harness:backend-engineer-subagent')
        self.returned(agent='general-purpose')
        self.returned(response={'status': 'async_launched', 'agentId': 'a1', 'outputFile': '/tmp/x'})
        self.returned(response={'status': 'completed', 'content': []})
        self.assertEqual(self.stored(), [])
        self.assertEqual(self.cli('advance', 'refunds', 'building', '--back', '--reason', 'rework')[0], 0)
        self.returned()                                               # a per-ticket review during the build stage
        self.assertEqual(self.stored(), [])

    def test_it_can_be_turned_off_and_never_fails_the_session(self):
        self.returned(env={'AEGISOPS_HARNESS_RETURNS': 'off'})
        self.assertEqual(self.stored(), [])
        result = subprocess.run([sys.executable, str(HOOK)], input='not json', capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, ''))

    def test_it_is_registered_for_the_subagent_tool(self):
        hooks = json.loads((ROOT / 'hooks' / 'hooks.json').read_text())['hooks']['PostToolUse']
        entry = next(e for e in hooks if e['matcher'] == 'Agent|Task')
        self.assertTrue(any('record-returns.py' in h['command'] for h in entry['hooks']))


if __name__ == '__main__':
    import unittest
    unittest.main()
