"""Lifecycle suite fixture: the shared Node shop plus wallet tests and a README, committed on `main`, with a local
`origin` and a fake `gh` (fixtures/fake_gh.py) whose `pr checks` runs the tests, so the session can reach `shipped`.
A case with "fixture": "<name>" gets the code base in fixtures/shop/<name>/ laid over it (brownfield, migration,
concurrency): real files, so they can be read, linted and run on their own."""
import json
import os
import pathlib
import subprocess
import sys

import node_shop

FAKE_GH = pathlib.Path(__file__).resolve().parents[2] / 'fixtures' / 'fake_gh.py'
SHOP = pathlib.Path(__file__).resolve().parents[2] / 'fixtures' / 'shop'

# The repository is onboarded: main carries the config that pins the verify command (references/aidlc.md), with the
# JUnit report it writes in a git-ignored folder. `npm test` stays the plain run for people and for the fixture's CI.
PINNED = ('mkdir -p reports && node --test --test-reporter=junit --test-reporter-destination=reports/junit.xml '
          '--test-reporter=spec --test-reporter-destination=stdout')

EXTRA = {
    '.aidlc.json': json.dumps({'schema': 1, 'verify': {'cmd': PINNED, 'junit': 'reports/*.xml'}}, indent=2) + '\n',
    '.gitignore': 'reports/\nnode_modules/\n',
    'README.md': '# shop\n\nA small wallet and math library. Run the tests with `npm test`.\n',
    '.github/workflows/ci.yml': ('name: ci\non: [pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n'
                                 '    steps:\n      - uses: actions/checkout@v4\n      - run: npm test\n'),
    'test/wallet.test.js': (
        "import test from 'node:test';\n"
        "import assert from 'node:assert';\n"
        "import { deposit, transfer, balance } from '../src/wallet.js';\n"
        "test('transfer moves money', () => {\n"
        "  deposit('ann', 10); transfer('ann', 'bob', 4);\n"
        "  assert.equal(balance('ann'), 6); assert.equal(balance('bob'), 4);\n"
        "});\n"),
}


def variant_files(name):
    """{repo-relative path: text} of fixtures/shop/<name>/."""
    root = SHOP / name
    if not root.is_dir():
        raise ValueError('unknown fixture %r (have: %s)' % (name, ', '.join(sorted(p.name for p in SHOP.iterdir()))))
    return {path.relative_to(root).as_posix(): path.read_text() for path in sorted(root.rglob('*')) if path.is_file()}


def build(repo, case):
    extra = dict(EXTRA)
    if case.get('fixture'):
        extra.update(variant_files(case['fixture']))
    result = node_shop.build(repo, case.get('setup', 'none'), extra)
    run_dir = pathlib.Path(repo).parent
    origin = run_dir / 'origin.git'
    subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(origin)], check=True)
    subprocess.run(['git', 'remote', 'add', 'origin', str(origin)], cwd=repo, check=True)
    subprocess.run(['git', 'push', '-q', '-u', 'origin', 'main'], cwd=repo, check=True, capture_output=True)
    bin_dir = run_dir / 'bin'
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / 'gh'
    gh.write_text('#!/bin/sh\nFAKE_GH_STATE="%s" exec "%s" "%s" "$@"\n' % (run_dir / 'gh-state', sys.executable, FAKE_GH))
    gh.chmod(0o755)
    return result
