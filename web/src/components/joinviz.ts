// The join lab: pick a join type, see which rows pair up, then run the SQL.
import { api } from '../api.ts';
import { h, mount, s } from '../lib/dom.ts';
import { plural } from '../lib/format.ts';
import {
  computeJoin, JOIN_NOTES, JOIN_SQL, survivors, type JoinRow, type JoinType, type Player, type Team,
} from '../lib/joins.ts';
import { highlightHTML } from '../lib/sql.ts';
import { renderError, renderTable } from './results.ts';
import { requestError } from './workbench.ts';

const TYPES: [JoinType, string][] = [
  ['inner', 'Inner'], ['left', 'Left'], ['right', 'Right'], ['full', 'Full'],
  ['semi', 'Semi (EXISTS)'], ['anti', 'Anti (NOT EXISTS)'], ['cross', 'Cross'],
];

export function renderJoinVisualizer(): HTMLElement {
  const root = h('div', { class: 'joinviz' }, h('p', { class: 'loading', role: 'status' }, 'Loading the join lab tables\u2026'));
  void load(root);
  return root;
}

async function load(root: HTMLElement): Promise<void> {
  let players: Player[];
  let teams: Team[];
  try {
    const [p, t] = await Promise.all([
      api.run({ sql: 'SELECT id, name, team_id, role FROM players ORDER BY id', dataset: 'joinlab' }),
      api.run({ sql: 'SELECT id, name, city FROM teams ORDER BY id', dataset: 'joinlab' }),
    ]);
    const pr = p.statements[0];
    const tr = t.statements[0];
    if (!pr || !tr || pr.error || tr.error) throw new Error('The join lab tables could not be loaded.');
    players = pr.rows.map((r) => ({ id: Number(r[0]), name: String(r[1]), team_id: r[2] === null ? null : Number(r[2]), role: String(r[3]) }));
    teams = tr.rows.map((r) => ({ id: Number(r[0]), name: String(r[1]), city: String(r[2]) }));
  } catch (error) {
    mount(root, renderError(requestError(error)));
    return;
  }

  let type: JoinType = 'inner';
  let rows: JoinRow[] = [];
  const playerRows = new Map<number, HTMLElement>();
  const teamRows = new Map<number, HTMLElement>();
  const playerList = h('ol', { class: 'jv-list', 'aria-label': 'players' }, players.map((p) => {
    const row = h('li', { class: 'jv-row' }, h('span', { class: 'jv-name' }, p.name),
      h('span', { class: 'jv-key' }, p.team_id === null ? 'team_id NULL' : `team_id ${p.team_id}`));
    playerRows.set(p.id, row);
    return row;
  }));
  const teamList = h('ol', { class: 'jv-list', 'aria-label': 'teams' }, teams.map((t) => {
    const row = h('li', { class: 'jv-row' }, h('span', { class: 'jv-key' }, `id ${t.id}`),
      h('span', { class: 'jv-name' }, `${t.name}, ${t.city}`));
    teamRows.set(t.id, row);
    return row;
  }));
  const lines = s('svg', { class: 'jv-lines', 'aria-hidden': 'true' });
  const middle = h('div', { class: 'jv-middle' }, lines);
  const note = h('p', { class: 'jv-note' });
  const code = h('code');
  const resultArea = h('div', { class: 'jv-result' });
  const engineArea = h('div', { class: 'jv-engine' });
  const typeButtons = TYPES.map(([id, label]) => h('button', {
    type: 'button', 'aria-pressed': String(id === type), on: { click: () => { type = id; update(); } },
  }, label));

  const draw = () => {
    const box = middle.getBoundingClientRect();
    if (!box.width) return;
    lines.setAttribute('viewBox', `0 0 ${box.width} ${box.height}`);
    lines.replaceChildren();
    for (const p of players) {
      for (const t of teams) {
        if (type !== 'cross' && p.team_id !== t.id) continue;
        const a = playerRows.get(p.id)?.getBoundingClientRect();
        const b = teamRows.get(t.id)?.getBoundingClientRect();
        if (!a || !b) continue;
        const y1 = a.top + a.height / 2 - box.top;
        const y2 = b.top + b.height / 2 - box.top;
        const active = type === 'semi' ? rows.some((r) => r.team?.id === t.id)
          : type === 'anti' ? false : rows.some((r) => r.player?.id === p.id && r.team?.id === t.id);
        lines.append(s('path', {
          d: `M 0 ${y1} C ${box.width / 2} ${y1}, ${box.width / 2} ${y2}, ${box.width} ${y2}`,
          class: active ? 'pair active' : 'pair',
        }));
      }
    }
  };

  function update(): void {
    rows = computeJoin(type, players, teams);
    const kept = survivors(type, rows);
    const teamOnly = type === 'semi' || type === 'anti';
    typeButtons.forEach((b, i) => b.setAttribute('aria-pressed', String(TYPES[i]?.[0] === type)));
    playerRows.forEach((row, id) => {
      row.classList.toggle('kept', !teamOnly && kept.players.has(id));
      row.classList.toggle('removed', !teamOnly && !kept.players.has(id));
    });
    teamRows.forEach((row, id) => {
      row.classList.toggle('kept', kept.teams.has(id));
      row.classList.toggle('removed', !kept.teams.has(id));
    });
    note.textContent = JOIN_NOTES[type];
    code.innerHTML = highlightHTML(JOIN_SQL[type]);
    const columns = teamOnly ? ['team'] : ['player', 'team'];
    const table = rows.map((r) => teamOnly ? [r.team?.name ?? null] : [r.player?.name ?? null, r.team?.name ?? null]);
    mount(resultArea, h('h4', null, `Result: ${plural(rows.length, 'row')}`), renderTable(columns, table, { caption: 'Join result' }));
    engineArea.replaceChildren();
    requestAnimationFrame(draw);
  }

  const runButton: HTMLButtonElement = h('button', {
    type: 'button', class: 'button',
    on: {
      click: async () => {
        runButton.disabled = true;
        try {
          const result = await api.run({ sql: JOIN_SQL[type], dataset: 'joinlab' });
          const statement = result.statements[0];
          if (!statement || statement.error) {
            mount(engineArea, renderError(statement?.error ?? result.error ?? requestError('No result')));
            return;
          }
          const agrees = statement.row_count === rows.length;
          mount(engineArea,
            h('p', { class: agrees ? 'agree' : 'disagree' }, agrees
              ? `SQLite returned ${plural(statement.row_count, 'row')}, the same as the diagram.`
              : `SQLite returned ${plural(statement.row_count, 'row')}, but the diagram shows ${rows.length}.`),
            renderTable(statement.columns, statement.rows, { caption: 'Engine result' }));
        } catch (error) {
          mount(engineArea, renderError(requestError(error)));
        } finally {
          runButton.disabled = false;
        }
      },
    },
  }, 'Run this SQL on the engine');

  mount(root,
    h('div', { class: 'segmented', role: 'group', 'aria-label': 'Join type' }, typeButtons),
    note,
    h('div', { class: 'jv-diagram' },
      h('div', null, h('h4', null, h('code', null, 'players')), playerList),
      middle,
      h('div', null, h('h4', null, h('code', null, 'teams')), teamList)),
    h('div', { class: 'two-up' },
      h('div', null, h('pre', { class: 'code' }, code), runButton, engineArea),
      resultArea));
  new ResizeObserver(() => draw()).observe(middle);
  update();
}
