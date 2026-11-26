import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// The wallet reads its data file once, at import: point it at a scratch file first.
process.env.WALLET_FILE = join(mkdtempSync(join(tmpdir(), 'wallet-')), 'wallet.json');
const { deposit, transfer, balance } = await import('../src/wallet.js');

test('a deposit is added to the balance', () => {
  deposit('ann', 10.5);
  assert.equal(balance('ann'), 10.5);
});

test('a transfer moves the amount', () => {
  deposit('bob', 20);
  transfer('bob', 'cat', 7.5);
  assert.equal(balance('bob'), 12.5);
  assert.equal(balance('cat'), 7.5);
});

test('a transfer above the balance is rejected', () => {
  deposit('dan', 1);
  assert.throws(() => transfer('dan', 'eve', 2), { code: 'INSUFFICIENT_FUNDS' });
  assert.equal(balance('dan'), 1);
});

test('amounts must be positive numbers', () => {
  for (const bad of [0, -1, '5']) assert.throws(() => deposit('fay', bad), { code: 'INVALID_AMOUNT' });
});
