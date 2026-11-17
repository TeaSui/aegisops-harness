#!/usr/bin/env python3
"""TDD reminder gate (advisory, fails open).

  check   PreToolUse Edit|Write|MultiEdit|Bash: before the first production-code write of a session that has no
          recorded failing test run, block ONCE with a reminder. Later attempts pass, so changes that need no new
          test (refactor under existing coverage, docs, config) cost one extra turn.
  record  PostToolUse Bash: remember that a test command failed (the RED evidence) for this session.

Skipped for test files, non-code files, repositories without a recognizable test setup, and when
TEA_SDLC_TDD_GATE=off. Any internal error allows the action. State: ~/.claude/state/tdd/<session>.json
"""
import json
import os
import pathlib
import re
import sys

CODE_EXT = ('.java', '.kt', '.scala', '.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.cs', '.rb', '.php',
            '.swift', '.dart', '.c', '.cc', '.cpp', '.h')
TEST_PATH = re.compile(r'(^|/)(tests?|__tests__|specs?|e2e)(/|$)|(^|/)src/test/|(Test|Tests|IT)\.(java|kt|scala|cs)$'
                       r'|\.(test|spec)\.[jt]sx?$|(^|/)test_[^/]*\.py$|_test\.(go|py)$')
SKIP_DIRS = re.compile(r'(^|/)(node_modules|build|dist|target|\.gradle|\.git|vendor)(/|$)')
TEST_CMD = re.compile(r'\b(gradle|gradlew|mvn|mvnw)\b.*\btest\b|\bnpm (run )?test\b|\b(npx )?(vitest|jest)\b|\bpytest\b'
                      r'|\bgo test\b|\bcargo test\b|\bnode --test\b|\bdotnet test\b|\bflutter test\b|\bmake test\b')
RED = re.compile(r'BUILD FAILED|tests? completed, \d+ failed|\b[1-9]\d* failed\b|AssertionError|# fail [1-9]'
                 r'|--- FAIL|\bFAIL\b|Failures: [1-9]|Tests:\s+\d+ failed|FAILED')
WRITEISH = re.compile(r'open\([^)]*,\s*[\'"][wa]|write_text|cat\s*>|cat\s*<<|tee\s|sed\s+-i|perl\s+-pi|>>?\s*\S+')
INFRA = ('build.gradle', 'build.gradle.kts', 'pom.xml', 'package.json', 'pyproject.toml', 'pytest.ini', 'setup.cfg',
         'tox.ini', 'go.mod', 'Cargo.toml', 'pubspec.yaml')
STATE_DIR = pathlib.Path.home() / '.claude' / 'state' / 'tdd'


def is_prod_code(path):
    path = path.replace('\\', '/')
    return path.endswith(CODE_EXT) and not TEST_PATH.search(path) and not SKIP_DIRS.search(path)


def bash_writes_prod(command):
    if not WRITEISH.search(command):
        return None
    for match in re.finditer(r'[\w./~-]+\.(?:java|kt|scala|py|js|jsx|ts|tsx|go|rs|cs|rb|php|swift|dart|c|cc|cpp|h)\b',
                             command):
        if is_prod_code(match.group(0)):
            return match.group(0)
    return None


def has_test_setup(cwd):
    here = pathlib.Path(cwd or '.').resolve()
    for folder in [here, *list(here.parents)[:4]]:
        if folder == pathlib.Path.home():
            break
        if any((folder / name).exists() for name in INFRA):
            return True
    return False


def state_file(session):
    return STATE_DIR / (re.sub(r'[^A-Za-z0-9_-]', '_', session) + '.json')


def load(session):
    try:
        return json.loads(state_file(session).read_text())
    except (OSError, ValueError):
        return {}


def save(session, state):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_file(session).write_text(json.dumps(state))
    except OSError:
        pass


def result_text(payload):
    # Field name for the tool output has varied (tool_response / tool_output); scan everything but the input.
    skip = {'tool_input', 'tool_name', 'session_id', 'cwd', 'transcript_path', 'hook_event_name'}
    return json.dumps({k: v for k, v in payload.items() if k not in skip})


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if os.environ.get('TEA_SDLC_TDD_GATE', '').lower() == 'off':
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    session = payload.get('session_id') or ''
    tool = payload.get('tool_name')
    tin = payload.get('tool_input') or {}
    if not session:
        return 0
    if mode == 'record':
        if tool == 'Bash' and TEST_CMD.search(str(tin.get('command', ''))) and \
                RED.search(result_text(payload)):
            state = load(session)
            state['red'] = True
            save(session, state)
        return 0
    if tool in ('Edit', 'Write', 'MultiEdit'):
        target = str(tin.get('file_path', ''))
        target = target if is_prod_code(target) else None
    elif tool == 'Bash':
        target = bash_writes_prod(str(tin.get('command', '')))
    else:
        return 0
    if not target:
        return 0
    state = load(session)
    if state.get('red') or state.get('reminded') or not has_test_setup(payload.get('cwd')):
        return 0
    state['reminded'] = True
    save(session, state)
    sys.stderr.write(
        f'tdd-gate: you are about to change production code ({target}) and no failing test run is recorded in this '
        'session. For a behavior change or bug fix: write the test, run it, and show it failing for the expected '
        'reason BEFORE this edit (skill test-driven-development). If this change needs no new test (docs, config, '
        'refactor under existing coverage), retry the same edit: this reminder appears once per session.\n')
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # advisory gate: never block on its own failure
        sys.exit(0)
