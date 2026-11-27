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

test('CON-1 transfers issued together never overdraw the wallet', async () => {
  await deposit('gus', 5);
  const settled = await Promise.allSettled(Array.from({ length: 20 }, () => transfer('gus', 'hal', 1)));
  assert.equal(settled.filter((result) => result.status === 'fulfilled').length, 5);
  assert.equal(await balance('gus'), 0);
  assert.equal(await balance('hal'), 5);
});

test('CON-2 deposits issued together all count', async () => {
  await Promise.all(Array.from({ length: 30 }, () => deposit('ivy', 1)));
  assert.equal(await balance('ivy'), 30);
});

test('CON-3 opposite transfers issued together both finish', async () => {
  await deposit('jon', 5);
  await deposit('kim', 5);
  await Promise.all([transfer('jon', 'kim', 1), transfer('kim', 'jon', 2)]);
  assert.equal(await balance('jon'), 6);
  assert.equal(await balance('kim'), 4);
});
