import { load, save } from './store.js';

const FILE = process.env.WALLET_FILE || 'data/wallet.json';

function coded(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function cents(amount) {
  if (!Number.isInteger(amount) || amount <= 0) throw coded('INVALID_AMOUNT', String(amount));
  return amount;
}

export function deposit(user, amount) {
  cents(amount);
  const state = load(FILE);
  state.balances[user] = (state.balances[user] || 0) + amount;
  save(FILE, state);
}

export function transfer(from, to, amount) {
  cents(amount);
  const state = load(FILE);
  if ((state.balances[from] || 0) < amount) throw coded('INSUFFICIENT_FUNDS', from);
  state.balances[from] -= amount;
  state.balances[to] = (state.balances[to] || 0) + amount;
  save(FILE, state);
}

export const balance = (user) => load(FILE).balances[user] || 0;
