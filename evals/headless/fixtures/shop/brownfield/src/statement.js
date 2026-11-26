import { entriesOf } from './ledger.js';
import { requireAccount } from './accounts.js';
import { format } from './money.js';

export function statement(account) {
  requireAccount(account);
  let running = 0;
  return entriesOf(account).map((entry) => {
    running += entry.delta;
    return {
      kind: entry.kind,
      amount: Math.abs(entry.delta),
      counterparty: entry.counterparty ?? null,
      ref: entry.ref,
      balanceAfter: running,
    };
  });
}

export function formatStatement(account) {
  return statement(account)
    .map((line) => `${line.kind.padEnd(13)}${format(line.amount).padStart(10)}${format(line.balanceAfter).padStart(11)}`)
    .join('\n');
}
