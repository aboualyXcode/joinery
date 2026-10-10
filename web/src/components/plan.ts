// Execution plans: a tree of operators, index advice and the bytecode program.
import { h } from '../lib/dom.ts';
import { formatMs, formatNumber, formatSteps, plural } from '../lib/format.ts';
import type { ExplainResponse, PlanNode } from '../types.ts';
import { renderError } from './results.ts';

export const KIND_LABEL: Record<string, string> = {
  scan: 'Full scan', 'index-scan': 'Index scan', search: 'Index search', 'auto-index': 'Temporary index',
  sort: 'Sort', correlated: 'Runs per row', subquery: 'Subquery', materialize: 'Materialized',
  coroutine: 'Co-routine', compound: 'Compound', constant: 'Constant row', bloom: 'Bloom filter', join: 'Join',
  aggregate: 'Aggregate', limit: 'Limit', hash: 'Hash', parallel: 'Parallel', window: 'Window', other: 'Step',
};

function nodeView(node: PlanNode): HTMLElement {
  const metrics = Object.entries(node.metrics)
    .map(([key, value]) => h('span', null, `${key.replace(/_/g, ' ')}: ${formatNumber(value)}`));
  return h('li', { class: `plan-node ${node.severity}` },
    h('div', { class: 'plan-card' },
      h('span', { class: `kind kind-${node.kind}` }, KIND_LABEL[node.kind] ?? node.kind),
      h('code', { class: 'plan-label' }, node.label),
      node.note ? h('p', { class: 'plan-note' }, node.note) : null,
      metrics.length ? h('p', { class: 'facts' }, metrics) : null),
    node.children.length ? h('ul', null, node.children.map(nodeView)) : null);
}

export function flattenPlan(nodes: PlanNode[]): PlanNode[] {
  return nodes.flatMap((node) => [node, ...flattenPlan(node.children)]);
}

function figure(label: string, value: string): HTMLElement {
  return h('div', null, h('dt', null, label), h('dd', null, value));
}

function bytecode(plan: ExplainResponse): HTMLElement | null {
  const summary = plan.bytecode_summary;
  if (!summary || !plan.bytecode.length) return null;
  return h('details', { class: 'bytecode' },
    h('summary', null, `Bytecode program: ${formatNumber(summary.instructions)} instructions, ${plural(summary.loops, 'loop')}`),
    h('p', { class: 'muted' },
      "This is the program SQLite's virtual machine runs. A loop arrow marks an instruction that jumps back to repeat the loop body for the next row."),
    h('div', { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': 'Bytecode program' },
      h('table', { class: 'data bytecode-table' },
        h('thead', null, h('tr', null, ['addr', 'opcode', 'p1', 'p2', 'p3', 'p4', 'p5', 'what it does']
          .map((name) => h('th', { scope: 'col' }, name)))),
        h('tbody', null, plan.bytecode.map((op) => h('tr', { class: op.loop_to !== null ? 'loop' : undefined },
          h('td', { class: 'num' }, String(op.addr)),
          h('td', null, h('code', null, op.opcode),
            op.loop_to !== null ? h('span', { class: 'loop-mark' }, ` \u21ba ${op.loop_to}`) : null),
          [op.p1, op.p2, op.p3, op.p4, op.p5].map((value) => h('td', { class: 'num' }, value === null ? '' : String(value))),
          h('td', { class: 'note' }, op.note || (op.comment ? String(op.comment) : ''))))))));
}

export function renderPlan(plan: ExplainResponse, options: { bytecode?: boolean } = {}): HTMLElement {
  const metrics = plan.metrics;
  return h('div', { class: 'plan' },
    plan.setup_error ? renderError(plan.setup_error) : null,
    plan.error ? renderError(plan.error) : null,
    metrics ? h('dl', { class: 'figures' },
      figure('Rows returned', formatNumber(metrics.row_count)),
      figure('Time', formatMs(metrics.elapsed_ms)),
      metrics.vm_steps !== null ? figure('Work', formatSteps(metrics.vm_steps)) : null) : null,
    plan.advice.length ? h('ul', { class: 'advice', 'aria-label': 'Plan advice' },
      plan.advice.map((advice) => h('li', { class: advice.severity }, advice.message))) : null,
    plan.tree.length ? h('div', { class: 'plan-tree' }, h('ul', null, plan.tree.map(nodeView))) : null,
    plan.plan_text ? h('pre', { class: 'plan-text' }, plan.plan_text) : null,
    options.bytecode === false ? null : bytecode(plan),
    !plan.tree.length && !plan.plan_text && !plan.error ? h('p', { class: 'muted' }, 'This statement has no query plan.') : null);
}

export const renderBytecode = bytecode;
