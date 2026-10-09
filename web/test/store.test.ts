import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createStore, type KeyValueStorage } from '../src/lib/store.ts';

function memory(initial: Record<string, string> = {}): KeyValueStorage {
  const data = new Map(Object.entries(initial));
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => { data.set(k, v); }, removeItem: (k) => { data.delete(k); } };
}

test('progress persists through storage', () => {
  const storage = memory();
  const first = createStore(storage, () => 42);
  first.complete('joins-never-ordered');
  first.saveAttempt('joins-never-ordered', 'SELECT 1');
  const second = createStore(storage);
  assert.ok(second.isComplete('joins-never-ordered'));
  assert.equal(second.attempt('joins-never-ordered'), 'SELECT 1');
});

test('corrupt or foreign data is ignored', () => {
  assert.equal(Object.keys(createStore(memory({ 'joinery.progress.v1': '{oops' })).get().completed).length, 0);
  const store = createStore(memory());
  assert.equal(store.importJson('{"completed": 3}'), false);
  assert.equal(store.importJson('not json'), false);
});

test('export and import round-trip', () => {
  const source = createStore(memory());
  source.complete('a');
  const target = createStore(memory());
  assert.ok(target.importJson(source.exportJson()));
  assert.ok(target.isComplete('a'));
});

test('it works without any storage', () => {
  const store = createStore(null);
  store.complete('x');
  assert.ok(store.isComplete('x'));
});
