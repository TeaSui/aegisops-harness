import test from 'node:test';
import assert from 'node:assert/strict';
import { openAccount, deposit, transfer, balance } from '../src/wallet.js';

test('a deposit is added to the balance', () => {
  openAccount('ann');
  deposit('ann', 1000);
  assert.equal(balance('ann'), 1000);
});

test('a transfer moves the amount and returns its identifier', () => {
  openAccount('bob');
  openAccount('cat');
  deposit('bob', 5000);
  const id = transfer('bob', 'cat', 2000);
  assert.match(id, /^tr-\d+$/);
  assert.equal(balance('bob'), 3000);
  assert.equal(balance('cat'), 2000);
});

test('a transfer above the balance is rejected and changes nothing', () => {
  openAccount('dan');
  openAccount('eve');
  deposit('dan', 100);
  assert.throws(() => transfer('dan', 'eve', 101), { code: 'INSUFFICIENT_FUNDS' });
  assert.equal(balance('dan'), 100);
  assert.equal(balance('eve'), 0);
});

test('amounts are positive integer cents', () => {
  openAccount('fay');
  for (const bad of [0, -5, 1.5, '10']) assert.throws(() => deposit('fay', bad), { code: 'INVALID_AMOUNT' });
});

test('unknown accounts and self-transfers are rejected', () => {
  openAccount('gus');
  deposit('gus', 500);
  assert.throws(() => transfer('gus', 'nobody', 100), { code: 'UNKNOWN_ACCOUNT' });
  assert.throws(() => transfer('gus', 'gus', 100), { code: 'SAME_ACCOUNT' });
});
