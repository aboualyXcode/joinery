import { api } from '../api.ts';
import { createWorkbench } from '../components/workbench.ts';
import { h, mount } from '../lib/dom.ts';
import { exploreData } from '../lib/explore.ts';
import { formatNumber } from '../lib/format.ts';
import { preference, setPreference } from '../lib/store.ts';
import type { DatasetDetail, Meta } from '../types.ts';

function schemaView(detail: DatasetDetail, preview: (sql: string) => void): HTMLElement {
  return h('div', null,
    h('h2', null, detail.title),
    h('p', { class: 'muted' }, detail.summary),
    h('ul', { class: 'schema-tables' }, detail.tables.map((table) => h('li', null, h('details', null,
      h('summary', null, h('code', null, table.name), h('span', { class: 'muted' }, ` ${formatNumber(table.row_count)} rows`)),
      h('ul', { class: 'schema-columns' }, table.columns.map((c) => h('li', null, h('code', null, c.name),
        h('span', { class: 'muted' }, ` ${c.type}${c.primary_key ? ', key' : ''}${c.references ? `, references ${c.references}` : ''}`)))),
      h('button', { type: 'button', class: 'button quiet', on: { click: () => preview(`SELECT *\nFROM ${table.name}\nLIMIT 20;`) } },
        `Preview ${table.name}`))))));
}

export async function renderPlayground(target: HTMLElement, meta: Meta, params: URLSearchParams): Promise<void> {
  document.title = 'Playground | Joinery';
  const STARTERS = exploreData().presets.playground;
  let dataset = params.get('dataset') ?? preference('playground.dataset', 'shop');
  if (!meta.datasets.some((d) => d.id === dataset)) dataset = 'shop';
  const savedEngine = preference('playground.engine', 'sqlite');
  const engine = meta.engines.some((e) => e.id === savedEngine) ? savedEngine : 'sqlite';
  const schemaPanel = h('div', { class: 'schema-panel' });
  const showSchema = async () => {
    mount(schemaPanel, h('p', { class: 'loading', role: 'status' }, 'Loading tables\u2026'));
    try {
      const detail = await api.dataset(dataset);
      mount(schemaPanel, schemaView(detail, (sql) => { workbench.setSql(sql); void workbench.execute('run'); }));
    } catch {
      mount(schemaPanel, h('p', { class: 'muted' }, 'The tables could not be loaded.'));
    }
  };
  const workbench = createWorkbench({
    sql: params.get('sql') ?? preference(`playground.sql.${dataset}`, STARTERS[dataset] ?? ''),
    dataset, engine, meta, label: 'Playground SQL', pickers: true, minLines: 10, maxLines: 30,
    onChange: (state) => {
      setPreference('playground.engine', state.engine);
      if (state.dataset !== dataset) {
        dataset = state.dataset;
        setPreference('playground.dataset', dataset);
        workbench.setSql(preference(`playground.sql.${dataset}`, STARTERS[dataset] ?? ''));
        void showSchema();
      } else {
        setPreference(`playground.sql.${dataset}`, state.sql);
      }
    },
  });
  mount(target, h('div', { class: 'playground' },
    h('aside', { class: 'schema', 'aria-label': 'Tables in this dataset' }, schemaPanel),
    h('section', { class: 'playground-main' },
      h('h1', null, 'Playground'),
      h('p', { class: 'lede' }, 'Write any SQL against the sample data. Each run gets a private copy of the dataset, so experiment freely: nothing you change is kept.'),
      workbench.element)));
  void showSchema();
  if (params.get('sql')) void workbench.execute('run');
}
