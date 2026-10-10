// The query map: what feeds the result (dependencies), how many rows survive
// each logical stage and what each costs, and the physical plan as a tree,
// with the bottlenecks called out on top.
import { api } from '../api.ts';
import { h, mount, s } from '../lib/dom.ts';
import { exploreData, matchFailure } from '../lib/explore.ts';
import { formatMs, formatNumber, formatSteps, plural } from '../lib/format.ts';
import { highlightHTML } from '../lib/sql.ts';
import { href } from '../router.ts';
import type { Dependencies, DepNode, PlanNode, StepsResponse, VisualizeResponse } from '../types.ts';
import { createEditor } from './editor.ts';
import { KIND_LABEL } from './plan.ts';
import { renderError } from './results.ts';
import { renderStageDetail } from './stepper.ts';
import { requestError } from './workbench.ts';

const NW = 168;
const NH = 52;
const stageName = (clause: string, title: string) => (clause === 'WITH' ? title.replace(/^CTE /, '') : clause);
const short = (text: string, n: number) => (text.length > n ? `${text.slice(0, n - 1)}\u2026` : text);
const button = (handler: () => void) => ({
  tabindex: '0', role: 'button',
  on: {
    click: handler,
    keydown: (event: KeyboardEvent) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); handler(); } },
  },
});

// ------------------------------------------------------------------ dependencies

function nodeCaption(node: DepNode): string {
  if (node.status === 'error') return 'fails here';
  if (node.status === 'blocked') return 'blocked';
  if (node.kind === 'subquery' && node.correlated) return 'runs once per row';
  if (node.rows !== undefined && node.rows !== null) return `${formatNumber(node.rows)} ${node.rows === 1 ? 'row' : 'rows'}`;
  return node.kind === 'function' ? 'table function' : '';
}

const KIND_TAG: Record<string, string> = { table: 'table', cte: 'CTE', subquery: 'subquery', function: 'function', missing: 'missing', query: 'result' };

function dependencyDiagram(deps: Dependencies, show: (node: DepNode) => void): SVGSVGElement | HTMLElement {
  const nodes = deps.nodes ?? [];
  const edges = deps.edges ?? [];
  if (!deps.supported || !nodes.length) return h('p', { class: 'muted' }, deps.reason ?? 'Nothing to draw.');
  const layer = new Map(nodes.map((n) => [n.id, 0]));
  const flowing = edges.filter((e) => e.kind !== 'writes' && e.kind !== 'recursive');
  for (let pass = 0; pass < nodes.length; pass += 1) {
    for (const e of flowing) layer.set(e.to, Math.max(layer.get(e.to) ?? 0, (layer.get(e.from) ?? 0) + 1));
  }
  const columns = new Map<number, DepNode[]>();
  nodes.forEach((n) => { const l = layer.get(n.id) ?? 0; columns.set(l, [...(columns.get(l) ?? []), n]); });
  const pos = new Map<string, { x: number; y: number }>();
  columns.forEach((list, l) => list.forEach((n, i) => pos.set(n.id, { x: 16 + l * 214, y: 26 + i * 78 })));
  const writes = edges.some((e) => e.kind === 'writes');
  const width = 16 + columns.size * 214;
  const height = 26 + Math.max(...[...columns.values()].map((c) => c.length)) * 78 + (writes ? 56 : 0);
  const svg = s('svg', { class: 'deps', viewBox: `0 0 ${width} ${height}`, role: 'group', 'aria-label': 'What feeds the result' });
  svg.style.setProperty('--w', `${width}px`);
  const bottom = height - (writes ? 40 : 0);
  for (const e of edges) {
    const a = pos.get(e.from);
    const b = pos.get(e.to);
    if (!a || !b) continue;
    let d: string;
    let lx: number;
    let ly: number;
    if (e.kind === 'recursive') {
      d = `M ${a.x + NW - 34} ${a.y} C ${a.x + NW - 34} ${a.y - 24}, ${a.x + NW + 18} ${a.y - 24}, ${a.x + NW} ${a.y + 14}`;
      lx = a.x + NW - 30;
      ly = a.y - 12;
    } else if (e.kind === 'writes') {
      d = `M ${a.x + NW / 2} ${a.y + NH} C ${a.x + NW / 2} ${bottom + 30}, ${b.x + NW / 2} ${bottom + 30}, ${b.x + NW / 2} ${b.y + NH}`;
      lx = (a.x + b.x + NW) / 2;
      ly = bottom + 24;
    } else {
      const x1 = a.x + NW;
      const y1 = a.y + NH / 2;
      const x2 = b.x;
      const y2 = b.y + NH / 2;
      d = `M ${x1} ${y1} C ${x1 + 24} ${y1}, ${x2 - 24} ${y2}, ${x2} ${y2}`;
      lx = (x1 + x2) / 2;
      ly = (y1 + y2) / 2 - 6;
    }
    svg.append(s('path', { class: `dep-edge kind-${e.kind}${e.broken ? ' broken' : ''}`, d }));
    const source = nodes.find((n) => n.id === e.from);
    const tag = e.kind === 'recursive' ? 'recursive' : e.kind === 'writes' ? 'writes'
      : e.kind !== 'reads' ? (source?.role ?? e.kind).replace('-', ' ').toUpperCase() : '';
    if (tag) svg.append(s('text', { class: 'dep-edge-label', x: lx, y: ly, 'text-anchor': 'middle' }, tag));
  }
  for (const n of nodes) {
    const p = pos.get(n.id);
    if (!p) continue;
    svg.append(s('g', {
      class: `dep-node dep-${n.kind} status-${n.status}${n.correlated ? ' correlated' : ''}`,
      transform: `translate(${p.x} ${p.y})`, 'aria-label': `${n.label}: ${KIND_TAG[n.kind]}, ${nodeCaption(n)}`,
      ...button(() => show(n)),
    },
    s('rect', { width: NW, height: NH, rx: n.kind === 'table' ? 2 : 9 }),
    n.kind === 'table' ? s('line', { x1: 0, y1: 8, x2: NW, y2: 8, class: 'table-rule' }) : null,
    s('text', { class: 'dep-label', x: 12, y: 26 }, short(n.label, 19)),
    s('text', { class: 'dep-caption', x: 12, y: 43 }, nodeCaption(n)),
    s('text', { class: 'dep-tag', x: NW - 10, y: 18, 'text-anchor': 'end' }, KIND_TAG[n.kind] ?? n.kind)));
  }
  return svg;
}

function nodeDetail(node: DepNode): HTMLElement {
  return h('div', { class: 'qm-node' },
    h('h4', null, `${node.label} (${KIND_TAG[node.kind] ?? node.kind})`),
    h('p', { class: 'facts' },
      node.rows !== undefined && node.rows !== null ? h('span', null, `${formatNumber(node.rows)} rows`) : null,
      node.work ? h('span', null, formatSteps(node.work)) : null,
      node.correlated ? h('span', null, 'correlated: it reruns for each outer row') : null,
      node.blocked_by?.length ? h('span', null, `waiting on ${node.blocked_by.map((b) => b.split(':').pop()).join(', ')}`) : null),
    node.error ? renderError(node.error) : node.message ? renderError({ type: 'Missing', message: node.message, code: null }) : null,
    node.sql ? h('pre', { class: 'code small' }, h('code', { html: highlightHTML(node.sql) })) : null);
}

// ------------------------------------------------------------------ stages

function stageBand(steps: StepsResponse, select: (index: number) => void): SVGSVGElement | HTMLElement {
  const stages = steps.stages;
  if (!steps.supported || !stages.length) return h('p', { class: 'muted' }, steps.reason ?? 'No stages to draw.');
  const rowsOut = stages.map((st) => (st.error ? 0 : st.kept_count ?? st.row_count) || 0);
  const rowsIn = stages.map((st, i) => (st.error ? 0 : st.input_count ?? (i ? rowsOut[i - 1] ?? 0 : rowsOut[i] ?? 0)) || 0);
  const max = Math.max(1, ...rowsOut, ...rowsIn);
  const scale = (n: number) => (n <= 0 ? 3 : 10 + 104 * Math.log10(n + 1) / Math.log10(max + 1));
  const work = stages.map((st, i) => Math.max(0, (st.vm_steps ?? 0) - (i ? stages[i - 1]?.vm_steps ?? 0 : 0)));
  const maxWork = Math.max(1, ...work);
  const hottest = work.indexOf(Math.max(...work));
  const colW = 108;
  const mid = 92;
  const width = 30 + stages.length * colW;
  const svg = s('svg', { class: 'band', viewBox: `0 0 ${width} 214`, role: 'group', 'aria-label': 'Rows kept at each stage' });
  svg.style.setProperty('--w', `${width}px`);
  stages.forEach((stage, i) => {
    const x = 16 + i * colW;
    const out = scale(rowsOut[i] ?? 0);
    const inp = scale(rowsIn[i] ?? 0);
    const next = stages[i + 1];
    if (next) {
      const nh = scale(rowsIn[i + 1] ?? 0);
      svg.append(s('polygon', {
        class: 'band-flow',
        points: `${x + 30},${mid - out / 2} ${x + colW},${mid - nh / 2} ${x + colW},${mid + nh / 2} ${x + 30},${mid + out / 2}`,
      }));
    }
    const dropped = (rowsIn[i] ?? 0) - (rowsOut[i] ?? 0);
    const heat = Math.min(4, Math.round((work[i] ?? 0) / maxWork * 4));
    svg.append(s('g', { class: `band-stage heat-${heat}${stage.error ? ' failed' : ''}`, 'aria-label': `${stage.clause}: ${formatNumber(rowsOut[i] ?? 0)} rows`, ...button(() => select(i)) },
      s('text', { class: 'band-clause', x: x + 15, y: 16, 'text-anchor': 'middle' }, short(stageName(stage.clause, stage.title), 13)),
      dropped > 0 ? s('rect', { class: 'band-dropped', x, y: mid - inp / 2, width: 30, height: inp, rx: 3 }) : null,
      s('rect', { class: 'band-bar', x, y: mid - out / 2, width: 30, height: out, rx: 3 }),
      s('text', { class: 'band-rows', x: x + 15, y: 172, 'text-anchor': 'middle' }, formatNumber(rowsOut[i] ?? 0)),
      dropped > 0 ? s('text', { class: 'band-drop', x: x + 15, y: 188, 'text-anchor': 'middle' }, `\u2212${formatNumber(dropped)}`) : null,
      i === hottest && stages.length > 1 && (work[i] ?? 0) > 0 ? s('text', { class: 'band-hot', x: x + 15, y: 206, 'text-anchor': 'middle' }, 'most work') : null));
  });
  return svg;
}

// ------------------------------------------------------------------ plan tree

function planDiagram(tree: PlanNode[], show: (node: PlanNode) => void): SVGSVGElement | HTMLElement {
  if (!tree.length) return h('p', { class: 'muted' }, 'This statement has no plan tree.');
  const root: PlanNode = { id: -1, label: 'Query', kind: 'root', table: null, index: null, severity: 'info', note: '', metrics: {}, children: tree };
  const BW = 214;
  const BH = 52;
  const positions = new Map<PlanNode, { x: number; y: number }>();
  let slot = 0;
  let depthMax = 0;
  const place = (node: PlanNode, depth: number): number => {
    depthMax = Math.max(depthMax, depth);
    let x: number;
    if (!node.children.length) {
      x = slot * (BW + 18);
      slot += 1;
    } else {
      const xs = node.children.map((child) => place(child, depth + 1));
      x = ((xs[0] ?? 0) + (xs[xs.length - 1] ?? 0)) / 2;
    }
    positions.set(node, { x, y: depth * 82 });
    return x;
  };
  place(root, 0);
  const width = slot * (BW + 18) + 10;
  const height = (depthMax + 1) * 82;
  const svg = s('svg', { class: 'plan-graph', viewBox: `-6 -6 ${width} ${height}`, role: 'group', 'aria-label': 'Physical plan' });
  svg.style.setProperty('--w', `${width}px`);
  positions.forEach((p, node) => node.children.forEach((child) => {
    const c = positions.get(child);
    if (c) svg.append(s('path', { class: 'plan-edge', d: `M ${p.x + BW / 2} ${p.y + BH} C ${p.x + BW / 2} ${p.y + BH + 20}, ${c.x + BW / 2} ${c.y - 20}, ${c.x + BW / 2} ${c.y}` }));
  }));
  positions.forEach((p, node) => {
    svg.append(s('g', {
      class: `plan-g sev-${node.severity} kind-${node.kind}`, transform: `translate(${p.x} ${p.y})`,
      'aria-label': `${node.label}. ${node.note}`, ...button(() => show(node)),
    },
    s('rect', { width: BW, height: BH, rx: 6 }),
    s('text', { class: 'plan-kind', x: 10, y: 19 }, node.kind === 'root' ? 'Start' : KIND_LABEL[node.kind] ?? node.kind),
    s('text', { class: 'plan-text-label', x: 10, y: 38 }, short(node.label, 30)),
    s('title', null, node.note ? `${node.label}: ${node.note}` : node.label)));
  });
  return svg;
}

// ------------------------------------------------------------------ findings

interface Finding { severity: 'warn' | 'info' | 'good'; text: string; link?: string }

function findings(result: VisualizeResponse): Finding[] {
  const out: Finding[] = [];
  const nodes = result.dependencies.nodes ?? [];
  for (const node of nodes.filter((n) => n.status === 'error')) {
    const blocked = nodes.filter((n) => n.status === 'blocked').length;
    const message = node.error?.message ?? node.message ?? '';
    const failure = matchFailure(message);
    out.push({ severity: 'warn', text: `${node.label} fails${blocked ? `, so ${plural(blocked, 'part')} downstream cannot run` : ''}: ${message}`,
      ...(failure ? { link: href(`explore/failures/${failure.id}`) } : {}) });
  }
  const stages = result.steps.stages;
  const work = stages.map((st, i) => Math.max(0, (st.vm_steps ?? 0) - (i ? stages[i - 1]?.vm_steps ?? 0 : 0)));
  const total = work.reduce((a, b) => a + b, 0);
  if (total > 0 && stages.length > 1 && !stages.some((st) => st.error)) {
    const top = work.indexOf(Math.max(...work));
    const share = Math.round((work[top] ?? 0) / total * 100);
    if (share >= 40) out.push({ severity: share >= 70 ? 'warn' : 'info', text: `${stageName(stages[top]?.clause ?? '', stages[top]?.title ?? '')} does ${share}% of the work across the stages.` });
  }
  for (const advice of result.plan?.advice ?? []) out.push({ severity: advice.severity, text: advice.message });
  if (nodes.some((n) => n.correlated)) {
    out.push({ severity: 'info', text: 'A correlated subquery reruns for every outer row.', link: href('explore/failures/correlated-subquery') });
  }
  if (!out.length) out.push({ severity: 'good', text: 'No bottleneck stands out for this data size.' });
  return out;
}

// ------------------------------------------------------------------ assembly

export function renderQueryMap(result: VisualizeResponse): HTMLElement {
  const detail = h('div', { class: 'qm-detail', 'aria-live': 'polite' });
  const plan = result.plan;
  const metrics = plan?.metrics;
  return h('div', { class: 'query-map' },
    h('ul', { class: 'findings', 'aria-label': 'Bottlenecks and problems' }, findings(result).map((f) => h('li', { class: f.severity },
      h('span', { class: 'badge' }, f.severity === 'warn' ? 'Check' : f.severity === 'good' ? 'Fine' : 'Note'), ' ', f.text,
      f.link ? [' ', h('a', { href: f.link }, 'See the failure map')] : null))),
    h('div', { class: 'qm-grid' },
      h('section', { class: 'qm-panel' }, h('h4', null, 'What feeds the result'),
        h('div', { class: 'scroll-x' }, dependencyDiagram(result.dependencies, (node) => mount(detail, nodeDetail(node))))),
      h('section', { class: 'qm-panel' }, h('h4', null, 'Rows kept at each stage'),
        h('div', { class: 'scroll-x' }, stageBand(result.steps, (i) => {
          const stage = result.steps.stages[i];
          if (stage) mount(detail, renderStageDetail(stage, i, result.steps.stages.length));
        })))),
    h('section', { class: 'qm-panel' }, h('h4', null, 'How the engine runs it'),
      metrics ? h('p', { class: 'facts' }, h('span', null, `${formatNumber(metrics.row_count)} rows`),
        h('span', null, formatMs(metrics.elapsed_ms)), metrics.vm_steps !== null ? h('span', null, formatSteps(metrics.vm_steps)) : null) : null,
      plan?.error ? renderError(plan.error) : h('div', { class: 'scroll-x' }, planDiagram(plan?.tree ?? [], (node) => mount(detail,
        h('div', { class: 'qm-node' }, h('h4', null, node.label), h('p', null, node.note || 'Select another step to compare.'),
          Object.keys(node.metrics).length ? h('p', { class: 'facts' }, Object.entries(node.metrics).map(([k, v]) => h('span', null, `${k.replace(/_/g, ' ')}: ${formatNumber(v)}`))) : null))))),
    detail);
}

export function renderQueryExplorer(options: { preset?: string | undefined; pickers?: boolean } = {}): HTMLElement {
  const presets = exploreData().queries;
  let current = presets.find((q) => q.id === options.preset) ?? presets[0];
  const output = h('div', { class: 'qm-output' });
  const status = h('p', { class: 'status', role: 'status' });
  const editor = createEditor({ value: current?.sql ?? '', label: 'Query to map', minLines: 4, maxLines: 18, onRun: () => void run() });
  const run = async () => {
    if (!current) return;
    status.textContent = 'Mapping\u2026';
    try {
      mount(output, renderQueryMap(await api.visualize({ sql: editor.getValue(), dataset: current.dataset })));
      status.textContent = `Mapped on the ${current.dataset} dataset.`;
    } catch (error) {
      mount(output, renderError(requestError(error)));
      status.textContent = 'The map could not be drawn.';
    }
  };
  const presetButtons = presets.map((q) => h('button', {
    type: 'button', 'aria-pressed': String(q === current),
    on: { click: () => { current = q; editor.setValue(q.sql); presetButtons.forEach((b, i) => b.setAttribute('aria-pressed', String(presets[i] === q))); void run(); } },
  }, q.title));
  void run();
  return h('div', { class: 'query-explorer' },
    options.pickers === false ? null : h('div', { class: 'segmented', role: 'group', 'aria-label': 'Example queries' }, presetButtons),
    editor.element,
    h('div', { class: 'toolbar' }, h('button', { type: 'button', class: 'button primary', on: { click: () => void run() } }, 'Map this query'),
      h('span', { class: 'shortcut' }, h('kbd', null, 'Ctrl'), ' + ', h('kbd', null, 'Enter'))),
    status, output);
}
