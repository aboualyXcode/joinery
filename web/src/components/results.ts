// Result tables, error explanations and lint advice.
import { h } from '../lib/dom.ts';
import { formatCell, formatMs, formatSteps, numericColumns, plural } from '../lib/format.ts';
import type { Cell, EngineError, Finding, RunResponse, StatementResult } from '../types.ts';

export interface TableOptions {
  kept?: boolean[] | null;
  caption?: string;
}

export function renderTable(columns: string[], rows: Cell[][], options: TableOptions = {}): HTMLElement {
  const numeric = numericColumns(rows, columns.length);
  const kept = options.kept ?? null;
  const head = h('tr', null,
    kept ? h('th', { scope: 'col', class: 'marker' }, h('span', { class: 'sr-only' }, 'Kept')) : null,
    columns.map((name, i) => h('th', { scope: 'col', class: numeric[i] ? 'num' : undefined }, name)));
  const body = rows.map((row, r) => h('tr', { class: kept ? (kept[r] ? 'kept' : 'removed') : undefined },
    kept ? h('td', { class: 'marker' },
      h('span', { 'aria-hidden': 'true' }, kept[r] ? '\u2713' : '\u2715'),
      h('span', { class: 'sr-only' }, kept[r] ? 'kept' : 'removed')) : null,
    row.map((value, c) => {
      const view = formatCell(value);
      const classes = [view.kind === 'null' ? 'null' : '', numeric[c] ? 'num' : ''].filter(Boolean).join(' ');
      return h('td', { class: classes || undefined }, view.text);
    })));
  return h('div', { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': options.caption ?? 'Query result' },
    h('table', { class: 'data' },
      options.caption ? h('caption', { class: 'sr-only' }, options.caption) : null,
      h('thead', null, head),
      h('tbody', null, rows.length ? body : h('tr', null,
        h('td', { class: 'empty', colspan: String(columns.length + (kept ? 1 : 0)) }, 'No rows')))));
}

export function renderError(error: EngineError, onSuggestion?: (value: string) => void): HTMLElement {
  const info = error.explanation;
  const suggestions = info?.suggestions ?? [];
  return h('div', { class: 'callout error', role: 'alert' },
    h('p', { class: 'callout-title' }, info?.title ?? 'The query failed'),
    info?.detail ? h('p', null, info.detail) : null,
    h('p', { class: 'engine-message' }, h('code', null, error.message)),
    info?.hint ? h('p', { class: 'hint' }, info.hint) : null,
    suggestions.length ? h('p', { class: 'suggestions' }, 'Did you mean ',
      suggestions.map((value, i) => [i ? ', ' : '', onSuggestion
        ? h('button', { type: 'button', class: 'link', on: { click: () => onSuggestion(value) } }, value)
        : h('code', null, value)]), '?') : null);
}

export function renderWarnings(findings: Finding[]): HTMLElement | null {
  if (!findings.length) return null;
  return h('ul', { class: 'warnings', 'aria-label': 'Advice about this query' },
    findings.map((finding) => h('li', { class: finding.severity },
      h('span', { class: 'badge' }, finding.severity === 'warning' ? 'Check' : 'Tip'), ' ', finding.message)));
}

function oneLine(sql: string): string {
  const flat = sql.replace(/\s+/g, ' ').trim();
  return flat.length > 96 ? `${flat.slice(0, 95)}\u2026` : flat;
}

export function statementSummary(result: StatementResult): string {
  if (result.error) return 'Failed';
  if (result.kind === 'rows') {
    const shown = result.truncated ? `, showing the first ${result.rows.length}` : '';
    return `${plural(result.row_count, 'row')}${result.row_count_capped ? ' or more' : ''}${shown}`;
  }
  return result.changes ? `${plural(result.changes, 'row')} changed` : 'Done';
}

export function renderStatement(result: StatementResult, onSuggestion?: (value: string) => void): HTMLElement {
  const facts = [statementSummary(result), formatMs(result.elapsed_ms), formatSteps(result.vm_steps)].filter(Boolean);
  return h('section', { class: 'statement' },
    h('div', { class: 'statement-head' },
      h('code', { class: 'statement-sql' }, oneLine(result.sql)),
      h('p', { class: 'facts' }, facts.map((fact) => h('span', null, fact)))),
    result.error ? renderError(result.error, onSuggestion)
      : result.kind === 'rows' ? renderTable(result.columns, result.rows, { caption: 'Result rows' })
        : null);
}

export function renderRun(response: RunResponse, onSuggestion?: (value: string) => void): HTMLElement {
  return h('div', { class: 'run-output' },
    renderWarnings(response.warnings),
    !response.statements.length && response.error ? renderError(response.error, onSuggestion) : null,
    response.statements.map((statement) => renderStatement(statement, onSuggestion)),
    response.skipped ? h('p', { class: 'muted' }, `${plural(response.skipped, 'statement')} after the error did not run.`) : null);
}
