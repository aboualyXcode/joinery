"""Compare a learner's result with the expected result and explain the difference."""

from __future__ import annotations

import json


def _cell(value: object) -> object:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return round(float(value), 6) + 0.0
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value


def normalize(rows: list[list]) -> list[tuple]:
    return [tuple(_cell(v) for v in row) for row in rows]


def _sort_key(row: tuple) -> tuple:
    return tuple((0, "") if v is None else (1, v) if isinstance(v, float) else (2, str(v)) for v in row)


def _show(row: tuple | list) -> str:
    return "(" + ", ".join("NULL" if v is None else repr(v) if isinstance(v, str) else
                           (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)) for v in row) + ")"


def compare(expected: dict, actual: dict, *, order_matters: bool = False, check_names: bool = False) -> dict:
    """``expected`` and ``actual`` hold columns, rows and row_count."""
    exp_cols, act_cols = list(expected["columns"]), list(actual["columns"])
    if len(exp_cols) != len(act_cols):
        return _fail(f"Expected {len(exp_cols)} column(s) but got {len(act_cols)}.",
                     [f"Expected columns: {', '.join(exp_cols)}", f"Your columns: {', '.join(act_cols) or '(none)'}"],
                     "Check the select list: which values does the question ask for?")
    names_differ = [e for e, a in zip(exp_cols, act_cols, strict=True) if e.lower() != a.lower()]
    if check_names and names_differ:
        return _fail("The values may be right, but the column names differ.",
                     [f"Expected columns: {', '.join(exp_cols)}", f"Your columns: {', '.join(act_cols)}"],
                     "Rename columns with AS, for example count(*) AS orders.")
    exp_count, act_count = int(expected["row_count"]), int(actual["row_count"])
    if exp_count != act_count:
        if act_count > exp_count:
            hint = ("Too many rows. Check the WHERE conditions, look for a missing join condition, or for duplicates "
                    "from joining a one-to-many relationship.")
        else:
            hint = ("Too few rows. Check the filters, whether an INNER JOIN drops unmatched rows that a LEFT JOIN "
                    "would keep, and how NULLs are handled.")
        return _fail(f"Expected {exp_count} row(s) but got {act_count}.", [], hint)
    exp_rows, act_rows = normalize(expected["rows"]), normalize(actual["rows"])
    if order_matters:
        if exp_rows == act_rows:
            return _pass(names_differ, exp_cols)
        if sorted(exp_rows, key=_sort_key) == sorted(act_rows, key=_sort_key):
            return _fail("The rows are right but in the wrong order.", [],
                         "Check ORDER BY: the column, the direction (ASC/DESC) and a tie-breaker.")
        pairs = zip(exp_rows, act_rows, strict=False)
    else:
        sorted_exp, sorted_act = sorted(exp_rows, key=_sort_key), sorted(act_rows, key=_sort_key)
        if sorted_exp == sorted_act:
            return _pass(names_differ, exp_cols)
        pairs = zip(sorted_exp, sorted_act, strict=False)
    for number, (exp_row, act_row) in enumerate(pairs, start=1):
        if exp_row != act_row:
            where = "Row" if order_matters else "Sorted row"
            return _fail("Some values differ from the expected result.",
                         [f"{where} {number}: expected {_show(exp_row)}", f"{where} {number}: got {_show(act_row)}"],
                         "Compare the calculation with the question: rounding, filters and which rows are counted.")
    return _fail("Some values differ from the expected result.", [], None)


def _pass(names_differ: list[str], expected_columns: list[str]) -> dict:
    details = [f"Tip: the reference solution names the columns {', '.join(expected_columns)}."] if names_differ else []
    return {"passed": True, "summary": "Correct. Your result matches the expected result.", "details": details,
            "hint": None}


def _fail(summary: str, details: list[str], hint: str | None) -> dict:
    return {"passed": False, "summary": summary, "details": details, "hint": hint}
