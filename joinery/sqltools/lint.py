"""Advisory lint rules: patterns that run fine but often surprise people."""

from __future__ import annotations

import re

from .split import split_statements
from .stepper import _clause_positions, _depths
from .tokenizer import NUMBER, OP, STRING, WORD, Token, significant, tokenize

INDEX_BREAKERS = {"LOWER", "UPPER", "DATE", "DATETIME", "STRFTIME", "SUBSTR", "SUBSTRING", "TRIM", "ABS",
                  "ROUND", "COALESCE", "IFNULL", "JULIANDAY", "YEAR", "MONTH", "DATE_TRUNC", "CAST"}
AGGREGATES = {"COUNT", "SUM", "AVG", "MIN", "MAX", "GROUP_CONCAT", "STRING_AGG", "TOTAL", "JSON_GROUP_ARRAY"}


def _finding(rule: str, severity: str, message: str, base: int, tok: Token | None) -> dict:
    span = {"start": base + tok.start, "end": base + tok.end} if tok else {"start": None, "end": None}
    return {"rule": rule, "severity": severity, "message": message, **span}


def _clause_span(tokens: list[Token], name: str) -> tuple[int, int] | None:
    positions = _clause_positions(tokens, 0) if tokens else []
    for n, (clause, _kw, body) in enumerate(positions):
        if clause == name:
            end = positions[n + 1][1] if n + 1 < len(positions) else len(tokens)
            return body, end
    return None


def lint_statement(sql: str, base: int = 0, dialect: str = "sqlite") -> list[dict]:
    tokens = significant(tokenize(sql, dialect))
    if not tokens:
        return []
    findings: list[dict] = []
    depths = _depths(tokens)
    first = tokens[0].upper if tokens[0].kind == WORD else ""

    for i, tok in enumerate(tokens[:-1]):
        nxt = tokens[i + 1]
        if tok.kind == OP and tok.text in ("=", "<>", "!=") and nxt.is_word("NULL"):
            findings.append(_finding("null-comparison", "warning",
                                     "Comparing with NULL using = or <> is never true. Use IS NULL or IS NOT NULL.",
                                     base, tok))
        if tok.is_word("NOT") and nxt.is_word("IN") and i + 3 < len(tokens) and tokens[i + 2].is_op("(") \
                and tokens[i + 3].is_word("SELECT"):
            findings.append(_finding("not-in-subquery", "info",
                                     "NOT IN returns no rows at all if the subquery produces a NULL. "
                                     "NOT EXISTS behaves the way most people expect.", base, tok))
        if tok.is_word("LIKE") and nxt.kind == STRING and nxt.text.startswith("'%"):
            findings.append(_finding("leading-wildcard", "info",
                                     "A pattern that starts with % cannot use a B-tree index, so every row is checked.",
                                     base, nxt))
        if tok.is_word("UNION") and depths[i] == 0 and not nxt.is_word("ALL"):
            findings.append(_finding("union-distinct", "info",
                                     "UNION removes duplicates, which costs a sort or hash. "
                                     "Use UNION ALL when duplicates cannot occur or are wanted.", base, tok))

    if first in ("UPDATE", "DELETE") and not any(t.is_word("WHERE") and depths[i] == 0 for i, t in enumerate(tokens)):
        findings.append(_finding("missing-where", "warning",
                                 f"This {first} has no WHERE clause, so it changes every row in the table.",
                                 base, tokens[0]))

    if first in ("SELECT", "WITH"):
        start = next((i for i, t in enumerate(tokens) if t.is_word("SELECT") and depths[i] == 0), None)
        if start is not None:
            outer = tokens[start:]
            from_span = _clause_span(outer, "FROM")
            where_span = _clause_span(outer, "WHERE")
            has_join = any(t.is_word("JOIN") for t in outer)
            if len(outer) > 1 and outer[1].is_op("*") and has_join:
                findings.append(_finding("select-star-join", "info",
                                         "SELECT * over a join returns every column of every table, including "
                                         "duplicates such as several id columns. List the columns you need.",
                                         base, outer[1]))
            if from_span:
                outer_depths = _depths(outer)
                commas = [outer[k] for k in range(*from_span) if outer[k].is_op(",") and outer_depths[k] == outer_depths[from_span[0]]]
                if commas and not where_span:
                    findings.append(_finding("cartesian-product", "warning",
                                             "Tables listed with commas and no WHERE clause pair every row with "
                                             "every row (a Cartesian product). Use JOIN ... ON.", base, commas[0]))
            if where_span:
                for k in range(where_span[0], where_span[1] - 1):
                    tok = outer[k]
                    if tok.kind == WORD and tok.upper in INDEX_BREAKERS and outer[k + 1].is_op("("):
                        findings.append(_finding("function-on-column", "info",
                                                 f"Wrapping a column in {tok.text}() stops a plain index on that column "
                                                 "from being used. Compare the raw column, for example with a range, or "
                                                 "create an index on the expression.", base, tok))
                        break
            limit_span = _clause_span(outer, "LIMIT")
            if limit_span and not _clause_span(outer, "ORDER BY"):
                findings.append(_finding("limit-without-order", "info",
                                         "LIMIT without ORDER BY returns an arbitrary set of rows.", base,
                                         outer[limit_span[0] - 1]))
            if limit_span:
                body = outer[limit_span[0]:limit_span[1]]
                for n, tok in enumerate(body):
                    is_offset = (n > 0 and body[n - 1].is_word("OFFSET")) or (n + 1 < len(body) and body[n + 1].is_op(","))
                    if tok.kind == NUMBER and is_offset and re.fullmatch(r"\d+", tok.text) and int(tok.text) >= 1000:
                        findings.append(_finding("large-offset", "info",
                                                 "A large OFFSET still reads and discards every skipped row. Keyset "
                                                 "pagination (WHERE id > last_seen ORDER BY id LIMIT n) stays fast.",
                                                 base, tok))
            having_span = _clause_span(outer, "HAVING")
            if having_span and not any(outer[k].kind == WORD and outer[k].upper in AGGREGATES
                                       for k in range(*having_span)):
                findings.append(_finding("having-without-aggregate", "info",
                                         "This HAVING condition has no aggregate, so it could be a WHERE condition "
                                         "and filter rows before grouping.", base, outer[having_span[0] - 1]))
    return findings


def lint(sql: str, dialect: str = "sqlite") -> list[dict]:
    findings = []
    for statement in split_statements(sql, dialect):
        findings.extend(lint_statement(statement.text, statement.start, dialect))
    return findings
