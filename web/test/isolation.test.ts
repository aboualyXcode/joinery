import assert from 'node:assert/strict';
import { test } from 'node:test';
import { type Level, LEVELS, SCENARIOS } from '../src/data/isolation.ts';

test('every outcome describes every step', () => {
  for (const scenario of SCENARIOS) {
    for (const { id } of LEVELS) {
      const outcome = scenario.outcomes[id];
      assert.equal(outcome.results.length, scenario.steps.length, `${scenario.id}/${id}`);
      outcome.errors.forEach((index) => assert.ok(index < scenario.steps.length));
      assert.ok(scenario.standard[id], `${scenario.id}/${id} standard`);
    }
  }
});

test('anomalies match PostgreSQL behaviour at each level', () => {
  const anomalies: Record<string, Level[]> = {
    'dirty-read': [],
    'non-repeatable-read': ['read-uncommitted', 'read-committed'],
    'phantom-read': ['read-uncommitted', 'read-committed'],
    'lost-update': ['read-uncommitted', 'read-committed'],
    'write-skew': ['read-uncommitted', 'read-committed', 'repeatable-read'],
  };
  for (const scenario of SCENARIOS) {
    const actual = LEVELS.map((l) => l.id).filter((level) => scenario.outcomes[level].anomaly);
    assert.deepEqual(actual, anomalies[scenario.id], scenario.id);
  }
});
