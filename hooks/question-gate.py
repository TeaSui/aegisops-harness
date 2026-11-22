#!/usr/bin/env python3
"""Question gate hook (PreToolUse AskUserQuestion; fails open). Enforces references/aidlc.md §0 inside AegisOps-Harness commands.

Only acts after an AegisOps-Harness work command (`/aegisops-harness:aidlc`, a stage command, `fix`, `prompt-builder`) ran in this
session; plain Claude Code sessions and `/aegisops-harness:grilling` (an interview by design) are untouched.
  * Delegated input (`do not ask`, `not available for questions`, `end to end`, `Status: ready-for-agent`, ...):
    every question is blocked. The decision becomes a recorded assumption, marked RISK-ACCEPTANCE NEEDED when it
    accepts a security or compliance risk, and the final report lists it.
  * Otherwise: the first question of a command run is blocked when no Atlassian (Rovo) tool was called since the
    command started. A retry passes, so a session without Rovo is never stuck.
Off with AEGISOPS_HARNESS_QUESTION_GATE=off. State: ~/.claude/state/question-gate/<session>.json
"""
import json
import os
import pathlib
import re
import sys

STATE_DIR = pathlib.Path.home() / '.claude' / 'state' / 'question-gate'
COMMANDS = ('aidlc', 'spec', 'plan', 'build', 'verify', 'review', 'ship', 'fix', 'prompt-builder')
COMMAND = re.compile(r'<command-name>/?aegisops-harness:([\w-]+)</command-name>')
ARGS = re.compile(r'<command-args>(.*?)</command-args>', re.S)
DELEGATED = re.compile(r"\b(?:do not|don't|dont|never) ask\b|\bnot available for questions\b|\bwithout asking\b"
                       r"|\bno questions\b|\bend[ -]to[ -]end\b|^\s*Status:\s*ready-for-agent\s*$", re.I | re.M)
ROVO = re.compile(r'atlassian|rovo|confluence|jira', re.I)


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(str(p.get('text', '')) for p in content if isinstance(p, dict) and p.get('type') == 'text')
    return ''


def scan(transcript):
    """(command, args, command entry uuid, Rovo called since it) for the latest AegisOps-Harness command in the transcript."""
    command = args = uuid = None
    rovo = False
    try:
        lines = pathlib.Path(transcript).read_text(errors='replace').splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        message = entry.get('message') or {}
        if entry.get('type') == 'user':
            text = text_of(message.get('content'))
            match = COMMAND.search(text)
            if match:
                found = ARGS.search(text)
                command, args, uuid, rovo = match.group(1), (found.group(1) if found else ''), entry.get('uuid'), False
        elif entry.get('type') == 'assistant' and command:
            for part in message.get('content') or []:
                if isinstance(part, dict) and part.get('type') == 'tool_use' and ROVO.search(str(part.get('name'))):
                    rovo = True
    return (command, args or '', uuid or '', rovo) if command else None


def main():
    if os.environ.get('AEGISOPS_HARNESS_QUESTION_GATE', '').lower() == 'off':
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get('tool_name') != 'AskUserQuestion':
        return 0
    found = scan(payload.get('transcript_path') or '')
    if not found or found[0] not in COMMANDS:
        return 0
    command, args, uuid, rovo = found
    if DELEGATED.search(args):
        sys.stderr.write(
            f'question-gate: /aegisops-harness:{command} was started with every decision delegated ("do not ask", '
            '"end to end" or Status: ready-for-agent), so do not ask the user. For each open question: take your '
            'recommended option and record it (at the spec stage under Assumptions in spec.md, later with '
            '`aidlc ruling <spec> --decision "<decision>" --why "<reasoning; sources checked>" --if-wrong "<impact>"`). When it accepts a security or '
            'compliance risk, start the decision with "RISK-ACCEPTANCE NEEDED:". List these first in the final report. '
            'Then continue; references/aidlc.md §0.\n')
        return 2
    session = re.sub(r'[^A-Za-z0-9_-]', '_', str(payload.get('session_id') or 'none'))
    marker = STATE_DIR / (session + '.json')
    try:
        seen = json.loads(marker.read_text())
    except (OSError, ValueError):
        seen = {}
    if rovo or seen.get(uuid):
        return 0
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(dict(seen, **{uuid: True})))
    except OSError:
        pass
    sys.stderr.write(
        f'question-gate: no Atlassian Rovo search ran since /aegisops-harness:{command} started. Before asking the user, '
        'search Rovo for each question (`search` with the domain terms, then `fetch` / `getConfluencePage` / '
        '`getJiraIssue`), record what settled it under Sources, and drop the questions it answers. A question with '
        'a safe default that is not a security, compliance, money or irreversible decision is a recorded assumption, '
        'not a question. If Rovo is not connected, say so in the question and retry: this check runs once per '
        'command. references/aidlc.md §0.\n')
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # never block on its own failure
        sys.exit(0)
