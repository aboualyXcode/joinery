"""Explain database errors in plain language, with fixes and suggestions."""

from __future__ import annotations

import difflib
import re

from .tokenizer import IDENT, WORD, significant, tokenize

RESERVED = {"ORDER", "GROUP", "SELECT", "TABLE", "INDEX", "KEY", "VALUES", "FROM", "WHERE", "USER", "LIMIT"}
FUNCTION_HINTS = {
    "NOW": "SQLite uses datetime('now') or CURRENT_TIMESTAMP.",
    "GETDATE": "SQLite uses datetime('now') or CURRENT_TIMESTAMP.",
    "DATE_TRUNC": "In SQLite, truncate with date(d, 'start of month') or strftime('%Y-%m', d).",
    "DATETRUNC": "In SQLite, truncate with date(d, 'start of month') or strftime('%Y-%m', d).",
    "EXTRACT": "In SQLite, use strftime('%Y', d) for the year, '%m' for the month and so on.",
    "YEAR": "In SQLite, use CAST(strftime('%Y', d) AS INTEGER).",
    "MONTH": "In SQLite, use CAST(strftime('%m', d) AS INTEGER).",
    "DATEDIFF": "In SQLite, subtract julianday() values: julianday(b) - julianday(a) gives days.",
    "DATEADD": "In SQLite, use date(d, '+7 days') or datetime(d, '-1 hour').",
    "DATE_ADD": "In SQLite, use date(d, '+7 days') or datetime(d, '-1 hour').",
    "TO_CHAR": "In SQLite, format with strftime() for dates or printf() for numbers.",
    "LEN": "SQLite calls it length().",
    "ISNULL": "SQLite uses ifnull(a, b) or the standard coalesce(a, b).",
    "NVL": "SQLite uses ifnull(a, b) or the standard coalesce(a, b).",
    "ILIKE": "SQLite's LIKE is already case-insensitive for ASCII letters.",
    "GENERATE_SERIES": "This SQLite build has no generate_series(); use a recursive CTE.",
    "REGEXP_LIKE": "SQLite has no built-in regular expressions; use LIKE or GLOB patterns.",
    "MEDIAN": "This SQLite build has no median(); use ROW_NUMBER() or NTILE() in a CTE.",
    "PERCENTILE_CONT": "This SQLite build has no percentiles; rank rows with ROW_NUMBER() and pick the middle.",
    "ARRAY_AGG": "SQLite uses json_group_array() or group_concat().",
    "STRING_SPLIT": "SQLite has no string_split(); use json_each() over a JSON array or a recursive CTE.",
}


def _close(name: str, options: list[str]) -> list[str]:
    lowered = {o.lower(): o for o in options}
    return [lowered[m] for m in difflib.get_close_matches(name.lower(), list(lowered), n=3, cutoff=0.6)]


def _locate(sql: str, needle: str) -> dict | None:
    wanted = needle.strip('"`[]').lower()
    for tok in significant(tokenize(sql)):
        if tok.text.strip('"`[]').lower() == wanted:
            return {"start": tok.start, "end": tok.end}
    return None


def explain_error(error: dict | None, sql: str, tables: dict[str, list[str]],
                  checks: dict[str, str] | None = None) -> dict | None:
    if not error:
        return None
    message = str(error.get("message", ""))
    kind = error.get("type")
    columns = sorted({c for cols in tables.values() for c in cols})

    def out(title: str, detail: str, hint: str = "", suggestions: list[str] | None = None,
            token: str | None = None) -> dict:
        return {"title": title, "detail": detail, "hint": hint, "suggestions": suggestions or [],
                "position": _locate(sql, token) if token else None}

    if kind == "Timeout":
        return out("The query took too long",
                   "Each run has a time limit so one query cannot slow the platform down for everyone.",
                   "Common causes: a join with no join condition (every row paired with every row), a recursive CTE "
                   "with no stopping condition, or a correlated subquery over a large table.")
    if kind == "Blocked":
        return out("Disabled on this engine", message,
                   "Shared engines roll every run back, so commands that would end the transaction or change the "
                   "server are refused.")
    if kind in ("ResourceLimit",) or "out of memory" in message:
        return out("The query used too much memory",
                   "The sandbox caps memory for every run.",
                   "Aggregate or filter earlier, or add LIMIT while you explore.")

    if m := re.search(r"no such table: (?:\w+\.)?(\S+)", message):
        name = m.group(1)
        return out("Unknown table", f"There is no table called {name} in this dataset.",
                   "Check the spelling, or open the schema panel to see the tables.",
                   _close(name, list(tables)), name)
    if m := re.search(r"no such column: (\S+)", message):
        name = m.group(1)
        bare = name.split(".")[-1]
        if re.search(r'"' + re.escape(bare) + r'"', sql):
            return out("Double quotes name a column, not a string",
                       f'In standard SQL, "{bare}" means a column called {bare}. Text values go in single quotes.',
                       f"Write '{bare}' instead of \"{bare}\".", [], bare)
        hint = "Check the spelling and that the column belongs to one of the tables in FROM."
        if "." in name:
            alias = name.split(".")[0]
            hint = f"Check that {alias} is a table or alias in FROM and that it has a column called {bare}."
        return out("Unknown column", f"No table in this query has a column called {name}.", hint,
                   _close(bare, columns), bare)
    if m := re.search(r"ambiguous column name: (\S+)", message):
        name = m.group(1).split(".")[-1]
        owners = sorted(t for t, cols in tables.items() if name in cols)
        return out("Ambiguous column",
                   f"More than one table in FROM has a column called {name}" + (f" ({', '.join(owners)})." if owners else "."),
                   f"Qualify it with a table alias, for example o.{name}.", [], name)
    if m := re.search(r"misuse of window function (\w+)", message):
        return out("Window function in the wrong place",
                   f"{m.group(1)}() is computed after WHERE, GROUP BY and HAVING, so those clauses cannot use it.",
                   "Compute it in a CTE or subquery, then filter the outer query. (DuckDB also offers QUALIFY.)")
    if "misuse of aggregate" in message or "aggregate functions are not allowed" in message:
        return out("Aggregate in the wrong place",
                   "Aggregates such as count() and sum() are computed after the rows are grouped, so WHERE "
                   "(which runs before grouping) cannot use them.",
                   "Filter groups with HAVING, or compute the aggregate in a subquery or CTE.")
    if "GROUP BY clause is required before HAVING" in message:
        return out("HAVING without GROUP BY", "HAVING filters groups, so it needs GROUP BY.",
                   "Add GROUP BY, or use WHERE to filter rows.")
    if m := re.search(r"near \"(.+?)\": syntax error", message):
        token = m.group(1)
        upper = token.upper()
        tips = {
            "FROM": "Is there a trailing comma at the end of the select list?",
            "WHERE": "Clause order is SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY, LIMIT.",
            "GROUP": "Clause order is SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY, LIMIT.",
            "HAVING": "HAVING comes after GROUP BY.",
            "ORDER": "ORDER BY comes after HAVING and before LIMIT.",
            ")": "Check for a trailing comma inside parentheses, or unbalanced parentheses.",
            "QUALIFY": "QUALIFY is DuckDB syntax. In SQLite, compute the window function in a CTE and filter outside.",
            "TOP": "TOP is SQL Server syntax. SQLite puts LIMIT n at the end of the query.",
            "ILIKE": "SQLite has no ILIKE; its LIKE is case-insensitive for ASCII letters.",
        }
        hint = tips.get(upper, "Look just before this word for a missing comma, operator or keyword.")
        words = [t.upper for t in significant(tokenize(sql)) if t.kind == WORD]
        for foreign in ("TOP", "QUALIFY", "ILIKE"):
            if foreign in words and (foreign != "TOP" or "SELECT" in words[: words.index("TOP")][-2:]):
                hint = tips[foreign]
        if upper in RESERVED and upper not in tips:
            hint = f"{token} is a reserved word. If it is a column or table name, put it in double quotes."
        return out(f"Syntax error near {token}", "The parser stopped here because the SQL does not fit the grammar.",
                   hint, [], token)
    if "incomplete input" in message:
        return out("Incomplete statement", "The statement ended before it was complete.",
                   "Look for an unclosed parenthesis or a missing closing quote.")
    if m := re.search(r"unrecognized token: (.+)", message):
        return out("Unrecognized text", f"The parser could not read {m.group(1)}.",
                   "Usually an unclosed quote. Strings use single quotes; identifiers use double quotes.")
    if m := re.search(r"UNIQUE constraint failed: (\S+)", message):
        return out("Duplicate value", f"Another row already has the same {m.group(1)}, which must be unique.",
                   "Use a different value, or upsert with INSERT ... ON CONFLICT (...) DO UPDATE.")
    if m := re.search(r"NOT NULL constraint failed: (\S+)", message):
        return out("Missing required value", f"{m.group(1)} cannot be NULL.",
                   "Provide a value for it in the INSERT or UPDATE, or give the column a DEFAULT.")
    if m := re.search(r"CHECK constraint failed: (\S+)", message):
        rule = (checks or {}).get(m.group(1))
        detail = f"The value breaks the rule {m.group(1)}" + (f": CHECK ({rule})." if rule else ".")
        return out("Value breaks a rule", detail, "Change the value so the condition is true.")
    if "FOREIGN KEY constraint failed" in message:
        return out("Broken reference",
                   "A row would point at a parent row that does not exist, or a parent row still has children.",
                   "Insert the parent first, or delete the children before the parent.")
    if "cannot start a transaction within a transaction" in message:
        return out("Transaction already open", "BEGIN was run while a transaction was already active.",
                   "COMMIT or ROLLBACK the current transaction first.")
    if m := re.search(r"cannot (commit|rollback) - no transaction is active", message):
        return out("No transaction is open", f"There is nothing to {m.group(1)}.", "Start one with BEGIN.")
    if "no such savepoint" in message:
        return out("Unknown savepoint", message, "Create it with SAVEPOINT name before rolling back to it.")
    if "not authorized" in message or "authorization denied" in message:
        return out("Disabled in the sandbox",
                   "ATTACH, extension loading and most PRAGMA statements are disabled so every run stays isolated.",
                   "Read-only PRAGMAs such as table_info, index_list and foreign_key_list still work.")
    if "database or disk is full" in message:
        return out("Storage limit reached", "Each run can only grow the database by a limited amount.",
                   "Insert fewer rows.")
    if "string or blob too big" in message:
        return out("Value too large", "Values are limited to 1 MB in the sandbox.", "Aggregate fewer rows.")
    if m := re.search(r"do not have the same number of result columns", message):
        return out("Mismatched branches", "Every SELECT in a UNION, INTERSECT or EXCEPT must return the same "
                   "number of columns.", "Add or remove columns so the branches line up.")
    if m := re.search(r"sub-select returns (\d+) columns - expected 1", message):
        return out("Subquery returns too many columns",
                   f"A subquery used as a single value must return one column, not {m.group(1)}.",
                   "Select just the column you need inside the subquery.")
    if m := re.search(r"no such function: (\w+)", message):
        name = m.group(1).upper()
        return out("Unknown function", f"{m.group(1)}() does not exist in this engine.",
                   FUNCTION_HINTS.get(name, "Function names differ between databases; see the Reference page."),
                   [], m.group(1))
    if m := re.search(r"wrong number of arguments to function (\w+)", message):
        return out("Wrong number of arguments", f"{m.group(1)}() was called with the wrong number of arguments.",
                   "Check the function's signature in the engine's documentation.", [], m.group(1))
    if m := re.search(r"(table|index|view|trigger) (\S+) already exists", message):
        return out(f"{m.group(1).title()} already exists", f"There is already a {m.group(1)} called {m.group(2)}.",
                   f"Use CREATE {m.group(1).upper()} IF NOT EXISTS, or pick another name.")
    if m := re.search(r"cannot store (\w+) value in (\w+) column (\S+)", message):
        return out("Type mismatch", f"{m.group(3)} is a STRICT {m.group(2)} column and refuses {m.group(1)} values.",
                   "Convert the value with CAST, or fix the data.")
    if "row value misused" in message:
        return out("Row value misused", "A parenthesized list of values was used where one value is expected.",
                   "Remove the extra parentheses, or compare row values of equal size.")
    return None


def identifiers(sql: str) -> list[str]:
    return [t.text for t in significant(tokenize(sql)) if t.kind in (WORD, IDENT)]
