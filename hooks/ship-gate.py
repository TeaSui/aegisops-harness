#!/usr/bin/env python3
"""PreToolUse gate for Bash: `gh pr merge` waits until the branch's active spec has passed the `shipped` gate.

A full-workflow change is bound to its branch by `aidlc advance <spec> building` (README `branch:`). Merging that
branch before `aidlc advance <spec> shipped` passes would ship without a GO decision, a rollback plan, green CI or a
review of the current code (references/aidlc.md). Branches with no bound spec (fast path, chores) are not gated.

Blocks only on real gate findings; an infrastructure error (gh unavailable, engine unreadable) lets the merge through
with a note, like the contract check in hooks/pr-review-gate.py. Off with TEA_SDLC_SHIP_GATE=off.
"""
import importlib.util
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

MERGE = re.compile(r'(^|[;&|\s])gh\s+pr\s+merge\b')
PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
FINISHED = ('shipped', 'implemented', 'partially-implemented', 'superseded', 'abandoned')


def run(args, cwd, timeout=20):
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def merge_target(command):
    """The PR argument of the first `gh pr merge` in the command, or None for the current branch."""
    try:
        words = shlex.split(command[MERGE.search(command).start():])
    except ValueError:
        words = command.split()
    args, skip = [], False
    for word in words[3:]:
        if word in ('&&', '||', ';', '|'):
            break
        if skip:
            skip = False
            continue
        if word.startswith('-'):
            skip = word in ('-t', '--subject', '-b', '--body', '-F', '--body-file', '-A', '--author-email',
                            '--match-head-commit', '-R', '--repo')
            continue
        args.append(word)
    return args[0] if args else None


def head_branch(target, cwd):
    if target is None:
        return run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd)
    if re.fullmatch(r'\d+|https?://\S+/pull/\d+\S*', target):
        gh = os.environ.get('AIDLC_GH') or 'gh'
        return run([gh, 'pr', 'view', target, '--json', 'headRefName', '-q', '.headRefName'], cwd)
    return target


def main():
    if os.environ.get('TEA_SDLC_SHIP_GATE', '').lower() == 'off':
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    command = str((payload.get('tool_input') or {}).get('command', '')) if payload.get('tool_name') == 'Bash' else ''
    if not MERGE.search(command):
        return 0
    cwd = payload.get('cwd') or None
    top = run(['git', 'rev-parse', '--show-toplevel'], cwd)
    branch = head_branch(merge_target(command), cwd)
    if not top or not branch:
        return 0
    spec = importlib.util.spec_from_file_location('tea_sdlc_aidlc', PLUGIN_ROOT / 'scripts' / 'aidlc.py')
    aidlc = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(aidlc)
        pending = [path for path in aidlc.specs_for_branch(top, branch) if aidlc.stage(path) not in FINISHED]
        blocked = [(path, [m for level, m in aidlc.check(path, 'shipped') if level == 'FAIL']) for path in pending]
    except Exception as error:  # never block a merge on the gate's own failure
        sys.stderr.write(f'ship-gate: skipped ({type(error).__name__}); run `aidlc check <spec> --to shipped` yourself.\n')
        return 0
    blocked = [(path, findings) for path, findings in blocked if findings]
    if not blocked:
        return 0
    cli = f'python3 "{PLUGIN_ROOT}/scripts/aidlc.py"'
    lines = [f'ship-gate: branch {branch} carries a spec that has not passed the `shipped` gate:']
    for path, findings in blocked:
        rel = pathlib.Path(path).resolve().relative_to(pathlib.Path(top).resolve()).as_posix()
        lines.append(f'  {rel} (stage {aidlc.stage(path)}):')
        lines.extend(f'    - {finding}' for finding in findings[:8])
    lines.append(f'Finish the ship stage (skill tea-sdlc:shipping): write ship.md (GO, rollback, post-release '
                 f'verification), then `{cli} advance <spec> shipped`, then merge.')
    sys.stderr.write('\n'.join(lines) + '\n')
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # an unexpected failure must not block the user's merge
        sys.exit(0)
