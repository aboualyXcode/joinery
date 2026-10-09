import { renderIndexLab } from '../components/indexlab.ts';
import { renderIsolationSimulator } from '../components/isolation.ts';
import { renderJoinVisualizer } from '../components/joinviz.ts';
import { renderJourney } from '../components/journey.ts';
import { h, mount } from '../lib/dom.ts';
import { href } from '../router.ts';
import type { Meta } from '../types.ts';
import { LABS } from './home.ts';

export function renderLabs(target: HTMLElement, meta: Meta, id: string | undefined): void {
  const lab = LABS.find((l) => l.id === id);
  if (!lab) {
    document.title = 'Labs | Joinery';
    mount(target, h('div', { class: 'page' },
      h('h1', null, 'Labs'),
      h('p', { class: 'lede' }, 'Interactive models of how databases work, each backed by real queries or documented engine behaviour.'),
      h('ul', { class: 'card-list' }, LABS.map((l) => h('li', null, h('a', { href: href(`labs/${l.id}`) }, l.title), h('p', null, l.text))))));
    return;
  }
  document.title = `${lab.title} | Joinery`;
  const body = lab.id === 'joins' ? renderJoinVisualizer()
    : lab.id === 'isolation' ? renderIsolationSimulator()
      : lab.id === 'indexes' ? renderIndexLab() : renderJourney(meta);
  mount(target, h('div', { class: 'page wide' },
    h('p', null, h('a', { href: href('labs') }, 'All labs')),
    h('h1', null, lab.title),
    h('p', { class: 'lede' }, lab.text),
    body));
}
