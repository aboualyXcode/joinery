// The join lab computes each join type in the browser so it can draw which
// rows pair up; the engine then runs the real SQL for comparison.

export type JoinType = 'inner' | 'left' | 'right' | 'full' | 'cross' | 'semi' | 'anti';

export interface Player { id: number; name: string; team_id: number | null; role: string }
export interface Team { id: number; name: string; city: string }
export interface JoinRow { player: Player | null; team: Team | null }

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
