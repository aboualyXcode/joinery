import { api } from '../api.ts';
import { renderErd } from '../components/erd.ts';
import { renderExample } from '../components/example.ts';
import { renderExercise } from '../components/exercise.ts';
import { renderIndexLab } from '../components/indexlab.ts';
import { renderIsolationSimulator } from '../components/isolation.ts';
import { renderJoinVisualizer } from '../components/joinviz.ts';
import { renderJourney } from '../components/journey.ts';
import { renderProcessingOrder } from '../components/order.ts';
import { h, mount } from '../lib/dom.ts';
import { DIALECT_NAMES, plural } from '../lib/format.ts';
import { highlightHTML } from '../lib/sql.ts';
import { store } from '../lib/store.ts';
import { href } from '../router.ts';
import type { Lesson, Meta, Module, Section } from '../types.ts';
import { moduleProgress } from './home.ts';

export function lessonDone(exercises: string[]): boolean {
  return exercises.length > 0 && exercises.every((id) => store.isComplete(id));
}

export function highlightStatic(root: HTMLElement): void {
  root.querySelectorAll<HTMLElement>('.prose pre > code').forEach((code) => {
    if (code.classList.contains('language-sql') || !code.className) code.innerHTML = highlightHTML(code.textContent ?? '');
  });
}

function rail(modules: Module[], current: string | null): HTMLElement {
  return h('nav', { class: 'rail', 'aria-label': 'Course contents' }, modules.map((module) => h('div', { class: 'rail-module' },
    h('p', { class: 'rail-title' }, `${module.number}. ${module.title}`),
    h('ol', null, module.lessons.map((lesson) => {
      const done = lessonDone(lesson.exercises);
      return h('li', null, h('a', {
        href: href(`learn/${lesson.id}`), 'aria-current': lesson.id === current ? 'page' : undefined,
        class: done ? 'done' : undefined,
      }, h('span', { class: 'lesson-number' }, lesson.number), lesson.title,
      done ? h('span', { class: 'sr-only' }, ' (completed)') : null));
    })))));
}

function widget(type: string, lesson: Lesson, meta: Meta): HTMLElement {
  switch (type) {
    case 'join-visualizer': return renderJoinVisualizer();
    case 'isolation-simulator': return renderIsolationSimulator();
    case 'index-lab': return renderIndexLab();
    case 'query-journey': return renderJourney(meta);
    case 'processing-order': return renderProcessingOrder();
    case 'erd': {
      const holder = h('p', { class: 'loading', role: 'status' }, 'Drawing the diagram\u2026');
      api.dataset(lesson.dataset)
        .then((detail) => holder.replaceWith(renderErd(detail)))
        .catch(() => { holder.textContent = 'The diagram could not be loaded.'; });
      return holder;
    }
    default:
      return h('p', { class: 'muted' }, `Unknown widget: ${type}`);
  }
}

function renderSection(section: Section, lesson: Lesson, meta: Meta): HTMLElement {
  return h('section', { class: 'lesson-section' },
    h('h2', null, section.title),
    section.html ? h('div', { class: 'prose', html: section.html }) : null,
    section.widget ? h('div', { class: 'widget' }, widget(section.widget.type, lesson, meta)) : null,
    section.examples.map((example) => renderExample(example, meta)));
}

export async function renderCurriculum(target: HTMLElement): Promise<void> {
  const { modules } = await api.curriculum();
  document.title = 'The course | Joinery';
  mount(target, h('div', { class: 'page' },
    h('h1', null, 'The course'),
    h('p', { class: 'lede' }, 'Six modules take you from your first SELECT to production pipelines, performance work and troubleshooting. Each lesson runs on real data and ends with graded exercises.'),
    modules.map((module) => {
      const progress = moduleProgress(module);
      return h('section', { class: 'module' },
        h('h2', null, `${module.number}. ${module.title}`),
        h('p', null, module.summary),
        h('p', { class: 'muted' }, `${progress.done} of ${progress.total} exercises solved`),
        h('ol', { class: 'lesson-list' }, module.lessons.map((lesson) => h('li', { class: lessonDone(lesson.exercises) ? 'done' : undefined },
          h('a', { href: href(`learn/${lesson.id}`) }, `${lesson.number} ${lesson.title}`),
          h('p', null, lesson.summary),
          h('p', { class: 'muted' }, `${lesson.level}, about ${lesson.minutes} minutes, ${plural(lesson.exercises.length, 'exercise')}`)))));
    })));
}

export async function renderLesson(target: HTMLElement, id: string, meta: Meta): Promise<void> {
  const [lesson, { modules }] = await Promise.all([api.lesson(id), api.curriculum()]);
  store.visit(lesson.id);
  document.title = `${lesson.title} | Joinery`;
  const module = modules.find((m) => m.id === lesson.module);
  const railHolder = h('div', { class: 'rail-holder' }, rail(modules, lesson.id));
  const refreshRail = () => railHolder.replaceChildren(rail(modules, lesson.id));
  const notes = Object.entries(lesson.dialect_notes);
  const article = h('article', { class: 'lesson' },
    h('header', { class: 'lesson-head' },
      h('p', { class: 'lesson-meta' },
        h('span', null, `Lesson ${lesson.number}`), module ? h('span', null, module.title) : null,
        h('span', null, lesson.level), h('span', null, `about ${lesson.minutes} minutes`),
        h('a', { href: href(`datasets/${lesson.dataset}`) }, `${lesson.dataset} dataset`)),
      h('h1', null, lesson.title),
      h('p', { class: 'lede' }, lesson.summary),
      lesson.objectives.length ? h('div', { class: 'objectives' },
        h('h2', null, 'In this lesson you will'),
        h('ul', null, lesson.objectives.map((objective) => h('li', { html: objective })))) : null),
    lesson.sections.map((section) => renderSection(section, lesson, meta)),
    lesson.exercises.length ? h('section', { class: 'exercises' },
      h('h2', null, 'Exercises'),
      lesson.exercises.map((exercise, i) => renderExercise(exercise, i + 1, refreshRail))) : null,
    notes.length ? h('section', { class: 'dialects' },
      h('h2', null, 'In other databases'),
      h('dl', null, notes.map(([engine, html]) => h('div', null, h('dt', null, DIALECT_NAMES[engine] ?? engine), h('dd', { html }))))) : null,
    lesson.references.length ? h('section', { class: 'references' },
      h('h2', null, 'Further reading'),
      h('ul', null, lesson.references.map((ref) => h('li', null, h('a', { href: ref.url, rel: 'noopener noreferrer', target: '_blank' }, ref.title))))) : null,
    h('nav', { class: 'pager', 'aria-label': 'Lessons' },
      lesson.previous ? h('a', { href: href(`learn/${lesson.previous}`), rel: 'prev' }, 'Previous lesson') : h('span'),
      lesson.next ? h('a', { href: href(`learn/${lesson.next}`), rel: 'next' }, 'Next lesson')
        : h('a', { href: href('progress') }, 'See your progress')));
  mount(target, h('div', { class: 'lesson-layout' },
    h('details', { class: 'rail-toggle', open: window.matchMedia('(min-width: 960px)').matches },
      h('summary', null, 'Course contents'), railHolder),
    article));
  highlightStatic(article);
}
