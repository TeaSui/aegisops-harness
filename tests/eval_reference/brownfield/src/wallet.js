import { post, balanceOf } from './ledger.js';
import { openAccount, requireAccount, isOpen } from './accounts.js';
import { coded } from './money.js';
import { quoteFee, FEE_ACCOUNT } from './fees.js';

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
  const fee = quoteFee(cents);
  if (balanceOf(from) < cents + fee) throw coded('INSUFFICIENT_FUNDS', from);
  if (!isOpen(FEE_ACCOUNT)) openAccount(FEE_ACCOUNT);
  const id = `tr-${++transfers}`;
  post([
    { account: from, delta: -cents, kind: 'transfer-out', ref: id, counterparty: to },
    { account: from, delta: -fee, kind: 'fee', ref: id, counterparty: FEE_ACCOUNT },
    { account: to, delta: cents, kind: 'transfer-in', ref: id, counterparty: from },
    { account: FEE_ACCOUNT, delta: fee, kind: 'fee-income', ref: id, counterparty: from },
  ]);
  return id;
}

export const balance = (account) => balanceOf(requireAccount(account));
