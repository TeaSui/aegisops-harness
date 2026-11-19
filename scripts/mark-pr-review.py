#!/usr/bin/env python3
"""Record a completed pre-PR review for the current HEAD, read by hooks/pr-review-gate.py.

Usage (from inside the repository under review):
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer code-reviewer --open-findings 0 --note "pass 1, 3 fixed"

API (scripts/aidlc.py `advance … reviewed`): record(repo_top, head, reviewer, open_findings, note) -> Path
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

STATE_ROOT = pathlib.Path.home() / '.claude' / 'state' / 'pr-review'


def git(args):
    return subprocess.run(['git', *args], capture_output=True, text=True, timeout=30)


def record(repo_top, head, reviewer, open_findings, note=''):
    """Write the record for `head` of the repository whose `git rev-parse --show-toplevel` is `repo_top`."""
    repo_id = hashlib.sha256(str(repo_top).encode()).hexdigest()[:16]
    data = {
        'head': head,
        'reviewer': reviewer,
        'open_findings': open_findings,
        'note': note,
        'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    # HOME is read at call time (not import time) so a caller that changes HOME, such as a test, is honored.
    target = pathlib.Path.home() / '.claude' / 'state' / 'pr-review' / repo_id / f'{head}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + '\n')
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--open-findings', type=int, required=True)
    parser.add_argument('--note', default='')
    args = parser.parse_args()
    if args.open_findings < 0:
        sys.exit('open-findings must be >= 0')

    top = git(['rev-parse', '--show-toplevel'])
    head = git(['rev-parse', 'HEAD'])
    if top.returncode or head.returncode:
        sys.exit('not inside a git repository with commits')

    sha = head.stdout.strip()
    target = record(top.stdout.strip(), sha, args.reviewer, args.open_findings, args.note)
    print(f'recorded pre-PR review for {sha[:12]}: {target}')


if __name__ == '__main__':
    main()
