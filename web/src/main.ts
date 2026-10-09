// Application shell: header, routing, theme and progress summary.
import { api } from './api.ts';
import { renderError } from './components/results.ts';
import { requestError } from './components/workbench.ts';
import { h, mount, s, spinner } from './lib/dom.ts';
import { preference, setPreference, store } from './lib/store.ts';
import { href, parseHash } from './router.ts';
import type { Meta } from './types.ts';
import { renderDatasets } from './views/datasets.ts';
import { renderHome } from './views/home.ts';
import { renderLabs } from './views/labs.ts';
import { renderCurriculum, renderLesson } from './views/learn.ts';
import { renderPlayground } from './views/playground.ts';
import { renderProgress } from './views/progress.ts';
import { renderReference } from './views/reference.ts';

const NAV: [string, string][] = [
  ['learn', 'Learn'], ['playground', 'Playground'], ['datasets', 'Datasets'], ['labs', 'Labs'], ['reference', 'Reference'],
];
const THEMES = ['system', 'light', 'dark'];

function applyTheme(theme: string): void {
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

function logo(): SVGSVGElement {
  return s('svg', { class: 'logo', viewBox: '0 0 32 32', 'aria-hidden': 'true' },
    s('path', { d: 'M5 7 L16 16 L5 25 Z M27 7 L16 16 L27 25 Z' }));
}

function header(main: HTMLElement) {
  const links = NAV.map(([id, label]) => h('a', { href: href(id), 'data-section': id }, label));
  const progress = h('a', { class: 'progress-link', href: href('progress') }, 'Progress');
  let theme = preference('theme', 'system');
  const themeButton = h('button', {
    type: 'button', class: 'theme-button',
    on: {
      click: () => {
        theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length] ?? 'system';
        setPreference('theme', theme);
        applyTheme(theme);
        label();
      },
    },
  });
  const label = () => {
    themeButton.textContent = `Theme: ${theme}`;
    themeButton.setAttribute('aria-label', `Colour theme: ${theme}. Press to change.`);
  };
  label();
  const element = h('header', { class: 'site-header' },
    h('a', { class: 'skip-link', href: '#main-content', on: { click: (event: Event) => { event.preventDefault(); main.focus(); } } }, 'Skip to content'),
    h('a', { class: 'brand', href: href('') }, logo(), h('span', null, 'Joinery')),
    h('nav', { class: 'main-nav', 'aria-label': 'Main' }, links),
    h('div', { class: 'header-tools' }, progress, themeButton));
  return {
    element,
    setActive(section: string) {
      links.forEach((link) => {
        if (link.dataset.section === section) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
      });
    },
    async refresh() {
      try {
        const { modules } = await api.curriculum();
        const all = modules.flatMap((m) => m.lessons.flatMap((l) => l.exercises));
        progress.textContent = `${all.filter((id) => store.isComplete(id)).length} / ${all.length} solved`;
      } catch {
        progress.textContent = 'Progress';
      }
    },
  };
}

function footer(meta: Meta): HTMLElement {
  return h('footer', { class: 'site-footer' },
    h('p', null, `Joinery ${meta.version}. Engines on this server: `,
      meta.engines.map((e, i) => [i ? ', ' : '', `${e.name} ${e.version}${e.experimental ? ' (experimental)' : ''}`]), '.'),
    h('p', { class: 'muted' }, 'All sample data is fictional. Every query runs on a private copy that is thrown away afterwards.'));
}

async function boot(): Promise<void> {
  applyTheme(preference('theme', 'system'));
  const app = document.getElementById('app');
  if (!app) return;
  let meta: Meta;
  try {
    meta = await api.meta();
  } catch (error) {
    mount(app, h('main', { class: 'page' }, h('h1', null, 'Joinery could not start'), renderError(requestError(error))));
    return;
  }
  const main = h('main', { id: 'main-content', tabindex: '-1' });
  const top = header(main);
  mount(app, top.element, main, footer(meta), h('div', { id: 'announcer', class: 'sr-only', 'aria-live': 'polite' }));
  store.subscribe(() => void top.refresh());
  void top.refresh();
  let first = true;

  const route = async () => {
    const { path, params } = parseHash(location.hash);
    const section = path[0] ?? '';
    top.setActive(section);
    main.replaceChildren(spinner('Loading\u2026'));
    try {
      if (!section) await renderHome(main, meta);
      else if (section === 'learn') await (path[1] ? renderLesson(main, path[1], meta) : renderCurriculum(main));
      else if (section === 'playground') await renderPlayground(main, meta, params);
      else if (section === 'datasets') await renderDatasets(main, meta, path[1] ?? 'shop');
      else if (section === 'labs') renderLabs(main, meta, path[1]);
      else if (section === 'reference') await renderReference(main, meta);
      else if (section === 'progress') await renderProgress(main);
      else {
        document.title = 'Not found | Joinery';
        mount(main, h('div', { class: 'page' }, h('h1', null, 'There is no page here'),
          h('p', null, 'The link may be out of date. ', h('a', { href: href('learn') }, 'Browse the course'), ' or ',
            h('a', { href: href('') }, 'go to the home page'), '.')));
      }
    } catch (error) {
      mount(main, h('div', { class: 'page' }, h('h1', null, 'This page could not be loaded'),
        renderError(requestError(error)), h('p', null, h('a', { href: href('') }, 'Go to the home page'))));
    }
    if (!first) {
      main.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }
    first = false;
  };
  window.addEventListener('hashchange', () => {
    if (location.hash === '' || location.hash.startsWith('#/')) void route();
  });
  await route();
}

void boot();
