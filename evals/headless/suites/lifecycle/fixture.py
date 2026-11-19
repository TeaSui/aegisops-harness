"""Lifecycle suite fixture: the shared Node shop plus wallet tests and a README, committed on `main`, with a local
`origin` and a fake `gh` (fixtures/fake_gh.py) whose `pr checks` runs the tests, so the session can reach `shipped`."""
import os
import pathlib
import subprocess
import sys

import node_shop

FAKE_GH = pathlib.Path(__file__).resolve().parents[2] / 'fixtures' / 'fake_gh.py'

EXTRA = {
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


def build(repo, case):
    result = node_shop.build(repo, case.get('setup', 'none'), EXTRA)
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
