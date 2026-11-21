"""Tests for the target-repository warnings in scripts/check-setup.py.

Every git call runs with GIT_CONFIG_GLOBAL=/dev/null and GIT_CONFIG_NOSYSTEM=1, so the
user's real global config and excludes file are never read or changed.
Run: python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'check-setup.py'
SPEC = importlib.util.spec_from_file_location('check_setup', SCRIPT)
check_setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_setup)

ISOLATED_ENV = {
    'GIT_CONFIG_GLOBAL': os.devnull,
    'GIT_CONFIG_NOSYSTEM': '1',
    'GIT_AUTHOR_NAME': 'test', 'GIT_AUTHOR_EMAIL': 'test@example.com',
    'GIT_COMMITTER_NAME': 'test', 'GIT_COMMITTER_EMAIL': 'test@example.com',
}


class ProjectWarningsTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, ISOLATED_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True, text=True)

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, *paths):
        self.git('add', *paths)
        self.git('commit', '-q', '-m', 'test')

    def warnings(self):
        top, found = check_setup.project_warnings(self.repo)
        self.assertEqual(self.repo, top)
        return found

    def assert_warns(self, fragment):
        found = self.warnings()
        self.assertTrue(any(fragment in w for w in found), '%r not in %r' % (fragment, found))

    def assert_silent(self, fragment):
        found = self.warnings()
        self.assertFalse(any(fragment in w for w in found), '%r unexpectedly in %r' % (fragment, found))

    def use_excludes_file(self, patterns):
        excludes = self.base / 'excludes'
        excludes.write_text(patterns)
        self.git('config', 'core.excludesFile', str(excludes))

    # CLAUDE.md tracked but empty at HEAD
    def test_empty_tracked_claude_md_warns(self):
        self.write('CLAUDE.md', '')
        self.commit('CLAUDE.md')
        self.write('CLAUDE.md', '# Rules\n')  # uncommitted content does not reach worktrees
        self.assert_warns('CLAUDE.md')

    def test_non_empty_claude_md_is_silent(self):
        self.write('CLAUDE.md', '# Rules\n')
        self.commit('CLAUDE.md')
        self.assert_silent('CLAUDE.md')

    def test_untracked_claude_md_is_silent(self):
        self.write('README.md', 'x\n')
        self.commit('README.md')
        self.assert_silent('CLAUDE.md')

    # .claude/rules untracked or ignored
    def test_ignored_rules_dir_warns(self):
        self.write('.gitignore', '.claude\n')
        self.write('.claude/rules/backward-compatible.md', '# rule\n')
        self.commit('.gitignore')
        self.assert_warns('.claude/rules/ is ignored')

    def test_untracked_rules_dir_warns(self):
        self.write('.claude/rules/backward-compatible.md', '# rule\n')
        self.write('README.md', 'x\n')
        self.commit('README.md')
        self.assert_warns('.claude/rules/ is untracked')

    def test_tracked_rules_dir_is_silent(self):
        self.write('.claude/rules/backward-compatible.md', '# rule\n')
        self.commit('.claude/rules/backward-compatible.md')
        self.assert_silent('.claude/rules')

    # docs/ ignored, e.g. by a personal core.excludesFile
    def test_docs_ignored_by_excludes_file_warns(self):
        self.use_excludes_file('docs/*\n')
        self.assert_warns('docs/')

    def test_docs_not_ignored_is_silent(self):
        self.use_excludes_file('*.log\n')
        self.assert_silent('docs/')

    def test_repo_negation_overrides_excludes_file(self):
        self.use_excludes_file('docs/*\n')
        self.write('.gitignore', '!/docs/\n!/docs/**\n')
        self.assert_silent('docs/')

    def test_not_a_git_repo_returns_nothing(self):
        outside = self.base / 'plain'
        outside.mkdir()
        self.assertEqual((None, []), check_setup.project_warnings(outside))


class CheckSetupCliTest(unittest.TestCase):
    def test_project_warnings_do_not_fail_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            env = dict(os.environ, **ISOLATED_ENV)
            subprocess.run(['git', 'init', '-q'], cwd=repo, check=True, env=env)
            (repo / 'CLAUDE.md').write_text('')
            subprocess.run(['git', 'add', 'CLAUDE.md'], cwd=repo, check=True, env=env)
            subprocess.run(['git', 'commit', '-q', '-m', 'empty'], cwd=repo, check=True, env=env)
            result = subprocess.run([sys.executable, str(SCRIPT), '--project', str(repo)],
                                    capture_output=True, text=True, env=env, timeout=120)
        report = json.loads(result.stdout)
        self.assertEqual('PASS', report['status'], report['errors'])
        self.assertEqual(0, result.returncode)
        self.assertTrue(any('CLAUDE.md' in w for w in report['warnings']), report['warnings'])



class PluginIntegrityTest(unittest.TestCase):
    """check-setup.py run against a scratch copy of the plugin with one defect injected."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'plugin'
        import shutil
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('.git', '__pycache__', '.idea', 'node_modules'))

    def check(self):
        result = subprocess.run([sys.executable, str(self.root / 'scripts' / 'check-setup.py'), '--root',
                                 str(self.root), '--project', str(self.root)], capture_output=True, text=True,
                                timeout=60)
        return json.loads(result.stdout)

    def test_clean_copy_passes(self):
        self.assertEqual(self.check()['errors'], [])

    def test_dangling_skill_reference_fails(self):
        rule = self.root / 'rules' / 'agents.md'
        rule.write_text(rule.read_text() + '\nThen run /tea-sdlc:no-such-skill.\n')
        (self.root / 'hooks' / 'autopilot.py').write_text(
            (self.root / 'hooks' / 'autopilot.py').read_text() + '\n# see tea-sdlc:missing-command\n')
        errors = ' '.join(self.check()['errors'])
        self.assertIn('tea-sdlc:missing-command', errors)
        self.assertIn('no-such-skill', errors)

    def test_model_invocable_skill_fails(self):
        # tea-sdlc runs only from slash commands: a skill the model could load on its own is an error.
        skill = self.root / 'skills' / 'plan' / 'SKILL.md'
        skill.write_text(skill.read_text().replace('disable-model-invocation: true\n', '', 1))
        self.assertIn('skills/plan/SKILL.md: needs disable-model-invocation: true', ' '.join(self.check()['errors']))

    def test_bare_agent_name_fails(self):
        # Claude Code registers plugin agents as tea-sdlc:<name>; a bare subagent_type is "not found".
        rule = self.root / 'rules' / 'agents.md'
        rule.write_text(rule.read_text() + '\nDispatch `backend-engineer-subagent` for the API.\n')
        errors = ' '.join(self.check()['errors'])
        self.assertIn('rules/agents.md', errors)
        self.assertIn('must be named tea-sdlc:backend-engineer-subagent', errors)

    def test_namespaced_agent_name_and_agent_file_paths_pass(self):
        rule = self.root / 'rules' / 'agents.md'
        rule.write_text(rule.read_text() + '\nDispatch `tea-sdlc:qa-subagent`; template '
                        'skills/review/code-reviewer.md.\n')
        self.assertEqual(self.check()['errors'], [])

    def test_stale_map_and_unphased_skill_fail(self):
        (self.root / 'HOW-IT-WORKS.md').write_text('# old\n')
        self.assertIn('HOW-IT-WORKS.md is stale', ' '.join(self.check()['errors']))
        subprocess.run([sys.executable, str(self.root / 'scripts' / 'map.py')], check=True, capture_output=True)
        new = self.root / 'skills' / 'brand-new' / 'SKILL.md'
        new.parent.mkdir()
        new.write_text('---\nname: brand-new\ndescription: Use when testing.\n---\n# x\n')
        self.assertIn('skills in no phase', ' '.join(self.check()['errors']))

    def test_hook_with_syntax_error_fails(self):
        (self.root / 'hooks' / 'broken.py').write_text('def oops(:\n')
        self.assertIn('hooks/broken.py', ' '.join(self.check()['errors']))

    def test_each_root_is_checked_on_its_own(self):
        rule = self.root / 'rules' / 'agents.md'
        rule.write_text(rule.read_text() + '\nThen run /tea-sdlc:no-such-skill.\n')
        probe = (
            'import importlib.util, json, sys, io, contextlib\n'
            'spec = importlib.util.spec_from_file_location("cs", sys.argv[1]); m = importlib.util.module_from_spec(spec)\n'
            'spec.loader.exec_module(m)\n'
            'for root in sys.argv[2:]:\n'
            '    sys.argv = ["x", "--root", root, "--project", root]; out = io.StringIO()\n'
            '    with contextlib.redirect_stdout(out): m.main()\n'
            '    print(json.dumps(json.loads(out.getvalue())["errors"]))\n')
        result = subprocess.run([sys.executable, '-c', probe, str(ROOT / 'scripts' / 'check-setup.py'), str(ROOT),
                                 str(self.root)], capture_output=True, text=True, timeout=120)
        first, second = [json.loads(line) for line in result.stdout.splitlines()[-2:]]
        self.assertEqual(first, [])
        self.assertIn('no-such-skill', ' '.join(second))

    def test_check_setup_does_not_touch_the_real_state_dir(self):
        home = self.root.parent / 'home'
        stale = home / '.claude' / 'state' / 'tdd' / 'old.json'
        stale.parent.mkdir(parents=True)
        stale.write_text('{}')
        os.utime(stale, (0, 0))
        subprocess.run([sys.executable, str(self.root / 'scripts' / 'check-setup.py'), '--root', str(self.root),
                        '--project', str(self.root)], capture_output=True, text=True, timeout=60,
                       env={**os.environ, 'HOME': str(home)})
        self.assertTrue(stale.exists())


    def test_bundled_file_ignored_by_git_fails(self):
        # Seen for real: a global `cdk*` exclude kept skills/cdk-testing out of every release.
        env = {**os.environ, **ISOLATED_ENV}
        excludes = self.root.parent / 'excludes'
        excludes.write_text('cdk*\n')
        for args in (['init', '-q'], ['config', 'core.excludesFile', str(excludes)]):
            subprocess.run(['git', *args], cwd=self.root, env=env, check=True, capture_output=True)
        gitignore = self.root / '.gitignore'
        gitignore.write_text('\n'.join(l for l in gitignore.read_text().splitlines() if 'cdk-testing' not in l) + '\n')
        result = subprocess.run([sys.executable, str(self.root / 'scripts' / 'check-setup.py'), '--root', str(self.root),
                                 '--project', str(self.root)], capture_output=True, text=True, timeout=60, env=env)
        self.assertIn('skills/cdk-testing/SKILL.md', ' '.join(json.loads(result.stdout)['errors']))


if __name__ == '__main__':
    unittest.main()
