"""hooks/ship-gate.py: `gh pr merge` is blocked while the branch's active spec has not passed the `shipped` gate."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOK = ROOT / 'hooks' / 'ship-gate.py'
GIT_ENV = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 't',
           'GIT_AUTHOR_EMAIL': 't@e', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@e'}


class ShipGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.home, self.repo = base / 'home', base / 'repo'
        self.home.mkdir()
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'main')
        (self.repo / 'a.txt').write_text('x')
        self.git('add', '-A')
        self.git('commit', '-qm', 'base')
        self.git('checkout', '-qb', 'feat/refunds')
        # A fake gh: `gh pr view 42 …` prints the head branch; `gh pr checks` fails (no PR) so gates fall back.
        self.gh = base / 'gh'
        self.gh.write_text('#!/bin/sh\ncase "$*" in\n  *"pr view 42"*) echo feat/refunds ;;\n'
                           '  *"pr view 7"*) echo feat/other ;;\n  *) exit 1 ;;\nesac\n')
        self.gh.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True, env={**os.environ, **GIT_ENV})

    def spec(self, status, branch='feat/refunds', slug='refunds'):
        folder = self.repo / 'docs' / 'specs' / slug
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'README.md').write_text(f'---\nstatus: {status}\nkey: RFD\nbranch: {branch}\n---\n# Refunds\n')
        return folder

    def run_hook(self, command, env=None):
        payload = {'session_id': 's1', 'cwd': str(self.repo), 'tool_name': 'Bash', 'tool_input': {'command': command}}
        clean = {k: v for k, v in os.environ.items() if not k.startswith('AEGISOPS_HARNESS_')}
        full_env = {**clean, **GIT_ENV, 'HOME': str(self.home), 'AIDLC_GH': str(self.gh), **(env or {})}
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), env=full_env,
                              capture_output=True, text=True, timeout=60)

    def test_merge_of_a_branch_whose_spec_is_not_shipped_is_blocked(self):
        self.spec('reviewed')
        result = self.run_hook('gh pr merge --squash')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('docs/specs/refunds', result.stderr)
        self.assertIn('shipped', result.stderr)
        self.assertIn('ship.md', result.stderr)

    def test_shipped_status_alone_is_not_enough(self):
        # The gate re-checks the evidence; a README that only claims `shipped` does not merge.
        self.spec('shipped')
        self.assertEqual(self.run_hook('gh pr merge --squash').returncode, 2)

    def test_pr_number_resolves_to_its_head_branch(self):
        self.spec('building')
        self.assertEqual(self.run_hook('gh pr merge 42 --merge').returncode, 2)
        self.assertEqual(self.run_hook('gh pr merge 7 --merge').returncode, 0)

    def test_branch_without_a_spec_is_not_gated(self):
        self.spec('building', branch='feat/elsewhere')
        self.assertEqual(self.run_hook('gh pr merge').returncode, 0)

    def test_other_commands_and_finished_specs_pass(self):
        self.spec('implemented')
        self.assertEqual(self.run_hook('gh pr merge').returncode, 0)
        self.spec('building', slug='other')
        self.assertEqual(self.run_hook('gh pr view 42').returncode, 0)
        self.assertEqual(self.run_hook('git status').returncode, 0)

    def test_off_switch(self):
        self.spec('reviewed')
        self.assertEqual(self.run_hook('gh pr merge', {'AEGISOPS_HARNESS_SHIP_GATE': 'off'}).returncode, 0)

    def test_bad_input_fails_open(self):
        result = subprocess.run([sys.executable, str(HOOK)], input='nope', capture_output=True, text=True,
                                env={**os.environ, 'HOME': str(self.home)})
        self.assertEqual(result.returncode, 0)



# End-to-end cases on a spec that really went through the lifecycle (builders from test_aidlc).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_aidlc import Base as LifecycleBase  # noqa: E402


class ShipGateLifecycleTest(LifecycleBase):
    def merge(self, command='gh pr merge --squash', env=None):
        payload = {'tool_name': 'Bash', 'cwd': str(self.repo), 'tool_input': {'command': command}}
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                              timeout=120, env={**os.environ, **(env or {})})

    def shipped(self):
        self.shipped_ready()
        self.git('add', '-A')
        self.git('commit', '-qm', 'refunds')
        code, out, err = self.cli('advance', 'refunds', 'shipped')
        self.assertEqual(code, 0, out + err)
        self.git('add', '-A')
        self.git('commit', '-qm', 'ship record')

    def test_shipped_spec_merges(self):
        self.shipped()
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_code_changed_after_shipping_is_blocked(self):
        # H2: a shipped spec is re-checked; code edited after the review must not merge.
        self.shipped()
        self.write('src/refunds/model.py', 'def refund(amount):\n    return -amount\n')
        self.git('commit', '-qam', 'sneaky change')
        result = self.merge()
        self.assertEqual(result.returncode, 2)
        self.assertIn('docs/specs/refunds', result.stderr)

    def test_abandoned_spec_blocks_the_merge_of_its_branch(self):
        self.shipped_ready()
        self.cli('advance', 'refunds', 'abandoned', '--reason', 'superseded by a vendor feature')
        self.git('add', '-A')
        self.git('commit', '-qm', 'abandon')
        result = self.merge()
        self.assertEqual(result.returncode, 2)
        self.assertIn('abandoned', result.stderr)

    def test_merging_another_branch_checks_that_branch(self):
        # H3: from main, `gh pr merge feat/refunds` must evaluate the spec on feat/refunds, not main's tree.
        self.verified_ready()
        self.git('add', '-A')
        self.git('commit', '-qm', 'refunds wip')
        self.git('checkout', '-q', 'main')
        result = self.merge('gh pr merge feat/refunds --squash')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('docs/specs/refunds', result.stderr)
        self.assertEqual(self.git('worktree', 'list').count('\n'), 0)  # the temporary worktree is gone

    def test_non_literal_target_is_blocked(self):
        self.shipped()
        result = self.merge('PR=42; gh pr merge "$PR" --squash')
        self.assertEqual(result.returncode, 2)
        self.assertIn('literal', result.stderr)


if __name__ == '__main__':
    unittest.main()
