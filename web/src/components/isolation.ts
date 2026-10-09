// The isolation simulator: step two transactions through classic anomalies.
import { h, mount } from '../lib/dom.ts';
import { LEVELS, type Level, SCENARIOS } from '../data/isolation.ts';

export function renderIsolationSimulator(): HTMLElement {
  let scenario = SCENARIOS[0];
  let level: Level = 'read-committed';
  let shown = 0;
  const summary = h('p', { class: 'iso-summary' });
  const setup = h('p', { class: 'muted' });
  const tbody = h('tbody');
  const verdict = h('div', { class: 'iso-verdict', 'aria-live': 'polite' });
  const scenarioButtons = SCENARIOS.map((sc) => h('button', {
    type: 'button', 'aria-pressed': 'false', on: { click: () => { scenario = sc; shown = 0; render(); } },
  }, sc.title));
  const levelButtons = LEVELS.map((l) => h('button', {
    type: 'button', 'aria-pressed': 'false', on: { click: () => { level = l.id; render(); } },
  }, l.name));
  const next = h('button', {
    type: 'button', class: 'button primary', on: { click: () => { shown += 1; render(); } },
  }, 'Next step');
  const showAll = h('button', {
    type: 'button', class: 'button', on: { click: () => { shown = scenario?.steps.length ?? 0; render(); } },
  }, 'Show all steps');
  const reset = h('button', { type: 'button', class: 'button', on: { click: () => { shown = 0; render(); } } }, 'Start over');

  function render(): void {
    if (!scenario) return;
    const current = scenario;
    scenarioButtons.forEach((b, i) => b.setAttribute('aria-pressed', String(SCENARIOS[i] === current)));
    levelButtons.forEach((b, i) => b.setAttribute('aria-pressed', String(LEVELS[i]?.id === level)));
    summary.textContent = current.summary;
    setup.textContent = `Starting data: ${current.setup}`;
    const outcome = current.outcomes[level];
    shown = Math.min(shown, current.steps.length);
    tbody.replaceChildren(...current.steps.map((step, i) => {
      const visible = i < shown;
      const classes = [visible ? 'shown' : 'pending', i === shown - 1 ? 'current' : '',
        visible && outcome.errors.includes(i) ? 'error' : ''].filter(Boolean).join(' ');
      return h('tr', { class: classes },
        h('td', { class: 'num' }, String(i + 1)),
        h('td', null, step.tx === 'T1' ? h('code', null, step.sql) : ''),
        h('td', null, step.tx === 'T2' ? h('code', null, step.sql) : ''),
        h('td', { class: 'iso-result' }, visible ? outcome.results[i] ?? '' : ''));
    }));
    next.disabled = shown >= current.steps.length;
    if (shown >= current.steps.length) {
      const name = LEVELS.find((l) => l.id === level)?.name ?? level;
      mount(verdict,
        h('p', { class: outcome.anomaly ? 'anomaly' : 'prevented' },
          h('strong', null, outcome.anomaly ? 'Anomaly. ' : 'Prevented. '), outcome.verdict),
        h('p', { class: 'muted' }, `The SQL standard at ${name}: ${current.standard[level]}`));
    } else {
      verdict.replaceChildren();
    }
  }

  render();
  return h('div', { class: 'isolation' },
    h('div', { class: 'segmented', role: 'group', 'aria-label': 'Scenario' }, scenarioButtons),
    h('div', { class: 'segmented', role: 'group', 'aria-label': 'Isolation level' }, levelButtons),
    summary, setup,
    h('div', { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': 'Transaction timeline' },
      h('table', { class: 'data iso-table' },
        h('thead', null, h('tr', null,
          h('th', { scope: 'col', class: 'num' }, 'Step'), h('th', { scope: 'col' }, 'Transaction T1'),
          h('th', { scope: 'col' }, 'Transaction T2'), h('th', { scope: 'col' }, 'What happens'))),
        tbody)),
    h('div', { class: 'toolbar' }, next, showAll, reset),
    verdict,
    h('p', { class: 'muted' },
      'Outcomes follow PostgreSQL 18. MySQL, SQL Server and SQLite behave differently in places; the transactions lesson explains how.'));
}
