// The processing-order widget: a query typeset clause by clause, numbered by
// the order in which the database evaluates it, with a live stepper.
import { api } from '../api.ts';
import { h, mount } from '../lib/dom.ts';
import { exploreData } from '../lib/explore.ts';
import { renderError } from './results.ts';
import { renderSteps } from './stepper.ts';
import { requestError } from './workbench.ts';

const ORDINALS = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh'];

export function renderProcessingOrder(hero = false): HTMLElement {
  const clauses = exploreData().presets.processing;
  const sample = clauses.map(([keyword, body]) => `${keyword} ${body}`).join('\n');
  const items = clauses.map(([keyword, body, step]) => {
    const item = h('li', { class: 'clause', 'data-step': String(step) },
      h('span', { class: 'step-badge', title: `Evaluated ${ORDINALS[step - 1] ?? ''}` },
        h('span', { class: 'sr-only' }, 'evaluation step '), String(step)),
      h('code', null, h('span', { class: 'tok-keyword' }, keyword), ` ${body}`));
    item.style.setProperty('view-transition-name', `clause-${step}`);
    return item;
  });
  const list = h('ol', { class: 'clauses', 'aria-label': 'A query, clause by clause, numbered in evaluation order' }, items);
  const output = h('div', { class: 'order-output' });
  let logical = false;

  const toggle: HTMLButtonElement = h('button', {
    type: 'button', class: 'button', 'aria-pressed': 'false',
    on: {
      click: () => {
        logical = !logical;
        const apply = () => {
          items.forEach((item) => { item.style.order = logical ? item.dataset.step ?? '' : ''; });
          list.classList.toggle('logical', logical);
        };
        const doc = document as Document & { startViewTransition?: (callback: () => void) => unknown };
        if (doc.startViewTransition && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
          doc.startViewTransition(apply);
        } else {
          apply();
        }
        toggle.setAttribute('aria-pressed', String(logical));
        toggle.textContent = logical ? 'Back to written order' : 'Reorder by evaluation';
      },
    },
  }, 'Reorder by evaluation');

  const run: HTMLButtonElement = h('button', {
    type: 'button', class: 'button primary',
    on: {
      click: async () => {
        run.disabled = true;
        mount(output, h('p', { class: 'loading', role: 'status' }, 'Running each stage on the shop data\u2026'));
        try {
          mount(output, renderSteps(await api.steps({ sql: sample, dataset: 'shop' })));
        } catch (error) {
          mount(output, renderError(requestError(error)));
        } finally {
          run.disabled = false;
        }
      },
    },
  }, 'Run it stage by stage');

  return h('div', { class: hero ? 'order hero-order' : 'order' },
    h('div', { class: 'order-sheet' }, list),
    h('div', { class: 'toolbar' }, run, toggle),
    output);
}
