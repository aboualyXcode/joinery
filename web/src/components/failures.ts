// The failure explorer: start from a symptom or paste a message, then watch
// the failure travel across the engine map and reproduce it live.
import { api } from '../api.ts';
import { h, mount, s } from '../lib/dom.ts';
import { formatNumber, formatSteps, plural } from '../lib/format.ts';
import { KIND_NAMES, matchFailure } from '../lib/explore.ts';
import { highlightHTML } from '../lib/sql.ts';
import { href } from '../router.ts';
import type { CompareSide, ExploreData, Failure } from '../types.ts';
import { createEngineMap, pathChips } from './enginemap.ts';
import { flattenPlan } from './plan.ts';
import { renderError, renderTable } from './results.ts';
import { renderTimeline } from './timeline.ts';
import { requestError } from './workbench.ts';

const ENGINE_LABELS: Record<string, string> = {
  sqlite: 'SQLite', postgres: 'PostgreSQL', mysql: 'MySQL', mssql: 'SQL Server', duckdb: 'DuckDB',
};

function fan(data: ExploreData, symptomId: string, selected: string | null, choose: (id: string) => void): SVGSVGElement {
  const symptom = data.symptoms.find((sy) => sy.id === symptomId) ?? data.symptoms[0];
  const ids = symptom?.failures ?? [];
  const rowH = 46;
  const height = Math.max(ids.length * rowH + 10, 120);
  const svg = s('svg', { class: 'fan', viewBox: `0 0 640 ${height}`, role: 'group', 'aria-label': `Causes of: ${symptom?.title ?? ''}` });
  const cy = height / 2;
  svg.append(s('rect', { class: 'fan-symptom', x: 4, y: cy - 30, width: 180, height: 60, rx: 8 }),
    s('text', { class: 'fan-symptom-text', x: 94, y: cy + 5, 'text-anchor': 'middle' }, symptom?.title ?? ''));
  ids.forEach((id, i) => {
    const failure = data.failures.find((f) => f.id === id);
    if (!failure) return;
    const y = 8 + i * rowH + rowH / 2;
    svg.append(s('path', { class: `fan-wire${id === selected ? ' on' : ''}`, d: `M 184 ${cy} C 230 ${cy}, 230 ${y}, 270 ${y}` }));
    svg.append(s('g', {
      class: `fan-cause kind-${failure.kind}${id === selected ? ' on' : ''}`, tabindex: '0', role: 'button',
      'aria-label': `${failure.title}: ${failure.tell}`,
      on: {
        click: () => choose(id),
        keydown: (event: KeyboardEvent) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(id); } },
      },
    },
    s('rect', { x: 270, y: y - 19, width: 362, height: 38, rx: 6 }),
    s('text', { class: 'fan-title', x: 282, y: y - 3 }, failure.title),
    s('text', { class: 'fan-tell', x: 282, y: y + 12 }, failure.tell)));
  });
  return svg;
}

function bars(rows: { label: string; value: number }[]): HTMLElement {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return h('div', { class: 'bars' }, rows.map((row) => {
    const fill = h('span', { class: 'bar-fill' });
    fill.style.setProperty('--value', String(row.value / max));
    return h('div', { class: 'bar-row' }, h('span', { class: 'bar-label' }, row.label),
      h('span', { class: 'bar' }, fill), h('span', { class: 'bar-value' }, formatSteps(row.value)));
  }));
}

async function runCompare(failure: Failure, target: HTMLElement): Promise<void> {
  const compare = failure.compare;
  if (!compare) return;
  const sides: [string, CompareSide][] = [[compare.slow.label ?? 'Slow', compare.slow], [compare.fast.label ?? 'Fast', compare.fast]];
  mount(target, h('p', { class: 'loading', role: 'status' }, 'Running both versions\u2026'));
  try {
    if (failure.kind === 'wrong') {
      const results = await Promise.all(sides.map(([, side]) => api.run({ sql: side.sql, dataset: compare.dataset })));
      mount(target, h('div', { class: 'two-up' }, sides.map(([name, side], i) => {
        const statement = results[i]?.statements[0];
        return h('section', null, h('h4', null, `${name}: ${plural(statement?.row_count ?? 0, 'row')}`),
          h('pre', { class: 'code small' }, h('code', { html: highlightHTML(side.sql) })),
          statement ? renderTable(statement.columns, statement.rows, { caption: `${name} result` }) : null);
      })));
      return;
    }
    const plans = await Promise.all(sides.map(([, side]) => api.explain({ sql: side.sql, dataset: compare.dataset, setup: side.setup ?? null })));
    mount(target,
      bars(sides.map(([name], i) => ({ label: name, value: plans[i]?.metrics?.vm_steps ?? 0 }))),
      h('div', { class: 'two-up' }, sides.map(([name, side], i) => h('section', null,
        h('h4', null, name),
        side.setup ? h('p', { class: 'muted' }, 'After: ', h('code', null, side.setup)) : null,
        h('pre', { class: 'code small' }, h('code', { html: highlightHTML(side.sql) })),
        h('ul', { class: 'plan-mini' }, flattenPlan(plans[i]?.tree ?? []).map((node) =>
          h('li', { class: `kind-${node.kind} ${node.severity}` }, node.label)))))));
  } catch (error) {
    mount(target, renderError(requestError(error)));
  }
}

async function runDemo(failure: Failure, target: HTMLElement): Promise<void> {
  const demo = failure.demo;
  if (!demo) return;
  mount(target, h('p', { class: 'loading', role: 'status' }, 'Running it on SQLite\u2026'));
  try {
    const result = await api.run({ sql: demo.sql, dataset: demo.dataset });
    const failed = result.statements.find((st) => st.error);
    const last = result.statements[result.statements.length - 1];
    mount(target,
      renderTimeline(result, demo.sql),
      failed?.error ? renderError(failed.error) : result.error ? renderError(result.error)
        : last ? h('div', null, h('p', { class: 'muted' }, 'No error was raised:'), renderTable(last.columns, last.rows)) : null);
  } catch (error) {
    mount(target, renderError(requestError(error)));
  }
}

function detail(data: ExploreData, failure: Failure): HTMLElement {
  const live = h('div', { class: 'live' });
  const messages = Object.entries(failure.messages ?? {});
  return h('div', { class: 'failure-detail' },
    h('div', { class: 'detail-head' }, h('h3', null, failure.title), h('span', { class: `kind-badge kind-${failure.kind}` }, KIND_NAMES[failure.kind] ?? failure.kind)),
    pathChips(data, failure),
    h('dl', { class: 'facts-list' },
      h('div', null, h('dt', null, 'You see'), h('dd', null, failure.sees)),
      h('div', null, h('dt', null, 'Cause'), h('dd', null, failure.cause)),
      h('div', null, h('dt', null, 'Fix'), h('dd', null, failure.fix))),
    messages.length ? h('table', { class: 'messages' }, h('tbody', null, messages.map(([engine, message]) =>
      h('tr', null, h('th', { scope: 'row' }, ENGINE_LABELS[engine] ?? engine), h('td', null, h('code', null, message)))))) : null,
    failure.demo ? h('div', null,
      h('pre', { class: 'code small' }, h('code', { html: highlightHTML(failure.demo.sql) })),
      h('button', { type: 'button', class: 'button primary', on: { click: () => void runDemo(failure, live) } }, 'Reproduce it on SQLite')) : null,
    failure.compare ? h('button', { type: 'button', class: 'button primary', on: { click: () => void runCompare(failure, live) } },
      failure.kind === 'wrong' ? 'Run the wrong and the right query' : 'Compare the work done') : null,
    live);
}

export function renderFailureExplorer(data: ExploreData, options: { initial?: string | undefined; symptom?: string | undefined; matcher?: boolean } = {}): HTMLElement {
  let selected: Failure | undefined = data.failures.find((f) => f.id === options.initial);
  let symptomId = options.symptom ?? data.symptoms.find((sy) => selected && sy.failures.includes(selected.id))?.id ?? data.symptoms[0]?.id ?? '';
  const map = createEngineMap(data, (station) => {
    const first = data.failures.find((f) => f.origin === station.id);
    if (first) choose(first.id);
  });
  const fanArea = h('div', { class: 'fan-area' });
  const detailArea = h('div', { class: 'failure-area', 'aria-live': 'polite' });
  const matchNote = h('p', { class: 'match-note', role: 'status' });
  const symptomButtons = data.symptoms.map((sy) => h('button', {
    type: 'button', 'aria-pressed': String(sy.id === symptomId),
    on: { click: () => { symptomId = sy.id; renderFan(); } },
  }, sy.title));

  function renderFan(): void {
    symptomButtons.forEach((b, i) => b.setAttribute('aria-pressed', String(data.symptoms[i]?.id === symptomId)));
    mount(fanArea, fan(data, symptomId, selected?.id ?? null, choose));
  }
  function choose(id: string): void {
    selected = data.failures.find((f) => f.id === id);
    if (!selected) return;
    if (!data.symptoms.find((sy) => sy.id === symptomId)?.failures.includes(id)) {
      symptomId = data.symptoms.find((sy) => sy.failures.includes(id))?.id ?? symptomId;
    }
    renderFan();
    map.trace(selected);
    mount(detailArea, detail(data, selected));
    if (location.hash.startsWith('#/explore/failures')) history.replaceState(null, '', href(`explore/failures/${id}`));
  }

  const matcher = options.matcher === false ? null : h('div', { class: 'matcher' },
    h('label', { for: 'paste-error' }, 'Paste an error message from any engine'),
    h('textarea', {
      id: 'paste-error', rows: '2', placeholder: 'For example: duplicate key value violates unique constraint "orders_pkey"',
      on: {
        input: (event: Event) => {
          const text = (event.target as HTMLTextAreaElement).value.trim();
          if (!text) { matchNote.textContent = ''; return; }
          const found = matchFailure(text);
          matchNote.textContent = found ? `Matched: ${found.title}` : 'No match yet. Paste the whole message, including the error code if there is one.';
          if (found) choose(found.id);
        },
      },
    }),
    matchNote);

  const root = h('div', { class: 'failure-explorer' },
    matcher,
    h('div', { class: 'segmented', role: 'group', 'aria-label': 'Start from what you see' }, symptomButtons),
    h('div', { class: 'failure-layout' },
      h('div', { class: 'failure-left' }, fanArea),
      h('div', { class: 'failure-right' }, map.element, detailArea)));
  renderFan();
  if (selected) choose(selected.id);
  else mount(detailArea, h('p', { class: 'muted' }, `Choose one of the ${formatNumber(data.failures.length)} failures to see where it starts and where it surfaces.`));
  return root;
}
