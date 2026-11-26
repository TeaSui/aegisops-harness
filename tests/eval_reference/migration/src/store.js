import { existsSync, readFileSync, writeFileSync } from 'node:fs';

// The data file, version 2: { "version": 2, "balances": { "<user>": <integer cents> } }
// Version 1 had no version field and held decimal currency units.
export const VERSION = 2;

function coded(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

export function migrate(raw) {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) throw coded('CORRUPT_DATA', 'not an object');
  if (raw.version === VERSION) return raw;
  if (raw.version !== undefined) throw coded('UNSUPPORTED_VERSION', String(raw.version));
  const balances = {};
  for (const [user, amount] of Object.entries(raw.balances ?? {})) {
    if (typeof amount !== 'number' || !Number.isFinite(amount) || amount < 0) throw coded('CORRUPT_DATA', user);
    balances[user] = Math.round(amount * 100);
  }
  return { version: VERSION, balances };
}

export function load(path) {
  if (!existsSync(path)) return { version: VERSION, balances: {} };
  const text = readFileSync(path, 'utf8');
  let raw;
  try {
    raw = JSON.parse(text);
  } catch {
    throw coded('CORRUPT_DATA', 'not JSON');
  }
  const state = migrate(raw);
  if (raw.version !== VERSION) {
    const backup = path.replace(/\.json$/, '') + '.v1.bak.json';
    if (!existsSync(backup)) writeFileSync(backup, text);
    save(path, state);
  }
  return state;
}

export function save(path, state) {
  writeFileSync(path, JSON.stringify(state, null, 2) + '\n');
}
