import { post, balanceOf } from './ledger.js';
import { openAccount, requireAccount } from './accounts.js';
import { coded } from './money.js';

let transfers = 0;

function amount(cents) {
  if (!Number.isInteger(cents) || cents <= 0) throw coded('INVALID_AMOUNT', String(cents));
  return cents;
}

export { openAccount };

export function deposit(account, cents) {
  requireAccount(account);
  post([{ account, delta: amount(cents), kind: 'deposit', ref: null }]);
}

export function transfer(from, to, cents) {
  requireAccount(from);
  requireAccount(to);
  amount(cents);
  if (from === to) throw coded('SAME_ACCOUNT', from);
  if (balanceOf(from) < cents) throw coded('INSUFFICIENT_FUNDS', from);
  const id = `tr-${++transfers}`;
  post([
    { account: from, delta: -cents, kind: 'transfer-out', ref: id, counterparty: to },
    { account: to, delta: cents, kind: 'transfer-in', ref: id, counterparty: from },
  ]);
  return id;
}

export const balance = (account) => balanceOf(requireAccount(account));
