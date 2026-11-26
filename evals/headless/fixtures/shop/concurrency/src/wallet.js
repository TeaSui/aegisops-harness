import { db } from './db.js';

function coded(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function amount(cents) {
  if (!Number.isInteger(cents) || cents <= 0) throw coded('INVALID_AMOUNT', String(cents));
  return cents;
}

export async function deposit(user, cents) {
  amount(cents);
  const current = await db.get(user);
  await db.put(user, current + cents);
}

export async function transfer(from, to, cents) {
  amount(cents);
  if (from === to) throw coded('SAME_ACCOUNT', from);
  const available = await db.get(from);
  if (available < cents) throw coded('INSUFFICIENT_FUNDS', from);
  const target = await db.get(to);
  await db.put(from, available - cents);
  await db.put(to, target + cents);
}

export const balance = (user) => db.get(user);
