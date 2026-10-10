import { api } from '../api.ts';
import { createEngineMap, legend } from '../components/enginemap.ts';
import { renderProcessingOrder } from '../components/order.ts';
import { exploreData, hasExplore } from '../lib/explore.ts';
import { h, mount } from '../lib/dom.ts';
import { formatNumber, plural } from '../lib/format.ts';
import { store } from '../lib/store.ts';
import { href } from '../router.ts';
import type { Meta, Module } from '../types.ts';

export const LABS = [
  { id: 'joins', title: 'Join lab', text: 'Pick a join type, watch which rows pair up, then run the same SQL on the engine.' },
  { id: 'isolation', title: 'Isolation simulator', text: 'Step two transactions through dirty reads, lost updates, phantoms and write skew at each isolation level.' },
  { id: 'indexes', title: 'Index lab', text: 'Build an index column by column and compare the plans and the work done with and without it.' },
  { id: 'journey', title: 'Query journey', text: 'Follow one query through the parser, binder, optimizer, executor and storage engine.' },
];

export function moduleProgress(module: Module): { done: number; total: number } {
  const ids = module.lessons.flatMap((lesson) => lesson.exercises);
  return { done: ids.filter((id) => store.isComplete(id)).length, total: ids.length };
}

export async function renderHome(target: HTMLElement, meta: Meta): Promise<void> {
  const { modules } = await api.curriculum();
  const first = modules[0]?.lessons[0]?.id ?? 'select-basics';
  document.title = 'Joinery: learn SQL by running it';
  mount(target,
    h('section', { class: 'hero' },
      h('div', { class: 'hero-copy' },
        h('h1', null, 'You write SELECT first. The database runs it fifth.'),
        h('p', { class: 'lede' },
          'Joinery teaches SQL by running it. Every example executes on a real engine, every stage of a query shows the rows it keeps and the rows it drops, and every exercise is checked against the actual result.'),
        h('p', { class: 'actions' },
          h('a', { class: 'button primary', href: href(`learn/${first}`) }, 'Start the first lesson'),
          h('a', { class: 'button', href: href('playground') }, 'Open the playground'))),
      renderProcessingOrder(true)),
    hasExplore() ? h('section', { class: 'home-section engine-teaser' },
      h('h2', null, 'See inside the engine'),
      h('p', { class: 'lede' }, 'Nineteen components, from your driver to the disk. Follow a query through them, watch an error travel back, or map your own SQL.'),
      h('p', { class: 'actions' },
        h('a', { class: 'button primary', href: href('explore/flows/select') }, 'Follow a SELECT'),
        h('a', { class: 'button', href: href('explore/failures') }, 'Trace a failure'),
        h('a', { class: 'button', href: href('explore/query') }, 'Map a query')),
      createEngineMap(exploreData(), (station) => { location.hash = href('explore/map'); void station; }).element, legend()) : null,
    h('section', { class: 'home-section' },
      h('h2', null, 'The course'),
      h('ol', { class: 'module-list' }, modules.map((module) => {
        const progress = moduleProgress(module);
        return h('li', null,
          h('a', { href: href(`learn/${module.lessons[0]?.id ?? ''}`) },
            h('span', { class: 'module-number' }, String(module.number)), module.title),
          h('p', null, module.summary),
          h('p', { class: 'muted' }, `${plural(module.lessons.length, 'lesson')}, ${progress.done} of ${progress.total} exercises solved`));
      }))),
    h('section', { class: 'home-section' },
      h('h2', null, 'Labs'),
      h('ul', { class: 'card-list' }, LABS.map((lab) => h('li', null,
        h('a', { href: href(`labs/${lab.id}`) }, lab.title), h('p', null, lab.text))))),
    h('section', { class: 'home-section' },
      h('h2', null, 'Practice data'),
      h('ul', { class: 'card-list' }, meta.datasets.map((d) => h('li', null,
        h('a', { href: href(`datasets/${d.id}`) }, d.title), h('p', null, d.summary),
        h('p', { class: 'muted' }, `${d.tables} tables, ${formatNumber(d.rows)} rows`))))));
}
