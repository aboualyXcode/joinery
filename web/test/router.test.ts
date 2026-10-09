import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatCell, formatSteps, numericColumns, plural } from '../src/lib/format.ts';
import { href, parseHash } from '../src/router.ts';

test('hash routes parse into path segments and parameters', () => {
  const route = parseHash('#/learn/joins?dataset=shop&sql=SELECT%201');
  assert.deepEqual(route.path, ['learn', 'joins']);
  assert.equal(route.params.get('sql'), 'SELECT 1');
  assert.deepEqual(parseHash('#main-content').path, []);
  assert.deepEqual(parseHash('').path, []);
});

test('links drop empty parameters', () => {
  assert.equal(href('playground', { dataset: 'shop', sql: undefined }), '#/playground?dataset=shop');
  assert.equal(href(''), '#/');
});

test('cells and figures format for people', () => {
  assert.deepEqual(formatCell(null), { text: 'NULL', kind: 'null' });
  assert.equal(formatCell({ blob: '00ff', bytes: 2 }).kind, 'blob');
  assert.deepEqual(numericColumns([[1, 'a'], [null, 'b'], [2.5, null]], 2), [true, false]);
  assert.equal(plural(1, 'row'), '1 row');
  assert.equal(plural(1200, 'row'), '1,200 rows');
  assert.equal(formatSteps(50), 'under 100 VM steps');
});
