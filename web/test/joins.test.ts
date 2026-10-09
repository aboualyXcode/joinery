import assert from 'node:assert/strict';
import { test } from 'node:test';
import { computeJoin, type JoinType, type Player, survivors, type Team } from '../src/lib/joins.ts';

const teams: Team[] = [
  { id: 1, name: 'Comets', city: 'Leeds' }, { id: 2, name: 'Herons', city: 'Lagos' },
  { id: 3, name: 'Owls', city: 'Lima' }, { id: 4, name: 'Foxes', city: 'Lyon' },
];
const players: Player[] = [[1, 1], [2, 1], [3, 2], [4, 2], [5, 3], [6, null], [7, null]]
  .map(([id, team]) => ({ id: id as number, name: `p${id}`, team_id: team as number | null, role: 'x' }));

test('every join type returns the textbook number of rows', () => {
  const expected: Record<JoinType, number> = { inner: 5, left: 7, right: 6, full: 8, semi: 3, anti: 1, cross: 28 };
  for (const [type, count] of Object.entries(expected)) {
    assert.equal(computeJoin(type as JoinType, players, teams).length, count, type);
  }
});

test('outer joins pad the missing side with NULL', () => {
  const left = computeJoin('left', players, teams);
  assert.equal(left.filter((row) => row.team === null).length, 2);
  const right = computeJoin('right', players, teams);
  assert.deepEqual(right.filter((row) => row.player === null).map((row) => row.team?.name), ['Foxes']);
});

test('survivors say which source rows reach the result', () => {
  const kept = survivors('inner', computeJoin('inner', players, teams));
  assert.deepEqual([...kept.teams].sort(), [1, 2, 3]);
  assert.equal(kept.players.size, 5);
  assert.deepEqual([...survivors('anti', computeJoin('anti', players, teams)).teams], [4]);
});
