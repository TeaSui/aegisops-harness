import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { load, save, migrate } from '../src/store.js';

const scratch = () => join(mkdtempSync(join(tmpdir(), 'store-')), 'wallet.json');

test('MIG-7 a missing file loads as an empty version 2 state', () => {
  const path = scratch();
  assert.deepEqual(load(path), { version: 2, balances: {} });
  assert.equal(existsSync(path), false);
});

test('MIG-2 version 1 amounts become cents', () => {
  assert.deepEqual(migrate({ balances: { ann: 0.30000000000000004, bob: 19.99, cat: 1.005 } }),
    { version: 2, balances: { ann: 30, bob: 1999, cat: 100 } });
});

test('MIG-3 MIG-4 loading a version 1 file rewrites it once and keeps the original', () => {
  const path = scratch();
  const original = JSON.stringify({ balances: { ann: 12.5 } });
  writeFileSync(path, original);
  assert.deepEqual(load(path), { version: 2, balances: { ann: 1250 } });
  const rewritten = readFileSync(path, 'utf8');
  assert.equal(readFileSync(path.replace(/\.json$/, '.v1.bak.json'), 'utf8'), original);
  assert.deepEqual(load(path), { version: 2, balances: { ann: 1250 } });
  assert.equal(readFileSync(path, 'utf8'), rewritten);
});

test('MIG-5 MIG-6 a newer version or a corrupt balance is refused and the file is left alone', () => {
  const newer = scratch();
  writeFileSync(newer, '{"version":3,"balances":{}}');
  assert.throws(() => load(newer), { code: 'UNSUPPORTED_VERSION' });
  assert.equal(readFileSync(newer, 'utf8'), '{"version":3,"balances":{}}');
  const corrupt = scratch();
  writeFileSync(corrupt, '{"balances":{"ann":"ten"}}');
  assert.throws(() => load(corrupt), { code: 'CORRUPT_DATA' });
  assert.equal(readFileSync(corrupt, 'utf8'), '{"balances":{"ann":"ten"}}');
});

test('save then load returns the state', () => {
  const path = scratch();
  save(path, { version: 2, balances: { ann: 1250 } });
  assert.deepEqual(load(path), { version: 2, balances: { ann: 1250 } });
});
