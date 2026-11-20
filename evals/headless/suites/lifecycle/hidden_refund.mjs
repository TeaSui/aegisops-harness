const w = await import(new URL('file://' + process.argv[2]).href);
const out = {};
const fnName = Object.keys(w).find(k => /refund/i.test(k) && typeof w[k] === 'function' && !/get|list|find/i.test(k));
const refund = w[fnName];
const idOf = t => (t && typeof t === 'object') ? (t.id ?? t.transferId ?? t.txId) : t;
const tryRefund = (id, amt) => { try { amt === undefined ? refund(id) : refund(id, amt); return true; } catch (e) { return false; } };
try {
  w.deposit('ann', 10); const t = w.transfer('ann', 'bob', 4); const id = idOf(t);
  const ok = tryRefund(id) || tryRefund(id, 4);
  out.money_returned = ok && w.balance('ann') === 10 && w.balance('bob') === 0;
  out.at_most_once = !tryRefund(id) && !tryRefund(id, 4) && w.balance('ann') === 10;
  w.deposit('cat', 10); const t2 = w.transfer('cat', 'dan', 3); const id2 = idOf(t2);
  out.never_more_than_sent = !tryRefund(id2, 5) && w.balance('cat') === 7 && w.balance('dan') === 3;
} catch (e) { out.error = String(e).slice(0, 200); }
out.refund_fn = fnName || null;
console.log(JSON.stringify(out));
