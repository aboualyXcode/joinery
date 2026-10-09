"""Turn raw EXPLAIN output into a tree the client can draw, plus advice.

SQLite reports a logical plan (EXPLAIN QUERY PLAN) and the bytecode program
its virtual machine runs (EXPLAIN). PostgreSQL reports a JSON tree. Both are
normalized into the same node shape:

    {"id", "label", "kind", "table", "index", "severity", "note", "metrics", "children"}
"""

from __future__ import annotations

import re

from .stepper import _clause_positions, _from_sources, _text
from .tokenizer import significant, tokenize

_TABLE_AFTER = re.compile(r"^(?:SCAN|SEARCH|BLOOM FILTER ON|RIGHT-JOIN)\s+(\S+)")
_INDEX = re.compile(r"USING (?:AUTOMATIC )?(?:PARTIAL )?(?:COVERING )?INDEX (\S+)")
_PARENS = re.compile(r"\(([^()]*)\)\s*$")

NOTES = {
    "scan": "Reads every row of the table.",
    "index-scan": "Walks an index in order instead of the table, which can avoid a sort.",
    "search": "Uses an index or the primary key to jump straight to matching rows.",
    "auto-index": "SQLite built a temporary index for this query because none existed.",
    "sort": "Sorts rows with a temporary B-tree: extra work an index in the right order could avoid.",
    "correlated": "Runs once for every row of the outer query.",
    "subquery": "Runs a subquery once and reuses its result.",
    "materialize": "Computes a subquery or CTE once and stores the rows in a temporary table.",
    "coroutine": "Produces rows on demand for the outer query, without storing them all.",
    "compound": "Combines the results of several SELECTs.",
    "constant": "Produces a single row without reading any table.",
    "bloom": "A Bloom filter quickly skips rows that cannot match the join.",
    "other": "",
}

OPCODES = {
    "Init": "Start the program; jump to the setup code at P2.",
    "Goto": "Jump to address P2.",
    "Halt": "Stop the program.",
    "Transaction": "Begin a read (P2=0) or write (P2=1) transaction.",
    "OpenRead": "Open a read cursor on a table or index B-tree.",
    "OpenWrite": "Open a write cursor on a table or index B-tree.",
    "OpenEphemeral": "Create a temporary B-tree, for example for DISTINCT or a subquery.",
    "OpenAutoindex": "Create a temporary automatic index.",
    "OpenPseudo": "Open a cursor over a single row held in a register.",
    "Rewind": "Move the cursor to the first entry; jump to P2 if the table is empty.",
    "Next": "Advance the cursor and jump back to P2 if there is another row: the loop.",
    "Prev": "Step the cursor backwards and loop.",
    "Column": "Read column P2 of the current row into register P3.",
    "Rowid": "Read the rowid of the current row.",
    "ResultRow": "Emit one result row to the caller.",
    "SeekGE": "Position an index cursor at the first key >= the search key.",
    "SeekGT": "Position an index cursor at the first key > the search key.",
    "SeekLE": "Position an index cursor at the last key <= the search key.",
    "SeekLT": "Position an index cursor at the last key < the search key.",
    "SeekRowid": "Jump directly to the row with the given rowid.",
    "DeferredSeek": "Remember to seek the table row only if a column outside the index is needed.",
    "IdxGT": "Stop the index range when the key is greater than the bound.",
    "IdxGE": "Stop the index range when the key is greater than or equal to the bound.",
    "IdxLT": "Stop the index range when the key is less than the bound.",
    "IdxLE": "Stop the index range when the key is less than or equal to the bound.",
    "IdxRowid": "Read the rowid stored in an index entry.",
    "NotFound": "Jump if the key is not in the index.",
    "Found": "Jump if the key is in the index.",
    "Eq": "Compare two registers and jump if equal.",
    "Ne": "Compare two registers and jump if not equal.",
    "Lt": "Compare and jump if less than.",
    "Le": "Compare and jump if less than or equal.",
    "Gt": "Compare and jump if greater than.",
    "Ge": "Compare and jump if greater than or equal.",
    "If": "Jump if the register is true.",
    "IfNot": "Jump if the register is false or NULL.",
    "IsNull": "Jump if the register is NULL.",
    "NotNull": "Jump if the register is not NULL.",
    "Integer": "Load an integer constant into a register.",
    "String8": "Load a string constant into a register.",
    "Real": "Load a floating-point constant into a register.",
    "Null": "Set registers to NULL.",
    "Copy": "Copy registers.",
    "SCopy": "Make a shallow copy of a register.",
    "Add": "Add two registers.",
    "Subtract": "Subtract two registers.",
    "Multiply": "Multiply two registers.",
    "Divide": "Divide two registers.",
    "Function": "Call a scalar SQL function.",
    "AggStep": "Feed one row into an aggregate such as count() or sum().",
    "AggFinal": "Finish an aggregate and produce its value.",
    "AggValue": "Read the current value of a window aggregate.",
    "SorterOpen": "Open a sorter for ORDER BY or GROUP BY.",
    "SorterInsert": "Add a row to the sorter.",
    "SorterSort": "Sort the collected rows; jump to P2 if there are none.",
    "SorterData": "Read the current row out of the sorter.",
    "SorterNext": "Advance through the sorted rows: the output loop.",
    "MakeRecord": "Pack registers into a record for storage or sorting.",
    "Insert": "Write a row into a table.",
    "Delete": "Delete the current row.",
    "IdxInsert": "Write an entry into an index.",
    "IdxDelete": "Delete an entry from an index.",
    "NewRowid": "Choose a rowid for a new row.",
    "Once": "Run the following code only the first time through.",
    "InitCoroutine": "Set up a co-routine that yields rows to the outer query.",
    "Yield": "Switch between a co-routine and its caller.",
    "EndCoroutine": "Finish a co-routine.",
    "Gosub": "Call a subroutine.",
    "Return": "Return from a subroutine.",
    "Affinity": "Apply column type affinity to registers.",
    "Cast": "Convert a value to another type.",
    "Concat": "Concatenate two strings.",
    "Compare": "Compare two runs of registers.",
    "Jump": "Jump based on the result of the last Compare.",
    "Sequence": "Get the next value of a sequence counter.",
    "Variable": "Load a bound parameter.",
    "FkCounter": "Track outstanding foreign key violations.",
    "FkIfZero": "Jump if there are no foreign key violations.",
    "Noop": "Do nothing (often a label for a jump).",
    "Explain": "A comment marking the start of a plan step.",
    "IfPos": "Jump if the register is positive, then decrement it (used for LIMIT and OFFSET).",
    "DecrJumpZero": "Decrement the register and jump when it reaches zero (LIMIT).",
}


def _classify(detail: str) -> str:
    text = detail.upper()
    if text.startswith("SCAN CONSTANT ROW"):
        return "constant"
    if "AUTOMATIC" in text:
        return "auto-index"
    if text.startswith("SEARCH"):
        return "search"
    if text.startswith("SCAN"):
        return "index-scan" if " USING " in text and "INDEX" in text else "scan"
    if text.startswith("USE TEMP B-TREE"):
        return "sort"
    if text.startswith("CORRELATED"):
        return "correlated"
    if "SUBQUERY" in text:
        return "subquery"
    if text.startswith("MATERIALIZE"):
        return "materialize"
    if text.startswith("CO-ROUTINE"):
        return "coroutine"
    if text.startswith(("COMPOUND", "UNION", "EXCEPT", "INTERSECT", "LEFT-MOST")):
        return "compound"
    if text.startswith("BLOOM FILTER"):
        return "bloom"
    return "other"


def aliases_for(sql: str) -> dict[str, str]:
    """Map the aliases in a statement's top-level FROM clause to table names."""
    tokens = significant(tokenize(sql))
    start = next((i for i, t in enumerate(tokens) if t.is_word("SELECT")), None)
    if start is None:
        return {}
    positions = _clause_positions(tokens, start)
    for n, (clause, _kw, body) in enumerate(positions):
        if clause == "FROM":
            end = positions[n + 1][1] if n + 1 < len(positions) else len(tokens)
            return {alias: table for table, alias in _from_sources(_text(sql, tokens, body, end)) if table}
    return {}


def sqlite_tree(rows: list[list], table_rows: dict[str, int],
                aliases: dict[str, str] | None = None) -> tuple[list[dict], list[dict]]:
    """Build the plan tree from EXPLAIN QUERY PLAN rows and derive advice.

    SQLite names plan nodes by alias when the query uses one, so ``aliases``
    maps them back to table names.
    """
    aliases = aliases or {}
    nodes: dict[int, dict] = {}
    roots: list[dict] = []
    for node_id, parent, _unused, detail in rows:
        kind = _classify(str(detail))
        table_match = _TABLE_AFTER.match(str(detail))
        index_match = _INDEX.search(str(detail))
        table = table_match.group(1) if table_match else None
        table = aliases.get(table, table) if table else None
        node = {
            "id": int(node_id), "label": str(detail), "kind": kind, "table": table,
            "index": index_match.group(1) if index_match else None,
            "severity": "good" if kind in ("search", "index-scan", "constant") else "info",
            "note": NOTES.get(kind, ""), "metrics": {}, "children": [],
        }
        if table and table in table_rows:
            node["metrics"]["table_rows"] = table_rows[table]
        nodes[int(node_id)] = node
        (nodes[int(parent)]["children"] if int(parent) in nodes else roots).append(node)

    advice: list[dict] = []

    def visit(siblings: list[dict]) -> None:
        loops = [n for n in siblings if n["kind"] in ("scan", "search", "index-scan", "auto-index")]
        for position, node in enumerate(loops):
            rows_in_table = node["metrics"].get("table_rows", 0)
            if node["kind"] == "scan" and position > 0 and rows_in_table > 50:
                node["severity"] = "warn"
                node["note"] = (f"Reads all {rows_in_table:,} rows of {node['table']} once for every row of the "
                                "outer loop: a nested-loop join without a usable index.")
                advice.append({"severity": "warn", "message": (
                    f"{node['table']} is scanned in full inside a join loop. Index the column it is joined on.")})
            elif node["kind"] == "auto-index":
                node["severity"] = "warn"
                cols = _PARENS.search(node["label"])
                column_list = ", ".join(part.split("=")[0].split(">")[0].split("<")[0].strip()
                                        for part in cols.group(1).split(" AND ")) if cols else "the join column"
                advice.append({"severity": "warn", "message": (
                    f"SQLite builds a temporary index on {node['table']}({column_list}) every time this runs. "
                    f"A permanent one would help: CREATE INDEX idx_{node['table']}_{column_list.split(',')[0].strip()} "
                    f"ON {node['table']} ({column_list});")})
        for node in siblings:
            if node["kind"] == "correlated":
                node["severity"] = "warn"
                advice.append({"severity": "warn", "message": (
                    "A correlated subquery runs once per outer row. A join or a window function is often cheaper.")})
            if node["kind"] == "sort":
                advice.append({"severity": "info", "message": (
                    f"{node['label'].title().replace('B-Tree', 'B-tree')}: an index whose column order matches "
                    "could deliver rows already sorted.")})
            visit(node["children"])

    visit(roots)
    if not advice and any(n["kind"] == "scan" and n["metrics"].get("table_rows", 0) > 1000 for n in nodes.values()):
        advice.append({"severity": "info", "message": (
            "The query reads whole tables. That is right when it needs most rows; if it filters to a few, "
            "an index on the filtered column turns the SCAN into a SEARCH.")})
    return roots, advice


def annotate_bytecode(rows: list[list]) -> tuple[list[dict], dict]:
    program, loops = [], 0
    histogram: dict[str, int] = {}
    for row in rows:
        addr, opcode, p1, p2, p3, p4, p5, comment = (list(row) + [None] * 8)[:8]
        loop = opcode in ("Next", "Prev", "SorterNext", "VNext") and isinstance(p2, int) and isinstance(addr, int) and p2 < addr
        loops += 1 if loop else 0
        histogram[str(opcode)] = histogram.get(str(opcode), 0) + 1
        program.append({"addr": addr, "opcode": opcode, "p1": p1, "p2": p2, "p3": p3, "p4": p4, "p5": p5,
                        "comment": comment, "note": OPCODES.get(str(opcode), ""), "loop_to": p2 if loop else None})
    common = sorted(histogram.items(), key=lambda item: (-item[1], item[0]))[:6]
    return program, {"instructions": len(program), "loops": loops, "common": common}


_PG_KIND = {
    "Seq Scan": "scan", "Index Scan": "search", "Index Only Scan": "search", "Bitmap Heap Scan": "search",
    "Bitmap Index Scan": "search", "Sort": "sort", "Incremental Sort": "sort", "Hash Join": "join",
    "Merge Join": "join", "Nested Loop": "join", "Aggregate": "aggregate", "HashAggregate": "aggregate",
    "GroupAggregate": "aggregate", "Limit": "limit", "Hash": "hash", "Materialize": "materialize",
    "Memoize": "materialize", "CTE Scan": "subquery", "Subquery Scan": "subquery", "Gather": "parallel",
    "Gather Merge": "parallel", "WindowAgg": "window", "Unique": "aggregate", "Append": "compound",
    "Result": "constant", "Function Scan": "scan", "Values Scan": "constant",
}


def postgres_tree(plan_json) -> tuple[list[dict], list[dict]]:
    """Normalize EXPLAIN (FORMAT JSON) output from PostgreSQL."""
    advice: list[dict] = []
    counter = [0]
    root = plan_json[0]["Plan"] if isinstance(plan_json, list) else plan_json["Plan"]

    def convert(plan: dict) -> dict:
        counter[0] += 1
        node_type = plan.get("Node Type", "?")
        kind = _PG_KIND.get(node_type, "other")
        relation = plan.get("Relation Name")
        label = node_type + (f" on {relation}" if relation else "") + (
            f" using {plan['Index Name']}" if plan.get("Index Name") else "")
        metrics = {key: plan[src] for key, src in (("rows_estimated", "Plan Rows"), ("rows_actual", "Actual Rows"),
                                                    ("cost", "Total Cost"), ("time_ms", "Actual Total Time"),
                                                    ("loops", "Actual Loops")) if src in plan}
        node = {"id": counter[0], "label": label, "kind": kind, "table": relation, "index": plan.get("Index Name"),
                "severity": "good" if kind == "search" else "info",
                "note": plan.get("Filter") and f"Filter: {plan['Filter']}" or NOTES.get(kind, ""),
                "metrics": metrics, "children": [convert(child) for child in plan.get("Plans", [])]}
        estimated, actual = metrics.get("rows_estimated"), metrics.get("rows_actual")
        if kind == "scan" and plan.get("Filter") and (estimated or 0) > 10_000:
            node["severity"] = "warn"
            advice.append({"severity": "warn", "message": f"Sequential scan of {relation} with a filter: consider an index."})
        if estimated and actual is not None and (actual > estimated * 10 or estimated > max(actual, 1) * 10):
            advice.append({"severity": "info", "message": (
                f"{label}: the planner estimated {estimated:,} rows but found {actual:,}. Run ANALYZE to refresh statistics.")})
        return node

    return [convert(root)], advice
