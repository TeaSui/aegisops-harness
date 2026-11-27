import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { load, save } from '../src/store.js';

test('a missing file loads as an empty state', () => {
  assert.deepEqual(load(join(mkdtempSync(join(tmpdir(), 'store-')), 'none.json')), { balances: {} });
});

test('save then load returns the state', () => {
  const path = join(mkdtempSync(join(tmpdir(), 'store-')), 'wallet.json');
  save(path, { balances: { ann: 12.5 } });
  assert.deepEqual(load(path), { balances: { ann: 12.5 } });
});
