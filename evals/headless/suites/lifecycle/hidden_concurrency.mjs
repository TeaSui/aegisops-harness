// Hidden outcome checks for L6-concurrent-transfers. Argument: the fixture repository. Prints one JSON object.
const repo = process.argv[2];
const load = (rel) => import(new URL('file://' + repo + '/' + rel).href);
const out = { sequential_still_works: false, no_overdraft: false, no_lost_deposit: false, no_deadlock: false,
              rejected_writes_nothing: false, independent_wallets_overlap: false };
const within = (promise, ms) => Promise.race([
  promise.then(() => true, () => true),
  new Promise((resolve) => setTimeout(() => resolve(false), ms)),
]);
// Event-loop turns a batch needs. The store answers one turn after each call, so turns measure how much of the work
// overlapped, without a clock: a batch that runs one wallet operation at a time needs a turn per store call.
async function turns(work) {
  let count = 0;
  let running = true;
  const tick = () => { count += 1; if (running) setImmediate(tick); };
  setImmediate(tick);
  await work();
  running = false;
  return count;
}
try {
  const w = await load('src/wallet.js');

  await w.deposit('s1', 500);
  await w.transfer('s1', 's2', 200);
  out.sequential_still_works = (await w.balance('s1')) === 300 && (await w.balance('s2')) === 200;

  // 50 transfers of 1 issued together from a wallet holding 10: exactly 10 may succeed.
  await w.deposit('a', 10);
  const settled = await Promise.allSettled(Array.from({ length: 50 }, () => w.transfer('a', 'b', 1)));
  const rejected = settled.filter((result) => result.status === 'rejected');
  out.no_overdraft = settled.length - rejected.length === 10 && rejected.length === 40
    && rejected.every((result) => result.reason && result.reason.code === 'INSUFFICIENT_FUNDS')
    && (await w.balance('a')) === 0 && (await w.balance('b')) === 10;

  await Promise.all(Array.from({ length: 100 }, () => w.deposit('c', 1)));
  out.no_lost_deposit = (await w.balance('c')) === 100;

  // Opposite transfers issued together must all finish (a lock per wallet taken in one order).
  await w.deposit('d', 5);
  await w.deposit('e', 5);
  const finished = await within(Promise.all([w.transfer('d', 'e', 1), w.transfer('e', 'd', 2),
                                             w.transfer('d', 'e', 3), w.transfer('e', 'd', 1)]), 1500);
  out.no_deadlock = finished && (await w.balance('d')) === 4 && (await w.balance('e')) === 6;

  if (finished) {
    await w.deposit('f', 3);
    let code = null;
    try { await w.transfer('f', 'g', 5); } catch (error) { code = error && error.code; }
    out.rejected_writes_nothing = code === 'INSUFFICIENT_FUNDS' && (await w.balance('f')) === 3 && (await w.balance('g')) === 0;

    // 12 transfers between 12 unrelated pairs of wallets: with one lock for everything they queue up
    // (at least 4 store calls each, so 48 turns or more); with a lock per wallet they overlap.
    for (let i = 0; i < 12; i += 1) await w.deposit('p' + i, 10);
    const used = await turns(() => Promise.all(Array.from({ length: 12 }, (_, i) => w.transfer('p' + i, 'q' + i, 1))));
    out.turns = used;
    let moved = true;
    for (let i = 0; i < 12; i += 1) moved = moved && (await w.balance('p' + i)) === 9 && (await w.balance('q' + i)) === 1;
    out.independent_wallets_overlap = moved && used < 24;
  }
} catch (error) {
  out.error = String(error).slice(0, 200);
}
console.log(JSON.stringify(out));
process.exit(0);
