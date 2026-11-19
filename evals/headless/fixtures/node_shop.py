"""A small Node repository (no dependencies, `node --test`) shared by the headless suites.

src/math.js and src/wallet.js with one test file, committed on `main`. Wallet balances are floats on purpose: a
domain expert should notice it. `setup` variants mutate the committed state:
  failing  math.divide multiplies, so `npm test` is red
  pending  an uncommitted sub() is appended to src/math.js
"""
import pathlib
import subprocess

FILES = {
    'package.json': '{"name":"shop","type":"module","scripts":{"test":"node --test"}}\n',
    'src/math.js': 'export const add = (a, b) => a + b;\nexport const divide = (a, b) => a / b;\n',
    'src/wallet.js': (
        '// Wallet balances are stored as JS numbers (floating point).\n'
        'const balances = new Map();\n'
        'export function deposit(user, amount) { balances.set(user, (balances.get(user) || 0) + amount); }\n'
        'export function transfer(from, to, amount) {\n'
        '  balances.set(from, (balances.get(from) || 0) - amount);\n'
        '  balances.set(to, (balances.get(to) || 0) + amount);\n'
        '}\n'
        'export const balance = (user) => balances.get(user) || 0;\n'),
    'test/math.test.js': (
        "import test from 'node:test';\n"
        "import assert from 'node:assert';\n"
        "import { add, divide } from '../src/math.js';\n"
        "test('add', () => assert.equal(add(1, 2), 3));\n"
        "test('divide', () => assert.equal(divide(6, 3), 2));\n"),
}


def git(repo, *args):
    subprocess.run(['git', *args], cwd=str(repo), check=True, capture_output=True, text=True)


def build(repo, setup='none', extra_files=None):
    repo = pathlib.Path(repo)
    repo.mkdir(parents=True, exist_ok=True)
    for rel, content in {**FILES, **(extra_files or {})}.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    git(repo, 'init', '-q')
    git(repo, 'symbolic-ref', 'HEAD', 'refs/heads/main')
    git(repo, 'config', 'user.email', 'eval@example.invalid')  # sessions that commit need an identity
    git(repo, 'config', 'user.name', 'eval')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'init')
    math = repo / 'src' / 'math.js'
    if setup == 'failing':
        math.write_text(math.read_text().replace('a / b', 'a * b'))
    elif setup == 'pending':
        math.write_text(math.read_text() + 'export const sub = (a, b) => a - b;\n')
    elif setup not in ('none', '', None):
        raise ValueError('unknown setup %r' % setup)
    return repo
