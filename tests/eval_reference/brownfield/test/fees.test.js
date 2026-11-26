import test from 'node:test';
import assert from 'node:assert/strict';
import { quoteFee } from '../src/fees.js';

test('FEE-2 the fee is 1% rounded half up, at least one cent', () => {
  assert.deepEqual([1, 50, 149, 150, 250, 10000].map(quoteFee), [1, 1, 1, 2, 3, 100]);
});
