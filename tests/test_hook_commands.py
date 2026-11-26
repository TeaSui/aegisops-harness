"""The secret, PR and merge gates recognise the command, not one spelling of it (ETA-8).

Proof E of the assessment: each gate blocked its canonical command (`git commit`, `gh pr create`, `gh pr merge`) and
let an equivalent one through (`git -C . commit`, `/usr/bin/git push`, `gh api …/pulls`, `gh api -X PUT …/merge`), and
no gate saw a pull request opened or merged through a GitHub MCP tool.
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

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / 'hooks'
GIT_ENV = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 't',
           'GIT_AUTHOR_EMAIL': 't@e', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@e'}
# Assembled here so that no file in the repository holds a token-shaped string (the plugin's own gate scans pushes).
SECRET = 'github_token = "%s"\n' % ('gh' + 'p_' + '1234567890abcdefghijklmnopqrstuvwxyzAB')


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_') + '_under_test', HOOKS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inv = load('invocations')


class ParsingTest(unittest.TestCase):
    def subs(self, command):
        return [call['sub'] for call in inv.git_calls(command)]

    def test_eta_8_git_subcommand_is_found_behind_options_paths_and_wrappers(self):
        for command in ('git commit -m x', 'git -C . commit -m x', 'git -c user.name=a commit -m x',
                        '/usr/bin/git commit', '"git" commit', 'env GIT_TRACE=1 git commit', 'FOO=1 git commit',
                        'command git commit', 'sudo -u me git commit', 'git --no-pager -C sub commit',
                        'git --git-dir=.git --work-tree=. commit', 'bash -c "git commit -m x"',
                        "sh -c 'cd a && git commit -m x'", 'eval "git commit -m x"', 'echo $(git commit -m x)',
                        'echo `git commit -m x`', 'cd repo && git commit', 'git status\ngit commit -m x',
                        'git add -A; git commit -qm "a && b"', 'time git commit', 'xargs git commit'):
            self.assertEqual(self.subs(command)[-1:], ['commit'], command)

    def test_eta_8_text_that_only_mentions_git_is_not_a_git_command(self):
        for command in ('echo "git commit"', 'grep -r "git push" docs', 'git log --grep commit',
                        'git config alias.commit x', 'cat commit', 'legit commit', 'git stash push'):
            self.assertNotIn('commit', self.subs(command), command)
            self.assertNotIn('push', [s for s in self.subs(command) if command != 'git stash push'], command)
        self.assertEqual(self.subs('git stash push'), ['stash'])

    def test_eta_8_directory_of_a_git_call(self):
        (call,) = inv.git_calls('git -C services/pay -c a=b commit -am "x y"')
        self.assertEqual((call['sub'], call['dir'], call['args']), ('commit', 'services/pay', ['-am', 'x y']))

    def test_eta_8_pull_request_creation_in_every_spelling(self):
        for command in ('gh pr create --fill', 'gh pr -R o/r create', 'cd x && gh pr create',
                        'gh api repos/o/r/pulls -f title=t -f head=b -f base=main',
                        'gh api --method POST /repos/o/r/pulls --input body.json',
                        'gh api -X POST repos/o/r/pulls', "gh api graphql -f query='mutation { createPullRequest(input: {}) { clientMutationId } }'",
                        'python3 scripts/pr.py create --title t', 'hub pull-request -m t',
                        'curl -X POST https://api.github.com/repos/o/r/pulls -d @body.json',
                        'curl -s -u x https://api.bitbucket.org/2.0/repositories/w/r/pullrequests -d @b.json'):
            self.assertTrue(inv.opens_pull_request(command), command)
        for command in ('gh pr list', 'gh pr view 7', 'gh api repos/o/r/pulls', 'gh api repos/o/r/pulls/7',
                        'gh api repos/o/r/pulls/7/comments -f body=x', 'echo "gh pr create"',
                        'curl https://api.github.com/repos/o/r/pulls'):
            self.assertFalse(inv.opens_pull_request(command), command)

    def test_eta_8_pull_request_merge_in_every_spelling(self):
        cases = {'gh pr merge --squash': None, 'gh pr merge 42 --merge': '42', 'gh pr merge feat/x': 'feat/x',
                 'gh pr merge https://github.com/o/r/pull/9 --auto': 'https://github.com/o/r/pull/9',
                 'gh api -X PUT repos/o/r/pulls/42/merge': '42',
                 'gh api --method PUT /repos/o/r/pulls/42/merge -f merge_method=squash': '42',
                 "gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'": '$',
                 'python3 scripts/pr.py merge 42': '42',
                 'curl -X PUT https://api.github.com/repos/o/r/pulls/42/merge': '42',
                 'curl -X POST https://api.bitbucket.org/2.0/repositories/w/r/pullrequests/42/merge': '42',
                 'gh pr merge $PR': '$'}
        for command, target in cases.items():
            self.assertEqual(inv.merges_pull_request(command), (True, target), command)
        for command in ('gh pr view 42', 'gh api repos/o/r/pulls/42/merge', 'git merge feat/x', 'echo gh pr merge'):
            self.assertEqual(inv.merges_pull_request(command)[0], False, command)


class GateCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = pathlib.Path(tmp.name).resolve()
        self.home, self.repo, self.bin = self.base / 'home', self.base / 'repo', self.base / 'bin'
        for folder in (self.home, self.repo, self.bin):
            folder.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('AEGISOPS_HARNESS_')}
        self.env.update(GIT_ENV, HOME=str(self.home))
        self.git('init', '-q', '-b', 'main')
        (self.repo / 'a.txt').write_text('x\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'base')

    def git(self, *args, cwd=None):
        return subprocess.run(['git', *args], cwd=cwd or self.repo, check=True, capture_output=True, text=True,
                              env=self.env).stdout.strip()

    def hook(self, name, tool, tool_input, env=None, cwd=None):
        payload = {'session_id': 's1', 'cwd': str(cwd or self.repo), 'tool_name': tool, 'tool_input': tool_input}
        return subprocess.run([sys.executable, str(HOOKS / name)], input=json.dumps(payload), capture_output=True,
                              text=True, timeout=120, env=dict(self.env, **(env or {})))

    def bash(self, name, command, env=None):
        return self.hook(name, 'Bash', {'command': command}, env)


class SecurityGateTest(GateCase):
    """The scanner is a stand-in that records how it was called; real gitleaks is used further down when installed."""

    def setUp(self):
        super().setUp()
        self.log = self.base / 'gitleaks.log'
        fake = self.bin / 'gitleaks'
        fake.write_text('#!/bin/sh\nprintf "%s|%s\\n" "$PWD" "$*" >> "{}"\nexit ${{FAKE_GITLEAKS_EXIT:-0}}\n'.format(self.log))
        fake.chmod(0o755)
        self.env['PATH'] = str(self.bin) + os.pathsep + self.env['PATH']

    def scans(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_eta_8_proof_e_equivalent_commits_and_pushes_are_scanned(self):
        for command in ('git commit -m x', 'git -C . commit -m x', 'git -c user.name=a push origin main',
                        '/usr/bin/git push origin main', 'bash -c "git commit -m x"', 'git add -A && git commit -m x'):
            before = len(self.scans())
            result = self.bash('security-gate.py', command)
            self.assertEqual(result.returncode, 0, command + result.stderr)
            self.assertGreater(len(self.scans()), before, command + ': not scanned')

    def test_eta_8_a_finding_blocks_every_spelling(self):
        for command in ('git commit -m x', 'git -C . commit -m x', '/usr/bin/git push origin main'):
            result = self.bash('security-gate.py', command, {'FAKE_GITLEAKS_EXIT': '1'})
            self.assertEqual(result.returncode, 2, command)
            self.assertIn('potential secret', result.stderr)

    def test_eta_8_the_scan_runs_where_the_git_command_runs(self):
        nested = self.repo / 'services' / 'pay'
        nested.mkdir(parents=True)
        self.bash('security-gate.py', 'git -C services/pay commit -m x')
        self.assertTrue(self.scans()[-1].startswith(str(nested) + '|'), self.scans())

    def test_commit_all_also_scans_what_is_not_staged(self):
        # `git commit -a` commits tracked changes that were never staged: a staged-only scan does not see them.
        for command in ('git commit -am x', 'git commit --all -m x', 'git commit -qam "x"', 'git commit -m x a.txt'):
            self.log.write_text('')
            self.bash('security-gate.py', command)
            modes = [line.split('|', 1)[1] for line in self.scans()]
            self.assertTrue(any('--staged' in mode for mode in modes), command)
            self.assertTrue(any('--pre-commit' in mode and '--staged' not in mode for mode in modes), command)
        self.log.write_text('')
        self.bash('security-gate.py', 'git commit -m "a plain commit"')
        self.assertEqual(len(self.scans()), 1)

    def test_commit_then_push_scans_both(self):
        self.bash('security-gate.py', 'git commit -m x && git push')
        modes = ' '.join(self.scans())
        self.assertIn('--staged', modes)
        self.assertIn('--log-opts', modes)

    def test_first_push_of_a_branch_scans_what_no_remote_has(self):
        self.git('checkout', '-q', '-b', 'feat/new')
        self.bash('security-gate.py', 'git push -u origin feat/new')
        self.assertIn('--log-opts=HEAD --not --remotes', self.scans()[-1])
        origin = self.base / 'origin.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(origin)], check=True)
        self.git('remote', 'add', 'origin', str(origin))
        self.git('push', '-q', '-u', 'origin', 'feat/new')
        self.bash('security-gate.py', 'git push')
        self.assertIn('--log-opts=@{u}..HEAD', self.scans()[-1])

    def test_no_scanner_blocks_and_other_commands_pass_untouched(self):
        self.assertEqual(self.bash('security-gate.py', 'git status && echo "git commit"').returncode, 0)
        self.assertEqual(self.scans(), [])
        (self.bin / 'gitleaks').unlink()
        env = {'PATH': str(self.bin) + os.pathsep + '/usr/bin:/bin'}
        self.assertEqual(self.bash('security-gate.py', 'git -C . commit -m x', env).returncode, 2)


@unittest.skipUnless(shutil.which('gitleaks'), 'needs gitleaks')
class RealGitleaksTest(GateCase):
    def test_first_push_of_a_clean_new_branch_is_allowed(self):
        # 5.0.0 scanned `@{u}..HEAD`; a new branch has no upstream, gitleaks exited 1 and the gate said
        # "gitleaks found a potential secret" for a clean branch.
        origin = self.base / 'origin.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(origin)], check=True)
        self.git('remote', 'add', 'origin', str(origin))
        self.git('push', '-q', '-u', 'origin', 'main')
        self.git('checkout', '-q', '-b', 'feat/new')
        (self.repo / 'a.txt').write_text('x\ny\n')
        self.git('commit', '-qam', 'clean change')
        result = self.bash('security-gate.py', 'git push -u origin feat/new')
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.repo / 'cfg.py').write_text(SECRET)
        self.git('add', '-A')
        self.git('commit', '-qm', 'oops')
        self.assertEqual(self.bash('security-gate.py', 'git -C . push -u origin feat/new').returncode, 2)

    def test_a_secret_in_an_unstaged_tracked_file_blocks_commit_all(self):
        with open(self.repo / 'a.txt', 'a') as handle:
            handle.write(SECRET)
        self.assertEqual(self.bash('security-gate.py', 'git commit -m "staged only"').returncode, 0)
        result = self.bash('security-gate.py', 'git commit -am "everything"')
        self.assertEqual(result.returncode, 2)
        self.assertIn('potential secret', result.stderr)


class PullRequestGateTest(GateCase):
    def setUp(self):
        super().setUp()
        self.git('checkout', '-q', '-b', 'feat/z')
        (self.repo / 'b.txt').write_text('y\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'work')

    def record_review(self):
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'mark-pr-review.py'), '--reviewer', 'code-review',
                        '--open-findings', '0'], cwd=self.repo, check=True, capture_output=True, env=self.env)

    def test_eta_8_proof_e_the_api_form_is_gated_like_gh_pr_create(self):
        for command in ('gh pr create --fill', 'gh api repos/o/r/pulls -f title=t -f head=feat/z -f base=main',
                        'curl -X POST https://api.github.com/repos/o/r/pulls -d @body.json'):
            result = self.bash('pr-review-gate.py', command)
            self.assertEqual(result.returncode, 2, command)
            self.assertIn('no pre-PR review recorded', result.stderr)
        self.assertEqual(self.bash('pr-review-gate.py', 'gh api repos/o/r/pulls').returncode, 0)  # a read
        self.record_review()
        self.assertEqual(self.bash('pr-review-gate.py', 'gh api repos/o/r/pulls -f title=t').returncode, 0)

    def test_eta_8_an_mcp_pull_request_is_gated(self):
        tool, args = 'mcp__github__create_pull_request', {'owner': 'o', 'repo': 'r', 'head': 'feat/z', 'base': 'main',
                                                          'title': 't'}
        result = self.hook('pr-review-gate.py', tool, args)
        self.assertEqual(result.returncode, 2)
        self.assertIn('no pre-PR review recorded', result.stderr)
        self.record_review()
        self.assertEqual(self.hook('pr-review-gate.py', tool, args).returncode, 0)
        self.assertEqual(self.hook('pr-review-gate.py', 'mcp__plugin_engineering_github__create_pull_request',
                                   dict(args, head='o:feat/z')).returncode, 0)
        other = self.hook('pr-review-gate.py', tool, dict(args, head='feat/somewhere-else'))
        self.assertEqual(other.returncode, 2)
        self.assertIn('check out feat/somewhere-else', other.stderr)
        self.assertEqual(self.hook('pr-review-gate.py', 'mcp__github__list_pull_requests', args).returncode, 0)

    def test_eta_8_matchers_route_the_mcp_tools_to_the_gates(self):
        import re
        hooks = json.loads((HOOKS / 'hooks.json').read_text())['hooks']['PreToolUse']

        def gates_for(tool):
            names = []
            for entry in hooks:
                matcher = entry['matcher']
                plain = re.fullmatch(r'[\w ,|-]+', matcher)       # letters, digits, _ - space , | : exact names
                hit = tool in re.split(r'[|,]\s*', matcher) if plain else re.search(matcher, tool)
                if hit:
                    names += [h['command'].split('/hooks/')[1].split('.py')[0] for h in entry['hooks']]
            return names

        self.assertIn('pr-review-gate', gates_for('mcp__github__create_pull_request'))
        self.assertIn('pr-review-gate', gates_for('mcp__plugin_engineering_github__create_pull_request'))
        self.assertIn('ship-gate', gates_for('mcp__github__merge_pull_request'))
        self.assertIn('ship-gate', gates_for('mcp__github__enable_pr_auto_merge'))
        self.assertEqual(gates_for('mcp__github__list_pull_requests'), [])
        self.assertIn('security-gate', gates_for('Bash'))


if __name__ == '__main__':
    unittest.main()
