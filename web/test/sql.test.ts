import assert from 'node:assert/strict';
import { test } from 'node:test';
import { highlightHTML, tokenize } from '../src/lib/sql.ts';

test('tokenize classifies keywords, functions, strings, identifiers and comments', () => {
  const tokens = tokenize(`SELECT count(*), "order" FROM t WHERE a = 'x;y' -- note`)
    .filter((t) => t.kind !== 'ws').map((t) => `${t.kind}:${t.text}`);
  assert.deepEqual(tokens, ['keyword:SELECT', 'function:count', 'op:(', 'op:*', 'op:)', 'op:,', 'ident:"order"',
    'keyword:FROM', 'word:t', 'keyword:WHERE', 'word:a', 'op:=', "string:'x;y'", 'comment:-- note']);
});

test('tokens cover the input exactly', () => {
  const sql = "SELECT 1.5e3, x'ff', :name, ? /* c */ FROM [t] WHERE a <> b || c";
  assert.equal(tokenize(sql).map((t) => t.text).join(''), sql);
});

test('highlighting escapes HTML', () => {
  const html = highlightHTML("SELECT '<img src=x onerror=alert(1)>'");
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
});

test('an error range is marked', () => {
  assert.match(highlightHTML('SELECT nope FROM t', [7, 11]), /<mark class="tok-error"><span class="tok-word">nope<\/span><\/mark>/);
});
