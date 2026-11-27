// Hidden outcome checks for L4-brownfield-fee. Argument: the fixture repository. Prints one JSON object of booleans.
const repo = process.argv[2];
const load = (rel) => import(new URL('file://' + repo + '/' + rel).href);
const out = { fee_quote: false, sender_pays_amount_plus_fee: false, conserved: false, insufficient_is_atomic: false,
              statement_has_fee_line: false, api_unchanged: false };
const codeOf = (fn) => { try { fn(); return null; } catch (error) { return (error && error.code) || 'threw'; } };
const FEES = 'sys:fees';
try {
  const wallet = await load('src/wallet.js');
  const ledger = await load('src/ledger.js');
  const statements = await load('src/statement.js');
  let fees = null;
  try { fees = await load('src/fees.js'); } catch (error) { out.error = 'src/fees.js: ' + String(error).slice(0, 120); }

  if (fees && typeof fees.quoteFee === 'function') {
    // 1% rounded half up to the cent, at least one cent: floor, ceil and half-even each miss one of these.
    const amounts = [1, 50, 149, 150, 250, 10000, 123456];
    out.fee_quote = JSON.stringify(amounts.map((n) => fees.quoteFee(n))) === JSON.stringify([1, 1, 1, 2, 3, 100, 1235]);
  }

  wallet.openAccount('hf-a');
  wallet.openAccount('hf-b');
  wallet.deposit('hf-a', 10000);
  const feesBefore = ledger.balanceOf(FEES);
  const id = wallet.transfer('hf-a', 'hf-b', 2500);
  const charged = ledger.balanceOf(FEES) - feesBefore;
  out.sender_pays_amount_plus_fee = wallet.balance('hf-a') === 7475 && wallet.balance('hf-b') === 2500 && charged === 25;
  out.conserved = wallet.balance('hf-a') + wallet.balance('hf-b') + charged === 10000;

  wallet.openAccount('hf-c');
  wallet.openAccount('hf-d');
  wallet.deposit('hf-c', 100);
  const sizeBefore = ledger.size();
  const feesMid = ledger.balanceOf(FEES);
  const rejected = codeOf(() => wallet.transfer('hf-c', 'hf-d', 100)) === 'INSUFFICIENT_FUNDS';  // needs 100 + 1
  const untouched = wallet.balance('hf-c') === 100 && wallet.balance('hf-d') === 0 && ledger.size() === sizeBefore
    && ledger.balanceOf(FEES) === feesMid;
  const exact = codeOf(() => wallet.transfer('hf-c', 'hf-d', 99)) === null && wallet.balance('hf-c') === 0;
  out.insufficient_is_atomic = rejected && untouched && exact;

  const lines = statements.statement('hf-a');
  const at = lines.findIndex((line) => line.kind === 'transfer-out' && line.ref === id);
  const fee = lines[at + 1];
  out.statement_has_fee_line = at >= 0 && lines[at].amount === 2500 && Boolean(fee) && fee.kind === 'fee'
    && fee.amount === 25 && fee.ref === id && lines[lines.length - 1].balanceAfter === wallet.balance('hf-a')
    && JSON.stringify(statements.statement('hf-b').map((line) => line.kind)) === JSON.stringify(['transfer-in']);

  out.api_unchanged = typeof id === 'string' && id.length > 0
    && ['openAccount', 'deposit', 'transfer', 'balance'].every((name) => typeof wallet[name] === 'function')
    && ['post', 'balanceOf', 'entriesOf', 'size'].every((name) => typeof ledger[name] === 'function')
    && typeof statements.formatStatement('hf-a') === 'string'
    && statements.formatStatement('hf-a').split('\n').length === lines.length;
} catch (error) {
  out.error = String(error).slice(0, 200);
}
console.log(JSON.stringify(out));
