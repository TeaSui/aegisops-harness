"""TDD suite judge.

Walks the session's tool calls in order and classifies each as a test edit, a production edit, a red test run or a
green test run. Passes when there is a production edit, a red run happened before the first production edit, and a
test run (red or green) happened after the last edit.
"""
import json
import re

RED = re.compile(r'\bfail [1-9]|^\s*not ok\b|AssertionError|\b[1-9]\d* (failed|failing)\b|\btests? failed\b|'
                 r'exit code [1-9]', re.I | re.M)
TEST_CMD = re.compile(r'\b(npm (run )?test|npx (jest|vitest|mocha)|node --test|pytest|go test)\b')
SHELL_WRITE = re.compile(r'(>>?\s*|tee\s+(-a\s+)?)\S*\bsrc/|sed -i')
EDIT_TOOLS = ('Edit', 'Write', 'MultiEdit')


def is_test_path(path):
    path = path.replace('\\', '/')
    return bool(re.search(r'(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.\w+$', path))


def is_prod_path(path):
    path = path.replace('\\', '/')
    return not is_test_path(path) and bool(re.search(r'(^|/)src/', path))


def events(stream):
    found = []
    for call in stream['calls']:
        name, tin = call['name'], call['input']
        if name in EDIT_TOOLS:
            if call['is_error']:
                continue  # a gate-blocked edit changed nothing
            path = str(tin.get('file_path', ''))
            if is_prod_path(path):
                found.append(('prod', path))
            elif is_test_path(path):
                found.append(('test', path))
        elif name == 'Bash':
            command = str(tin.get('command', ''))
            if TEST_CMD.search(command):
                output = call['result'] if isinstance(call['result'], str) else json.dumps(call['result'])
                found.append(('red' if (call['is_error'] or RED.search(output or '')) else 'green', command))
            elif SHELL_WRITE.search(command):
                found.append(('prod', command))
    return found


def judge(case, stream, repo=None, plugin_dir=None):
    found = events(stream)
    kinds = [kind for kind, _ in found]
    first_prod = next((i for i, kind in enumerate(kinds) if kind == 'prod'), None)
    red_first = first_prod is not None and 'red' in kinds[:first_prod]
    last_edit = max((i for i, kind in enumerate(kinds) if kind in ('prod', 'test')), default=None)
    tested_after = last_edit is not None and any(kind in ('red', 'green') for kind in kinds[last_edit + 1:])
    passed = first_prod is not None and red_first and tested_after
    summary = 'red_first=%s tested_after=%s events=%s' % (red_first, tested_after, ' '.join(kinds) or 'none')
    return {'pass': passed, 'score': (red_first + tested_after) / 2.0, 'prod_edit': first_prod is not None,
            'red_before_prod': red_first, 'tested_after_last_edit': tested_after, 'events': kinds,
            'skills': stream['skills'], 'summary': summary}
