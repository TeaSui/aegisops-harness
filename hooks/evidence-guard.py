#!/usr/bin/env python3
"""Evidence guard (PreToolUse Bash | Edit | Write | MultiEdit). A guard rail; fails open on its own errors.

The lifecycle gates read evidence from the spec folder, so the session that is gated must not be the one that writes it:
  * `aidlc approve <spec>` records a person's approval of the spec text. It passes only when the user's latest
    AegisOps-Harness command in this session is `/aegisops-harness:approve` for that spec. With `--delegated` it passes
    unless the request that started the work did not hand the decisions over.
  * `aidlc attest` stores a reviewer's return: hooks/record-returns.py does that when the reviewer returns.
  * `ledger.md` and `returns/` of a spec folder are written by `aidlc` only: edits and shell writes are refused.
A person at a terminal is not affected. This stops the default path, not a session that sets out to forge files: the
transcript it reads is not a documented interface, and a file can be written in ways no pattern sees. `aidlc ci` behind
branch protection is the enforcement (references/aidlc.md, trust model). Off with AEGISOPS_HARNESS_EVIDENCE_GUARD=off.
"""
import importlib.util
import json
import os
import pathlib
import re
import shlex
import sys

HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = re.compile(r'(^|/)docs/specs/[^/]+/(ledger\.md$|returns(/|$))')
VALUE_OPTIONS = ('--by', '--repo', '--agent', '--axis', '--file', '--note')
WRITERS = ('rm', 'mv', 'cp', 'truncate', 'dd', 'install', 'tee', 'touch', 'ln')
SEPARATORS = ('&&', '||', ';', '|', '&')


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def words(command):
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def aidlc_calls(command):
    """[(subcommand, arguments)] for every `aidlc.py <subcommand> …` in a shell command."""
    tokens, calls = words(command), []
    for index, token in enumerate(tokens):
        if pathlib.PurePosixPath(token.replace('\\', '/')).name != 'aidlc.py':
            continue
        rest = []
        for word in tokens[index + 1:]:
            if word in SEPARATORS or word.rstrip(';') != word and not rest:
                break
            rest.append(word.rstrip(';'))
            if word.endswith(';'):
                break
        sub = next((word for word in rest if not word.startswith('-')), None)
        if sub:
            calls.append((sub, rest[rest.index(sub) + 1:]))
    return calls


def positional(arguments):
    """The first argument that is neither an option nor an option's value."""
    skip = False
    for word in arguments:
        if skip:
            skip = False
        elif word in VALUE_OPTIONS:
            skip = True
        elif not word.startswith('-'):
            return word
    return None


def typed_commands(transcript, gate):
    """[(name, args)] of the AegisOps-Harness commands the user typed in this session, oldest first."""
    found = []
    try:
        lines = pathlib.Path(transcript).read_text(errors='replace').splitlines()
    except (OSError, TypeError, ValueError):
        return found
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get('type') != 'user':
            continue
        text = gate.text_of((entry.get('message') or {}).get('content'))
        match = gate.COMMAND.search(text)
        if match:
            args = gate.ARGS.search(text)
            found.append((match.group(1), args.group(1) if args else ''))
    return found


def approve_refusal(arguments, transcript):
    """Why this `aidlc approve` may not run in the session, or None when it may."""
    gate = load('question_gate', 'question-gate.py')
    commands = typed_commands(transcript or '', gate)
    target = positional(arguments)
    slug = pathlib.PurePosixPath((target or '').rstrip('/')).name
    if '--delegated' in arguments:
        work = [args for name, args in commands if name in gate.COMMANDS]
        if work and not gate.DELEGATED.search(work[-1]):
            return ('evidence-guard: `approve --delegated` records that the request handed the decisions over, and the '
                    'request that started this work did not hand the decisions over. Present the spec and ask the user '
                    f'to type /aegisops-harness:approve {slug or "<slug>"}.')
        return None
    latest = commands[-1] if commands else None
    if latest and latest[0] == 'approve' and slug and slug in re.split(r'[\s/]+', latest[1].strip()):
        return None
    return ('evidence-guard: an approval is the user\'s act, and it is of the spec text as it is now. Present the spec, '
            f'then ask the user to type /aegisops-harness:approve {slug or "<slug>"} (that command, typed by them, lets '
            'this through; they can also run `aidlc approve` in their own terminal). If the request delegated every '
            'decision, record that instead: `aidlc approve <spec> --delegated`.')


def shell_targets(command, tdd):
    """Paths a shell command writes, removes or moves: redirect targets, `sed -i` operands and the operands of rm, mv,
    cp, tee and the like."""
    targets = list(tdd.REDIRECT.findall(command))
    for part in tdd.segments(command):
        tokens = words(part)
        if tokens and (pathlib.PurePosixPath(tokens[0]).name in WRITERS or tdd.INPLACE.search(part)):
            targets += tokens[1:]
        if 'tee' in tokens:
            targets += tokens[tokens.index('tee') + 1:]
    return [target.strip('\'"') for target in targets]


def main():
    if os.environ.get('AEGISOPS_HARNESS_EVIDENCE_GUARD', '').lower() == 'off':
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    tool, tool_input = payload.get('tool_name'), payload.get('tool_input') or {}
    refusal = None
    if tool in ('Edit', 'Write', 'MultiEdit'):
        path = str(tool_input.get('file_path', '')).replace('\\', '/')
        if EVIDENCE.search(path):
            refusal = evidence_refusal(path)
    elif tool == 'Bash':
        command = str(tool_input.get('command', ''))
        for sub, arguments in aidlc_calls(command):
            if sub == 'approve':
                refusal = refusal or approve_refusal(arguments, payload.get('transcript_path'))
            elif sub == 'attest':
                refusal = refusal or ('evidence-guard: a reviewer\'s return is stored by the plugin when the reviewer '
                                      'agent returns (hooks/record-returns.py), not by the session that was reviewed. '
                                      'Dispatch the reviewer in the foreground and its return is recorded; a person can '
                                      'record one from their own terminal.')
        if refusal is None and 'docs/specs/' in command.replace('\\', '/'):
            tdd = load('tdd_gate', 'tdd-gate.py')
            written = next((t for t in shell_targets(command, tdd) if EVIDENCE.search(t.replace('\\', '/'))), None)
            if written:
                refusal = evidence_refusal(written)
    if refusal:
        sys.stderr.write(refusal + '\n')
        return 2
    return 0


def evidence_refusal(path):
    return (f'evidence-guard: {path} is evidence the lifecycle gates read, and only `aidlc` writes it. A decision goes '
            'in with `aidlc ruling`, a finished ticket with `aidlc task-done`, a test run with `aidlc verify`; a '
            'reviewer\'s return is stored when the reviewer returns. Do not edit, move or remove the file.')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # a guard rail: never block on its own failure
        sys.exit(0)
