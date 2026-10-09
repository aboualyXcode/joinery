import { api } from '../api.ts';
import { renderErd, renderTableDetail } from '../components/erd.ts';
import { h, mount } from '../lib/dom.ts';
import { DIALECT_NAMES } from '../lib/format.ts';
import { href } from '../router.ts';
import type { Meta, TableSchema } from '../types.ts';

export async function renderDatasets(target: HTMLElement, meta: Meta, id: string): Promise<void> {
  const datasetId = meta.datasets.some((d) => d.id === id) ? id : 'shop';
  const detail = await api.dataset(datasetId);
  document.title = `${detail.title} | Joinery`;
  const tableArea = h('div', { class: 'table-area', 'aria-live': 'polite' });
  const select = (table: TableSchema) => mount(tableArea, renderTableDetail(table, detail.id));
  mount(target, h('div', { class: 'page wide' },
    h('nav', { class: 'segmented', 'aria-label': 'Datasets' }, meta.datasets.map((d) => h('a', {
      href: href(`datasets/${d.id}`), 'aria-current': d.id === detail.id ? 'page' : undefined,
    }, d.title))),
    h('h1', null, detail.title),
    h('div', { class: 'prose', html: detail.description_html }),
    h('p', { class: 'muted' }, 'Select a table in the diagram to see its columns. PK marks a primary key and FK a foreign key.'),
    renderErd(detail, select),
    tableArea,
    h('section', { class: 'downloads' },
      h('h2', null, 'Load it into your own database'),
      h('p', null, 'Each script creates the tables and inserts every row, using the types and syntax of its engine.'),
      h('ul', { class: 'download-list' }, detail.dialects.map((dialect) => h('li', null,
        h('a', { href: api.exportUrl(detail.id, dialect), download: `${detail.id}.${dialect}.sql` },
          `${DIALECT_NAMES[dialect] ?? dialect} script`)))))));
  const first = detail.tables[0];
  if (first) select(first);
}
