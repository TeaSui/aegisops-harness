import { existsSync, readFileSync, writeFileSync } from 'node:fs';

// The data file, version 1: { "balances": { "<user>": <amount as a decimal number of currency units> } }
export function load(path) {
  if (!existsSync(path)) return { balances: {} };
  return JSON.parse(readFileSync(path, 'utf8'));
}

export function save(path, state) {
  writeFileSync(path, JSON.stringify(state, null, 2) + '\n');
}
