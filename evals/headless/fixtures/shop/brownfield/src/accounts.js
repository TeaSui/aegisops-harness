import { coded } from './money.js';

const open = new Set();

export function openAccount(id) {
  if (typeof id !== 'string' || !/^[a-z][a-z0-9:_-]*$/.test(id)) throw coded('INVALID_ACCOUNT', String(id));
  open.add(id);
  return id;
}

export function requireAccount(id) {
  if (!open.has(id)) throw coded('UNKNOWN_ACCOUNT', String(id));
  return id;
}

export const isOpen = (id) => open.has(id);
