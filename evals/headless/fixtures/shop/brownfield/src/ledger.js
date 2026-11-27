import { coded } from './money.js';

// Append-only journal. A posting is a list of entries that is written completely or not at all.
const entries = [];

export function post(lines) {
  for (const line of lines) {
    if (!Number.isInteger(line.delta) || line.delta === 0) {
      throw coded('INVALID_AMOUNT', `delta must be a non-zero integer, got ${line.delta}`);
    }
  }
  const posted = lines.map((line, index) => ({ id: entries.length + index + 1, ...line }));
  entries.push(...posted);
  return posted;
}

export const balanceOf = (account) => entries.reduce((sum, entry) => (entry.account === account ? sum + entry.delta : sum), 0);
export const entriesOf = (account) => entries.filter((entry) => entry.account === account);
export const size = () => entries.length;
