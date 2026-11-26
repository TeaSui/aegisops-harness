#!/usr/bin/env python3
"""PreToolUse gate for Bash: block git commit/push unless gitleaks reports no secrets.

Fails closed: missing gitleaks, scanner errors, or unreadable hook input block the command.
The git call is read from the command (hooks/invocations.py): `git -C dir commit`, `/usr/bin/git push`,
`bash -c "git commit"`, `if …; then git commit; fi` are scanned, in the folder the call runs in. What the parser does
not know (`chronic git push`) falls to a text match on the unquoted command, which scans everything a commit or a
push could take. Text that mentions a commit inside a string or a written file (`echo "run git commit"`) is no commit.
  commit   the staged content; with -a/--all or paths on the line, also tracked changes that were never staged.
  push     the commits the upstream does not have; on a branch without an upstream, the commits no remote has
           (`@{u}` does not exist there, and 5.0.0 reported that scanner error as a secret on every first push).
Not covered: other refs named on the push line, aliases, and commits made by another tool; CI is the backstop.
"""
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
GIT_COMMIT = re.compile(r'(^|[;&|\s])git\s+commit\b')  # the 5.0.0 text match: the floor under the parser
GIT_PUSH = re.compile(r'(^|[;&|\s])git\s+push\b')
BASE = ['gitleaks', 'git', '--redact', '--no-banner']
SCAN_ERROR = re.compile(r'failed to scan|partial scan', re.I)


def deny(reason):
    sys.stderr.write(reason + '\n')
    sys.exit(2)


def invocations():
    spec = importlib.util.spec_from_file_location('aegisops_harness_invocations', HERE / 'invocations.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def calls_in(command):
    """[{sub, args, dir, worktree}] for the commits and pushes in a command. The parser reads them; a text match on
    the unquoted command is the floor for each kind the parser did not find. The floor cannot read arguments, so its
    commit scans staged and unstaged changes alike."""
    try:
        inv = invocations()
        found = [dict(call, worktree=call['sub'] == 'commit' and inv.commit_takes_worktree(call['args']))
                 for call in inv.git_calls(command) if call['sub'] in ('commit', 'push')]
        text = inv.unquoted(command)
    except Exception:  # the parser itself failed: the whole text is the floor
        found, text = [], command
    seen = {call['sub'] for call in found}
    if 'commit' not in seen and GIT_COMMIT.search(text):
        found.append({'sub': 'commit', 'args': [], 'dir': None, 'worktree': True})
    if 'push' not in seen and GIT_PUSH.search(text):
        found.append({'sub': 'push', 'args': [], 'dir': None, 'worktree': False})
    return found


def folder_of(call, cwd):
    if call['dir'] and cwd:
        target = os.path.normpath(os.path.join(cwd, call['dir']))
        if os.path.isdir(target):
            return target
    return cwd or None


def push_range(cwd):
    """What a push is about to publish: the commits its upstream lacks, or, without one, the commits no remote has."""
    try:
        upstream = subprocess.run(['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'], cwd=cwd,
                                  capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return 'HEAD --not --remotes'
    return '@{u}..HEAD' if upstream.returncode == 0 else 'HEAD --not --remotes'


def scans_for(call, cwd):
    if call['sub'] == 'push':
        return [BASE + ['--log-opts=' + push_range(cwd)]]
    scans = [BASE + ['--pre-commit', '--staged']]
    if call['worktree']:
        scans.append(BASE + ['--pre-commit'])
    return scans


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        deny('security-gate: unreadable hook input; blocking as a precaution.')

    if payload.get('tool_name') != 'Bash':
        sys.exit(0)
    command = (payload.get('tool_input') or {}).get('command', '')
    calls = calls_in(command)
    if not calls:
        sys.exit(0)

    if shutil.which('gitleaks') is None:
        deny('security-gate: gitleaks is not installed, so git commit/push is blocked. Install gitleaks and retry.')

    for call in calls:
        cwd = folder_of(call, payload.get('cwd') or None)
        for args in scans_for(call, cwd):
            try:
                result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=180)
            except (OSError, subprocess.TimeoutExpired) as error:
                deny(f'security-gate: gitleaks could not complete ({type(error).__name__}); blocking.')
            if result.returncode == 0:
                continue
            if result.returncode == 1 and not SCAN_ERROR.search(result.stderr + result.stdout):
                deny('security-gate: gitleaks found a potential secret; remove it and retry.\n'
                     + result.stdout[-2000:])
            deny(f'security-gate: gitleaks could not scan (exit {result.returncode}); blocking.\n'
                 + (result.stderr or result.stdout)[-1000:])
    sys.exit(0)


if __name__ == '__main__':
    main()
