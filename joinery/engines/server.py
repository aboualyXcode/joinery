"""Server engines: PostgreSQL, MySQL and SQL Server (experimental).

Datasets live in a shared database that ``python -m joinery provision``
loads. Each run:

1. connects as a low-privilege role that can only read and write the
   dataset tables,
2. opens one transaction with a statement timeout and a lock timeout,
3. wraps every statement in a savepoint, so an error never poisons the rest
   of the run,
4. refuses statements the guard flags (transaction control, privilege
   changes, file access and so on), and
5. always rolls the transaction back, whatever happened.

These engines are validated by the CI workflow against real servers; see
docs/engines.md for their current status.
"""

from __future__ import annotations

import importlib.util
import math
import time
from collections.abc import Callable
from urllib.parse import unquote, urlsplit

from ..sandbox.worker import Budget, convert
from ..sqltools.split import statement_texts
from .base import Engine, failure
from .guard import check_statement

TIMEOUT_MARKERS = ("statement timeout", "max_execution_time", "query execution was interrupted",
                   "query timeout", "timeout expired")


class ServerEngine(Engine):
    experimental = True
    driver = ""

    def __init__(self, dsn: str, limits: dict, connect: Callable | None = None) -> None:
        self.dsn = dsn
        self.limits = limits
        self._connect_override = connect
        self._version = "not connected"

    # -- driver-specific hooks -------------------------------------------------
    def connect(self, dataset_id: str, timeout_ms: int):
        raise NotImplementedError

    def begin(self, cur, dataset_id: str, timeout_ms: int) -> None:
        raise NotImplementedError

    def savepoint_sql(self, name: str) -> tuple[str, str, str | None]:
        """SQL to create, roll back to and release a savepoint."""
        return f"SAVEPOINT {name}", f"ROLLBACK TO SAVEPOINT {name}", f"RELEASE SAVEPOINT {name}"

    def explain(self, cur, sql: str, analyze: bool) -> dict:
        raise NotImplementedError

    def server_version(self, cur) -> str:
        return "unknown"

    # -- shared machinery ------------------------------------------------------
    def available(self) -> bool:
        return self._connect_override is not None or importlib.util.find_spec(self.driver) is not None

    def version(self) -> str:
        return self._version

    def _open(self, dataset_id: str, timeout_ms: int):
        if self._connect_override is not None:
            return self._connect_override(dataset_id, timeout_ms)
        return self.connect(dataset_id, timeout_ms)

    def _error(self, exc: BaseException) -> dict:
        message = str(exc).strip() or type(exc).__name__
        if any(marker in message.lower() for marker in TIMEOUT_MARKERS):
            return {"type": "Timeout", "message": message, "code": getattr(exc, "sqlstate", None)}
        return {"type": type(exc).__name__, "message": message, "code": getattr(exc, "sqlstate", None)}

    def execute(self, cur, sql: str, budget: Budget) -> dict:
        result: dict = {
            "sql": sql, "kind": "command", "columns": [], "rows": [], "row_count": 0,
            "row_count_capped": False, "truncated": False, "changes": 0,
            "elapsed_ms": 0.0, "vm_steps": None, "error": None,
        }
        started = time.perf_counter()
        try:
            cur.execute(sql)
            if cur.description:
                result["kind"] = "rows"
                result["columns"] = [str(col[0]) for col in cur.description]
                rows, count, full = [], 0, False
                cap, max_rows = int(self.limits["count_cap"]), int(self.limits["max_rows"])
                max_chars = int(self.limits["max_cell_chars"])
                while count < cap:
                    batch = cur.fetchmany(256)
                    if not batch:
                        break
                    for raw in batch:
                        count += 1
                        if not full and len(rows) < max_rows:
                            row = [convert(v, max_chars) for v in raw]
                            if budget.take(sum(len(str(c)) + 4 for c in row)):
                                rows.append(row)
                            else:
                                full = True
                result.update(rows=rows, row_count=count, truncated=count > len(rows),
                              row_count_capped=count >= cap)
            elif isinstance(cur.rowcount, int) and cur.rowcount > 0:
                result["changes"] = cur.rowcount
        except Exception as exc:  # drivers raise their own hierarchies
            result["error"] = self._error(exc)
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return result

    def run(self, dataset_id: str, batches: list[dict], *, timeout_ms: int) -> dict:
        if not dataset_id.isidentifier():
            return failure("UnknownDataset", f"There is no dataset called {dataset_id}.")
        try:
            conn = self._open(dataset_id, timeout_ms)
        except Exception as exc:
            return failure("ConnectionError", f"Could not connect to {self.name}: {exc}")
        deadline = time.monotonic() + timeout_ms / 1000
        budget = Budget(int(self.limits["max_output_bytes"]))
        try:
            cur = conn.cursor()
            self.begin(cur, dataset_id, timeout_ms)
            self._version = self.server_version(cur)
            outputs = []
            counter = 0
            for batch in batches:
                sql = str(batch.get("sql", ""))
                statements = statement_texts(sql, self.dialect) if batch.get("split", True) else [sql.strip()]
                statements = [s for s in statements if s]
                if len(statements) > int(self.limits["max_statements"]):
                    return failure("JobError", f"too many statements: the limit is {self.limits['max_statements']} per run")
                results = []
                for statement in statements:
                    if time.monotonic() > deadline:
                        break
                    reason = check_statement(statement, self.dialect)
                    if reason:
                        entry = {"sql": statement, "kind": "command", "columns": [], "rows": [], "row_count": 0,
                                 "row_count_capped": False, "truncated": False, "changes": 0, "elapsed_ms": 0.0,
                                 "vm_steps": None, "error": {"type": "Blocked", "message": reason, "code": None}}
                    else:
                        counter += 1
                        create, rollback, release = self.savepoint_sql(f"joinery_sp{counter}")
                        cur.execute(create)
                        if batch.get("explain"):
                            entry = self.explain(cur, statement, bool(batch.get("analyze")))
                        else:
                            entry = self.execute(cur, statement, budget)
                        if entry.get("error"):
                            cur.execute(rollback)
                        elif release:
                            cur.execute(release)
                    results.append(entry)
                    if entry.get("error") and batch.get("stop_on_error", True):
                        break
                outputs.append({"id": batch.get("id"), "statements": results,
                                "skipped": len(statements) - len(results)})
            return {"ok": True, "engine": self.id, "engine_version": self._version, "batches": outputs,
                    "timed_out": time.monotonic() > deadline, "error": None}
        except Exception as exc:
            return failure(type(exc).__name__, f"{self.name} run failed: {exc}")
        finally:
            try:
                conn.rollback()
            finally:
                conn.close()


def _explain_entry(sql: str) -> dict:
    return {"sql": sql, "plan": [], "plan_text": None, "plan_json": None, "bytecode": [], "analyze": None,
            "error": None}


class PostgresEngine(ServerEngine):
    id = "postgres"
    name = "PostgreSQL"
    dialect = "postgres"
    driver = "psycopg"

    def connect(self, dataset_id: str, timeout_ms: int):
        import psycopg

        return psycopg.connect(self.dsn, connect_timeout=5, autocommit=False)

    def begin(self, cur, dataset_id: str, timeout_ms: int) -> None:
        cur.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
        cur.execute("SET LOCAL lock_timeout = 1000")
        cur.execute(f"SET LOCAL idle_in_transaction_session_timeout = {int(timeout_ms) + 5000}")
        cur.execute("SET LOCAL work_mem = '16MB'")
        cur.execute(f"SET LOCAL search_path = {dataset_id}")

    def server_version(self, cur) -> str:
        cur.execute("SHOW server_version")
        return str(cur.fetchone()[0])

    def explain(self, cur, sql: str, analyze: bool) -> dict:
        out = _explain_entry(sql)
        options = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
        try:
            cur.execute(f"EXPLAIN ({options}) {sql}")
            value = cur.fetchone()[0]
            out["plan_json"] = value
        except Exception as exc:
            out["error"] = self._error(exc)
        return out


def _mysql_params(dsn: str) -> dict:
    parts = urlsplit(dsn)
    return {
        "host": parts.hostname or "localhost",
        "port": parts.port or 3306,
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
    }


class MysqlEngine(ServerEngine):
    id = "mysql"
    name = "MySQL"
    dialect = "mysql"
    driver = "pymysql"

    def connect(self, dataset_id: str, timeout_ms: int):
        import pymysql

        seconds = math.ceil(timeout_ms / 1000) + 2
        return pymysql.connect(database=f"joinery_{dataset_id}", connect_timeout=5, read_timeout=seconds,
                               write_timeout=seconds, autocommit=False, charset="utf8mb4",
                               **_mysql_params(self.dsn))

    def begin(self, cur, dataset_id: str, timeout_ms: int) -> None:
        cur.execute(f"SET SESSION max_execution_time = {int(timeout_ms)}")
        cur.execute("SET SESSION innodb_lock_wait_timeout = 2")
        cur.execute("START TRANSACTION")

    def server_version(self, cur) -> str:
        cur.execute("SELECT VERSION()")
        return str(cur.fetchone()[0])

    def explain(self, cur, sql: str, analyze: bool) -> dict:
        out = _explain_entry(sql)
        try:
            cur.execute(("EXPLAIN ANALYZE " if analyze else "EXPLAIN FORMAT=TREE ") + sql)
            out["plan_text"] = "\n".join(str(row[0]) for row in cur.fetchall())
        except Exception as exc:
            out["error"] = self._error(exc)
        return out


class MssqlEngine(ServerEngine):
    id = "mssql"
    name = "SQL Server"
    dialect = "mssql"
    driver = "mssql_python"

    def connect(self, dataset_id: str, timeout_ms: int):
        import mssql_python

        conn = mssql_python.connect(f"{self.dsn.rstrip(';')};Database=joinery_{dataset_id}")
        try:
            conn.autocommit = False
            conn.timeout = math.ceil(timeout_ms / 1000)
        except AttributeError:
            pass
        return conn

    def begin(self, cur, dataset_id: str, timeout_ms: int) -> None:
        cur.execute("SET LOCK_TIMEOUT 1000")
        cur.execute("SET XACT_ABORT OFF")

    def savepoint_sql(self, name: str) -> tuple[str, str, str | None]:
        return f"SAVE TRANSACTION {name}", f"ROLLBACK TRANSACTION {name}", None

    def server_version(self, cur) -> str:
        cur.execute("SELECT CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(32))")
        return str(cur.fetchone()[0])

    def explain(self, cur, sql: str, analyze: bool) -> dict:
        out = _explain_entry(sql)
        try:
            cur.execute("SET SHOWPLAN_TEXT ON")
            try:
                cur.execute(sql)
                lines = []
                while True:
                    lines.extend(str(row[0]) for row in cur.fetchall())
                    if not cur.nextset():
                        break
                out["plan_text"] = "\n".join(lines)
            finally:
                cur.execute("SET SHOWPLAN_TEXT OFF")
        except Exception as exc:
            out["error"] = self._error(exc)
        return out
