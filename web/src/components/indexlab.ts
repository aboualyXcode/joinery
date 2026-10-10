// The index lab: build an index column by column and compare the plans.
import { api } from '../api.ts';
import { h, mount } from '../lib/dom.ts';
import { exploreData } from '../lib/explore.ts';
import { formatSteps } from '../lib/format.ts';
import { highlightHTML } from '../lib/sql.ts';
import { flattenPlan, renderPlan } from './plan.ts';
import { renderError } from './results.ts';
import { requestError } from './workbench.ts';

export function renderIndexLab(): HTMLElement {
  const PRESETS = exploreData().presets.index_lab;
  let preset = PRESETS[0];
  let chosen: string[] = [];
  const code = h('code');
  const columnArea = h('div', { class: 'segmented', role: 'group', 'aria-label': 'Index columns, in order' });
  const indexLine = h('p', { class: 'index-line' });
  const result = h('div', { class: 'lab-compare', 'aria-live': 'polite' });
  const compare = h('button', { type: 'button', class: 'button primary', on: { click: () => void run() } }, 'Compare plans');
  const presetButtons = PRESETS.map((p) => h('button', {
    type: 'button', 'aria-pressed': 'false', on: { click: () => { preset = p; chosen = []; result.replaceChildren(); render(); } },
  }, p.title));

  function render(): void {
    if (!preset) return;
    const current = preset;
    presetButtons.forEach((b, i) => b.setAttribute('aria-pressed', String(PRESETS[i] === current)));
    code.innerHTML = highlightHTML(current.sql);
    columnArea.replaceChildren(...current.columns.map((column) => h('button', {
      type: 'button', 'aria-pressed': String(chosen.includes(column)),
      on: {
        click: () => {
          chosen = chosen.includes(column) ? chosen.filter((c) => c !== column) : [...chosen, column];
          render();
        },
      },
    }, chosen.includes(column) ? `${chosen.indexOf(column) + 1}. ${column}` : column)));
    indexLine.textContent = chosen.length
      ? `CREATE INDEX lab_index ON ${current.table} (${chosen.join(', ')});`
      : 'Pick columns in the order the index should store them.';
    compare.disabled = !chosen.length;
  }

  async function run(): Promise<void> {
    if (!preset || !chosen.length) return;
    const current = preset;
    compare.disabled = true;
    mount(result, h('p', { class: 'loading', role: 'status' }, 'Explaining the query with and without the index\u2026'));
    try {
      const setup = `CREATE INDEX lab_index ON ${current.table} (${chosen.join(', ')})`;
      const [before, after] = await Promise.all([
        api.explain({ sql: current.sql, dataset: 'shop' }),
        api.explain({ sql: current.sql, dataset: 'shop', setup }),
      ]);
      const used = flattenPlan(after.tree).some((n) => n.index === 'lab_index');
      const was = before.metrics?.vm_steps ?? null;
      const now = after.metrics?.vm_steps ?? null;
      const message = !used
        ? 'SQLite did not use the new index. The index can only help when its leading column is constrained by the query.'
        : was !== null && now !== null && now < was
          ? `With the index the query takes ${formatSteps(now)} instead of ${formatSteps(was)}, about ${Math.max(1, Math.round(was / Math.max(now, 1)))} times fewer.`
          : 'SQLite uses the index, but for this query it saves little work.';
      mount(result,
        h('p', { class: used ? 'agree' : 'disagree' }, message),
        h('div', { class: 'two-up' },
          h('section', null, h('h4', null, 'Without the index'), renderPlan(before, { bytecode: false })),
          h('section', null, h('h4', null, 'With the index'), renderPlan(after, { bytecode: false }))));
    } catch (error) {
      mount(result, renderError(requestError(error)));
    } finally {
      compare.disabled = !chosen.length;
    }
  }

  render();
  return h('div', { class: 'index-lab' },
    h('div', { class: 'segmented', role: 'group', 'aria-label': 'Query' }, presetButtons),
    h('pre', { class: 'code' }, code),
    columnArea, indexLine,
    h('div', { class: 'toolbar' }, compare),
    result);
}
