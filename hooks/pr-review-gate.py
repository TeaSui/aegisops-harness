#!/usr/bin/env python3
"""PreToolUse gate for Bash: block opening a PR (`gh pr create`, `scripts/pr.py create`, a Bitbucket API POST) until a
pre-PR review is recorded for HEAD.

The gate verifies that a review was recorded (scripts/mark-pr-review.py) with zero open findings.
It cannot verify review quality; rules/pre-pr-review.md owns that.
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

# `gh pr create`, `scripts/pr.py create` (GitHub or Bitbucket), or a raw POST to Bitbucket's pullrequests endpoint.
PR_CREATE = re.compile(r'(^|[;&|\s])gh\s+pr\s+create\b|pr\.py["\']?\s+create\b'
                       r'|\bcurl\b[^;&|]*api\.bitbucket\.org/[^;&|\s]*/pullrequests/?["\']?(\s|$)')
STATE_ROOT = pathlib.Path.home() / '.claude' / 'state' / 'pr-review'
PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent


def deny(reason):
    sys.stderr.write(reason + '\n')
    sys.exit(2)


def contract_findings(root):
    # Hard gate: blocks only on real findings; a broken checker must not block PRs.
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('check_contract', PLUGIN_ROOT / 'scripts' / 'check-contract.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return [m for level, m in module.scan(root) if level == 'FAIL']
    except Exception:
        return []


def spec_review(top, cwd):
    """(passed, message) for full-workflow specs bound to the current branch, or (None, None) when there are none.

    The review stage of references/aidlc.md is keyed to the code fingerprint, not to HEAD, so committing review.md,
    the ledger or README after `aidlc advance reviewed` keeps the review valid. Any failure to load the engine means
    "no opinion" and the HEAD record below decides, as before."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('aegisops_harness_aidlc', PLUGIN_ROOT / 'scripts' / 'aidlc.py')
        aidlc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(aidlc)
        branch = git(['rev-parse', '--abbrev-ref', 'HEAD'], cwd).stdout.strip()
        bound = [p for p in aidlc.specs_for_branch(top, branch)
                 if aidlc.stage(p) not in ('implemented', 'partially-implemented', 'superseded', 'abandoned')]
        if not bound:
            return None, None
        problems = []
        for path in bound:
            failures = [m for level, m in aidlc.check(path, 'reviewed') if level == 'FAIL']
            if failures:
                rel = pathlib.Path(path).resolve().relative_to(pathlib.Path(top).resolve()).as_posix()
                problems.append(f'{rel} (stage {aidlc.stage(path)}) has not passed the `reviewed` gate:\n    - '
                                + '\n    - '.join(failures[:6]))
        if problems:
            return False, ('pr-review-gate: this branch carries a full-workflow spec whose review stage is not done.\n  '
                           + '\n  '.join(problems)
                           + f'\nFinish it (/aegisops-harness:review, or the pass in rules/pre-pr-review.md), then `python3 "{PLUGIN_ROOT}/scripts/'
                             'aidlc.py" advance <spec> reviewed`, then retry.')
        return True, None
    except Exception:
        return None, None


def git(args, cwd):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, timeout=30)


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        deny('pr-review-gate: unreadable hook input; blocking as a precaution.')

    if payload.get('tool_name') != 'Bash':
        sys.exit(0)
    command = (payload.get('tool_input') or {}).get('command', '')
    if not PR_CREATE.search(command):
        sys.exit(0)

    cwd = payload.get('cwd') or None
    top = git(['rev-parse', '--show-toplevel'], cwd)
    head = git(['rev-parse', 'HEAD'], cwd)
    if top.returncode or head.returncode:
        deny('pr-review-gate: not in a git repository with commits; cannot verify the pre-PR review.')

    reviewed, message = spec_review(top.stdout.strip(), cwd)
    if reviewed is False:
        deny(message)
    if reviewed:
        contract_failures = contract_findings(top.stdout.strip())
        if contract_failures:
            deny('pr-review-gate: an active spec declares an external contract that fails the contract gate '
                 '(python3 "' + str(PLUGIN_ROOT / 'scripts' / 'check-contract.py') + '" --scan <repo>):\n  - '
                 + '\n  - '.join(contract_failures[:8]))
        sys.exit(0)

    repo_id = hashlib.sha256(top.stdout.strip().encode()).hexdigest()[:16]
    sha = head.stdout.strip()
    marker = STATE_ROOT / repo_id / f'{sha}.json'
    if not marker.is_file():
        deny(f'pr-review-gate: no pre-PR review recorded for HEAD {sha[:12]}. '
             f'Run {PLUGIN_ROOT}/rules/pre-pr-review.md, record it with '
             f'python3 "{PLUGIN_ROOT}/scripts/mark-pr-review.py", then retry.')

    try:
        record = json.loads(marker.read_text())
    except (OSError, ValueError):
        deny('pr-review-gate: review record is unreadable; re-record it.')

    open_findings = record.get('open_findings')
    if not isinstance(open_findings, int) or open_findings != 0:
        deny(f'pr-review-gate: review record lists {open_findings!r} open finding(s); '
             'fix or clear them, re-record, then retry.')

    contract_failures = contract_findings(top.stdout.strip())
    if contract_failures:
        deny('pr-review-gate: an active spec declares an external contract that fails the contract gate '
             '(python3 "' + str(PLUGIN_ROOT / 'scripts' / 'check-contract.py') + '" --scan <repo>):\n  - '
             + '\n  - '.join(contract_failures[:8]))
    sys.exit(0)


if __name__ == '__main__':
    main()
