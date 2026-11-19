"""Lifecycle suite fixture: the shared Node shop plus wallet tests and a README, committed on `main`."""
import node_shop

EXTRA = {
    'README.md': '# shop\n\nA small wallet and math library. Run the tests with `npm test`.\n',
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
    return node_shop.build(repo, case.get('setup', 'none'), EXTRA)
