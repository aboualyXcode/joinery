# Joinery

**Learn SQL by running it.** Joinery is an interactive SQL course, playground and reference. Every example executes on a real database engine, every stage of a query shows the rows it keeps and the rows it drops, and every exercise is graded against the actual result.

[![CI](https://github.com/aboualyXcode/joinery/actions/workflows/ci.yml/badge.svg)](https://github.com/aboualyXcode/joinery/actions/workflows/ci.yml)
[![Engines](https://github.com/aboualyXcode/joinery/actions/workflows/engines.yml/badge.svg)](https://github.com/aboualyXcode/joinery/actions/workflows/engines.yml)
![Lessons](https://img.shields.io/badge/lessons-26-1f5c4e)
![Exercises](https://img.shields.io/badge/graded%20exercises-66-1f5c4e)
![Runtime JavaScript dependencies](https://img.shields.io/badge/runtime%20JS%20dependencies-none-1f5c4e)

![The home page stepping through a query: the WHERE stage highlights the rows it keeps and strikes out the rows it removes](docs/screenshots/home-stepper.png)

SQL is written `SELECT` first but evaluated `FROM` first. Joinery makes that order visible: press **Step through** on any query and it runs one real query per logical stage, from the join to the limit, and shows which rows survive each one. Then it shows you how the engine executed it, operator by operator and instruction by instruction.

## Contents

- [Quick start](#quick-start)
- [What is inside](#what-is-inside)
- [The course](#the-course)
- [Engines and dialects](#engines-and-dialects)
- [How it works](#how-it-works)
- [Security](#security)
- [Development](#development)
- [Extending Joinery](#extending-joinery)
- [Project structure](#project-structure)
- [What has been verified](#what-has-been-verified)
- [Credits](#credits)

## Quick start

**With Docker** (nothing else to install):

```sh
git clone https://github.com/aboualyXcode/joinery.git
cd joinery
docker compose up --build
```

Open <http://localhost:8000>. To add PostgreSQL 18, MySQL 9.7 and SQL Server 2025 as extra engines (experimental), run `docker compose --profile engines up --build` and open <http://localhost:8001>.

**Locally**, with Python 3.12+ and Node.js 22.18+ on Linux or macOS:

```sh
python3 -m venv .venv && . .venv/bin/activate
make setup      # Python and Node dev dependencies, plus Chromium for browser tests
make dev        # builds the client and datasets, serves http://127.0.0.1:8000
```

Windows users can run Joinery through Docker or WSL 2: the sandbox relies on POSIX resource limits.

## What is inside

- **A course of 26 lessons** in six modules, from `SELECT` to ELT pipelines, with 126 runnable examples and 66 graded exercises.
- **A playground** with a highlighting editor, five sample datasets, a schema browser and keyboard shortcuts (<kbd>Ctrl</kbd>+<kbd>Enter</kbd> runs, <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Enter</kbd> steps through).
- **The stepper**: a query split into its logical stages (`WITH`, `FROM`/`JOIN`, `WHERE`, `GROUP BY`, `HAVING`, `SELECT`, `DISTINCT`, `ORDER BY`, `LIMIT`), each executed for real. Filter stages highlight kept rows and strike through removed ones. `UPDATE` and `DELETE` statements preview the rows they will touch.
- **Execution plans** as a tree, with index advice, work counts, and SQLite's bytecode program annotated opcode by opcode, loops marked.
- **Errors explained**: plain-language causes, likely fixes and "did you mean" suggestions you can apply with one click, plus lint warnings for traps such as `= NULL`, `NOT IN` with NULLs, comma joins and index-defeating predicates.
- **Grading that teaches**: results are compared with tolerance and order rules, and the feedback says whether you have too many rows, the wrong columns, wrong values or the wrong order. Performance exercises also check that the plan uses an index.
- **Labs**: a join lab that draws which rows pair up for every join type, an isolation simulator for dirty reads, lost updates, phantoms and write skew, an index lab that compares plans with and without the index you design, and a query journey from parser to storage.
- **Entity relationship diagrams** for every dataset, and **downloadable scripts** that load each dataset into SQLite, PostgreSQL, MySQL, SQL Server or DuckDB.
- **A dialect reference**: 24 features compared across five engines, reviewed against the releases current in October 2026.

| | |
|---|---|
| ![Grouping, stage by stage, in the aggregation lesson](docs/screenshots/lesson-steps.png) | ![A query plan with index advice in the playground, dark theme](docs/screenshots/playground-plan-dark.png) |
| ![The shop dataset's entity relationship diagram](docs/screenshots/dataset-erd.png) | ![The join lab drawing a left join](docs/screenshots/join-lab.png) |

## The course

| Module | Lessons |
|---|---|
| 1. Foundations | Selecting columns and computing values, Filtering rows with WHERE, Sorting and paging, Data types, dates and text, Aggregating with GROUP BY and HAVING |
| 2. Combining data | Joins, Subqueries and EXISTS, Common table expressions, Set operations, Window functions |
| 3. Changing data and schema | Inserting, updating and deleting, Designing schemas, Constraints and data integrity, Indexes, Transactions and isolation |
| 4. Advanced analytics | Recursive queries, Working with JSON, Time series, Funnels, experiments, cohorts and pivots |
| 5. Performance | How a database runs a query, Reading execution plans, Optimizing queries |
| 6. Production SQL | ELT pipelines and data quality, SQL security, Testing, migrations and deployment, Troubleshooting |

Each lesson cites the official documentation and ends with notes on how PostgreSQL, MySQL, SQL Server and DuckDB differ. Examples carry per-dialect variants where the syntax differs.

The five datasets are fictional and generated deterministically, about 57,000 rows in total:

| Dataset | Domain | Highlights |
|---|---|---|
| `shop` | An online tea and coffee shop | Orders, line items with historical prices, payments and refunds, reviews, stock, a category tree, an org chart |
| `bank` | A retail bank | A year of signed transactions, transfers between accounts, weekday-only FX rates for as-of joins, suspicious bursts |
| `analytics` | Product analytics | Sessions of clickstream events with JSON properties, campaigns, an A/B test, sensor readings with gaps |
| `pipeline` | Data engineering | Raw text exports with every kind of mess, a type 2 customer dimension, a fact table, a run log with watermarks |
| `joinlab` | Join practice | Four teams and seven players, built so every join type returns something different |

## Engines and dialects

| Engine | Status | How it runs |
|---|---|---|
| SQLite 3.45+ | Verified: the full test suite and every lesson run on it | Process sandbox, private in-memory copy per run |
| DuckDB 1.5 | Experimental, validated by the engines workflow | Same process sandbox, external access disabled and configuration locked |
| PostgreSQL 18 | Experimental, validated by the engines workflow | Low-privilege role, one transaction per run, always rolled back |
| MySQL 8.4 and 9.7 LTS | Experimental, validated by the engines workflow | As above; DDL is limited to temporary tables because MySQL commits DDL implicitly |
| SQL Server 2025 | Experimental, validated by the engines workflow | As above, using Microsoft's `mssql-python` driver |

SQLite needs nothing extra and is always on. The others are enabled by installing their driver (DuckDB) or setting a connection string (the server engines). Lessons and grading run on SQLite; the other engines run the examples' dialect variants. See [docs/engines.md](docs/engines.md).

## How it works

```mermaid
flowchart LR
  B["Browser client<br/>TypeScript, no framework"] -->|JSON over HTTP| A["Flask API<br/>validation, CSP, rate limit"]
  A --> S["Service layer<br/>runs, plans, stepper, grading"]
  S --> C["Curriculum<br/>YAML and Markdown"]
  S --> E{"Engine"}
  E -->|"fresh child process"| W["Sandbox worker<br/>SQLite or DuckDB in memory"]
  W --> I[("Dataset images")]
  E -->|"one rolled-back transaction"| R[("PostgreSQL, MySQL, SQL Server")]
```

The browser never talks to a database. It sends SQL to the API, which hands each run to an engine. For SQLite and DuckDB that means a brand-new, resource-limited Python process that loads a pristine copy of the dataset, runs the statements and exits. The stepper, plans and grading are built from the same primitive: batches of statements executed by an engine. Details are in [docs/architecture.md](docs/architecture.md).

## Security

Submitted SQL is treated as untrusted code. Each SQLite run executes in a separate interpreter started in isolated mode with an empty environment. Before any SQL runs, the worker caps CPU time, memory, file size (zero, so nothing can be written to disk), open files and process creation. It then puts SQLite in defensive mode with lowered run-time limits, a heap limit, a database size cap and a wall-clock deadline. An authorizer refuses `ATTACH`, extension loading and every `PRAGMA` outside a read-only allowlist. The HTTP layer adds a strict Content Security Policy, request size limits, input validation and per-client rate limiting. The test suite attempts each escape: attaching files, `VACUUM INTO` writes, dangerous pragmas, extension loading, runaway recursion, huge allocations and database growth. Read [docs/security.md](docs/security.md) for the threat model and [SECURITY.md](SECURITY.md) to report a vulnerability.

## Development

| Command | What it does |
|---|---|
| `make setup` | Install Python and Node dev dependencies and the Playwright Chromium browser |
| `make dev` | Build the client and datasets, then serve with auto-reload |
| `make test` | Python unit, integration and security tests, plus TypeScript unit tests |
| `make validate` | Run every lesson example and exercise against SQLite |
| `make e2e` | Browser tests in Chromium |
| `make lint` | `ruff` and the TypeScript type check |
| `make audit` | `pip-audit` and `npm audit` |
| `make check` | Everything CI runs except the browser tests |
| `npm run watch` | Rebuild the client on every change |

`python -m joinery --help` lists the command line: `serve`, `build-datasets`, `export`, `validate`, `provision` and `doctor`. Testing is described in [docs/testing.md](docs/testing.md), configuration in [docs/configuration.md](docs/configuration.md), and deployment in [docs/deployment.md](docs/deployment.md).

## Extending Joinery

- [Writing lessons and exercises](docs/authoring-lessons.md): YAML format, check modes, plan checks, widgets and dialect variants.
- [Adding a dataset](docs/adding-datasets.md): deterministic generators, ERD layout and exports.
- [Adding an engine or dialect](docs/adding-dialects.md): the engine interface, the statement guard and provisioning.
- [The HTTP API](docs/api.md): every endpoint with examples.

## Project structure

```text
joinery/            Python package: API, service layer, engines, sandbox, datasets, SQL tools
  sandbox/          worker.py (the isolated process) and runner.py (spawns and supervises it)
  engines/          SQLite and DuckDB (sandboxed), PostgreSQL, MySQL and SQL Server (server engines)
  sqltools/         tokenizer, splitter, stepper, plan analysis, error explanations, lint rules
  datasets/         schema model, generators, image builder and dialect DDL export
  content/          curriculum loader and validator
content/            curriculum.yaml, 26 lessons, dialects.yaml
web/                TypeScript client, stylesheet and unit tests
tests/              Python tests; tests/e2e drives the client in Chromium
docs/               architecture, security, engines, testing, deployment and authoring guides
```

The full annotated tree is in [docs/project-structure.md](docs/project-structure.md).

## What has been verified

- The Python suite, curriculum validation (126 examples and 66 exercises on SQLite), the TypeScript type check, the Node unit tests, the production build and the Chromium browser tests all pass on Python 3.12, SQLite 3.45.1 and Node.js 22.
- DuckDB, PostgreSQL, MySQL and SQL Server support is implemented and unit-tested with a fake driver. It is validated against real servers by the engines workflow, which needs a GitHub runner because those servers were not available where this project was built. Treat those engines as experimental until that workflow is green.
- The Docker image and Compose stack follow the documented best practices, and CI builds and smoke-tests the image, but they have not been built outside CI.

## Credits

Created by [Mahmoud Aboualy](https://github.com/aboualyXcode).

Typefaces: Atkinson Hyperlegible Next and Atkinson Hyperlegible Mono by the Braille Institute, loaded from Google Fonts with system fonts as the fallback (set `JOINERY_WEB_FONTS=false` to stay fully self-hosted). Copperleaf, Tidewater Bank and every person in the sample data are fictional.

SQLite is in the public domain. PostgreSQL, MySQL, SQL Server and DuckDB are trademarks of their respective owners. Joinery is independent and not affiliated with or endorsed by any of them.
