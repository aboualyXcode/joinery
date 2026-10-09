# Testing

Joinery is tested at five levels. All of them run in CI; the commands below run them locally.

| Level | Command | What it covers |
|---|---|---|
| Python unit and integration | `python -m unittest discover -s tests -t .` | Tokenizer and splitter, sandbox and its security limits, datasets and exports, engines (server engines through a fake driver), stepper, plans, errors, lint, grading, the content loader, the HTTP API, headers and rate limiting |
| Curriculum | `python -m joinery validate` | Every lesson example runs (or fails with its expected error and returns its expected row count), every reference solution passes, and every starter fails |
| TypeScript | `npm run typecheck` and `npm test` | Strict type check of the client and tests; Node's test runner covers the tokenizer, join logic, isolation scenarios, storage, routing and formatting |
| Browser | `make e2e` | Playwright drives the built client in Chromium: stepping, examples, exercises and progress, the playground's error fixes, plans and stages, ERDs, every lab, the reference filter, keyboard shortcuts, theming, and mobile layouts without horizontal scrolling |
| Engines | the `Engines` workflow | Provisions real DuckDB, PostgreSQL 18, MySQL 9.7 and SQL Server 2025 and validates the examples' dialect variants |

The browser tests fail on any console error, which includes Content Security Policy violations, so a CSP regression cannot slip through. Set `JOINERY_SCREENSHOTS=1` alongside `JOINERY_E2E=1` to refresh the images in `docs/screenshots`.

## Writing tests

- Python tests use the standard library's `unittest`, so they need no extra packages; `pytest` can run them too.
- `tests/helpers.py` has `make_image()` for building small SQLite fixtures and `run()` for executing SQL in the real sandbox.
- Server engines are tested with the fake DB-API connection in `tests/test_engines.py`; add a case there whenever the transaction or savepoint handling changes.
- Content needs no unit tests of its own: `validate` checks every example and exercise, and `tests/test_content.py` runs it as part of the suite.

## Linting and audits

- `ruff check joinery tests scripts` (pyflakes, pycodestyle and bugbear rules; see `pyproject.toml`)
- `tsc` in strict mode with unused-code checks acts as the TypeScript linter
- `pip-audit` and `npm audit` check dependencies; CodeQL scans Python and TypeScript; Dependabot keeps pins current

## Environment notes

The suite was developed against Python 3.12 with SQLite 3.45.1 and Node.js 22. CI runs Python 3.12, 3.13 and 3.14 and Node.js 24. The sandbox relies on POSIX resource limits, so run the tests on Linux or macOS (or WSL 2).
