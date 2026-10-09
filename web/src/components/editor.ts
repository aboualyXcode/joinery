// A dependency-free SQL editor: a real <textarea> (so selection, undo, IME and
// screen readers all work) layered over a syntax-highlighted mirror.
import { h } from '../lib/dom.ts';
import { highlightHTML } from '../lib/sql.ts';

export interface EditorOptions {
  value: string;
  label: string;
  minLines?: number | undefined;
  maxLines?: number | undefined;
  onRun?: (() => void) | undefined;
  onStep?: (() => void) | undefined;
  onChange?: ((value: string) => void) | undefined;
}

export interface Editor {
  element: HTMLElement;
  getValue(): string;
  setValue(value: string): void;
  focus(): void;
  markError(range: { start: number; end: number } | null): void;
  replaceRange(range: { start: number; end: number }, text: string): void;
}

export function createEditor(options: EditorOptions): Editor {
  const gutter = h('div', { class: 'editor-gutter', 'aria-hidden': 'true' });
  const code = h('code');
  const mirror = h('pre', { class: 'editor-highlight', 'aria-hidden': 'true' }, code);
  const input = h('textarea', {
    class: 'editor-input', spellcheck: 'false', autocapitalize: 'off', autocomplete: 'off', wrap: 'off',
    'aria-label': options.label, value: options.value,
  });
  const element = h('div', { class: 'editor' }, gutter, h('div', { class: 'editor-body' }, mirror, input));
  let mark: [number, number] | null = null;
  let escaped = false;

  const sync = () => {
    mirror.scrollTop = input.scrollTop;
    mirror.scrollLeft = input.scrollLeft;
    gutter.scrollTop = input.scrollTop;
  };
  const render = () => {
    const text = input.value;
    code.innerHTML = `${highlightHTML(text, mark)}\n`;
    const lines = text.split('\n').length;
    if (gutter.childElementCount !== lines) {
      gutter.replaceChildren(...Array.from({ length: lines }, (_, i) => h('span', null, String(i + 1))));
    }
    const visible = Math.min(Math.max(lines, options.minLines ?? 4), options.maxLines ?? 28);
    element.style.setProperty('--lines', String(visible));
    sync();
  };
  const changed = () => {
    mark = null;
    render();
    options.onChange?.(input.value);
  };

  input.addEventListener('input', changed);
  input.addEventListener('scroll', sync);
  input.addEventListener('keydown', (event: KeyboardEvent) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      if (event.shiftKey) options.onStep?.();
      else options.onRun?.();
      return;
    }
    if (event.key === 'Escape') {
      escaped = true; // the next Tab moves focus instead of indenting
      return;
    }
    if (event.key === 'Tab' && !event.shiftKey && !escaped) {
      event.preventDefault();
      input.setRangeText('  ', input.selectionStart, input.selectionEnd, 'end');
      changed();
    }
    escaped = false;
  });
  render();

  return {
    element,
    getValue: () => input.value,
    setValue(value: string) {
      input.value = value;
      mark = null;
      render();
    },
    focus: () => input.focus(),
    markError(range) {
      mark = range ? [range.start, range.end] : null;
      render();
    },
    replaceRange(range, text) {
      input.setRangeText(text, range.start, range.end, 'end');
      changed();
      input.focus();
    },
  };
}
