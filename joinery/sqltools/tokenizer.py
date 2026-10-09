"""Dialect-aware lexical scanner for SQL.

The tokenizer powers statement splitting, the query stepper, lint rules and
statement classification for server engines. It is purely lexical. It never
decides whether SQL is safe to run: process isolation and database
permissions do that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WS = "ws"
COMMENT = "comment"
STRING = "string"
IDENT = "ident"  # quoted identifier: "x", `x`, [x]
WORD = "word"  # keyword or bare identifier
NUMBER = "number"
PARAM = "param"  # ?, ?1, :name, @name, $1
OP = "op"  # operators and punctuation


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    text: str
    start: int
    end: int
    terminated: bool = True

    @property
    def upper(self) -> str:
        return self.text.upper()

    @property
    def significant(self) -> bool:
        return self.kind not in (WS, COMMENT)

    def is_word(self, *words: str) -> bool:
        return self.kind == WORD and self.text.upper() in words

    def is_op(self, *ops: str) -> bool:
        return self.kind == OP and self.text in ops


@dataclass(frozen=True, slots=True)
class Dialect:
    name: str
    double_quoted_strings: bool = False  # MySQL treats "x" as a string by default
    backslash_escapes: bool = False  # MySQL string literals use \ escapes
    hash_comments: bool = False  # MySQL: # comment
    bracket_identifiers: bool = False  # SQL Server and SQLite: [x]
    backtick_identifiers: bool = False  # MySQL and SQLite: `x`
    dollar_quotes: bool = False  # PostgreSQL and DuckDB: $$body$$
    nested_comments: bool = False  # PostgreSQL: /* /* */ */
    question_mark_param: bool = True  # PostgreSQL uses ? as a jsonb operator
    at_params: bool = True  # @name variables or parameters


DIALECTS: dict[str, Dialect] = {
    "sqlite": Dialect("sqlite", bracket_identifiers=True, backtick_identifiers=True),
    "postgres": Dialect(
        "postgres", dollar_quotes=True, nested_comments=True, question_mark_param=False, at_params=False
    ),
    "mysql": Dialect(
        "mysql",
        double_quoted_strings=True,
        backslash_escapes=True,
        hash_comments=True,
        backtick_identifiers=True,
    ),
    "mssql": Dialect("mssql", bracket_identifiers=True),
    "duckdb": Dialect("duckdb", dollar_quotes=True, at_params=False),
}


def get_dialect(dialect: str | Dialect) -> Dialect:
    if isinstance(dialect, Dialect):
        return dialect
    try:
        return DIALECTS[dialect]
    except KeyError:
        raise ValueError(f"unknown SQL dialect: {dialect!r}") from None


_WS = re.compile(r"\s+")
_WORD = re.compile(r"[^\W\d][\w$]*")
_NUMBER = re.compile(
    r"0[xX][0-9A-Fa-f_]+|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?"
)
_OPERATOR = re.compile(r"->>|->|::|\|\||<=>|<=|>=|<>|!=|==|<<|>>|[-+*/%<>=~!&|^@#?(),;.\[\]{}:$]")
_DOLLAR_TAG = re.compile(r"\$(?:[^\W\d]\w*)?\$")
_DOLLAR_PARAM = re.compile(r"\$(?:\d+|[^\W\d]\w*)")
_NAMED_PARAM = re.compile(r"[:@]{1,2}[^\W\d]\w*")
_QMARK_PARAM = re.compile(r"\?\d*")
_STRING_PREFIXES = "nNeExXbB"


def _quoted_end(sql: str, i: int, quote: str, backslash: bool) -> tuple[int, bool]:
    """Return the index just past the closing quote that matches sql[i]."""
    j = i + 1
    n = len(sql)
    while j < n:
        ch = sql[j]
        if backslash and ch == "\\":
            j += 2
            continue
        if ch == quote:
            if j + 1 < n and sql[j + 1] == quote:
                j += 2
                continue
            return j + 1, True
        j += 1
    return n, False


def _block_comment_end(sql: str, i: int, nested: bool) -> tuple[int, bool]:
    depth = 0
    j = i
    n = len(sql)
    while j < n:
        if sql.startswith("/*", j):
            depth = depth + 1 if nested or depth == 0 else depth
            j += 2
        elif sql.startswith("*/", j):
            depth -= 1
            j += 2
            if depth == 0:
                return j, True
        else:
            j += 1
    return n, False


def tokenize(sql: str, dialect: str | Dialect = "sqlite") -> list[Token]:
    """Split SQL text into tokens. Whitespace and comments are kept."""
    d = get_dialect(dialect)
    tokens: list[Token] = []
    i = 0
    n = len(sql)

    def add(kind: str, end: int, terminated: bool = True) -> None:
        nonlocal i
        tokens.append(Token(kind, sql[i:end], i, end, terminated))
        i = end

    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if c.isspace():
            add(WS, _WS.match(sql, i).end())  # type: ignore[union-attr]
        elif (c == "-" and nxt == "-") or (c == "#" and d.hash_comments):
            j = sql.find("\n", i)
            add(COMMENT, n if j < 0 else j)
        elif c == "/" and nxt == "*":
            end, ok = _block_comment_end(sql, i, d.nested_comments)
            add(COMMENT, end, ok)
        elif c == "'":
            end, ok = _quoted_end(sql, i, "'", d.backslash_escapes)
            add(STRING, end, ok)
        elif c in _STRING_PREFIXES and nxt == "'":
            backslash = d.backslash_escapes or (c in "eE" and d.name == "postgres")
            end, ok = _quoted_end(sql, i + 1, "'", backslash)
            add(STRING, end, ok)
        elif c == '"':
            end, ok = _quoted_end(sql, i, '"', d.backslash_escapes and d.double_quoted_strings)
            add(STRING if d.double_quoted_strings else IDENT, end, ok)
        elif c == "`" and d.backtick_identifiers:
            end, ok = _quoted_end(sql, i, "`", False)
            add(IDENT, end, ok)
        elif c == "[" and d.bracket_identifiers:
            end, ok = _quoted_end(sql, i, "]", False)
            add(IDENT, end, ok)
        elif c == "$" and d.dollar_quotes and (m := _DOLLAR_TAG.match(sql, i)):
            tag = m.group(0)
            close = sql.find(tag, m.end())
            if close < 0:
                add(STRING, n, False)
            else:
                add(STRING, close + len(tag))
        elif c == "$" and (m := _DOLLAR_PARAM.match(sql, i)):
            add(PARAM, m.end())
        elif c.isdigit() or (c == "." and nxt.isdigit()):
            add(NUMBER, _NUMBER.match(sql, i).end())  # type: ignore[union-attr]
        elif m := _WORD.match(sql, i):
            add(WORD, m.end())
        elif c == "?" and d.question_mark_param:
            add(PARAM, _QMARK_PARAM.match(sql, i).end())  # type: ignore[union-attr]
        elif c == ":" and nxt != ":" and (m := _NAMED_PARAM.match(sql, i)):
            add(PARAM, m.end())
        elif c == "@" and d.at_params and (m := _NAMED_PARAM.match(sql, i)):
            add(PARAM, m.end())
        elif m := _OPERATOR.match(sql, i):
            add(OP, m.end())
        else:
            add(OP, i + 1)
    return tokens


def significant(tokens: list[Token]) -> list[Token]:
    """Tokens that carry meaning: everything except whitespace and comments."""
    return [t for t in tokens if t.significant]


def first_keyword(sql: str, dialect: str | Dialect = "sqlite") -> str | None:
    for tok in tokenize(sql, dialect):
        if tok.significant:
            return tok.upper if tok.kind == WORD else None
    return None


def is_blank(sql: str, dialect: str | Dialect = "sqlite") -> bool:
    """True when the text holds nothing but whitespace and comments."""
    return not any(t.significant for t in tokenize(sql, dialect))
