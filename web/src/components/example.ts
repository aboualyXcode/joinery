// A runnable lesson example, with tabs for each dialect's variant.
import { h } from '../lib/dom.ts';
import { DIALECT_NAMES } from '../lib/format.ts';
import type { Example, Meta } from '../types.ts';
import { createWorkbench } from './workbench.ts';

export function renderExample(example: Example, meta: Meta): HTMLElement {
  const enabled = new Set(meta.engines.map((engine) => engine.id));
  const dialects = ['sqlite', ...Object.keys(example.variants).filter((d) => d !== 'sqlite')];
  const workbench = createWorkbench({
    sql: example.sql, dataset: example.dataset, meta, setup: example.setup, minLines: 2, maxLines: 22,
    primary: example.mode, label: `SQL for the example: ${example.title || example.id}`,
  });
  const choose = (dialect: string, chosen: HTMLButtonElement) => {
    tabs?.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === chosen)));
    workbench.setSql(dialect === 'sqlite' ? example.sql : example.variants[dialect] ?? example.sql);
    if (dialect === 'sqlite' || enabled.has(dialect)) {
      workbench.setEngine(dialect);
      workbench.setDisabled(null);
    } else {
      workbench.setDisabled(`${DIALECT_NAMES[dialect] ?? dialect} is not enabled on this server, so this variant is for reading. docs/engines.md explains how to enable it.`);
    }
  };
  const tabs = dialects.length > 1 ? h('div', { class: 'dialect-tabs', role: 'group', 'aria-label': 'SQL dialect' },
    dialects.map((dialect) => h('button', {
      type: 'button', 'aria-pressed': String(dialect === 'sqlite'),
      on: { click: (event: Event) => choose(dialect, event.currentTarget as HTMLButtonElement) },
    }, DIALECT_NAMES[dialect] ?? dialect))) : null;
  return h('figure', { class: 'example', id: `example-${example.id}` },
    h('figcaption', null,
      h('span', { class: 'example-title' }, example.title || 'Example'),
      example.portable ? h('span', { class: 'tag' }, 'Portable SQL') : null),
    tabs,
    workbench.element,
    example.note_html ? h('div', { class: 'prose example-note', html: example.note_html }) : null);
}
