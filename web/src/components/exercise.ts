// A graded exercise: write SQL, check it, get feedback, hints and a solution.
import { api } from '../api.ts';
import { announce, h, mount, uid } from '../lib/dom.ts';
import { plural } from '../lib/format.ts';
import { highlightHTML } from '../lib/sql.ts';
import { store } from '../lib/store.ts';
import type { CheckResponse, Exercise } from '../types.ts';
import { createEditor } from './editor.ts';
import { renderError, renderRun, renderTable, renderWarnings } from './results.ts';
import { requestError } from './workbench.ts';

function verdict(result: CheckResponse): HTMLElement {
  return h('div', { class: `verdict ${result.passed ? 'pass' : 'fail'}` },
    h('p', { class: 'verdict-title' }, result.passed ? 'Correct' : 'Not yet'),
    h('p', null, result.summary),
    result.details.length ? h('ul', { class: 'details' }, result.details.map((detail) => h('li', null, detail))) : null,
    result.hint ? h('p', { class: 'hint' }, result.hint) : null,
    result.error ? renderError(result.error) : null,
    renderWarnings(result.warnings),
    !result.passed && !result.error ? h('div', { class: 'compare' },
      h('div', null, h('h4', null, `Expected: ${plural(result.expected.row_count, 'row')}`),
        renderTable(result.expected.columns, result.expected.rows, { caption: 'Expected result' })),
      result.actual ? h('div', null, h('h4', null, `Yours: ${plural(result.actual.row_count, 'row')}`),
        renderTable(result.actual.columns, result.actual.rows, { caption: 'Your result' })) : null) : null);
}

export function renderExercise(exercise: Exercise, number: number, onProgress?: () => void): HTMLElement {
  const titleId = uid('exercise');
  const feedback = h('div', { class: 'feedback' });
  const status = h('span', { class: 'exercise-status' });
  const hintList = h('ol', { class: 'hints' });
  const solution = h('div', { class: 'solution' });
  const buttons: HTMLButtonElement[] = [];
  let hintsShown = 0;

  const editor = createEditor({
    value: store.attempt(exercise.id) ?? exercise.starter,
    label: `Your SQL for exercise ${number}: ${exercise.title}`,
    minLines: 4,
    maxLines: 26,
    onRun: () => void check(),
    onChange: (value) => store.saveAttempt(exercise.id, value),
  });

  const showStatus = () => {
    const done = store.isComplete(exercise.id);
    status.textContent = done ? 'Solved' : 'Not solved yet';
    status.classList.toggle('done', done);
  };
  const busy = (value: boolean) => buttons.forEach((b) => { b.disabled = value; });
  const button = (label: string, action: () => void | Promise<void>, primary = false) => {
    const b = h('button', { type: 'button', class: primary ? 'button primary' : 'button', on: { click: () => void action() } }, label);
    buttons.push(b);
    return b;
  };

  async function check(): Promise<void> {
    busy(true);
    try {
      const result = await api.check(exercise.id, editor.getValue());
      if (result.passed) store.complete(exercise.id);
      showStatus();
      onProgress?.();
      mount(feedback, verdict(result));
      announce(result.passed ? 'Correct.' : `Not yet. ${result.summary}`);
    } catch (error) {
      mount(feedback, renderError(requestError(error)));
    } finally {
      busy(false);
    }
  }

  async function run(): Promise<void> {
    busy(true);
    try {
      const result = await api.run({ sql: editor.getValue(), dataset: exercise.dataset });
      mount(feedback, h('div', { class: 'exercise-run' },
        h('p', { class: 'muted' }, 'Your output, not yet checked:'), renderRun(result)));
    } catch (error) {
      mount(feedback, renderError(requestError(error)));
    } finally {
      busy(false);
    }
  }

  async function reveal(): Promise<void> {
    try {
      const { solution: sql } = await api.solution(exercise.id);
      mount(solution,
        h('p', { class: 'muted' }, 'One correct answer. Yours can differ and still pass.'),
        h('pre', { class: 'code' }, h('code', { html: highlightHTML(sql) })),
        h('button', {
          type: 'button', class: 'button',
          on: { click: () => { editor.setValue(sql); store.saveAttempt(exercise.id, sql); editor.focus(); } },
        }, 'Copy into the editor'));
    } catch (error) {
      mount(solution, renderError(requestError(error)));
    }
  }

  const hintButton = h('button', {
    type: 'button', class: 'button quiet',
    on: {
      click: () => {
        const hint = exercise.hints[hintsShown];
        if (hint === undefined) return;
        hintList.append(h('li', { html: hint }));
        hintsShown += 1;
        hintButton.disabled = hintsShown >= exercise.hints.length;
        hintButton.textContent = hintButton.disabled ? 'No more hints' : 'Show another hint';
      },
    },
  }, 'Show a hint');

  showStatus();
  return h('section', { class: 'exercise', id: `exercise-${exercise.id}`, 'aria-labelledby': titleId },
    h('header', { class: 'exercise-head' }, h('h3', { id: titleId }, `Exercise ${number}: ${exercise.title}`), status),
    h('div', { class: 'prose', html: exercise.prompt_html }),
    h('p', { class: 'muted' }, `Dataset: ${exercise.dataset}.${exercise.plan_check ? ' Joinery also checks that the plan uses an index.' : ''}`),
    editor.element,
    h('div', { class: 'toolbar' },
      button('Check answer', check, true), button('Run', run),
      exercise.hints.length ? hintButton : null,
      button('Show the solution', reveal),
      button('Reset', () => { editor.setValue(exercise.starter); store.saveAttempt(exercise.id, exercise.starter); })),
    hintList, solution, feedback);
}
