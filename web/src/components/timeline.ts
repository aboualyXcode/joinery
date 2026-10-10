// How an error travels through a script: each statement as a node, the one
// that failed in red pencil, everything after it skipped, transactions bracketed.
import { h } from '../lib/dom.ts';
import { tokenize } from '../lib/sql.ts';
import type { RunResponse } from '../types.ts';

function splitScript(sql: string): string[] {
  const parts: string[] = [];
  let current = '';
  for (const token of tokenize(sql)) {
    if (token.kind === 'op' && token.text === ';') {
      if (current.trim()) parts.push(current.trim());
      current = '';
    } else {
      current += token.text;
    }
  }
  if (current.trim()) parts.push(current.trim());
  return parts.filter((part) => tokenize(part).some((t) => t.kind !== 'ws' && t.kind !== 'comment'));
}

function firstWords(sql: string): string {
  const words = sql.replace(/--.*$/gm, '').trim().split(/\s+/).slice(0, 3).join(' ');
  return words.length > 26 ? `${words.slice(0, 25)}\u2026` : words;
}

export function renderTimeline(response: RunResponse, submitted: string): HTMLElement | null {
  const total = response.statements.length + response.skipped;
  if (total < 2) return null;
  const texts = splitScript(submitted);
  const items = Array.from({ length: total }, (_, i) => {
    const ran = response.statements[i];
    const sql = ran?.sql ?? (texts.length === total ? texts[i] ?? '' : `statement ${i + 1}`);
    const status = !ran ? 'skipped' : ran.error ? 'failed' : 'ok';
    return { sql, status };
  });
  const begin = items.findIndex((item) => /^\s*BEGIN\b/i.test(item.sql));
  const end = items.findIndex((item, i) => i > begin && /^\s*(COMMIT|END|ROLLBACK)\b/i.test(item.sql));
  const openAtEnd = begin >= 0 && (end < 0 || items[end]?.status !== 'ok');
  return h('div', { class: 'timeline', role: 'group', 'aria-label': 'How the script ran, statement by statement' },
    h('ol', { class: 'timeline-steps' }, items.map((item, i) => h('li', {
      class: `t-${item.status}${begin >= 0 && i >= begin && (end < 0 || i <= end) ? ' in-txn' : ''}`,
      title: item.sql,
    },
    h('span', { class: 't-number' }, String(i + 1)),
    h('code', null, firstWords(item.sql)),
    h('span', { class: 't-status' }, item.status === 'ok' ? 'ran' : item.status === 'failed' ? 'failed' : 'never ran')))),
    begin >= 0 ? h('p', { class: 'timeline-note' }, openAtEnd
      ? 'The transaction never committed, so every change inside it is discarded.'
      : 'The transaction committed.') : null);
}
