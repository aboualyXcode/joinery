"""Sandboxed SQL worker.

Joinery runs every submitted query in a short-lived child process started as
``python -I -S -B worker.py``. The parent writes one JSON job to stdin and
reads one JSON result from stdout. Before any submitted SQL runs, the worker:

* loads a pristine copy of the dataset into a private in-memory database,
* lowers operating-system limits: CPU time, address space, file size (zero,
  so nothing can be written to disk), open files and process creation,
* hardens the SQLite connection: defensive mode, untrusted schema, strict
  string quoting, low run-time limits, a hard heap limit, a page cap and an
  authorizer that refuses ATTACH/DETACH, extension loading and every PRAGMA
  outside a small read-only allowlist, and
* installs a progress handler that enforces a wall-clock deadline and counts
  virtual machine steps, which Joinery reports as a cost metric.

The worker imports nothing outside the standard library (DuckDB is the one
optional exception) and never writes to the filesystem.
"""

from __future__ import annotations

import json
import math
import resource
import signal
import sqlite3
import sys
import threading
import time

MAX_JOB_BYTES = 1_000_000
PROGRESS_INTERVAL = 100  # SQLite VM instructions between progress callbacks
TRANSACTION_WORDS = ("BEGIN", "COMMIT", "END", "ROLLBACK", "SAVEPOINT", "RELEASE")

DEFAULT_LIMITS = {
    "timeout_ms": 3000,
    "max_rows": 500,
    "count_cap": 100_000,
    "max_cell_chars": 2000,
    "max_output_bytes": 4_000_000,
    "max_statements": 50,
    "memory_mb": 512,
    "heap_mb": 192,
    "extra_pages": 8192,
}

# Read-only introspection that is useful for learning and harmless to allow.
INTROSPECTION_PRAGMAS = frozenset(
    {
        "table_info", "table_xinfo", "table_list", "index_list", "index_info", "index_xinfo",
        "foreign_key_list", "foreign_key_check", "integrity_check", "quick_check",
        "collation_list", "function_list", "module_list", "pragma_list", "database_list",
        "compile_options", "page_count", "page_size",
    }
)
# Settings that only change behaviour inside the learner's private database.
TOGGLE_PRAGMAS = frozenset(
    {"foreign_keys", "defer_foreign_keys", "recursive_triggers", "automatic_index",
     "reverse_unordered_selects", "query_only"}
)
DENIED_FUNCTIONS = frozenset({"load_extension", "fts3_tokenizer"})

SQLITE_CONFIG = (
    (sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True),
    (sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False),
    (sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, False),
    (sqlite3.SQLITE_DBCONFIG_WRITABLE_SCHEMA, False),
    (sqlite3.SQLITE_DBCONFIG_DQS_DML, False),
    (sqlite3.SQLITE_DBCONFIG_DQS_DDL, False),
    (sqlite3.SQLITE_DBCONFIG_ENABLE_FKEY, True),
    (sqlite3.SQLITE_DBCONFIG_ENABLE_TRIGGER, True),
    (sqlite3.SQLITE_DBCONFIG_ENABLE_VIEW, True),
)

SQLITE_RUNTIME_LIMITS = (
    (sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000),
    (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 100_000),
    (sqlite3.SQLITE_LIMIT_COLUMN, 200),
    (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 200),
    (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 50),
    (sqlite3.SQLITE_LIMIT_VDBE_OP, 250_000),
    (sqlite3.SQLITE_LIMIT_FUNCTION_ARG, 64),
    (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
    (sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH, 500),
    (sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 100),
    (sqlite3.SQLITE_LIMIT_TRIGGER_DEPTH, 20),
    (sqlite3.SQLITE_LIMIT_WORKER_THREADS, 0),
)


class JobError(Exception):
    """A problem with the job itself rather than with the submitted SQL."""


class Deadline:
    """Progress handler: enforces the time limit and counts VM steps."""

    def __init__(self, seconds: float) -> None:
        self.at = time.monotonic() + seconds
        self.ticks = 0
        self.expired = False

    def __call__(self) -> int:
        self.ticks += 1
        if time.monotonic() > self.at:
            self.expired = True
            return 1
        return 0

    def remaining(self) -> float:
        return self.at - time.monotonic()


class Budget:
    """Keeps the JSON result within a byte budget."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def take(self, amount: int) -> bool:
        if self.used + amount > self.limit:
            return False
        self.used += amount
        return True


# --------------------------------------------------------------------------- process limits


def _lower(kind: int, value: int, required: bool) -> None:
    _soft, hard = resource.getrlimit(kind)
    if hard != resource.RLIM_INFINITY:
        value = min(value, hard)
    try:
        resource.setrlimit(kind, (value, value))
    except (ValueError, OSError) as exc:
        if required:
            raise JobError(f"could not apply resource limit {kind}: {exc}") from exc


def restrict_process(limits: dict, *, limit_memory: bool, allow_threads: bool) -> None:
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)  # a write attempt fails instead of killing us
    cpu_seconds = max(1, math.ceil(limits["timeout_ms"] / 1000) + 1)
    _lower(resource.RLIMIT_CPU, cpu_seconds, required=True)
    _lower(resource.RLIMIT_FSIZE, 0, required=True)
    _lower(resource.RLIMIT_CORE, 0, required=False)
    _lower(resource.RLIMIT_NOFILE, 32, required=False)
    if limit_memory:
        _lower(resource.RLIMIT_AS, limits["memory_mb"] * 1024 * 1024, required=True)
    if not allow_threads:
        _lower(resource.RLIMIT_NPROC, 0, required=False)


# --------------------------------------------------------------------------- SQLite


def authorize(action: int, arg1: str | None, arg2: str | None, _db: str | None, _source: str | None) -> int:
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA:
        name = (arg1 or "").lower()
        if name in INTROSPECTION_PRAGMAS or name in TOGGLE_PRAGMAS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in DENIED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def open_sqlite(image: bytes | None, limits: dict, deadline: Deadline) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:", isolation_level=None)
    con.text_factory = lambda raw: raw.decode("utf-8", "replace")
    if image:
        con.deserialize(image)
    for option, enabled in SQLITE_CONFIG:
        con.setconfig(option, enabled)
    for category, value in SQLITE_RUNTIME_LIMITS:
        con.setlimit(category, value)
    page_count = con.execute("PRAGMA page_count").fetchone()[0]
    con.execute(f"PRAGMA max_page_count = {int(page_count) + int(limits['extra_pages'])}")
    con.execute(f"PRAGMA hard_heap_limit = {int(limits['heap_mb']) * 1024 * 1024}")
    con.execute("PRAGMA temp_store = MEMORY")
    con.execute("PRAGMA mmap_size = 0")
    con.execute("PRAGMA foreign_keys = ON")
    con.set_authorizer(authorize)
    con.set_progress_handler(deadline, PROGRESS_INTERVAL)
    return con


def _has_sql(text: str) -> bool:
    """True when text contains something other than whitespace and comments."""
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            i += 1
        elif text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            return True
    return False


def split_sqlite(sql: str, max_statements: int) -> list[str]:
    """Split with SQLite's own completeness test, so trigger bodies stay whole."""
    statements: list[str] = []
    start = 0
    for index, char in enumerate(sql):
        if char == ";" and sqlite3.complete_statement(sql[start:index + 1]):
            chunk = sql[start:index].strip()
            if _has_sql(chunk):
                statements.append(chunk)
            start = index + 1
            if len(statements) > max_statements:
                raise JobError(f"too many statements: the limit is {max_statements} per run")
    rest = sql[start:].strip()
    if _has_sql(rest):
        statements.append(rest)
    if len(statements) > max_statements:
        raise JobError(f"too many statements: the limit is {max_statements} per run")
    return statements


# --------------------------------------------------------------------------- values


def convert(value: object, max_chars: int) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if -(2**53) <= value <= 2**53 else str(value)
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + "\u2026"
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return {"blob": data[:32].hex(), "bytes": len(data)}
    # Values that DuckDB can return.
    if hasattr(value, "is_finite") and hasattr(value, "as_tuple"):  # decimal.Decimal
        return float(value) if value.is_finite() else str(value)  # type: ignore[attr-defined]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat(" ")  # type: ignore[attr-defined]
        except TypeError:
            return value.isoformat()  # type: ignore[attr-defined]
    if isinstance(value, (list, tuple, dict)):
        text = json.dumps(value, default=str)
        return text if len(text) <= max_chars else text[:max_chars] + "\u2026"
    return str(value)


def _size(row: list) -> int:
    return sum(len(str(cell)) + 4 for cell in row) + 2


# --------------------------------------------------------------------------- execution


class Runner:
    def __init__(self, con, engine: str, limits: dict, deadline: Deadline) -> None:
        self.con = con
        self.engine = engine
        self.limits = limits
        self.deadline = deadline
        self.budget = Budget(int(limits["max_output_bytes"]))

    # SQLite reports changes and VM steps; DuckDB reports neither.
    def _changes(self) -> int:
        return self.con.total_changes if self.engine == "sqlite" else 0

    def _error(self, exc: BaseException) -> dict:
        if self.deadline.expired or (self.engine == "duckdb" and "INTERRUPT" in str(exc).upper()):
            return {
                "type": "Timeout",
                "message": f"The query was stopped after {self.limits['timeout_ms']} ms, the time limit for one run.",
                "code": "SQLITE_INTERRUPT" if self.engine == "sqlite" else None,
            }
        if isinstance(exc, MemoryError):
            return {"type": "ResourceLimit", "message": "The query ran out of memory in the sandbox.", "code": None}
        return {
            "type": type(exc).__name__,
            "message": str(exc),
            "code": getattr(exc, "sqlite_errorname", None),
        }

    def execute(self, sql: str) -> dict:
        limits = self.limits
        result: dict = {
            "sql": sql, "kind": "command", "columns": [], "rows": [], "row_count": 0,
            "row_count_capped": False, "truncated": False, "changes": 0,
            "elapsed_ms": 0.0, "vm_steps": None, "error": None,
        }
        before = self._changes()
        ticks = self.deadline.ticks
        started = time.perf_counter()
        cursor = None
        try:
            cursor = self.con.execute(sql)
            if cursor.description is not None:
                result["kind"] = "rows"
                result["columns"] = [str(col[0]) for col in cursor.description]
                rows: list[list] = []
                count = 0
                max_rows = int(limits["max_rows"])
                cap = int(limits["count_cap"])
                max_chars = int(limits["max_cell_chars"])
                full = False
                while count < cap:
                    batch = cursor.fetchmany(256)
                    if not batch:
                        break
                    for raw in batch:
                        count += 1
                        if not full and len(rows) < max_rows:
                            row = [convert(value, max_chars) for value in raw]
                            if self.budget.take(_size(row)):
                                rows.append(row)
                            else:
                                full = True
                        if count >= cap:
                            result["row_count_capped"] = True
                            break
                result["rows"] = rows
                result["row_count"] = count
                result["truncated"] = count > len(rows)
        except (sqlite3.Error, MemoryError) as exc:
            result["error"] = self._error(exc)
        except Exception as exc:  # DuckDB raises its own exception hierarchy
            if self.engine == "sqlite":
                raise
            result["error"] = self._error(exc)
        finally:
            if cursor is not None and self.engine == "sqlite":
                cursor.close()
            result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            result["changes"] = max(0, self._changes() - before)
            if self.engine == "sqlite":
                result["vm_steps"] = (self.deadline.ticks - ticks) * PROGRESS_INTERVAL
        return result

    def explain(self, sql: str, analyze: bool) -> dict:
        first = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        out: dict = {"sql": sql, "plan": [], "plan_text": None, "bytecode": [], "analyze": None, "error": None}
        if first == "EXPLAIN":
            out["error"] = {"type": "ExplainError", "message": "Remove EXPLAIN: Joinery adds it for you.", "code": None}
            return out
        try:
            if self.engine == "sqlite":
                out["plan"] = [list(row) for row in self.con.execute("EXPLAIN QUERY PLAN " + sql).fetchall()]
                out["bytecode"] = [
                    [convert(value, 200) for value in row]
                    for row in self.con.execute("EXPLAIN " + sql).fetchmany(4000)
                ]
            else:
                rows = self.con.execute("EXPLAIN " + sql).fetchall()
                out["plan_text"] = "\n".join(str(row[-1]) for row in rows)
        except (sqlite3.Error, MemoryError) as exc:
            out["error"] = self._error(exc)
            return out
        except Exception as exc:
            if self.engine == "sqlite":
                raise
            out["error"] = self._error(exc)
            return out
        if analyze and first not in TRANSACTION_WORDS:
            out["analyze"] = self._analyze(sql)
        return out

    def _analyze(self, sql: str) -> dict:
        """Run the statement for metrics, then undo any changes it made."""
        if self.engine != "sqlite":
            return self.execute(sql)
        self.con.execute("SAVEPOINT joinery_analyze")
        try:
            return self.execute(sql)
        finally:
            try:
                self.con.execute("ROLLBACK TO joinery_analyze")
                self.con.execute("RELEASE joinery_analyze")
            except sqlite3.Error:
                pass

    def split(self, sql: str) -> list[str]:
        max_statements = int(self.limits["max_statements"])
        if self.engine == "duckdb":
            import duckdb

            parts = [stmt.query.strip() for stmt in duckdb.extract_statements(sql)]
            parts = [part for part in parts if _has_sql(part)]
            if len(parts) > max_statements:
                raise JobError(f"too many statements: the limit is {max_statements} per run")
            return parts
        return split_sqlite(sql, max_statements)

    def run_batches(self, batches: list[dict]) -> list[dict]:
        outputs = []
        for batch in batches:
            sql = str(batch.get("sql", ""))
            statements = self.split(sql) if batch.get("split", True) else ([sql] if _has_sql(sql) else [])
            results = []
            for statement in statements:
                if self.deadline.remaining() <= 0:
                    break
                if batch.get("explain"):
                    entry = self.explain(statement, bool(batch.get("analyze")))
                else:
                    entry = self.execute(statement)
                results.append(entry)
                if entry.get("error") and batch.get("stop_on_error", True):
                    break
            outputs.append(
                {"id": batch.get("id"), "statements": results, "skipped": len(statements) - len(results)}
            )
        return outputs


# --------------------------------------------------------------------------- DuckDB


def open_duckdb(job: dict, limits: dict):
    for path in job.get("extra_paths", []):
        if isinstance(path, str) and path not in sys.path:
            sys.path.append(path)
    import duckdb

    con = duckdb.connect(
        ":memory:",
        config={
            "threads": 1,
            "memory_limit": f"{int(limits['heap_mb'])}MB",
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
        },
    )
    seed = str(job["dataset_path"]).replace("'", "''")
    con.execute(f"ATTACH '{seed}' AS seed (READ_ONLY)")
    con.execute("COPY FROM DATABASE seed TO memory")
    con.execute("DETACH seed")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


# --------------------------------------------------------------------------- entry point


def handle(job: dict) -> dict:
    limits = {**DEFAULT_LIMITS, **{k: v for k, v in dict(job.get("limits", {})).items() if k in DEFAULT_LIMITS}}
    engine = job.get("engine", "sqlite")
    if engine not in ("sqlite", "duckdb"):
        raise JobError(f"unsupported engine: {engine}")
    batches = job.get("batches")
    if not isinstance(batches, list) or not batches:
        raise JobError("job has no batches")

    image = None
    if engine == "sqlite" and job.get("dataset_path"):
        with open(str(job["dataset_path"]), "rb") as handle_:
            image = handle_.read()

    restrict_process(limits, limit_memory=(engine == "sqlite"), allow_threads=(engine == "duckdb"))
    deadline = Deadline(int(limits["timeout_ms"]) / 1000)

    if engine == "sqlite":
        con = open_sqlite(image, limits, deadline)
        version = sqlite3.sqlite_version
    else:
        con = open_duckdb(job, limits)
        timer = threading.Timer(max(0.05, deadline.remaining()), con.interrupt)
        timer.daemon = True
        timer.start()
        import duckdb

        version = duckdb.__version__

    runner = Runner(con, engine, limits, deadline)
    batches_out = runner.run_batches(batches)
    return {
        "ok": True,
        "engine": engine,
        "engine_version": version,
        "batches": batches_out,
        "timed_out": deadline.expired,
        "error": None,
    }


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_JOB_BYTES + 1)
        if len(raw) > MAX_JOB_BYTES:
            raise JobError("job is too large")
        result = handle(json.loads(raw))
    except JobError as exc:
        result = {"ok": False, "error": {"type": "JobError", "message": str(exc), "code": None}}
    except MemoryError:
        result = {"ok": False, "error": {"type": "ResourceLimit", "message": "The sandbox ran out of memory.", "code": None}}
    except Exception as exc:  # report, never crash silently
        result = {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc), "code": None}}
    sys.stdout.write(json.dumps(result, separators=(",", ":"), allow_nan=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
