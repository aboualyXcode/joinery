import assert from 'node:assert/strict';
import { test } from 'node:test';
import { snapshotKey } from '../src/api.ts';

test('the browser computes the same snapshot key as joinery/snapshot.py', async () => {
  // The same value is asserted in tests/test_explore.py.
  assert.equal(await snapshotKey('/api/run', { sql: 'SELECT 1', dataset: 'joinlab' }), '61af01a76bcec8d1e918b76d7c23604970f5e576');
  assert.equal(
    await snapshotKey('/api/run', { sql: 'SELECT 1', dataset: 'joinlab', engine: 'sqlite', setup: null }),
    await snapshotKey('/api/run', { sql: 'SELECT 1', dataset: 'joinlab' }));
});
