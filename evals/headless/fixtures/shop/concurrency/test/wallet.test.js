import test from 'node:test';
import assert from 'node:assert/strict';
import { deposit, transfer, balance } from '../src/wallet.js';

test('a deposit is added to the balance', async () => {
  await deposit('ann', 1000);
  assert.equal(await balance('ann'), 1000);
});

test('a transfer moves the amount', async () => {
  await deposit('bob', 500);
  await transfer('bob', 'cat', 200);
  assert.equal(await balance('bob'), 300);
  assert.equal(await balance('cat'), 200);
});

test('a transfer above the balance is rejected', async () => {
  await deposit('dan', 100);
  await assert.rejects(transfer('dan', 'eve', 101), { code: 'INSUFFICIENT_FUNDS' });
  assert.equal(await balance('dan'), 100);
});

test('amounts are positive integer cents and a self-transfer is rejected', async () => {
  await assert.rejects(deposit('fay', 0), { code: 'INVALID_AMOUNT' });
  await assert.rejects(deposit('fay', 1.5), { code: 'INVALID_AMOUNT' });
  await assert.rejects(transfer('fay', 'fay', 1), { code: 'SAME_ACCOUNT' });
});
