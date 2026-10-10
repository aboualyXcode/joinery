"""Break a query into its logical processing stages and run each one.

SQL is written SELECT-first but evaluated FROM-first. The stepper rewrites a
single SELECT into a series of real queries, one per stage of the logical
processing order:

    WITH -> FROM/JOIN -> WHERE -> GROUP BY -> HAVING -> SELECT -> DISTINCT
         -> ORDER BY -> LIMIT/OFFSET

Each stage is executed by the engine, so every intermediate result is real.
Filter stages (WHERE, HAVING, LIMIT) also report which input rows were kept,
which the client draws as highlighted and struck-through rows.

The rewriting is lexical (see tokenizer.py). Queries it cannot decompose
safely are reported as unsupported and simply run whole. Security never
depends on this module: every stage query runs in the same sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tokenizer import IDENT, NUMBER, WORD, Token, significant, tokenize

CLAUSES = ("SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "WINDOW", "ORDER BY", "LIMIT")
SET_OPERATORS = ("UNION", "INTERSECT", "EXCEPT")
JOIN_WORDS = {"JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "NATURAL", "OUTER"}
NOT_ALIASES = {"ON", "USING", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "NATURAL", "OUTER", "WHERE",
               "GROUP", "HAVING", "ORDER", "LIMIT", "WINDOW", "UNION", "INTERSECT", "EXCEPT", "INDEXED", "NOT",
               "AS", "END", "NULL", "TRUE", "FALSE", "AND", "OR", "THEN", "ELSE", "DESC", "ASC"}
KEPT = "__kept"


@dataclass
class Stage:
    id: str
    clause: str
    title: str
    queries: list[str]
    count_query: str | None = None
    kind: str = "rows"  # rows | filter | limit
    detail: dict = field(default_factory=dict)


@dataclass
class StepPlan:
    supported: bool
    reason: str | None = None
    statement: str = "select"
    stages: list[Stage] = field(default_factory=list)
    written_order: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- lexical helpers


def _depths(tokens: list[Token]) -> list[int]:
    """Parenthesis depth *before* each token."""
    depth, out = 0, []
    for tok in tokens:
        out.append(depth)
        if tok.is_op("("):
            depth += 1
        elif tok.is_op(")"):
            depth = max(0, depth - 1)
    return out


def _text(sql: str, tokens: list[Token], start: int, end: int) -> str:
    """Source text spanning tokens[start:end]."""
    if start >= end:
        return ""
    return sql[tokens[start].start:tokens[end - 1].end].strip()


def _split_top(sql: str, tokens: list[Token], start: int, end: int) -> list[str]:
    """Split tokens[start:end] at top-level commas."""
    depths = _depths(tokens)
    base = depths[start] if start < len(tokens) else 0
    parts, begin = [], start
    for i in range(start, end):
        if tokens[i].is_op(",") and depths[i] == base:
            parts.append(_text(sql, tokens, begin, i))
            begin = i + 1
    parts.append(_text(sql, tokens, begin, end))
    return [p for p in parts if p]


def _short(text: str, limit: int = 80) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "\u2026"


def quote_ident(name: str, dialect: str) -> str:
    if dialect == "mysql":
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.replace('"', '""') + '"'


# --------------------------------------------------------------------------- parsing


@dataclass
class SelectParts:
    with_text: str
    ctes: list[str]
    distinct: bool
    select_list: str
    clauses: dict[str, str]
    written: list[str]


def _parse_with(sql: str, tokens: list[Token]) -> tuple[str, list[str], int] | None:
    """Return (with_text, cte_names, index of the main query) for a WITH prefix."""
    depths = _depths(tokens)
    i = 1
    if i < len(tokens) and tokens[i].is_word("RECURSIVE"):
        i += 1
    names = []
    while i < len(tokens):
        if tokens[i].kind not in (WORD, IDENT):
            return None
        names.append(tokens[i].text.strip('"`[]'))
        i += 1
        if i < len(tokens) and tokens[i].is_op("("):  # column list
            level = depths[i]
            i += 1
            while i < len(tokens) and not (tokens[i].is_op(")") and depths[i] == level + 1):
                i += 1
            i += 1
        if i >= len(tokens) or not tokens[i].is_word("AS"):
            return None
        i += 1
        while i < len(tokens) and tokens[i].is_word("NOT", "MATERIALIZED"):
            i += 1
        if i >= len(tokens) or not tokens[i].is_op("("):
            return None
        level = depths[i]
        i += 1
        while i < len(tokens) and not (tokens[i].is_op(")") and depths[i] == level + 1):
            i += 1
        i += 1
        if i < len(tokens) and tokens[i].is_op(","):
            i += 1
            continue
        break
    if i >= len(tokens):
        return None
    return sql[tokens[0].start:tokens[i].start], names, i


def _clause_positions(tokens: list[Token], start: int) -> list[tuple[str, int, int]]:
    """(clause, keyword index, body index) for top-level clauses from tokens[start]."""
    depths = _depths(tokens)
    base = depths[start]
    found = []
    i = start
    while i < len(tokens):
        tok = tokens[i]
        if depths[i] == base and tok.kind == WORD:
            word = tok.upper
            nxt = tokens[i + 1].upper if i + 1 < len(tokens) else ""
            if word in ("GROUP", "ORDER") and nxt == "BY":
                found.append((f"{word} BY", i, i + 2))
                i += 2
                continue
            if word in ("SELECT", "FROM", "WHERE", "HAVING", "WINDOW", "LIMIT"):
                found.append((word, i, i + 1))
        i += 1
    return found


def _set_operator_positions(tokens: list[Token], start: int) -> list[int]:
    depths = _depths(tokens)
    base = depths[start]
    return [i for i in range(start, len(tokens)) if depths[i] == base and tokens[i].is_word(*SET_OPERATORS)]


def parse_select(sql: str, tokens: list[Token], start: int, with_text: str, ctes: list[str]) -> SelectParts | str:
    positions = _clause_positions(tokens, start)
    if not positions or positions[0][0] != "SELECT" or positions[0][1] != start:
        return "The stepper decomposes SELECT queries."
    seen: list[str] = []
    for clause, _kw, _body in positions:
        if clause in seen and clause != "SELECT":
            return f"This query has more than one top-level {clause} clause."
        if clause == "SELECT" and seen:
            return "Nested SELECT outside parentheses is not supported."
        seen.append(clause)
    order = [CLAUSES.index(c) for c in seen]
    if order != sorted(order):
        return "The clauses are not in the standard order."
    bodies: dict[str, str] = {}
    for n, (clause, _kw, body) in enumerate(positions):
        end = positions[n + 1][1] if n + 1 < len(positions) else len(tokens)
        bodies[clause] = _text(sql, tokens, body, end)
    select_body = bodies.pop("SELECT")
    distinct = False
    first = significant(tokenize(select_body))
    if first and first[0].is_word("DISTINCT", "ALL"):
        distinct = first[0].is_word("DISTINCT")
        select_body = select_body[first[0].end:].strip()
    return SelectParts(with_text, ctes, distinct, select_body, bodies, seen)


# --------------------------------------------------------------------------- select-list and FROM analysis


def _select_items(select_list: str) -> list[tuple[str, str | None]]:
    """(expression, alias) for each select item."""
    toks = significant(tokenize(select_list))
    items = []
    for part in _split_top(select_list, toks, 0, len(toks)):
        ptoks = significant(tokenize(part))
        alias = None
        expr = part
        if len(ptoks) >= 3 and ptoks[-2].is_word("AS") and ptoks[-1].kind in (WORD, IDENT):
            alias = ptoks[-1].text.strip('"`[]')
            expr = part[: ptoks[-2].start].strip()
        elif (len(ptoks) >= 2 and ptoks[-1].kind in (WORD, IDENT) and ptoks[-1].upper not in NOT_ALIASES
              and not ptoks[-2].is_op(".", "+", "-", "*", "/", "||", "=", "<", ">", ",", "(")
              and not ptoks[-2].is_word("AND", "OR", "NOT", "IS", "IN", "LIKE", "THEN", "ELSE", "WHEN", "CASE",
                                         "DISTINCT", "BETWEEN")):
            alias = ptoks[-1].text.strip('"`[]')
            expr = part[: ptoks[-1].start].strip()
        items.append((expr, alias))
    return items


def _resolve_group_keys(group_by: str, items: list[tuple[str, str | None]]) -> list[str]:
    toks = significant(tokenize(group_by))
    keys = []
    aliases = {alias.lower(): expr for expr, alias in items if alias}
    for key in _split_top(group_by, toks, 0, len(toks)):
        ktoks = significant(tokenize(key))
        if len(ktoks) == 1 and ktoks[0].kind == NUMBER and ktoks[0].text.isdigit():
            position = int(ktoks[0].text)
            keys.append(items[position - 1][0] if 0 < position <= len(items) else key)
        elif len(ktoks) == 1 and ktoks[0].kind in (WORD, IDENT) and ktoks[0].text.strip('"`[]').lower() in aliases:
            keys.append(aliases[ktoks[0].text.strip('"`[]').lower()])
        else:
            keys.append(key)
    return keys


def _from_sources(from_text: str) -> list[tuple[str | None, str]]:
    """(table name or None, alias) for each FROM item, or [] when unclear."""
    toks = significant(tokenize(from_text))
    depths = _depths(toks)
    sources: list[tuple[str | None, str]] = []
    i = 0
    expecting = True
    while i < len(toks):
        tok = toks[i]
        if depths[i] != 0:
            i += 1
            continue
        if tok.is_op(","):
            expecting = True
            i += 1
            continue
        if tok.is_word(*JOIN_WORDS):
            if tok.is_word("JOIN"):
                expecting = True
            i += 1
            continue
        if expecting:
            expecting = False
            if tok.is_op("("):
                j = i + 1
                while j < len(toks) and not (toks[j].is_op(")") and depths[j] == 0):
                    j += 1
                k = j + 1
                if k < len(toks) and toks[k].is_word("AS"):
                    k += 1
                if k < len(toks) and toks[k].kind in (WORD, IDENT) and toks[k].upper not in NOT_ALIASES:
                    sources.append((None, toks[k].text.strip('"`[]')))
                    i = k + 1
                    continue
                return []
            if tok.kind in (WORD, IDENT):
                name = tok.text.strip('"`[]')
                k = i + 1
                if k + 1 < len(toks) and toks[k].is_op(".") and toks[k + 1].kind in (WORD, IDENT):
                    name = toks[k + 1].text.strip('"`[]')
                    k += 2
                if k < len(toks) and toks[k].is_op("("):  # table-valued function
                    return []
                if k < len(toks) and toks[k].is_word("AS"):
                    k += 1
                alias = name
                if k < len(toks) and toks[k].kind in (WORD, IDENT) and toks[k].upper not in NOT_ALIASES:
                    alias = toks[k].text.strip('"`[]')
                sources.append((name, alias))
                i = k
                continue
            return []
        i += 1
    return sources


def _from_columns(from_text: str, schema: dict[str, list[str]], dialect: str) -> str:
    sources = _from_sources(from_text)
    if len(sources) < 2:
        return "*"
    parts = []
    for table, alias in sources:
        columns = schema.get(table.lower()) if table else None
        qualified = quote_ident(alias, dialect)
        if columns is None:
            parts.append(f"{qualified}.*")
        else:
            parts.extend(f"{qualified}.{quote_ident(c, dialect)} AS {quote_ident(alias + '.' + c, dialect)}"
                         for c in columns)
    return ", ".join(parts)


# --------------------------------------------------------------------------- planning


def _limit_bounds(limit_text: str) -> tuple[int, int] | None:
    """(offset, count) when LIMIT and OFFSET are integer literals."""
    toks = significant(tokenize(limit_text))
    words = [t.text.upper() if t.kind == WORD else t.text for t in toks]
    try:
        if len(words) == 1:
            return 0, int(words[0])
        if len(words) == 3 and words[1] == "OFFSET":
            return int(words[2]), int(words[0])
        if len(words) == 3 and words[1] == ",":
            return int(words[0]), int(words[2])
    except ValueError:
        return None
    return None


def _has_aggregate(select_list: str) -> bool:
    names = {"COUNT", "SUM", "AVG", "MIN", "MAX", "GROUP_CONCAT", "STRING_AGG", "TOTAL", "JSON_GROUP_ARRAY",
             "JSON_GROUP_OBJECT", "ARRAY_AGG", "BOOL_AND", "BOOL_OR", "STDDEV", "VARIANCE", "MEDIAN"}
    toks = significant(tokenize(select_list))
    for i, tok in enumerate(toks[:-1]):
        if tok.kind == WORD and tok.upper in names and toks[i + 1].is_op("("):
            # an aggregate followed by OVER is a window function, not grouping
            depth, j = 0, i + 1
            while j < len(toks):
                if toks[j].is_op("("):
                    depth += 1
                elif toks[j].is_op(")"):
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if not (j + 1 < len(toks) and toks[j + 1].is_word("OVER", "FILTER")):
                return True
            if j + 1 < len(toks) and toks[j + 1].is_word("FILTER"):
                return True
    return False


def _plan_select(parts: SelectParts, schema: dict[str, list[str]], dialect: str) -> list[Stage]:
    w = parts.with_text
    c = parts.clauses
    q = lambda name: quote_ident(name, dialect)  # noqa: E731
    stages: list[Stage] = []
    for name in parts.ctes:
        stages.append(Stage(f"cte-{name}", "WITH", f"CTE {name}", [f"{w}SELECT * FROM {q(name)}"],
                            detail={"name": name}))
    if "FROM" not in c:
        stages.append(Stage("select", "SELECT", "SELECT", [f"{w}SELECT {parts.select_list}"],
                            detail={"no_from": True}))
        return stages
    src = f"FROM {c['FROM']}"
    cols = _from_columns(c["FROM"], schema, dialect)
    sources = _from_sources(c["FROM"])
    stages.append(Stage("from", "FROM", "FROM / JOIN", [f"{w}SELECT {cols} {src}"],
                        detail={"sources": [s[0] or s[1] for s in sources], "joins": len(sources) > 1}))
    where = f" WHERE {c['WHERE']}" if "WHERE" in c else ""
    if where:
        stages.append(Stage(
            "where", "WHERE", "WHERE",
            [f"{w}SELECT CASE WHEN ({c['WHERE']}) THEN 1 ELSE 0 END AS {q(KEPT)}, {cols} {src}"],
            count_query=f"{w}SELECT {cols} {src}{where}", kind="filter", detail={"condition": c["WHERE"]}))
    items = _select_items(parts.select_list)
    grouped = "GROUP BY" in c or _has_aggregate(parts.select_list) or "HAVING" in c
    group_sql = ""
    if grouped:
        keys = _resolve_group_keys(c["GROUP BY"], items) if "GROUP BY" in c else []
        group_sql = f" GROUP BY {', '.join(keys)}" if keys else ""
        labels = [f"{k} AS {q(_short(k, 48))}" for k in keys]
        count = f"COUNT(*) AS {q('rows in group')}"
        key_cols = ", ".join(labels + [count])
        stages.append(Stage("group", "GROUP BY", "GROUP BY" if keys else "Aggregate",
                            [f"{w}SELECT {key_cols} {src}{where}{group_sql}"],
                            detail={"keys": keys}))
        if "HAVING" in c:
            having = c["HAVING"]
            stages.append(Stage(
                "having", "HAVING", "HAVING",
                [f"{w}SELECT CASE WHEN ({having}) THEN 1 ELSE 0 END AS {q(KEPT)}, {key_cols} {src}{where}{group_sql}",
                 f"{w}SELECT {parts.select_list} {src}{where}{group_sql} HAVING {having}"],
                count_query=f"{w}SELECT {key_cols} {src}{where}{group_sql} HAVING {having}",
                kind="filter", detail={"condition": having}))
    having_sql = f" HAVING {c['HAVING']}" if "HAVING" in c else ""
    window_sql = f" WINDOW {c['WINDOW']}" if "WINDOW" in c else ""
    body = f"{src}{where}{group_sql}{having_sql}{window_sql}"
    window = " OVER" in parts.select_list.upper() or "OVER(" in parts.select_list.upper()
    stages.append(Stage("select", "SELECT", "SELECT", [f"{w}SELECT {parts.select_list} {body}"],
                        detail={"window": window, "grouped": grouped,
                                "items": [alias or _short(expr, 40) for expr, alias in items]}))
    if parts.distinct:
        stages.append(Stage("distinct", "DISTINCT", "DISTINCT", [f"{w}SELECT DISTINCT {parts.select_list} {body}"]))
    distinct = "DISTINCT " if parts.distinct else ""
    ordered = f"{w}SELECT {distinct}{parts.select_list} {body}"
    if "ORDER BY" in c:
        ordered += f" ORDER BY {c['ORDER BY']}"
        stages.append(Stage("order", "ORDER BY", "ORDER BY", [ordered], detail={"keys": c["ORDER BY"]}))
    if "LIMIT" in c:
        bounds = _limit_bounds(c["LIMIT"])
        stages.append(Stage("limit", "LIMIT", "LIMIT / OFFSET", [f"{ordered} LIMIT {c['LIMIT']}"], kind="limit",
                            detail={"limit": c["LIMIT"], "bounds": list(bounds) if bounds else None,
                                    "ordered": "ORDER BY" in c}))
    return stages


def _plan_dml(sql: str, tokens: list[Token]) -> StepPlan:
    depths = _depths(tokens)
    first = tokens[0].upper
    i = 1
    if first == "DELETE":
        if i < len(tokens) and tokens[i].is_word("FROM"):
            i += 1
    elif i + 1 < len(tokens) and tokens[i].is_word("OR"):
        i += 2
    if i >= len(tokens) or tokens[i].kind not in (WORD, IDENT):
        return StepPlan(False, "Could not find the target table.", first.lower())
    table = tokens[i].text
    where_index = next((k for k in range(i, len(tokens)) if depths[k] == 0 and tokens[k].is_word("WHERE")), None)
    stop = next((k for k in range(i, len(tokens)) if depths[k] == 0
                 and tokens[k].is_word("RETURNING", "ORDER", "LIMIT", "FROM") and k > i + 1), len(tokens))
    if first == "UPDATE" and any(depths[k] == 0 and tokens[k].is_word("FROM") for k in range(i + 1, len(tokens))):
        return StepPlan(False, "UPDATE ... FROM is not stepped; run it to see the result.", "update")
    condition = _text(sql, tokens, where_index + 1, stop) if where_index is not None else None
    where = f" WHERE {condition}" if condition else ""
    statement = sql.strip().rstrip(";")
    stages = [Stage("matched", "WHERE", "Rows the statement will touch", [f"SELECT * FROM {table}{where}"],
                    detail={"table": table, "condition": condition})]
    if first == "UPDATE":
        after = (f"CREATE TEMP TABLE joinery_matched AS SELECT rowid AS rid FROM {table}{where};\n{statement};\n"
                 f"SELECT t.* FROM {table} AS t JOIN joinery_matched AS m ON t.rowid = m.rid")
        stages.append(Stage("after", "UPDATE", "The same rows after the UPDATE", [after], detail={"table": table}))
    else:
        after = f"{statement};\nSELECT count(*) AS rows_left FROM {table}"
        stages.append(Stage("after", "DELETE", "Rows left in the table", [after], detail={"table": table}))
    return StepPlan(True, None, first.lower(), stages, [first, "WHERE"] if condition else [first])


def plan_steps(sql: str, schema: dict[str, list[str]], dialect: str = "sqlite") -> StepPlan:
    """Plan the stages for one statement. ``schema`` maps table name to column names."""
    tokens = significant(tokenize(sql, dialect))
    while tokens and tokens[-1].is_op(";"):
        tokens.pop()
    if not tokens:
        return StepPlan(False, "There is no query to step through.")
    if any(t.is_op(";") for t in tokens):
        return StepPlan(False, "Step through one statement at a time.")
    if any(not t.terminated for t in tokens):
        return StepPlan(False, "The query has an unterminated string or comment.")
    text = sql[tokens[0].start:tokens[-1].end]
    tokens = significant(tokenize(text, dialect))
    first = tokens[0].upper
    if first in ("UPDATE", "DELETE"):
        if dialect != "sqlite":
            return StepPlan(False, "Stepping through UPDATE and DELETE is available on SQLite.", first.lower())
        return _plan_dml(text, tokens)
    with_text, ctes, start = "", [], 0
    if first == "WITH":
        parsed = _parse_with(text, tokens)
        if parsed is None:
            return StepPlan(False, "Could not read the WITH clause.")
        with_text, ctes, start = parsed
    if not tokens[start].is_word("SELECT"):
        return StepPlan(False, "The stepper decomposes SELECT queries. Run other statements directly.",
                        first.lower())
    set_ops = _set_operator_positions(tokens, start)
    if set_ops:
        return _plan_compound(text, tokens, start, set_ops, with_text, ctes, dialect)
    parts = parse_select(text, tokens, start, with_text, ctes)
    if isinstance(parts, str):
        return StepPlan(False, parts)
    plan = StepPlan(True, None, "select", _plan_select(parts, schema, dialect), parts.written)
    if ctes:
        plan.written_order = ["WITH"] + plan.written_order
    return plan


def _plan_compound(text: str, tokens: list[Token], start: int, ops: list[int], with_text: str,
                   ctes: list[str], dialect: str) -> StepPlan:
    q = lambda name: quote_ident(name, dialect)  # noqa: E731
    stages = [Stage(f"cte-{n}", "WITH", f"CTE {n}", [f"{with_text}SELECT * FROM {q(n)}"], detail={"name": n})
              for n in ctes]
    bounds = [start] + ops + [len(tokens)]
    labels = []
    for n in range(len(bounds) - 1):
        begin = bounds[n] if n == 0 else bounds[n] + 1
        if n > 0 and begin < len(tokens) and tokens[begin].is_word("ALL", "DISTINCT"):
            begin += 1
        end = bounds[n + 1]
        branch = _text(text, tokens, begin, end)
        if n == len(bounds) - 2:  # trailing ORDER BY / LIMIT belong to the whole compound
            positions = [p for p in _clause_positions(tokens, begin) if p[0] in ("ORDER BY", "LIMIT")]
            if positions:
                branch = _text(text, tokens, begin, positions[0][1])
        stages.append(Stage(f"branch-{n + 1}", "SELECT", f"Branch {n + 1}", [f"{with_text}{branch}"]))
    for op in ops:
        word = tokens[op].upper
        if op + 1 < len(tokens) and tokens[op + 1].is_word("ALL"):
            word += " ALL"
        labels.append(word)
    stages.append(Stage("combine", " / ".join(dict.fromkeys(labels)), "Combine the branches", [text],
                        detail={"operators": labels}))
    return StepPlan(True, None, "compound", stages, ["SELECT"] + labels)


# --------------------------------------------------------------------------- execution and assembly


def batches_for(plan: StepPlan) -> list[dict]:
    batches = []
    for stage in plan.stages:
        for n, query in enumerate(stage.queries):
            batches.append({"id": f"{stage.id}:{n}", "sql": query, "split": stage.id == "after",
                            "stop_on_error": True})
        if stage.count_query:
            batches.append({"id": f"{stage.id}:count", "sql": stage.count_query, "split": False})
    return batches


def _describe(stage: Stage, rows_in: int | None, rows_out: int, kept: int | None) -> str:
    d = stage.detail
    if stage.clause == "WITH":
        return f"Evaluate the common table expression {d['name']}: {rows_out} rows."
    if stage.id == "from":
        if d.get("joins"):
            return (f"Combine {', '.join(d['sources'])} using the join conditions: {rows_out} rows. "
                    "Nothing else has happened yet: no filtering, grouping or column selection.")
        return f"Read every row of {', '.join(d['sources']) or 'the source'}: {rows_out} rows."
    if stage.id == "where":
        return (f"Keep only rows where {_short(d['condition'])} is true: {kept} of {rows_in} rows survive. "
                "Rows where it is false or NULL are removed.")
    if stage.id == "group":
        if d["keys"]:
            return f"Collapse the {rows_in} rows into {rows_out} groups, one per distinct {', '.join(_short(k, 40) for k in d['keys'])}."
        return f"No GROUP BY: aggregates treat all {rows_in} rows as one group."
    if stage.id == "having":
        return f"Keep only groups where {_short(d['condition'])} is true: {kept} of {rows_in} groups survive."
    if stage.id == "select":
        if d.get("no_from"):
            return "No FROM clause, so the select list is evaluated once."
        text = f"Evaluate the select list ({', '.join(d['items'][:6])}) for each {'group' if d['grouped'] else 'row'}."
        if d.get("window"):
            text += " Window functions (OVER) are computed here, after WHERE, GROUP BY and HAVING."
        return text
    if stage.id == "distinct":
        return f"Remove duplicate rows: {rows_in} become {rows_out}."
    if stage.id == "order":
        return f"Sort by {_short(d['keys'])}. Without ORDER BY, row order is not guaranteed."
    if stage.id == "limit":
        bounds = d.get("bounds")
        if bounds:
            offset, count = bounds
            skip = f" after skipping {offset}" if offset else ""
            text = f"Keep at most {count} rows{skip}."
        else:
            text = f"Apply LIMIT {_short(d['limit'])}."
        if not d.get("ordered"):
            text += " There is no ORDER BY, so which rows survive is arbitrary."
        return text
    if stage.id.startswith("branch-"):
        return f"Run {stage.title.lower()} on its own: {rows_out} rows."
    if stage.id == "combine":
        ops = ", ".join(d["operators"])
        return (f"Combine the branches with {ops}: {rows_out} rows. UNION, INTERSECT and EXCEPT remove duplicates; "
                "the ALL variants keep them.")
    if stage.id == "matched":
        where = f"where {_short(d['condition'])}" if d.get("condition") else "(no WHERE: every row)"
        return f"These {rows_out} rows of {d['table']} match {where}."
    if stage.id == "after":
        return "The statement has run against your private copy; nothing is saved."
    return ""


def assemble(plan: StepPlan, run_output: dict) -> dict:
    """Turn the engine output for ``batches_for(plan)`` into the API response."""
    if not plan.supported:
        return {"supported": False, "reason": plan.reason, "statement": plan.statement, "stages": []}
    if not run_output.get("ok"):
        return {"supported": True, "reason": None, "statement": plan.statement, "stages": [],
                "error": run_output.get("error")}
    results = {b["id"]: b["statements"] for b in run_output["batches"]}
    stages, previous_count = [], None
    for stage in plan.stages:
        chosen, error = None, None
        for n, query in enumerate(stage.queries):
            statements = results.get(f"{stage.id}:{n}", [])
            last = statements[-1] if statements else None
            if last and not last.get("error"):
                chosen = (query, last)
                break
            if last and error is None:
                error = last.get("error")
        if chosen is None:
            stages.append({"id": stage.id, "clause": stage.clause, "title": stage.title, "sql": stage.queries[0],
                           "error": error or {"type": "StepError", "message": "This stage did not run."}})
            break
        query, res = chosen
        columns, rows = list(res["columns"]), [list(r) for r in res["rows"]]
        kept_flags, kept_count, input_count = None, None, None
        if stage.kind == "filter" and columns and columns[0] == KEPT:
            kept_flags = [bool(r[0]) for r in rows]
            columns, rows = columns[1:], [r[1:] for r in rows]
            input_count = res["row_count"]
            count = results.get(f"{stage.id}:count", [])
            kept_count = count[-1]["row_count"] if count and not count[-1].get("error") else sum(kept_flags)
        elif stage.kind == "filter":
            input_count = previous_count
            kept_count = res["row_count"]
        if stage.kind == "limit" and stages and stage.detail.get("bounds"):
            prior = stages[-1]
            offset, count = stage.detail["bounds"]
            stages.append({**_stage_json(stage, query, prior["columns"], prior["rows"], prior["row_count"], res),
                           "kept": [offset <= i < offset + count for i in range(len(prior["rows"]))],
                           "kept_count": res["row_count"], "input_count": prior["row_count"],
                           "description": _describe(stage, prior["row_count"], res["row_count"], res["row_count"])})
            previous_count = res["row_count"]
            continue
        rows_in = input_count if input_count is not None else previous_count
        entry = _stage_json(stage, query, columns, rows, res["row_count"], res)
        entry.update(kept=kept_flags, kept_count=kept_count, input_count=rows_in,
                     description=_describe(stage, rows_in, kept_count if kept_count is not None else res["row_count"],
                                           kept_count))
        if stage.kind == "filter" and kept_flags is not None:
            entry["row_count"] = input_count
        stages.append(entry)
        previous_count = kept_count if kept_count is not None else res["row_count"]
    return {"supported": True, "reason": None, "statement": plan.statement, "stages": stages,
            "written_order": plan.written_order, "logical_order": [s["clause"] for s in stages]}


def _stage_json(stage: Stage, query: str, columns: list, rows: list, row_count: int, res: dict) -> dict:
    return {"id": stage.id, "clause": stage.clause, "title": stage.title, "sql": query, "columns": columns,
            "rows": rows, "row_count": row_count, "truncated": len(rows) < row_count,
            "elapsed_ms": res.get("elapsed_ms"), "vm_steps": res.get("vm_steps"), "error": None}
