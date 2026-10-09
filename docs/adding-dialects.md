# Adding an engine or dialect

## The engine interface

Every engine subclasses `joinery.engines.base.Engine` and implements `run(dataset_id, batches, *, timeout_ms)`. It returns the shape the sandbox worker returns: `{"ok", "engine_version", "batches": [{"id", "statements": [...], "skipped"}], "error"}`, where each statement result has `columns`, `rows`, `row_count`, `changes`, `elapsed_ms` and `error`. A batch is `{"id", "sql", "split", "explain", "analyze", "stop_on_error"}`. Because every engine speaks this shape, runs, plans, the stepper and grading work unchanged.

## Embedded engines

Embedded engines (like SQLite and DuckDB) should run inside the process sandbox. Add an `engine` branch to `joinery/sandbox/worker.py` that opens the engine with its own hardening (no file or network access, no extension loading, memory and thread limits, locked configuration), and an `Engine` subclass in `joinery/engines/embedded.py` that builds the job. Keep the worker importable with `python -I -S`: pass any package path through the job's `extra_paths`.

## Server engines

Server engines subclass `ServerEngine` in `joinery/engines/server.py` and implement:

- `connect()`: connect as the low-privilege sandbox login
- `begin()`: set statement and lock timeouts and select the dataset, then start the transaction
- `savepoint_sql()`: the dialect's savepoint statements
- `explain()`: return `plan_json` (normalized by `sqltools/plans.py`) or `plan_text`
- `server_version()`

The base class wraps each statement in a savepoint, enforces the guard and always rolls back. Then:

1. Add the dialect to `joinery/sqltools/tokenizer.py` (quoting, comments, escapes) and to the guard in `joinery/engines/guard.py`, with tests in `tests/test_guard.py`.
2. Map the logical types and literals in `joinery/datasets/ddl.py`, and add tests to `tests/test_datasets.py`.
3. Add provisioning to `joinery/provision.py`: create the sandbox login with read and write access to the dataset tables only, then load the export.
4. Register the engine in `joinery/engines/__init__.py` and `joinery/config.py` (a `JOINERY_<ENGINE>_DSN` variable).
5. Add the engine to `content/dialects.yaml`, the client's `DIALECT_NAMES`, the dialect notes of lessons where it differs, and `variants` for examples whose syntax differs.
6. Add a job to `.github/workflows/engines.yml` that starts the server as a service, provisions it and runs `python -m joinery validate --engine <id>`.

Mark the engine experimental (`experimental = True`) until that job is green.
