"""Split a SQL script into individual statements.

Semicolons inside strings, quoted identifiers, comments and dollar-quoted
bodies never split a statement. Semicolons inside the BEGIN ... END body of a
CREATE TRIGGER (or FUNCTION/PROCEDURE) do not split it either.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tokenizer import WORD, Dialect, Token, tokenize

_ROUTINES = {"TRIGGER", "FUNCTION", "PROCEDURE"}


@dataclass(frozen=True, slots=True)
class Statement:
    text: str
    start: int
    end: int


def _is_routine(head: list[str]) -> bool:
    return bool(head) and head[0] == "CREATE" and any(word in _ROUTINES for word in head[1:6])


def split_statements(sql: str, dialect: str | Dialect = "sqlite") -> list[Statement]:
    tokens = tokenize(sql, dialect)
    statements: list[Statement] = []
    start = 0
    head: list[str] = []
    depth = 0
    has_content = False

    def flush(end: int) -> None:
        raw = sql[start:end]
        stripped = raw.strip()
        if has_content and stripped:
            offset = start + (len(raw) - len(raw.lstrip()))
            statements.append(Statement(stripped, offset, offset + len(stripped)))

    tok: Token
    for tok in tokens:
        if not tok.significant:
            continue
        if tok.is_op(";") and depth == 0:
            flush(tok.start)
            start, head, depth, has_content = tok.end, [], 0, False
            continue
        has_content = True
        if tok.kind != WORD:
            continue
        word = tok.upper
        if len(head) < 6:
            head.append(word)
        if _is_routine(head):
            if word in ("BEGIN", "CASE"):
                depth += 1
            elif word == "END" and depth > 0:
                depth -= 1
    flush(len(sql))
    return statements


def statement_texts(sql: str, dialect: str | Dialect = "sqlite") -> list[str]:
    return [s.text for s in split_statements(sql, dialect)]
