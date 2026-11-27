import test from 'node:test';
import assert from 'node:assert/strict';
import { openAccount, deposit, transfer, balance } from '../src/wallet.js';
import { balanceOf, size } from '../src/ledger.js';

test('a deposit is added to the balance', () => {
  openAccount('ann');
  deposit('ann', 1000);
  assert.equal(balance('ann'), 1000);
});

test('FEE-1 a transfer costs the sender the amount plus the fee', () => {
  openAccount('bob');
  openAccount('cat');
  deposit('bob', 5000);
  const before = balanceOf('sys:fees');
  const id = transfer('bob', 'cat', 2000);
  assert.match(id, /^tr-\d+$/);
  assert.equal(balance('bob'), 2980);
  assert.equal(balance('cat'), 2000);
  assert.equal(balanceOf('sys:fees') - before, 20);
});

test('FEE-3 a transfer the sender cannot pay with its fee is rejected and writes nothing', () => {
  openAccount('dan');
  openAccount('eve');
  deposit('dan', 100);
  const entries = size();
  assert.throws(() => transfer('dan', 'eve', 100), { code: 'INSUFFICIENT_FUNDS' });
  assert.equal(balance('dan'), 100);
  assert.equal(balance('eve'), 0);
  assert.equal(size(), entries);
  transfer('dan', 'eve', 99);
  assert.equal(balance('dan'), 0);
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
