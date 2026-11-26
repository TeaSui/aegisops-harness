import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOK = ROOT / 'hooks' / 'autopilot.py'
SESSION_START = ROOT / 'hooks' / 'session-start'


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.home, self.repo = base / 'home', base / 'repo'
        self.home.mkdir()
        self.repo.mkdir()
        (self.repo / 'package.json').write_text('{}')

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, extra=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith('AEGISOPS_HARNESS_')}
        env['HOME'] = str(self.home)
        env.update(extra or {})
        return env

    def run_hook(self, mode, payload, env=None):
        payload = {'session_id': 's1', 'cwd': str(self.repo), **payload}
        return subprocess.run([sys.executable, str(HOOK), mode], input=json.dumps(payload),
                              env=self.env(env), capture_output=True, text=True, timeout=20)

    def context(self, result, event):
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return ''
        out = json.loads(result.stdout)
        self.assertEqual(out['hookSpecificOutput']['hookEventName'], event)
        return out['hookSpecificOutput']['additionalContext']


class NoPassiveActivationTest(HookCase):
    """AegisOps-Harness starts only from slash commands: no hook adds a note naming skills to a prompt or a tool result."""

    def test_prompt_hook_is_not_registered(self):
        hooks = json.loads((ROOT / 'hooks' / 'hooks.json').read_text())['hooks']
        self.assertNotIn('UserPromptSubmit', hooks)

    def test_prompt_mode_is_silent_even_for_workflow_words(self):
        for prompt in ('Add a refund endpoint that moves money', 'Fix the login bug', 'grill me', 'ship it'):
            result = self.run_hook('prompt', {'prompt': prompt})
            self.assertEqual((result.returncode, result.stdout.strip()), (0, ''), prompt)

    def test_tool_results_never_produce_a_note(self):
        for command, output in (('npm test', 'FAIL 1 failing'), ('git revert HEAD', ''), ('gh pr merge 1', '')):
            for _ in range(3):
                result = self.run_hook('post', {'tool_name': 'Bash', 'tool_input': {'command': command},
                                                'tool_response': {'stdout': output}})
                self.assertEqual((result.returncode, result.stdout.strip()), (0, ''), command)

    def test_every_skill_and_command_is_user_invoked_only(self):
        for path in sorted((ROOT / 'skills').glob('*/SKILL.md')) + sorted((ROOT / 'commands').glob('*.md')):
            head = path.read_text()[:1500]
            self.assertRegex(head, r'(?m)^disable-model-invocation:\s*true\s*$', str(path))


class VerifyGateTest(HookCase):
    def edit(self, path):
        return self.run_hook('post', {'tool_name': 'Edit', 'tool_input': {'file_path': str(self.repo / path)},
                                      'tool_response': {}})

    def bash(self, command, output=''):
        return self.run_hook('post', {'tool_name': 'Bash', 'tool_input': {'command': command},
                                      'tool_response': {'stdout': output}})

    def stop(self, active=False, env=None):
        return self.run_hook('stop', {'stop_hook_active': active}, env)

    def blocked(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return None
        out = json.loads(result.stdout)
        return out['reason'] if out.get('decision') == 'block' else None

    def test_blocks_stop_when_code_changed_after_the_last_test_run(self):
        self.edit('src/fee.ts')
        reason = self.blocked(self.stop())
        self.assertIsNotNone(reason)
        self.assertIn('src/fee.ts', reason)

    def test_test_run_after_the_edit_allows_stop(self):
        self.edit('src/fee.ts')
        self.bash('npm test', 'Tests: 3 passed')
        self.assertIsNone(self.blocked(self.stop()))

    def test_reminds_once_per_change_set(self):
        self.edit('src/fee.ts')
        self.assertIsNotNone(self.blocked(self.stop()))
        self.assertIsNone(self.blocked(self.stop()))

    def test_never_blocks_a_continuation(self):
        self.edit('src/fee.ts')
        self.assertIsNone(self.blocked(self.stop(active=True)))

    def test_mentioning_a_test_tool_does_not_count_as_a_test_run(self):
        self.edit('src/fee.ts')
        self.bash('npm install -D jest')
        self.assertIsNotNone(self.blocked(self.stop()))

    def test_a_write_chained_after_a_test_run_is_tracked(self):
        self.bash("npm test; sed -i 's/a/b/' src/app.py", 'Tests: 2 passed')
        self.assertIsNotNone(self.blocked(self.stop()))

    def test_concurrent_read_only_posts_keep_the_change_set(self):
        self.edit('src/fee.ts')
        payload = json.dumps({'session_id': 's1', 'cwd': str(self.repo), 'tool_name': 'Bash',
                              'tool_input': {'command': 'ls'}, 'tool_response': {}})
        procs = [subprocess.Popen([sys.executable, str(HOOK), 'post'], stdin=subprocess.PIPE, env=self.env(),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(16)]
        for proc in procs:
            proc.communicate(payload.encode())
        self.assertIsNotNone(self.blocked(self.stop()))

    def test_docs_and_config_edits_do_not_need_tests(self):
        self.edit('README.md')
        self.edit('config/app.yaml')
        self.assertIsNone(self.blocked(self.stop()))

    def test_no_test_setup_no_reminder(self):
        (self.repo / 'package.json').unlink()
        self.edit('src/fee.ts')
        self.assertIsNone(self.blocked(self.stop()))

    def test_can_be_turned_off(self):
        self.edit('src/fee.ts')
        self.assertIsNone(self.blocked(self.stop(env={'AEGISOPS_HARNESS_VERIFY_GATE': 'off'})))

    def test_reminders_are_capped_per_session(self):
        for name in ('a', 'b', 'c', 'd'):
            self.edit(f'src/{name}.ts')
            self.stop()
        self.edit('src/e.ts')
        self.assertIsNone(self.blocked(self.stop()))


class SubagentRulesTest(HookCase):
    def start(self, agent_type, env=None):
        return self.context(self.run_hook('subagent', {'agent_type': agent_type, 'agent_id': 'a1'}, env), 'SubagentStart')

    def test_implementers_get_the_house_rules(self):
        ctx = self.start('aegisops-harness:backend-engineer-subagent')
        for fragment in ('BLOCKED', 'requirement ID', 'tdd-gate', 'contracts/', 'do not dispatch'):
            self.assertIn(fragment, ctx)
        self.assertLess(len(ctx), 2000)

    def test_general_purpose_agents_get_them_too(self):
        self.assertIn('BLOCKED', self.start('general-purpose'))

    def test_read_only_built_ins_are_left_alone(self):
        for agent in ('Explore', 'claude-code-guide', 'statusline-setup'):
            self.assertEqual(self.start(agent), '', agent)

    def test_eta_14_note_opens_and_closes_with_the_same_tag(self):
        # 5.0.0 shipped <AegisOps-Harness> ... </aegisops-harness>: a mechanical rename that no test read.
        ctx = self.start('aegisops-harness:backend-engineer-subagent')
        self.assertRegex(ctx, r'(?s)\A<([\w-]+)>\n.*\n</\1>\Z')

class SessionSnapshotTest(HookCase):
    def start(self, env=None):
        env = self.env(env)
        env['PATH'] = '/usr/bin:/bin'  # no gitleaks on this PATH
        result = subprocess.run(['/bin/bash', str(SESSION_START)], input=json.dumps({'cwd': str(self.repo),
                                'source': 'startup', 'session_id': 's1'}), env=env, capture_output=True, text=True,
                                timeout=20, cwd=str(self.repo))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_bootstrap_still_injected(self):
        out = self.start()
        self.assertIn('<session-bootstrap>', out['hookSpecificOutput']['additionalContext'])

    def test_reports_active_specs_with_plan_progress(self):
        spec = self.repo / 'docs' / 'specs' / 'refund'
        spec.mkdir(parents=True)
        (spec / 'README.md').write_text('---\nstatus: accepted\ncontract: external\n---\n')
        (spec / 'plan.md').write_text('- [x] one\n- [ ] two\n- [ ] three\n')
        ctx = self.start()['hookSpecificOutput']['additionalContext']
        self.assertIn('docs/specs/refund', ctx)
        self.assertIn('1/3', ctx)
        self.assertIn('Next command (the user runs it): /aegisops-harness:plan', ctx)

    def test_spec_paths_are_resolved_from_the_repo_root(self):
        git_env = {**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True, env=git_env)
        spec = self.repo / 'docs' / 'specs' / 'refund'
        spec.mkdir(parents=True)
        (spec / 'README.md').write_text('---\nstatus: accepted\nkey: RFD\n---\n')
        (spec / 'plan.md').write_text('- [x] one\n- [ ] two\n')
        (self.repo / 'src').mkdir()
        env = self.env()
        env['PATH'] = '/usr/bin:/bin'
        result = subprocess.run(['/bin/bash', str(SESSION_START)], input=json.dumps({'cwd': str(self.repo / 'src')}),
                                env=env, capture_output=True, text=True, timeout=20, cwd=str(self.repo / 'src'))
        ctx = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
        self.assertIn('Spec docs/specs/refund at stage `accepted`, 1/2 tickets done', ctx)
        self.assertNotIn('src/docs', ctx)

    def test_missing_gitleaks_is_told_to_the_user_up_front(self):
        self.assertIn('gitleaks', self.start().get('systemMessage', ''))

    def enable_superpowers(self, local_override=None):
        settings = self.repo / '.claude'
        settings.mkdir(exist_ok=True)
        (settings / 'settings.json').write_text(json.dumps({'enabledPlugins': {
            'superpowers@anthropic-plugin-directory': True, 'aegisops-harness@AegisOps-Harness': True}}))
        if local_override is not None:
            (settings / 'settings.local.json').write_text(json.dumps({'enabledPlugins': {
                'superpowers@anthropic-plugin-directory': local_override}}))

    def test_old_gate_state_is_pruned(self):
        import time
        state = self.home / '.claude' / 'state' / 'tdd'
        state.mkdir(parents=True)
        old, new = state / 'old.json', state / 'new.json'
        old.write_text('{}')
        new.write_text('{}')
        stale = time.time() - 40 * 86400
        os.utime(old, (stale, stale))
        self.start()
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def hook_state_dirs(self):
        """STATE_DIR of every hook module, read with HOME pointing at the scratch home."""
        import importlib.util
        from unittest import mock
        found = {}
        with mock.patch.dict(os.environ, {'HOME': str(self.home)}):
            for path in sorted((ROOT / 'hooks').glob('*.py')):
                spec = importlib.util.spec_from_file_location('state_probe_' + path.stem.replace('-', '_'), path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'STATE_DIR'):
                    found[path.name] = pathlib.Path(module.STATE_DIR)
        return found

    def test_eta_14_every_hook_state_folder_is_pruned(self):
        # 5.0.0 renamed the folder the autopilot writes but not the one the prune walks (case differs), so on a
        # case-sensitive filesystem that state was never removed. Every hook that keeps per-session state is covered.
        import time
        folders = self.hook_state_dirs()
        self.assertIn('autopilot.py', folders)
        self.assertGreaterEqual(len(folders), 4, folders)
        stale = time.time() - 40 * 86400
        for folder in folders.values():
            self.assertTrue(str(folder).startswith(str(self.home)), folder)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'old.json').write_text('{}')
            (folder / 'new.json').write_text('{}')
            os.utime(folder / 'old.json', (stale, stale))
        self.start()
        for name, folder in folders.items():
            self.assertFalse((folder / 'old.json').exists(), name + ': old state not pruned in ' + str(folder))
            self.assertTrue((folder / 'new.json').exists(), name)

    def test_eta_14_snapshot_block_opens_and_closes_with_the_same_tag(self):
        import re
        spec = self.repo / 'docs' / 'specs' / 'refund'
        spec.mkdir(parents=True)
        (spec / 'README.md').write_text('---\nstatus: accepted\n---\n')
        ctx = self.start()['hookSpecificOutput']['additionalContext']
        block = re.search(r'(?s)<([\w-]+)>\nProject state at session start:.*?</([\w-]+)>', ctx)
        self.assertIsNotNone(block, ctx[-400:])
        self.assertEqual(block.group(1), block.group(2))

if __name__ == '__main__':
    unittest.main()
