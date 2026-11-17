#!/usr/bin/env python3
"""Contract gate hook (PreToolUse Edit|Write|MultiEdit|Bash, advisory, fails open).

When an active spec (README status proposed/accepted) declares `contract: external` and scripts/check-contract.py
reports a failure, block the FIRST production-code change of the session once, with the findings. Later attempts pass.
The hard enforcement is in hooks/pr-review-gate.py (no PR while the contract gate fails). Off with
TEA_SDLC_CONTRACT_GATE=off. State: ~/.claude/state/contract-gate/<session>.json
"""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
STATE_DIR = pathlib.Path.home() / '.claude' / 'state' / 'contract-gate'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if os.environ.get('TEA_SDLC_CONTRACT_GATE', '').lower() == 'off':
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    session = payload.get('session_id') or ''
    tool, tin = payload.get('tool_name'), payload.get('tool_input') or {}
    if not session:
        return 0
    tdd = load('tdd_gate', HERE / 'tdd-gate.py')
    if tool in ('Edit', 'Write', 'MultiEdit'):
        target = str(tin.get('file_path', ''))
        target = target if tdd.is_prod_code(target) else None
    elif tool == 'Bash':
        target = tdd.bash_writes_prod(str(tin.get('command', '')))
    else:
        return 0
    if not target:
        return 0
    marker = STATE_DIR / (re.sub(r'[^A-Za-z0-9_-]', '_', session) + '.json')
    if marker.exists():
        return 0
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=payload.get('cwd') or None,
                         capture_output=True, text=True)
    root = top.stdout.strip() if top.returncode == 0 and top.stdout.strip() else payload.get('cwd')
    if not root:
        return 0
    checker = load('check_contract', HERE.parent / 'scripts' / 'check-contract.py')
    failures = [m for level, m in checker.scan(root) if level == 'FAIL']
    if not failures:
        return 0
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        marker.write_text('{}')
    except OSError:
        pass
    sys.stderr.write(
        'contract-gate: an active spec declares an external contract and it does not pass '
        f'scripts/check-contract.py, and you are about to change production code ({target}):\n  - '
        + '\n  - '.join(failures[:8])
        + '\nFix the contract files first (python3 "' + str(HERE.parent / 'scripts' / 'check-contract.py')
        + '" --scan <repo>). If the change is unrelated to that contract, retry the same edit: this reminder '
        'appears once per session; pre-PR enforcement is strict.\n')
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # advisory gate: never block on its own failure
        sys.exit(0)
