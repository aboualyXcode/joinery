// The join lab computes each join type in the browser so it can draw which
// rows pair up; the engine then runs the real SQL for comparison.

export type JoinType = 'inner' | 'left' | 'right' | 'full' | 'cross' | 'semi' | 'anti';

export interface Player { id: number; name: string; team_id: number | null; role: string }
export interface Team { id: number; name: string; city: string }
export interface JoinRow { player: Player | null; team: Team | null }

export const JOIN_SQL: Record<JoinType, string> = {
  inner: 'SELECT p.name AS player, t.name AS team\nFROM players AS p\nJOIN teams AS t ON t.id = p.team_id;',
  left: 'SELECT p.name AS player, t.name AS team\nFROM players AS p\nLEFT JOIN teams AS t ON t.id = p.team_id;',
  right: 'SELECT p.name AS player, t.name AS team\nFROM players AS p\nRIGHT JOIN teams AS t ON t.id = p.team_id;',
  full: 'SELECT p.name AS player, t.name AS team\nFROM players AS p\nFULL JOIN teams AS t ON t.id = p.team_id;',
  cross: 'SELECT p.name AS player, t.name AS team\nFROM players AS p\nCROSS JOIN teams AS t;',
  semi: 'SELECT t.name AS team\nFROM teams AS t\nWHERE EXISTS (SELECT 1 FROM players AS p WHERE p.team_id = t.id);',
  anti: 'SELECT t.name AS team\nFROM teams AS t\nWHERE NOT EXISTS (SELECT 1 FROM players AS p WHERE p.team_id = t.id);',
};

export const JOIN_NOTES: Record<JoinType, string> = {
  inner: 'Only pairs that satisfy the ON condition. Unmatched rows on either side disappear.',
  left: 'Every player, matched or not. Players without a team get NULL team columns.',
  right: 'Every team, matched or not. Teams without players get NULL player columns.',
  full: 'Every row from both sides: matched pairs plus the unmatched rows from each side, padded with NULL.',
  cross: 'Every player paired with every team, with no condition at all: 7 × 4 = 28 rows.',
  semi: 'Teams that have at least one player, each listed once however many players match.',
  anti: 'Teams that have no players at all.',
};

export function computeJoin(type: JoinType, players: Player[], teams: Team[]): JoinRow[] {
  const matches = (p: Player, t: Team) => p.team_id !== null && p.team_id === t.id;
  const pairs: JoinRow[] = [];
  for (const p of players) for (const t of teams) if (matches(p, t)) pairs.push({ player: p, team: t });
  switch (type) {
    case 'inner':
      return pairs;
    case 'left':
      return players.flatMap((p): JoinRow[] => {
        const found = teams.filter((t) => matches(p, t));
        return found.length ? found.map((t) => ({ player: p, team: t })) : [{ player: p, team: null }];
      });
    case 'right':
      return teams.flatMap((t): JoinRow[] => {
        const found = players.filter((p) => matches(p, t));
        return found.length ? found.map((p) => ({ player: p, team: t })) : [{ player: null, team: t }];
      });
    case 'full': {
      const left = computeJoin('left', players, teams);
      const unmatchedTeams = teams.filter((t) => !players.some((p) => matches(p, t)));
      return [...left, ...unmatchedTeams.map((t) => ({ player: null, team: t }))];
    }
    case 'cross':
      return players.flatMap((p): JoinRow[] => teams.map((t) => ({ player: p, team: t })));
    case 'semi':
      return teams.filter((t) => players.some((p) => matches(p, t))).map((t) => ({ player: null, team: t }));
    case 'anti':
      return teams.filter((t) => !players.some((p) => matches(p, t))).map((t) => ({ player: null, team: t }));
  }
}

/** Which source rows appear in the result: used to highlight or strike them. */
export function survivors(type: JoinType, rows: JoinRow[]): { players: Set<number>; teams: Set<number> } {
  const players = new Set<number>();
  const teams = new Set<number>();
  for (const row of rows) {
    if (row.player && type !== 'semi' && type !== 'anti') players.add(row.player.id);
    if (row.team) teams.add(row.team.id);
  }
  return { players, teams };
}
