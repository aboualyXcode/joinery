// The query journey: what each stage of the engine produces for one query.
import { api } from '../api.ts';
import { h, mount } from '../lib/dom.ts';
import { formatMs, formatNumber, formatSteps, plural } from '../lib/format.ts';
import { tokenize } from '../lib/sql.ts';
import type { DatasetDetail, ExplainResponse, Meta, StepsResponse } from '../types.ts';
import { createEditor } from './editor.ts';
import { flattenPlan, renderBytecode, renderPlan } from './plan.ts';
import { renderError } from './results.ts';
import { requestError } from './workbench.ts';

const DEFAULT_SQL = `SELECT c.country, count(*) AS orders
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE o.ordered_at >= '2026-01-01'
GROUP BY c.country
ORDER BY orders DESC;`;

const STAGES = [
  { id: 'parser', name: 'Parser', text: 'Splits the text into tokens and checks them against the grammar, producing a syntax tree. Misspelled keywords and missing commas fail here.' },
  { id: 'binder', name: 'Binder', text: 'Looks up every table and column in the catalog and checks types. Unknown and ambiguous names fail here.' },
  { id: 'optimizer', name: 'Optimizer', text: 'Rewrites the query and picks a physical plan: which index to use, the join order and the join algorithm, guided by statistics.' },
  { id: 'executor', name: 'Executor', text: 'Runs the plan. SQLite compiles it into bytecode for its virtual machine and pulls rows through it one at a time.' },
  { id: 'storage', name: 'Storage', text: 'Reads B-tree pages of tables and indexes from the page cache or disk. A journal or write-ahead log keeps changes durable.' },
];

interface Trace { steps: StepsResponse; plan: ExplainResponse; schema: DatasetDetail }

function detail(stage: string, trace: Trace, sql: string): HTMLElement {
  const { steps, plan, schema } = trace;
  if (stage === 'parser') {
    const tokens = tokenize(sql).filter((t) => t.kind !== 'ws' && t.kind !== 'comment');
    return h('div', null,
      h('p', null, `${plural(tokens.length, 'token')}. Clauses as written: ${(steps.written_order ?? []).join(', ') || 'not a SELECT'}.`),
      h('p', { class: 'tokens' }, tokens.map((t) => h('span', { class: `token tok-${t.kind}`, title: t.kind }, t.text))));
  }
  if (stage === 'binder') {
    const tables = new Map(schema.tables.map((t) => [t.name.toLowerCase(), t]));
    const words = [...new Set(tokenize(sql).filter((t) => t.kind === 'word' || t.kind === 'ident')
      .map((t) => t.text.replace(/["`[\]]/g, '')))];
    return h('ul', { class: 'resolved' }, words.map((word) => {
      const table = tables.get(word.toLowerCase());
      if (table) return h('li', null, h('code', null, word), ` is a table with ${formatNumber(table.row_count)} rows`);
      const owners = schema.tables.filter((t) => t.columns.some((c) => c.name.toLowerCase() === word.toLowerCase()));
      if (owners.length) return h('li', null, h('code', null, word), ` is a column of ${owners.map((o) => o.name).join(', ')}`);
      return h('li', null, h('code', null, word), ' is an alias or an output column name');
    }));
  }
  if (stage === 'optimizer') {
    return h('div', null,
      steps.logical_order?.length ? h('p', null, `Logical order of evaluation: ${steps.logical_order.join(', ')}.`) : null,
      renderPlan({ ...plan, metrics: null }, { bytecode: false }));
  }
  if (stage === 'executor') {
    const summary = plan.bytecode_summary;
    const metrics = plan.metrics;
    return h('div', null,
      summary ? h('p', null, `The plan compiled to ${plural(summary.instructions, 'instruction')} with ${plural(summary.loops, 'loop')}. Most frequent: ${summary.common.map(([op, n]) => `${op} (${n})`).join(', ')}.`) : null,
      metrics ? h('p', null, `Running it returned ${plural(metrics.row_count, 'row')} in ${formatMs(metrics.elapsed_ms)}, taking ${formatSteps(metrics.vm_steps)}.`) : null,
      renderBytecode(plan));
  }
  const touched = flattenPlan(plan.tree).filter((n) => n.table);
  return h('ul', { class: 'resolved' }, touched.length ? touched.map((n) => h('li', null,
    h('code', null, n.table ?? ''),
    n.index ? ` is read through the index ${n.index}` : n.kind === 'scan' ? ': every page of its B-tree is read' : ' is read',
    n.metrics.table_rows ? ` (${formatNumber(n.metrics.table_rows)} rows)` : '')) : h('li', null, 'No table storage is read.'));
}

export function renderJourney(meta: Meta): HTMLElement {
  let dataset = 'shop';
  let trace: Trace | null = null;
  let current = 0;
  const panel = h('div', { class: 'journey-panel', 'aria-live': 'polite' });
  const editor = createEditor({ value: DEFAULT_SQL, label: 'Query to trace', minLines: 4, maxLines: 14, onRun: () => void run() });
  const datasetSelect = h('select', {
    'aria-label': 'Dataset', on: { change: (e: Event) => { dataset = (e.target as HTMLSelectElement).value; } },
  }, meta.datasets.map((d) => h('option', { value: d.id }, d.title)));
  datasetSelect.value = dataset;
  const traceButton = h('button', { type: 'button', class: 'button primary', on: { click: () => void run() } }, 'Trace the query');
  const stageButtons = STAGES.map((stage, i) => h('button', {
    type: 'button', class: 'journey-stage', 'aria-pressed': String(i === 0), on: { click: () => { current = i; render(); } },
  }, h('span', { class: 'stage-number' }, String(i + 1)), stage.name));

  function render(): void {
    stageButtons.forEach((b, i) => b.setAttribute('aria-pressed', String(i === current)));
    const stage = STAGES[current];
    if (!stage) return;
    mount(panel, h('h4', null, stage.name), h('p', null, stage.text),
      trace ? detail(stage.id, trace, editor.getValue())
        : h('p', { class: 'muted' }, 'Press "Trace the query" to see what this stage produces for your SQL.'));
  }

  async function run(): Promise<void> {
    traceButton.disabled = true;
    mount(panel, h('p', { class: 'loading', role: 'status' }, 'Tracing\u2026'));
    try {
      const sql = editor.getValue();
      const [steps, plan, schema] = await Promise.all([
        api.steps({ sql, dataset }), api.explain({ sql, dataset }), api.dataset(dataset),
      ]);
      trace = { steps, plan, schema };
      render();
    } catch (error) {
      trace = null;
      mount(panel, renderError(requestError(error)));
    } finally {
      traceButton.disabled = false;
    }
  }

  render();
  return h('div', { class: 'journey' },
    editor.element,
    h('div', { class: 'toolbar' }, traceButton, datasetSelect),
    h('ol', { class: 'journey-stages', 'aria-label': 'Stages of query processing' }, stageButtons.map((b) => h('li', null, b))),
    panel);
}
