#!/usr/bin/env python3
"""PreToolUse gate for Bash: a PR merge (`gh pr merge`, `scripts/pr.py merge`, a Bitbucket API merge) waits until the branch's spec has passed the `shipped` gate.

A full-workflow change is bound to its branch by `aidlc advance <spec> building` (README `branch:`). The gate:
- evaluates the spec as it is on the branch being merged: the current checkout when that branch is checked out,
  otherwise a temporary detached worktree of the PR head (or the branch);
- re-checks specs already at `shipped` (code may have changed since), and refuses the branch of an abandoned spec;
- refuses a PR whose head is not the commit checked locally, and a PR named through a variable.
Branches with no bound spec (fast path, chores) are not gated. Blocks only on real findings; an infrastructure error
(gh unavailable, engine unreadable, branch not fetched) lets the merge through with a note. Off with
TEA_SDLC_SHIP_GATE=off. Spec: references/aidlc.md.
"""
import importlib.util
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

# `gh pr merge`, `scripts/pr.py merge` (GitHub or Bitbucket), or a raw POST to Bitbucket's merge endpoint.
MERGE = re.compile(r'(^|[;&|\s])gh\s+pr\s+merge\b|pr\.py["\']?\s+merge\b'
                   r'|\bcurl\b[^;&|]*api\.bitbucket\.org/[^;&|\s]*/pullrequests/\d+/merge')
PR_REF = re.compile(r'\d+|https?://\S+/pull(?:-requests|requests)?/\d+\S*')
PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
POST_SHIP = ('implemented', 'partially-implemented', 'superseded')


def run(args, cwd, timeout=20):
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def merge_target(command):
    """The PR argument of the first merge command, or None for the current branch."""
    found = MERGE.search(command)
    curl = re.search(r'/pullrequests/(\d+)/merge', found.group(0))
    if curl:
        return curl.group(1)
    try:
        words = shlex.split(command[found.start():], posix=True)
    except ValueError:
        words = command.split()
    start = next((i + 1 for i, w in enumerate(words) if w == 'merge'), len(words))
    args, skip = [], False
    for word in words[start:]:
        if word in ('&&', '||', ';', '|'):
            break
        if skip:
            skip = False
            continue
        if word.startswith('-'):
            skip = word in ('-t', '--subject', '-b', '--body', '-F', '--body-file', '-A', '--author-email',
                            '--match-head-commit', '-R', '--repo', '--strategy')
            continue
        args.append(word)
    raw = command[MERGE.search(command).end():]
    if re.search(r'[$`]', raw.split('&&')[0].split(';')[0]):
        return '$'  # a variable or substitution: the gate cannot know which PR it is
    return args[0] if args else None


def pr_head(target, cwd):
    """(head branch, head commit) for a PR number, URL or branch, via scripts/pr.py (Bitbucket or gh); (None, None)
    when neither can tell."""
    try:
        pr = load_pr().client(cwd)
        if pr.__class__.__name__ == 'Bitbucket':
            found = pr.find(target)
            return (found['head'], found['head_sha']) if found else (None, None)
    except Exception:  # missing credentials or API down: let the merge through as before
        return None, None
    gh = os.environ.get('AIDLC_GH') or 'gh'
    out = run([gh, 'pr', 'view', target, '--json', 'headRefName,headRefOid'], cwd)
    try:
        data = json.loads(out or '')
        return data.get('headRefName'), data.get('headRefOid')
    except (ValueError, AttributeError):
        # Older fakes and gh versions may print the branch name alone.
        return (out.splitlines()[0].strip() if out else None), None


def load_pr():
    spec = importlib.util.spec_from_file_location('tea_sdlc_pr', PLUGIN_ROOT / 'scripts' / 'pr.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_engine():
    spec = importlib.util.spec_from_file_location('tea_sdlc_aidlc', PLUGIN_ROOT / 'scripts' / 'aidlc.py')
    aidlc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aidlc)
    return aidlc


def problems_in(aidlc, root, branch):
    """Gate findings for every spec bound to `branch` in the checkout at `root`."""
    problems = []
    for path in aidlc.specs_for_branch(str(root), branch):
        stage = aidlc.stage(path)
        rel = pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve()).as_posix()
        if stage in POST_SHIP:
            continue
        if stage == 'abandoned':
            problems.append((rel, stage, ['the spec bound to this branch was abandoned; do not merge its work '
                                          '(remove `branch:` from its README if the branch now carries other work)']))
            continue
        failures = [m for level, m in aidlc.check(path, 'shipped') if level == 'FAIL']
        if failures:
            problems.append((rel, stage, failures))
    return problems


def in_worktree(top, ref, fn):
    """Run fn(path) on a temporary detached checkout of `ref`, so the gate sees the branch being merged."""
    tmp = tempfile.mkdtemp(prefix='tea-sdlc-ship-gate-')
    try:
        if run(['git', 'worktree', 'add', '--detach', '--quiet', tmp, ref], top, timeout=120) is None:
            raise RuntimeError(f'could not check out {ref}')
        return fn(tmp)
    finally:
        run(['git', 'worktree', 'remove', '--force', tmp], top, timeout=60)
        shutil.rmtree(tmp, ignore_errors=True)


def deny(lines):
    sys.stderr.write('\n'.join(lines) + '\n')
    return 2


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
    if not top:
        return 0
    target = merge_target(command)
    if target == '$':
        return deny(['ship-gate: the merge command names its PR through a variable or command substitution, so the gate '
                     'cannot check which change ships. Run it with a literal PR number or branch.'])
    current = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], top)
    oid = None
    if target is None:
        branch = current
        _, oid = pr_head(current, top) if current else (None, None)
    elif PR_REF.fullmatch(target):
        branch, oid = pr_head(target, top)
    else:
        branch = target
        _, oid = pr_head(target, top)
    if not branch:
        return 0
    try:
        aidlc = load_engine()
        if branch == current:
            head = run(['git', 'rev-parse', 'HEAD'], top)
            if oid and head and not head.startswith(oid) and aidlc.specs_for_branch(top, branch):  # Bitbucket: short hash
                return deny([f'ship-gate: the PR head ({oid[:12]}) is not the commit checked here ({head[:12]}); '
                             'push or pull so the reviewed and shipped code is what merges, then retry.'])
            problems = problems_in(aidlc, top, branch)
        else:
            ref = oid if oid and run(['git', 'cat-file', '-e', oid + '^{commit}'], top) is not None else branch
            if run(['git', 'rev-parse', '--verify', '--quiet', ref + '^{commit}'], top) is None:
                sys.stderr.write(f'ship-gate: {branch} is not available locally; fetch it to let the gate check it.\n')
                return 0
            problems = in_worktree(top, ref, lambda path: problems_in(aidlc, path, branch))
    except Exception as error:  # never block a merge on the gate's own failure
        sys.stderr.write(f'ship-gate: skipped ({type(error).__name__}); run `aidlc check <spec> --to shipped` yourself.\n')
        return 0
    if not problems:
        return 0
    cli = f'python3 "{PLUGIN_ROOT}/scripts/aidlc.py"'
    lines = [f'ship-gate: branch {branch} carries a spec that has not passed the `shipped` gate:']
    for rel, stage, findings in problems:
        lines.append(f'  {rel} (stage {stage}):')
        lines.extend(f'    - {finding}' for finding in findings[:8])
    lines.append(f'Finish the ship stage (/tea-sdlc:ship): write ship.md (GO, rollback, post-release '
                 f'verification), then `{cli} advance <spec> shipped`, then merge.')
    return deny(lines)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # an unexpected failure must not block the user's merge
        sys.exit(0)
