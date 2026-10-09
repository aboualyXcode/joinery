// The logical-order stepper: one tab per stage, with kept rows highlighted
// and removed rows struck through.
import { h, uid } from '../lib/dom.ts';
import { formatNumber } from '../lib/format.ts';
import { highlightHTML } from '../lib/sql.ts';
import type { Stage, StepsResponse } from '../types.ts';
import { renderError, renderTable } from './results.ts';

function stageView(stage: Stage, index: number, total: number): HTMLElement {
  const counted = stage.kept_count !== null && stage.input_count !== null;
  const count = counted
    ? `${formatNumber(stage.kept_count ?? 0)} of ${formatNumber(stage.input_count ?? 0)} kept`
    : `${formatNumber(stage.row_count)} ${stage.row_count === 1 ? 'row' : 'rows'}`;
  return h('div', { class: 'stage' },
    h('div', { class: 'stage-head' },
      h('h4', null, `Stage ${index + 1} of ${total}: ${stage.title}`),
      h('span', { class: 'count' }, count)),
    stage.description ? h('p', { class: 'stage-description' }, stage.description) : null,
    stage.error ? renderError(stage.error)
      : renderTable(stage.columns, stage.rows, { kept: stage.kept, caption: `Rows at the ${stage.clause} stage` }),
    stage.truncated ? h('p', { class: 'muted' },
      `Showing the first ${formatNumber(stage.rows.length)} of ${formatNumber(stage.row_count)} rows.`) : null,
    h('details', { class: 'stage-sql' },
      h('summary', null, 'The query Joinery ran for this stage'),
      h('pre', { class: 'code' }, h('code', { html: highlightHTML(stage.sql) }))));
}

export function renderSteps(steps: StepsResponse): HTMLElement {
  if (!steps.supported) {
    return h('div', { class: 'callout' },
      h('p', { class: 'callout-title' }, 'This statement cannot be stepped through'),
      h('p', null, steps.reason ?? ''));
  }
  if (steps.error) return renderError(steps.error);
  const stages = steps.stages;
  if (!stages.length) return h('p', { class: 'muted' }, 'There are no stages to show.');
  const panel = h('div', { class: 'stage-panel', role: 'tabpanel' });
  const id = uid('steps');
  const tabs = stages.map((stage, i) => h('button', {
    type: 'button', role: 'tab', class: 'stage-tab', id: `${id}-${i}`, 'aria-selected': 'false', tabindex: '-1',
    on: { click: () => select(i) },
  }, h('span', { class: 'stage-number' }, String(i + 1)), h('span', null, stage.clause)));
  let current = 0;

  function select(index: number, focus = false): void {
    current = index;
    tabs.forEach((tab, n) => {
      tab.setAttribute('aria-selected', String(n === index));
      tab.tabIndex = n === index ? 0 : -1;
    });
    panel.setAttribute('aria-labelledby', `${id}-${index}`);
    const stage = stages[index];
    if (stage) panel.replaceChildren(stageView(stage, index, stages.length));
    if (focus) tabs[index]?.focus();
  }

  const tablist = h('div', {
    class: 'stage-tabs', role: 'tablist', 'aria-label': 'Stages in logical processing order',
    on: {
      keydown: (event: KeyboardEvent) => {
        if (event.key === 'ArrowRight') select(Math.min(stages.length - 1, current + 1), true);
        else if (event.key === 'ArrowLeft') select(Math.max(0, current - 1), true);
        else if (event.key === 'Home') select(0, true);
        else if (event.key === 'End') select(stages.length - 1, true);
        else return;
        event.preventDefault();
      },
    },
  }, tabs);
  select(0);
  const written = steps.written_order ?? [];
  return h('div', { class: 'stepper' },
    written.length ? h('div', { class: 'order-line' },
      h('span', { class: 'order-label' }, 'You wrote'),
      h('span', { class: 'chips' }, written.map((clause) => h('span', { class: 'chip' }, clause)))) : null,
    h('div', { class: 'order-line' }, h('span', { class: 'order-label' }, 'It runs'), tablist),
    panel);
}
