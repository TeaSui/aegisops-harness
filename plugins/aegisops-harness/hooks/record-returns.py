#!/usr/bin/env python3
"""Reviewer returns (PostToolUse Agent | Task). Silent on its own failure.

When a review-stage reviewer returns (aegisops-harness:code-reviewer, aegisops-harness:qa-subagent), store what it
returned, verbatim, in the returns/ folder of the spec that is at `verified` on this branch. The `reviewed` gate then
checks review.md against it: every returned finding is there with the severity it was given, and the QA verdict is the
one QA gave. The plugin records it, not the session whose work was reviewed (hooks/evidence-guard.py refuses its edits).

A reviewer dispatched in the background returns nothing to this hook: review-stage reviewers run in the foreground.
Per-ticket reviews during the build stage (spec at `building`) are not recorded. Off with AEGISOPS_HARNESS_RETURNS=off.
"""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
AGENTS = {'code-reviewer': None, 'qa-subagent': 'qa'}  # agent -> its fixed axis (None: named in the dispatch)
AXIS = re.compile(r'\baxis\b\W{0,4}(spec|standards|both)\b', re.I)


def text_of(response):
    """The reviewer's words out of a tool response (a string, a list of text blocks, or an object that holds one)."""
    if isinstance(response, str):
        return response
    if isinstance(response, list):
        return '\n'.join(part.get('text', '') if isinstance(part, dict) else str(part) for part in response)
    if isinstance(response, dict):
        if response.get('status') == 'async_launched':
            return ''
        for key in ('content', 'result', 'text'):
            if response.get(key):
                return text_of(response[key])
    return ''


def main():
    if os.environ.get('AEGISOPS_HARNESS_RETURNS', '').lower() == 'off':
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get('tool_name') not in ('Agent', 'Task'):
        return 0
    tool_input = payload.get('tool_input') or {}
    agent = str(tool_input.get('subagent_type', ''))
    bare = agent.split(':')[-1]
    if bare not in AGENTS:
        return 0
    text = text_of(payload.get('tool_response'))
    if not text.strip():
        return 0
    prompt = str(tool_input.get('prompt', ''))
    named = AXIS.search(prompt)
    axis = AGENTS[bare] or (named.group(1).lower() if named else 'both')
    cwd = payload.get('cwd') or None
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=cwd, capture_output=True, text=True, timeout=30)
    branch = subprocess.run(['git', 'symbolic-ref', '--quiet', '--short', 'HEAD'], cwd=cwd, capture_output=True,
                            text=True, timeout=30)
    if top.returncode or branch.returncode:
        return 0
    spec = importlib.util.spec_from_file_location('aegisops_harness_aidlc', HERE.parent / 'scripts' / 'aidlc.py')
    aidlc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aidlc)
    folders = [path for path in aidlc.specs_for_branch(top.stdout.strip(), branch.stdout.strip())
               if aidlc.stage(path) == 'verified']
    if len(folders) > 1:  # several specs on one branch: the one the dispatch names
        folders = [path for path in folders if pathlib.Path(path).name in prompt]
    if len(folders) != 1:
        return 0
    path, _ = aidlc.record_return(folders[0], agent, axis, text)
    rel = pathlib.Path(path).resolve().relative_to(pathlib.Path(top.stdout.strip()).resolve()).as_posix()
    note = (f'<aegisops-harness>\nStored this return in {rel}. The reviewed gate compares review.md with it: copy every '
            'finding line as returned and close it with "fixed:" or "cleared:".\n</aegisops-harness>')
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': note}}))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # recording is best effort: never break the session
        sys.exit(0)
