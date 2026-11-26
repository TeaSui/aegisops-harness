import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// The wallet reads its data file once, at import: point it at a scratch file first.
process.env.WALLET_FILE = join(mkdtempSync(join(tmpdir(), 'wallet-')), 'wallet.json');
const { deposit, transfer, balance } = await import('../src/wallet.js');

test('MIG-1 a deposit is added to the balance in cents', () => {
  deposit('ann', 1050);
  assert.equal(balance('ann'), 1050);
});

test('MIG-1 a transfer moves the amount', () => {
  deposit('bob', 2000);
  transfer('bob', 'cat', 750);
  assert.equal(balance('bob'), 1250);
  assert.equal(balance('cat'), 750);
});

test('a transfer above the balance is rejected', () => {
  deposit('dan', 100);
  assert.throws(() => transfer('dan', 'eve', 200), { code: 'INSUFFICIENT_FUNDS' });
  assert.equal(balance('dan'), 100);
});

test('MIG-1 amounts must be positive integer cents', () => {
  for (const bad of [0, -1, '5', 2.5]) assert.throws(() => deposit('fay', bad), { code: 'INVALID_AMOUNT' });
});
