import test from 'node:test';
import assert from 'node:assert/strict';
import { openAccount, deposit, transfer } from '../src/wallet.js';
import { statement, formatStatement } from '../src/statement.js';

test('a statement lists the entries of one account with a running balance', () => {
  openAccount('hal');
  openAccount('ivy');
  deposit('hal', 1000);
  const id = transfer('hal', 'ivy', 400);
  assert.deepEqual(statement('hal'), [
    { kind: 'deposit', amount: 1000, counterparty: null, ref: null, balanceAfter: 1000 },
    { kind: 'transfer-out', amount: 400, counterparty: 'ivy', ref: id, balanceAfter: 600 },
  ]);
  assert.deepEqual(statement('ivy'), [
    { kind: 'transfer-in', amount: 400, counterparty: 'hal', ref: id, balanceAfter: 400 },
  ]);
});

test('formatStatement prints one line per entry', () => {
  openAccount('jon');
  deposit('jon', 250);
  assert.equal(formatStatement('jon'), 'deposit            2.50       2.50');
});
