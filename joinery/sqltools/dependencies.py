"""The dependency graph of one statement: which tables, CTEs and subqueries
feed which, so the client can draw it and show how a failure propagates.

Nodes are tables, CTEs, subqueries, table-valued functions, relations that do
not exist, and the statement's result (or the table it writes). An edge
``a -> b`` means ``b`` reads from ``a``. Like the stepper, the analysis is
lexical; it never decides what is safe to run.
"""

from __future__ import annotations

from .stepper import NOT_ALIASES, _depths, quote_ident
from .tokenizer import IDENT, WORD, Token, significant, tokenize

END_FROM = {"WHERE", "GROUP", "HAVING", "ORDER", "LIMIT", "WINDOW", "UNION", "INTERSECT", "EXCEPT", "RETURNING",
            "SET", "VALUES"}
SUBQUERY_EDGE = {"derived": "reads", "exists": "filters", "not-exists": "filters", "in": "filters",
                 "not-in": "filters", "scalar": "value"}


def _close(toks: list[Token], depths: list[int], i: int) -> int:
    """Index of the parenthesis that closes the one at ``i``."""
    j = i + 1
    while j < len(toks) and not (toks[j].is_op(")") and depths[j] == depths[i] + 1):
        j += 1
    return j


def _name(tok: Token) -> str:
    return tok.text.strip('"`[]')


class Graph:
    def __init__(self, sql: str, tables: dict[str, list[str]], rows: dict[str, int], dialect: str) -> None:
        self.sql = sql
        self.dialect = dialect
        self.tables = {name.lower(): name for name in tables}
        self.rows = rows
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.ctes: dict[str, str] = {}
        self.definitions: list[tuple[str, str]] = []
        self.recursive = False
        self.counter = 0

    def node(self, node_id: str, **attrs) -> str:
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, **attrs}
        return node_id

    def edge(self, source: str, target: str, kind: str) -> None:
        if source == target:
            kind = "recursive"
        if not any(e["from"] == source and e["to"] == target for e in self.edges):
            self.edges.append({"from": source, "to": target, "kind": kind})

    def relation(self, name: str, function: bool = False) -> str:
        key = name.lower()
        if function:
            return self.node(f"function:{key}", kind="function", label=f"{name}()")
        if key in self.ctes:
            return self.ctes[key]
        if key in self.tables:
            table = self.tables[key]
            return self.node(f"table:{table}", kind="table", label=table, rows=self.rows.get(table))
        return self.node(f"missing:{key}", kind="missing", label=name, status="error",
                         message=f"no such table: {name}")

    # ------------------------------------------------------------------ CTEs
    def parse_with(self, text: str, toks: list[Token]) -> str:
        """Register the CTEs of a WITH clause and return the text after it."""
        depths = _depths(toks)
        i = 1
        if i < len(toks) and toks[i].is_word("RECURSIVE"):
            self.recursive = True
            i += 1
        bodies = []
        while i < len(toks) and toks[i].kind in (WORD, IDENT):
            start = toks[i].start
            name = _name(toks[i])
            i += 1
            if i < len(toks) and toks[i].is_op("("):
                i = _close(toks, depths, i) + 1
            while i < len(toks) and toks[i].is_word("AS", "NOT", "MATERIALIZED"):
                i += 1
            if i >= len(toks) or not toks[i].is_op("("):
                break
            close = _close(toks, depths, i)
            body = text[toks[i + 1].start:toks[close - 1].end] if close > i + 1 else ""
            node_id = self.node(f"cte:{name.lower()}", kind="cte", label=name, sql=body)
            self.ctes[name.lower()] = node_id
            self.definitions.append((name, text[start:toks[close].end]))
            bodies.append((node_id, body))
            i = close + 1
            if i < len(toks) and toks[i].is_op(","):
                i += 1
                continue
            break
        for node_id, body in bodies:
            self.analyze(body, node_id, set())
            if any(e["to"] == node_id and e["kind"] == "recursive" for e in self.edges):
                self.nodes[node_id]["recursive"] = True
        return text[toks[i].start:] if i < len(toks) else ""

    # ------------------------------------------------------------------ scopes
    def analyze(self, text: str, owner: str, outer: set[str]) -> None:
        toks = significant(tokenize(text, self.dialect))
        if not toks:
            return
        if toks[0].is_word("WITH"):
            text = self.parse_with(text, toks)
            toks = significant(tokenize(text, self.dialect))
        depths = _depths(toks)
        aliases: set[str] = set()
        derived: set[int] = set()
        expecting = in_from = False
        i = 0
        while i < len(toks):
            tok, depth = toks[i], depths[i]
            if depth != 0:
                i += 1
                continue
            if tok.kind == WORD and tok.upper == "FROM":
                in_from = expecting = True
            elif tok.kind == WORD and tok.upper == "JOIN":
                expecting = True
            elif tok.kind == WORD and tok.upper in END_FROM:
                in_from = expecting = False
            elif tok.is_op(",") and in_from:
                expecting = True
            elif expecting and tok.is_op("("):
                close = _close(toks, depths, i)
                derived.add(i)
                k = close + 1
                if k < len(toks) and toks[k].is_word("AS"):
                    k += 1
                if k < len(toks) and toks[k].kind in (WORD, IDENT) and toks[k].upper not in NOT_ALIASES:
                    aliases.add(_name(toks[k]).lower())
                expecting = False
                i = close + 1
                continue
            elif expecting and tok.kind in (WORD, IDENT):
                name = _name(tok)
                k = i + 1
                if k + 1 < len(toks) and toks[k].is_op(".") and toks[k + 1].kind in (WORD, IDENT):
                    name = _name(toks[k + 1])
                    k += 2
                function = k < len(toks) and toks[k].is_op("(")
                if function:
                    k = _close(toks, depths, k) + 1
                self.edge(self.relation(name, function), owner, "reads")
                if k < len(toks) and toks[k].is_word("AS"):
                    k += 1
                alias = name
                if k < len(toks) and toks[k].kind in (WORD, IDENT) and toks[k].upper not in NOT_ALIASES:
                    alias = _name(toks[k])
                    k += 1
                aliases.update({alias.lower(), name.lower()})
                expecting = False
                i = k
                continue
            i += 1
        scope = outer | aliases
        i = 0
        while i < len(toks):
            if depths[i] == 0 and toks[i].is_op("(") and i + 1 < len(toks) and toks[i + 1].is_word("SELECT", "WITH", "VALUES"):
                close = _close(toks, depths, i)
                body = text[toks[i + 1].start:toks[close - 1].end]
                prev = toks[i - 1] if i > 0 else None
                before = toks[i - 2] if i > 1 else None
                if i in derived:
                    kind = "derived"
                elif prev is not None and prev.is_word("EXISTS"):
                    kind = "not-exists" if before is not None and before.is_word("NOT") else "exists"
                elif prev is not None and prev.is_word("IN"):
                    kind = "not-in" if before is not None and before.is_word("NOT") else "in"
                else:
                    kind = "scalar"
                self.counter += 1
                sub = self.node(f"subquery:{self.counter}", kind="subquery", label=f"{kind} subquery", role=kind,
                                sql=body, correlated=self.correlated(body, scope))
                self.edge(sub, owner, SUBQUERY_EDGE[kind])
                self.analyze(body, sub, scope)
                i = close + 1
                continue
            i += 1

    def correlated(self, body: str, outer: set[str]) -> bool:
        toks = significant(tokenize(body, self.dialect))
        inner: set[str] = set()
        for n, tok in enumerate(toks[:-1]):
            if tok.is_word("FROM", "JOIN") or (tok.is_op(",") and n > 0):
                nxt = toks[n + 1]
                if nxt.kind in (WORD, IDENT):
                    inner.add(_name(nxt).lower())
                    if n + 2 < len(toks):
                        after = toks[n + 3] if toks[n + 2].is_word("AS") and n + 3 < len(toks) else toks[n + 2]
                        if after.kind in (WORD, IDENT) and after.upper not in NOT_ALIASES:
                            inner.add(_name(after).lower())
        for n, tok in enumerate(toks[:-1]):
            if tok.kind in (WORD, IDENT) and toks[n + 1].is_op("."):
                qualifier = _name(tok).lower()
                if qualifier in outer and qualifier not in inner:
                    return True
        return False

    # ------------------------------------------------------------------ helpers for counting
    def upstream_ctes(self, node_id: str) -> list[str]:
        seen, stack = set(), [node_id]
        while stack:
            current = stack.pop()
            for edge in self.edges:
                if edge["to"] == current and edge["from"] not in seen:
                    seen.add(edge["from"])
                    stack.append(edge["from"])
        if self.nodes[node_id]["kind"] == "cte":
            seen.add(node_id)
        return [name for name, _definition in self.definitions if self.ctes[name.lower()] in seen]

    def count_query(self, node_id: str) -> str | None:
        node = self.nodes[node_id]
        names = self.upstream_ctes(node_id)
        definitions = dict(self.definitions)
        prefix = ""
        if names:
            prefix = "WITH " + ("RECURSIVE " if self.recursive else "") + ", ".join(definitions[n] for n in names) + " "
        if node["kind"] == "cte":
            return f"{prefix}SELECT count(*) FROM {quote_ident(node['label'], self.dialect)}"
        if node["kind"] == "subquery" and not node.get("correlated") and node.get("sql"):
            return f"{prefix}SELECT count(*) FROM ({node['sql']})"
        return None


def dependency_graph(statement: str, tables: dict[str, list[str]], rows: dict[str, int],
                     dialect: str = "sqlite") -> Graph | dict:
    """Analyze one statement. Returns a Graph, or a dict explaining why not."""
    text = statement.strip().rstrip(";").strip()
    graph = Graph(text, tables, rows, dialect)
    toks = significant(tokenize(text, dialect))
    if not toks:
        return {"supported": False, "reason": "There is no statement to analyze."}
    main = text
    if toks[0].is_word("WITH"):
        main = graph.parse_with(text, toks)
        toks = significant(tokenize(main, dialect))
    if not toks:
        return {"supported": False, "reason": "The WITH clause has no main query."}
    first = toks[0].upper if toks[0].kind == WORD else ""
    if first in ("SELECT", "VALUES"):
        graph.statement = "select"
        graph.node("query", kind="query", label="Result")
        graph.analyze(main, "query", set())
        return graph
    if first in ("INSERT", "UPDATE", "DELETE", "REPLACE"):
        i = 1
        while i < len(toks) and toks[i].is_word("OR", "INTO", "FROM", "ROLLBACK", "ABORT", "REPLACE", "FAIL", "IGNORE"):
            i += 1
        if i >= len(toks) or toks[i].kind not in (WORD, IDENT):
            return {"supported": False, "reason": "Could not find the target table."}
        target_name = _name(toks[i])
        graph.statement = "insert" if first in ("INSERT", "REPLACE") else first.lower()
        graph.node("query", kind="query", label=f"{first} {target_name}")
        target = graph.relation(target_name)
        graph.edge("query", target, "writes")
        if first != "INSERT":
            graph.edge(target, "query", "reads")
        rest = main[toks[i].end:]
        rest_toks = significant(tokenize(rest, dialect))
        start = next((n for n, t in enumerate(rest_toks) if t.is_word("SELECT", "WITH")), None) if first == "INSERT" else 0
        if start is not None and rest_toks:
            graph.analyze(rest[rest_toks[start].start:], "query", {target_name.lower()})
        return graph
    return {"supported": False, "reason": "Dependency graphs cover SELECT, INSERT, UPDATE and DELETE."}


def propagate(graph: Graph) -> None:
    """Mark where a failure starts and everything downstream it blocks."""
    upstream: dict[str, list[str]] = {n: [] for n in graph.nodes}
    for edge in graph.edges:
        if edge["kind"] not in ("writes", "recursive"):
            upstream[edge["to"]].append(edge["from"])
    changed = True
    while changed:
        changed = False
        for node_id, node in graph.nodes.items():
            status = node.get("status")
            if status in ("error", "blocked"):
                continue
            broken = [u for u in upstream[node_id] if graph.nodes[u].get("status") in ("error", "blocked", "failed")]
            if broken and status in (None, "failed", "ok"):
                node["status"] = "blocked"
                node["blocked_by"] = broken
                changed = True
            elif status == "failed" and not broken:
                node["status"] = "error"
                changed = True
    for node in graph.nodes.values():
        node.setdefault("status", "ok")
    for edge in graph.edges:
        edge["broken"] = graph.nodes[edge["from"]]["status"] in ("error", "blocked")


def to_json(graph: Graph) -> dict:
    return {"supported": True, "statement": getattr(graph, "statement", "select"), "recursive": graph.recursive,
            "nodes": list(graph.nodes.values()), "edges": graph.edges}
