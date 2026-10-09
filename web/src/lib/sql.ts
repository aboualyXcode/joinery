// A small SQL tokenizer for syntax highlighting. The server has its own,
// dialect-aware tokenizer for anything that matters more than colour.

export type TokenKind = 'ws' | 'comment' | 'string' | 'ident' | 'keyword' | 'function' | 'word' | 'number'
  | 'param' | 'op';

export interface Token {
  kind: TokenKind;
  text: string;
  start: number;
  end: number;
}

export const KEYWORDS = new Set(`
  ADD ALL ALTER ALWAYS AND ANALYZE AS ASC ATTACH AUTOINCREMENT BEGIN BETWEEN BY CASCADE CASE CAST CHECK
  COLLATE COLUMN COMMIT CONFLICT CONSTRAINT CREATE CROSS CURRENT CURRENT_DATE CURRENT_TIME CURRENT_TIMESTAMP
  DEFAULT DEFERRABLE DELETE DESC DISTINCT DO DROP ELSE END ESCAPE EXCEPT EXCLUDE EXCLUDED EXISTS EXPLAIN
  FALSE FETCH FILTER FIRST FOLLOWING FOR FOREIGN FROM FULL GENERATED GLOB GROUP GROUPS HAVING IF IGNORE IN
  INDEX INNER INSERT INTERSECT INTO IS ISNULL JOIN KEY LAST LATERAL LEFT LIKE LIMIT MATERIALIZED MERGE NATURAL
  NO NOT NOTHING NOTNULL NULL NULLS OF OFFSET ON OR ORDER OTHERS OUTER OVER PARTITION PLAN PRAGMA PRECEDING
  PRIMARY QUALIFY QUERY RANGE RECURSIVE REFERENCES RELEASE RENAME REPLACE RESTRICT RETURNING RIGHT ROLLBACK
  ROW ROWS SAVEPOINT SELECT SET STORED STRICT TABLE TEMP TEMPORARY THEN TIES TO TOP TRANSACTION TRIGGER TRUE
  UNBOUNDED UNION UNIQUE UPDATE USING VACUUM VALUES VIEW VIRTUAL WHEN WHERE WINDOW WITH WITHOUT
`.trim().split(/\s+/));

const WORD = /[A-Za-z_\u0080-\uffff][\w$\u0080-\uffff]*/y;
const NUMBER = /0[xX][0-9A-Fa-f_]+|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?/y;
const OPERATOR = /->>|->|::|\|\||<=|>=|<>|!=|==|<<|>>|[-+*/%<>=~!&|^@#?(),;.[\]{}:$]/y;
const PARAM = /[?][0-9]*|[:@$][A-Za-z_][\w]*/y;

function quoted(sql: string, start: number, quote: string): number {
  let i = start + 1;
  while (i < sql.length) {
    if (sql[i] === quote) {
      if (sql[i + 1] === quote) { i += 2; continue; }
      return i + 1;
    }
    i += 1;
  }
  return sql.length;
}

function match(re: RegExp, sql: string, at: number): number {
  re.lastIndex = at;
  return re.test(sql) ? re.lastIndex : -1;
}

export function tokenize(sql: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  const push = (kind: TokenKind, end: number) => {
    tokens.push({ kind, text: sql.slice(i, end), start: i, end });
    i = end;
  };
  while (i < sql.length) {
    const c = sql.charAt(i);
    const next = sql.charAt(i + 1);
    if (/\s/.test(c)) {
      let end = i + 1;
      while (end < sql.length && /\s/.test(sql.charAt(end))) end += 1;
      push('ws', end);
    } else if (c === '-' && next === '-') {
      const nl = sql.indexOf('\n', i);
      push('comment', nl < 0 ? sql.length : nl);
    } else if (c === '/' && next === '*') {
      const close = sql.indexOf('*/', i + 2);
      push('comment', close < 0 ? sql.length : close + 2);
    } else if (c === "'") {
      push('string', quoted(sql, i, "'"));
    } else if (c === '"' || c === '`') {
      push('ident', quoted(sql, i, c));
    } else if (c === '[') {
      const close = sql.indexOf(']', i);
      push('ident', close < 0 ? sql.length : close + 1);
    } else if (/[0-9]/.test(c) || (c === '.' && /[0-9]/.test(next))) {
      push('number', match(NUMBER, sql, i));
    } else if (match(WORD, sql, i) > 0) {
      const end = match(WORD, sql, i);
      const word = sql.slice(i, end);
      let after = end;
      while (after < sql.length && sql.charAt(after) === ' ') after += 1;
      const upper = word.toUpperCase();
      const kind: TokenKind = sql.charAt(after) === '(' && !KEYWORDS.has(upper)
        ? 'function'
        : KEYWORDS.has(upper) ? 'keyword' : 'word';
      push(kind, end);
    } else if ((c === '?' || c === ':' || c === '@' || c === '$') && match(PARAM, sql, i) > i + (c === '?' ? 0 : 1)) {
      push('param', match(PARAM, sql, i));
    } else {
      const end = match(OPERATOR, sql, i);
      push('op', end > i ? end : i + 1);
    }
  }
  return tokens;
}

export function escapeHTML(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Highlighted HTML for the SQL. Every character is escaped. */
export function highlightHTML(sql: string, mark: [number, number] | null = null): string {
  let html = '';
  for (const token of tokenize(sql)) {
    const text = escapeHTML(token.text);
    const span = token.kind === 'ws' ? text : `<span class="tok-${token.kind}">${text}</span>`;
    const marked = mark !== null && token.kind !== 'ws' && token.start < mark[1] && token.end > mark[0];
    html += marked ? `<mark class="tok-error">${span}</mark>` : span;
  }
  return html;
}
