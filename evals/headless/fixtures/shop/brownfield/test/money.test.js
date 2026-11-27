import test from 'node:test';
import assert from 'node:assert/strict';
import { parse, format } from '../src/money.js';

test('parse reads units and up to two decimals as cents', () => {
  assert.equal(parse('12'), 1200);
  assert.equal(parse('12.3'), 1230);
  assert.equal(parse('12.34'), 1234);
  assert.throws(() => parse('12.345'), { code: 'INVALID_AMOUNT' });
  assert.throws(() => parse('-1'), { code: 'INVALID_AMOUNT' });
});

test('format prints cents with two decimals', () => {
  assert.equal(format(1234), '12.34');
  assert.equal(format(5), '0.05');
  assert.equal(format(-250), '-2.50');
});
