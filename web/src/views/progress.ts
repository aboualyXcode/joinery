import { api } from '../api.ts';
import { h, mount } from '../lib/dom.ts';
import { store } from '../lib/store.ts';
import { moduleProgress } from './home.ts';

function download(): void {
  const url = URL.createObjectURL(new Blob([store.exportJson()], { type: 'application/json' }));
  const link = h('a', { href: url, download: 'joinery-progress.json' });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function renderProgress(target: HTMLElement): Promise<void> {
  const { modules } = await api.curriculum();
  document.title = 'Your progress | Joinery';
  const all = modules.flatMap((m) => m.lessons.flatMap((l) => l.exercises));
  const done = all.filter((id) => store.isComplete(id)).length;
  const message = h('p', { class: 'status', role: 'status' });
  const file = h('input', {
    type: 'file', accept: 'application/json', hidden: true,
    on: {
      change: async (event: Event) => {
        const chosen = (event.target as HTMLInputElement).files?.[0];
        if (!chosen) return;
        if (store.importJson(await chosen.text())) await renderProgress(target);
        else message.textContent = 'That file is not a Joinery progress export.';
      },
    },
  });
  mount(target, h('div', { class: 'page' },
    h('h1', null, 'Your progress'),
    h('p', { class: 'lede' }, `${done} of ${all.length} exercises solved. Progress is stored in this browser only.`),
    h('ol', { class: 'progress-list' }, modules.map((module) => {
      const p = moduleProgress(module);
      const fill = h('span', { class: 'bar-fill' });
      fill.style.setProperty('--value', String(p.total ? p.done / p.total : 0));
      return h('li', null,
        h('span', { class: 'progress-name' }, `${module.number}. ${module.title}`),
        h('span', { class: 'bar', role: 'img', 'aria-label': `${p.done} of ${p.total} exercises solved` }, fill),
        h('span', { class: 'muted' }, `${p.done} / ${p.total}`));
    })),
    h('div', { class: 'toolbar' },
      h('button', { type: 'button', class: 'button', on: { click: download } }, 'Export progress'),
      h('button', { type: 'button', class: 'button', on: { click: () => file.click() } }, 'Import progress'),
      file,
      h('button', {
        type: 'button', class: 'button danger',
        on: {
          click: () => {
            if (window.confirm('Reset all progress stored in this browser?')) {
              store.reset();
              void renderProgress(target);
            }
          },
        },
      }, 'Reset progress')),
    message));
}
