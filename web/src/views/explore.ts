import { renderRelationships } from '../components/erd.ts';
import { renderEngineExplorer } from '../components/enginemap.ts';
import { renderFailureExplorer } from '../components/failures.ts';
import { renderQueryExplorer } from '../components/queryflow.ts';
import { h, mount } from '../lib/dom.ts';
import { exploreData } from '../lib/explore.ts';
import { href } from '../router.ts';
import type { Meta } from '../types.ts';

const TABS: [string, string][] = [['map', 'Engine map'], ['failures', 'Failures'], ['query', 'Query map'], ['relationships', 'Relationships']];
const TITLES: Record<string, string> = {
  map: 'The engine map', failures: 'How failures travel', query: 'Query map', relationships: 'Relationships',
};
const LEADS: Record<string, string> = {
  map: 'Every component a query passes through. Play a flow, or select a component.',
  failures: 'Start from what you see, or paste a message. The map shows where a failure starts and where you notice it.',
  query: 'What feeds a query, how many rows survive each stage and what each one costs, and how the engine runs it.',
  relationships: 'Tables, keys, and the join path between any two tables.',
};

export function renderExplore(target: HTMLElement, meta: Meta, path: string[], params: URLSearchParams): void {
  const data = exploreData();
  const section = path[1] === 'flows' || !path[1] ? 'map' : path[1];
  let body: HTMLElement;
  if (section === 'failures') {
    body = renderFailureExplorer(data, { initial: path[2] });
  } else if (section === 'query') {
    body = renderQueryExplorer({ preset: params.get('preset') ?? undefined });
  } else if (section === 'relationships') {
    const dataset = meta.datasets.some((d) => d.id === path[2]) ? path[2] ?? 'shop' : 'shop';
    body = h('div', null,
      h('nav', { class: 'segmented', 'aria-label': 'Datasets' }, meta.datasets.map((d) => h('a', {
        href: href(`explore/relationships/${d.id}`), 'aria-current': d.id === dataset ? 'page' : undefined,
      }, d.title))),
      renderRelationships(dataset));
  } else {
    body = renderEngineExplorer(data, { flow: path[1] === 'flows' ? path[2] : undefined });
  }
  document.title = `${TITLES[section] ?? 'Explore'} | Joinery`;
  mount(target, h('div', { class: 'page wide explore' },
    h('nav', { class: 'explore-tabs', 'aria-label': 'Explore' }, TABS.map(([id, name]) => h('a', {
      href: href(`explore/${id}`), 'aria-current': id === section ? 'page' : undefined,
    }, name))),
    h('h1', null, TITLES[section] ?? 'Explore'),
    h('p', { class: 'lede' }, LEADS[section] ?? ''),
    body));
}
