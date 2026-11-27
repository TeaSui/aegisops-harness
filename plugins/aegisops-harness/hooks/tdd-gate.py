#!/usr/bin/env python3
"""TDD reminder gate (advisory, fails open).

  check   PreToolUse Edit|Write|MultiEdit|Bash: before the first production-code write of a session that has no
          recorded failing test run, block ONCE with a reminder. Later attempts pass, so changes that need no new
          test (refactor under existing coverage, docs, config) cost one extra turn.
  record  PostToolUse Bash: remember that a test command failed (the RED evidence) for this session.

Skipped for test files, non-code files, repositories without a recognizable test setup, and when
AEGISOPS_HARNESS_TDD_GATE=off. Any internal error allows the action. State: ~/.claude/state/tdd/<session>.json
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
RED = re.compile(r'BUILD FAILED|tests? completed, \d+ failed|\b[1-9]\d* failed\b|AssertionError|# fail [1-9]'
                 r'|--- FAIL|\bFAIL\b|Failures: [1-9]|Tests:\s+\d+ failed|FAILED')
# A test run is a segment of the command that STARTS with a runner (after env vars and launchers such as npx,
# `python -m`, `uv run` or a ./ path), so `npm install -D jest` or `cat jest.config.js` is not one.
SEGMENTS = re.compile(r'&&|\|\||[;|\n]')
RUNNER = re.compile(
    r'^(?:\w+=\S*\s+)*(?:time\s+|timeout\s+\d+\S*\s+)?'
    r'(?:(?:npx|bunx|uvx)\s+|(?:pnpm|yarn)\s+(?:exec\s+|dlx\s+)?|(?:uv|poetry|pipenv|hatch)\s+run\s+'
    r'|python[\d.]*\s+-m\s+|\S*/)?'
    r'(?:(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test\b|(?:vitest|jest|mocha|ava|karma|pytest|tox|nox|rspec|phpunit|ctest'
    r'|unittest)\b|playwright\s+test\b|go\s+test\b|cargo\s+(?:test|nextest)\b|node\s+--test\b'
    r'|(?:dotnet|flutter|dart|swift|deno|mix|sbt|lein)\s+test\b|xcodebuild\b.*\btest\b|make\s+(?:test|check)\b'
    r'|(?:gradle|gradlew|mvn|mvnw)\b(?!.*(?:-DskipTests|-Dmaven\.test\.skip|-x\s+test\b)).*\b(?:test|check|verify)\b)')
# Shell writes: the target of `>`, `>>`, `1>`, `&>`, `&>>`, `>|` (not `2>` or `>&2`), every operand of `tee`, code paths in
# a segment that edits in place (sed -i / --in-place, perl -i), and code paths anywhere in a command whose inline code
# writes files (open(..., 'w'), write_text). Paths are found by splitting into tokens: linear on any input.
REDIRECT = re.compile(r'(?<![0-9>&])[1&]?>>?\|?(?!&)\s*([^\s;&|<>()]+)')
INPLACE = re.compile(r'\bsed\b.*\s(?:-[a-zA-Z]*i\b|-i\S*|--in-place)|\bperl\b.*\s-[a-zA-Z]*i')
INLINE_WRITE = re.compile(r'open\([^)]*,\s*[\'"][wax]|write_text|write_bytes')
INFRA = ('build.gradle', 'build.gradle.kts', 'pom.xml', 'package.json', 'pyproject.toml', 'pytest.ini', 'setup.cfg',
         'tox.ini', 'go.mod', 'Cargo.toml', 'pubspec.yaml')
STATE_DIR = pathlib.Path.home() / '.claude' / 'state' / 'tdd'


def is_prod_code(path):
    path = path.replace('\\', '/')
    return path.endswith(CODE_EXT) and not TEST_PATH.search(path) and not SKIP_DIRS.search(path)


def segments(command):
    return [part.strip() for part in SEGMENTS.split(command.replace('>|', '>'))]


def is_test_command(command):
    return any(RUNNER.match(part) for part in segments(command))


def _tokens(text):
    return [t for t in re.split(r'[\s\'"`(),;=\[\]{}<>|&]+', text) if t]


def bash_writes_prod(command):
    candidates = REDIRECT.findall(command)
    for part in segments(command):
        words = _tokens(part)
        if 'tee' in words:
            candidates += [w for w in words[words.index('tee') + 1:] if not w.startswith('-')]
        if INPLACE.search(part):
            candidates += words
    if INLINE_WRITE.search(command):
        candidates += _tokens(command)
    for candidate in candidates:
        candidate = candidate.strip('\'"')
        if is_prod_code(candidate):
            return candidate
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
        target = state_file(session)
        temp = target.with_suffix(f'.{os.getpid()}.tmp')
        temp.write_text(json.dumps(state))
        os.replace(temp, target)  # atomic: a concurrent reader never sees a half-written file
    except OSError:
        pass


def result_text(payload):
    # Field name for the tool output has varied (tool_response / tool_output); scan everything but the input.
    skip = {'tool_input', 'tool_name', 'session_id', 'cwd', 'transcript_path', 'hook_event_name'}
    return json.dumps({k: v for k, v in payload.items() if k not in skip})


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if os.environ.get('AEGISOPS_HARNESS_TDD_GATE', '').lower() == 'off':
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
        if tool == 'Bash' and is_test_command(str(tin.get('command', ''))) and \
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
        'reason BEFORE this edit (rules: skills/test-driven-development/SKILL.md). If this change needs no new test (docs, config, '
        'refactor under existing coverage), retry the same edit: this reminder appears once per session.\n')
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # advisory gate: never block on its own failure
        sys.exit(0)
