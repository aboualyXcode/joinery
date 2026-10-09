import { api } from '../api.ts';
import { h, mount } from '../lib/dom.ts';
import type { Meta } from '../types.ts';

export async function renderReference(target: HTMLElement, meta: Meta): Promise<void> {
  const reference = await api.dialects();
  document.title = 'Dialect reference | Joinery';
  const enabled = new Set(meta.engines.map((e) => e.id));
  const engines = reference.engines;
  const rows = reference.features.map((feature) => h('tr', { 'data-search': `${feature.name} ${feature.standard}`.toLowerCase() },
    h('th', { scope: 'row' }, feature.name, h('span', { class: 'standard' }, feature.standard)),
    engines.map((engine) => {
      const cell = feature.support[engine.id];
      const level = cell?.level ?? 'no';
      return h('td', { class: `level-${level}` },
        h('span', { class: 'level' }, level === 'yes' ? 'Yes' : level === 'partial' ? 'Partly' : 'No'),
        cell?.note_html ? h('span', { class: 'cell-note', html: cell.note_html }) : null);
    })));
  const filter = h('input', {
    type: 'search', class: 'filter', placeholder: 'Filter features', 'aria-label': 'Filter features',
    on: {
      input: () => {
        const query = filter.value.trim().toLowerCase();
        rows.forEach((row) => { row.hidden = Boolean(query) && !(row.dataset.search ?? '').includes(query); });
      },
    },
  });
  mount(target, h('div', { class: 'page wide' },
    h('h1', null, 'Dialect reference'),
    h('p', { class: 'lede' }, reference.standard),
    h('h2', null, 'Engines'),
    h('div', { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': 'Engines' },
      h('table', { class: 'data' },
        h('thead', null, h('tr', null, ['Engine', 'Current release', 'Status in Joinery', 'Python driver', 'On this server']
          .map((c) => h('th', { scope: 'col' }, c)))),
        h('tbody', null, engines.map((engine) => h('tr', null,
          h('th', { scope: 'row' }, h('a', { href: engine.docs, rel: 'noopener noreferrer', target: '_blank' }, engine.name)),
          h('td', null, engine.release), h('td', null, engine.status), h('td', null, engine.driver),
          h('td', null, enabled.has(engine.id) ? 'Enabled' : 'Not enabled')))))),
    h('h2', null, 'Feature matrix'),
    filter,
    h('div', { class: 'table-wrap matrix-wrap', role: 'region', tabindex: '0', 'aria-label': 'Feature matrix' },
      h('table', { class: 'data matrix' },
        h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Feature'), engines.map((e) => h('th', { scope: 'col' }, e.name)))),
        h('tbody', null, rows)))));
}
