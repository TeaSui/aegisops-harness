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


def simple_commands(command):
    """The simple commands of a shell command, read as the other gates read them (hooks/invocations.py): inside
    `bash -c`, `eval`, `$(…)`, `if … then`, a here-document fed to a shell, behind `sudo` and `env`."""
    try:
        return load('invocations', 'invocations.py').simple_commands(command.replace('\\\n', ' '))
    except Exception:
        return []


def aidlc_calls(command):
    """[(subcommand, arguments)] for every `aidlc.py <subcommand> …` in a shell command."""
    calls = []
    for tokens in simple_commands(command) + [words(command)]:  # the flat reading stays as the floor
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
            sub, at = None, 0
            while at < len(rest):  # `--repo .` takes a value: it is not the subcommand
                if rest[at] in VALUE_OPTIONS:
                    at += 2
                elif rest[at].startswith('-'):
                    at += 1
                else:
                    sub = rest[at]
                    break
            if sub and (sub, rest[at + 1:]) not in calls:
                calls.append((sub, rest[at + 1:]))
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


def model_runs(transcript, slug):
    """How many times the model has already run `aidlc approve <slug>` in this session (a call that is in the
    transcript was allowed, so it used up one typed command)."""
    count = 0
    try:
        lines = pathlib.Path(transcript).read_text(errors='replace').splitlines()
    except (OSError, TypeError, ValueError):
        return count
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        blocks = (entry.get('message') or {}).get('content') if isinstance(entry, dict) else None
        if entry.get('type') != 'assistant' or not isinstance(blocks, list):
            continue
        for block in blocks:
            if isinstance(block, dict) and block.get('type') == 'tool_use' and block.get('name') == 'Bash':
                for sub, rest in aidlc_calls(str((block.get('input') or {}).get('command', ''))):
                    target = positional(rest)
                    if sub == 'approve' and '--delegated' not in rest and \
                            pathlib.PurePosixPath((target or '').rstrip('/')).name == slug:
                        count += 1
    return count


def approve_refusal(arguments, transcript):
    """Why this `aidlc approve` may not run in the session, or None when it may."""
    gate = load('question_gate', 'question-gate.py')
    commands = typed_commands(transcript or '', gate)
    target = positional(arguments)
    slug = pathlib.PurePosixPath((target or '').rstrip('/')).name
    if '--delegated' in arguments:
        work = [args for name, args in commands if name in gate.COMMANDS]
        if not work:
            return ('evidence-guard: `approve --delegated` records that the request handed the decisions over, and this '
                    'session shows no work command to read that from (none typed, or the transcript cannot be read). '
                    f'Present the spec and ask the user to type /aegisops-harness:approve {slug or "<slug>"}.')
        if not gate.DELEGATED.search(work[-1]):
            return ('evidence-guard: `approve --delegated` records that the request handed the decisions over, and the '
                    'request that started this work did not hand the decisions over. Present the spec and ask the user '
                    f'to type /aegisops-harness:approve {slug or "<slug>"}.')
        return None
    latest = commands[-1] if commands else None
    if latest and latest[0] == 'approve' and slug and slug in re.split(r'[\s/]+', latest[1].strip()):
        typed = sum(1 for name, args in commands if name == 'approve' and slug in re.split(r'[\s/]+', args.strip()))
        if model_runs(transcript or '', slug) < typed:
            return None
        return (f'evidence-guard: the approval of {slug} that the user typed has been used (one run per typed command). '
                'The spec may have changed since: show it again and ask the user to type '
                f'/aegisops-harness:approve {slug}.')
    return ('evidence-guard: an approval is the user\'s act, and it is of the spec text as it is now. Present the spec, '
            f'then ask the user to type /aegisops-harness:approve {slug or "<slug>"} (that command, typed by them, lets '
            'this through; they can also run `aidlc approve` in their own terminal). If the request delegated every '
            'decision, record that instead: `aidlc approve <spec> --delegated`.')


COPIERS = ('cp', 'ln', 'install')  # only the last operand is written; the others are read


def shell_targets(command, tdd):
    """Paths a shell command writes, removes or moves: redirect targets, `sed -i` operands, the operands of rm, mv,
    tee and the like, the destination of cp, `of=` of dd, and what `git checkout|restore <rev> -- <path>` rewrites.
    A relative path is read against the folder the last `cd` moved to."""
    where, targets = '', []

    def at(path):
        path = path.strip('\'"')
        return str(pathlib.PurePosixPath(where) / path) if where and not path.startswith('/') else path

    for part in tdd.segments(command):
        tokens = words(part)
        if tokens and tokens[0] == 'cd' and len(tokens) > 1 and not tokens[1].startswith('-'):
            where = str(pathlib.PurePosixPath(where) / tokens[1]) if where else tokens[1]
            continue
        found = [at(t) for t in tdd.REDIRECT.findall(part)]
        name = pathlib.PurePosixPath(tokens[0]).name if tokens else ''
        if name in COPIERS:
            operands = [t for t in tokens[1:] if not t.startswith('-')]
            found += [at(operands[-1])] if operands else []
        elif name in WRITERS or tdd.INPLACE.search(part):
            found += [at(t[3:] if t.startswith('of=') else t) for t in tokens[1:]]
        elif name == 'git' and any(t in ('checkout', 'restore', 'apply') for t in tokens[1:3]) and '--' in tokens:
            found += [at(t) for t in tokens[tokens.index('--') + 1:]]
        if 'tee' in tokens:
            found += [at(t) for t in tokens[tokens.index('tee') + 1:]]
        targets += found
    return targets


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
        if refusal is None and re.search(r'specs|ledger\.md|returns', command):
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
