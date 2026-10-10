// The query workbench used by lesson examples and the playground:
// an editor, Run / Step through / Explain plan, and the output.
import { api } from '../api.ts';
import { announce, h, mount } from '../lib/dom.ts';
import { DIALECT_NAMES, plural } from '../lib/format.ts';
import type { EngineError, Meta, RunResponse } from '../types.ts';
import { createEditor } from './editor.ts';
import { renderPlan } from './plan.ts';
import { renderError, renderRun, statementSummary } from './results.ts';
import { renderQueryMap } from './queryflow.ts';
import { renderSteps } from './stepper.ts';
import { renderTimeline } from './timeline.ts';

export type Mode = 'run' | 'visualize' | 'steps' | 'plan';

export interface WorkbenchOptions {
  sql: string;
  dataset: string;
  meta: Meta;
  label: string;
  engine?: string | undefined;
  setup?: string | null | undefined;
  minLines?: number | undefined;
  maxLines?: number | undefined;
  pickers?: boolean | undefined;
  primary?: Mode | undefined;
  onChange?: ((state: { sql: string; dataset: string; engine: string }) => void) | undefined;
}

export interface Workbench {
  element: HTMLElement;
  getSql(): string;
  setSql(sql: string): void;
  setEngine(engine: string): void;
  setDataset(dataset: string): void;
  setDisabled(reason: string | null): void;
  execute(mode: Mode): Promise<void>;
}

export function requestError(error: unknown): EngineError {
  return { type: 'RequestError', message: error instanceof Error ? error.message : String(error), code: null };
}

export function createWorkbench(options: WorkbenchOptions): Workbench {
  let dataset = options.dataset;
  let engine = options.engine ?? 'sqlite';
  let lastMark: { start: number; end: number } | null = null;
  const status = h('p', { class: 'status', role: 'status' });
  const output = h('div', { class: 'output' });
  const notify = () => options.onChange?.({ sql: editor.getValue(), dataset, engine });
  const editor = createEditor({
    value: options.sql, label: options.label, minLines: options.minLines, maxLines: options.maxLines,
    onRun: () => void execute('run'), onStep: () => void execute('steps'), onChange: notify,
  });
  const primary = options.primary ?? 'run';
  const button = (mode: Mode, label: string) => h('button', {
    type: 'button', class: mode === primary ? 'button primary' : 'button', 'aria-pressed': 'false',
    on: { click: () => void execute(mode) },
  }, label);
  const buttons: Record<Mode, HTMLButtonElement> = {
    run: button('run', 'Run'),
    visualize: button('visualize', 'Visualize'),
    steps: button('steps', 'Step through'),
    plan: button('plan', 'Explain plan'),
  };
  const datasetSelect = options.pickers ? h('select', {
    'aria-label': 'Dataset',
    on: { change: (event: Event) => { dataset = (event.target as HTMLSelectElement).value; notify(); } },
  }, options.meta.datasets.map((d) => h('option', { value: d.id }, d.title))) : null;
  if (datasetSelect) datasetSelect.value = dataset;
  const engineSelect = options.pickers && options.meta.engines.length > 1 ? h('select', {
    'aria-label': 'Engine',
    on: { change: (event: Event) => { engine = (event.target as HTMLSelectElement).value; notify(); } },
  }, options.meta.engines.map((e) => h('option', { value: e.id },
    `${DIALECT_NAMES[e.id] ?? e.name}${e.experimental ? ' (experimental)' : ''}`))) : null;
  if (engineSelect) engineSelect.value = engine;
  const disabledNote = h('p', { class: 'muted disabled-note', hidden: true });

  const setBusy = (busy: boolean) => {
    Object.values(buttons).forEach((b) => { b.disabled = busy || !!disabledNote.textContent; });
    output.setAttribute('aria-busy', String(busy));
  };

  const markFirstError = (result: RunResponse, submitted: string) => {
    const failed = result.statements.find((s) => s.error);
    const position = failed?.error?.explanation?.position;
    if (!failed || !position) { lastMark = null; editor.markError(null); return; }
    const base = submitted.indexOf(failed.sql);
    const offset = options.setup ? submitted.length - editor.getValue().length : 0;
    lastMark = base >= 0 ? { start: base + position.start - offset, end: base + position.end - offset } : null;
    editor.markError(lastMark && lastMark.start >= 0 ? lastMark : null);
  };

  const replaceAtError = (value: string) => {
    if (lastMark && lastMark.start >= 0) editor.replaceRange(lastMark, value);
  };

  async function execute(mode: Mode): Promise<void> {
    const sql = editor.getValue();
    if (!sql.trim()) {
      status.textContent = 'Write a query first.';
      return;
    }
    Object.entries(buttons).forEach(([m, b]) => b.setAttribute('aria-pressed', String(m === mode)));
    setBusy(true);
    status.textContent = mode === 'run' ? 'Running\u2026' : mode === 'visualize' ? 'Mapping the query\u2026'
      : mode === 'steps' ? 'Running each stage\u2026' : 'Explaining\u2026';
    try {
      if (mode === 'run') {
        const submitted = options.setup ? `${options.setup.trim().replace(/;$/, '')};\n${sql}` : sql;
        const result = await api.run({ sql: submitted, dataset, engine });
        markFirstError(result, submitted);
        mount(output, result.error || result.skipped ? renderTimeline(result, submitted) : null, renderRun(result, replaceAtError));
        const failed = result.statements.find((s) => s.error);
        const last = result.statements[result.statements.length - 1];
        status.textContent = result.error
          ? `Failed: ${result.error.explanation?.title ?? result.error.message}`
          : failed ? 'A statement failed.'
            : last ? `${plural(result.statements.length, 'statement')} ran. ${statementSummary(last)}.` : 'Done.';
      } else if (mode === 'visualize') {
        const map = await api.visualize({ sql, dataset, engine });
        mount(output, renderQueryMap(map));
        status.textContent = `Mapped ${plural(map.dependencies.nodes?.length ?? 0, 'part')} and ${plural(map.steps.stages.length, 'stage')}.`;
      } else if (mode === 'steps') {
        const steps = await api.steps({ sql, dataset, engine });
        mount(output, renderSteps(steps));
        status.textContent = steps.supported ? `${plural(steps.stages.length, 'stage')}, in the order the database evaluates them.`
          : 'This statement runs as a whole.';
      } else {
        const plan = await api.explain({ sql, dataset, engine, setup: options.setup ?? null });
        mount(output, renderPlan(plan));
        status.textContent = plan.error ? 'The plan could not be produced.' : 'Plan ready.';
      }
    } catch (error) {
      mount(output, renderError(requestError(error)));
      status.textContent = 'The request failed.';
    } finally {
      setBusy(false);
    }
    announce(status.textContent ?? '');
  }

  const toolbar = h('div', { class: 'toolbar' },
    buttons.run, buttons.visualize, buttons.steps, buttons.plan,
    h('span', { class: 'spacer' }),
    datasetSelect, engineSelect,
    h('span', { class: 'shortcut' }, h('kbd', null, 'Ctrl'), ' + ', h('kbd', null, 'Enter'), ' runs'));
  return {
    element: h('div', { class: 'workbench' }, editor.element, toolbar, disabledNote, status, output),
    getSql: () => editor.getValue(),
    setSql: (sql: string) => editor.setValue(sql),
    setEngine(next: string) {
      engine = next;
      if (engineSelect) engineSelect.value = next;
    },
    setDataset(next: string) {
      dataset = next;
      if (datasetSelect) datasetSelect.value = next;
    },
    setDisabled(reason: string | null) {
      disabledNote.textContent = reason ?? '';
      disabledNote.hidden = !reason;
      setBusy(false);
    },
    execute,
  };
}
