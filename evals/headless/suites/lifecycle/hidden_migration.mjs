// Hidden outcome checks for L5-storage-migration. Argument: the fixture repository. Prints one JSON object of booleans.
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const repo = process.argv[2];
const load = (rel) => import(new URL('file://' + repo + '/' + rel).href);
const out = { migrates_v1: false, backup_kept: false, idempotent: false, rejects_future_version: false,
              rejects_corrupt: false, missing_file_is_empty: false, api_in_cents: false };
const codeOf = (fn) => { try { fn(); return null; } catch (error) { return (error && error.code) || 'threw'; } };
const scratch = () => mkdtempSync(join(tmpdir(), 'hidden-migration-'));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
try {
  const store = await load('src/store.js');

  // Version 1 holds decimal currency units, with the float noise real files have.
  const folder = scratch();
  const path = join(folder, 'wallet.json');
  const original = JSON.stringify({ balances: { ann: 0.30000000000000004, bob: 19.99, cat: 1.005, dan: 0 } }, null, 2) + '\n';
  writeFileSync(path, original);
  const cents = { ann: 30, bob: 1999, cat: 100, dan: 0 };
  const state = store.load(path);
  const onDisk = JSON.parse(readFileSync(path, 'utf8'));
  out.migrates_v1 = state.version === 2 && same(state.balances, cents) && onDisk.version === 2 && same(onDisk.balances, cents);

  const backup = join(folder, 'wallet.v1.bak.json');
  out.backup_kept = existsSync(backup) && readFileSync(backup, 'utf8') === original;

  const afterFirst = readFileSync(path, 'utf8');
  const again = store.load(path);
  out.idempotent = same(again, state) && readFileSync(path, 'utf8') === afterFirst
    && existsSync(backup) && readFileSync(backup, 'utf8') === original;

  const futureFolder = scratch();
  const future = join(futureFolder, 'wallet.json');
  const futureText = JSON.stringify({ version: 3, balances: { ann: 5 } });
  writeFileSync(future, futureText);
  out.rejects_future_version = codeOf(() => store.load(future)) === 'UNSUPPORTED_VERSION'
    && readFileSync(future, 'utf8') === futureText && !existsSync(join(futureFolder, 'wallet.v1.bak.json'));

  out.rejects_corrupt = [{ ann: 'ten' }, { ann: -5 }, { ann: null }].every((balances) => {
    const badFolder = scratch();
    const bad = join(badFolder, 'wallet.json');
    const text = JSON.stringify({ balances });
    writeFileSync(bad, text);
    return codeOf(() => store.load(bad)) === 'CORRUPT_DATA' && readFileSync(bad, 'utf8') === text
      && !existsSync(join(badFolder, 'wallet.v1.bak.json'));
  });

  const missing = join(scratch(), 'wallet.json');
  const empty = store.load(missing);
  out.missing_file_is_empty = empty.version === 2 && same(empty.balances, {}) && !existsSync(missing);

  // The wallet works in cents on a migrated file.
  const walletFile = join(scratch(), 'wallet.json');
  writeFileSync(walletFile, JSON.stringify({ balances: { ann: 0.3 } }));
  process.env.WALLET_FILE = walletFile;
  const wallet = await load('src/wallet.js');
  const start = wallet.balance('ann') === 30;
  wallet.deposit('ann', 250);
  wallet.transfer('ann', 'bob', 80);
  const moved = wallet.balance('ann') === 200 && wallet.balance('bob') === 80;
  const strict = codeOf(() => wallet.deposit('ann', 2.5)) === 'INVALID_AMOUNT';
  const saved = JSON.parse(readFileSync(walletFile, 'utf8'));
  out.api_in_cents = start && moved && strict && saved.version === 2 && same(saved.balances, { ann: 200, bob: 80 });
} catch (error) {
  out.error = String(error).slice(0, 200);
}
console.log(JSON.stringify(out));
