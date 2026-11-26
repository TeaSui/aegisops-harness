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

// One lock per wallet. `tails` holds, per wallet, a promise that settles when its current holder lets go.
const tails = new Map();

function acquire(key) {
  const previous = tails.get(key) ?? Promise.resolve();
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  tails.set(key, previous.then(() => held));
  return previous.then(() => release);
}

// Locks are always taken in sorted order, so two transfers in opposite directions cannot wait on each other.
async function withLocks(keys, work) {
  const ordered = [...new Set(keys)].sort();
  const releases = [];
  for (const key of ordered) releases.push(await acquire(key));
  try {
    return await work();
  } finally {
    for (const release of releases.reverse()) release();
  }
}

export async function deposit(user, cents) {
  amount(cents);
  return withLocks([user], async () => {
    const current = await db.get(user);
    await db.put(user, current + cents);
  });
}

export async function transfer(from, to, cents) {
  amount(cents);
  if (from === to) throw coded('SAME_ACCOUNT', from);
  return withLocks([from, to], async () => {
    const available = await db.get(from);
    if (available < cents) throw coded('INSUFFICIENT_FUNDS', from);
    const target = await db.get(to);
    await db.put(from, available - cents);
    await db.put(to, target + cents);
  });
}

export const balance = (user) => db.get(user);
