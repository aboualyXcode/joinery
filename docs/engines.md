# Engines and dialects

Joinery runs SQL on pluggable engines. SQLite is always available and is the engine every lesson and exercise is validated on. DuckDB, PostgreSQL, MySQL and SQL Server are optional and experimental.

## Status

| Engine | Target versions | Driver | Status |
|---|---|---|---|
| SQLite | 3.45 or later (current release 3.53) | Python's `sqlite3` | Verified by the full test suite and curriculum validation |
| DuckDB | 1.5.x (1.4 is the LTS; 2.0 is planned for October 2026) | `duckdb` 1.5.6 | Experimental: unit-tested here, validated by the engines workflow |
| PostgreSQL | 18 (19 is in beta) | `psycopg` 3.3 | Experimental: orchestration unit-tested with a fake driver, validated by the engines workflow |
| MySQL | 8.4 LTS and 9.7 LTS | `PyMySQL` 1.1 | Experimental, as above |
| SQL Server | 2025 (17.x) | `mssql-python` 1.15 | Experimental, as above |

"Experimental" means the code is complete but has not yet been run against real servers in this repository's history. The [engines workflow](../.github/workflows/engines.yml) starts each server as a service container, provisions the datasets and runs `python -m joinery validate --engine <name>`. Once it is green, the engine has been validated.

## Enabling engines

| Engine | How to enable |
|---|---|
| SQLite | Always on |
| DuckDB | `pip install duckdb==1.5.6`; `JOINERY_ENGINES=auto` (the default) picks it up and builds `.duckdb` images next to the SQLite ones |
| PostgreSQL | Provision, then set `JOINERY_POSTGRES_DSN=postgresql://joinery_sandbox:PASSWORD@host:5432/joinery` |
| MySQL | Provision, then set `JOINERY_MYSQL_DSN=mysql://joinery_sandbox:PASSWORD@host:3306` |
| SQL Server | Provision, then set `JOINERY_MSSQL_DSN=Server=host,1433;UID=joinery_sandbox;PWD=PASSWORD;Encrypt=yes;TrustServerCertificate=yes` |

Install the server drivers with `pip install -r requirements-engines.txt`. Provisioning creates the `joinery_sandbox` login and loads every dataset, using an administrator connection:

```sh
export JOINERY_SANDBOX_PASSWORD='choose-a-strong-password'
python -m joinery provision --engine postgres --admin-dsn postgresql://postgres:ADMIN@localhost:5432/joinery
python -m joinery provision --engine mysql --admin-dsn mysql://root:ADMIN@localhost:3306
python -m joinery provision --engine mssql --admin-dsn "Server=localhost,1433;UID=sa;PWD=ADMIN;Encrypt=yes;TrustServerCertificate=yes"
```

The Compose `engines` profile does all of this for you: `docker compose --profile engines up --build`.

## How datasets map to each engine

| Engine | Layout |
|---|---|
| SQLite | One image file per dataset, deserialized into memory for every run |
| DuckDB | One `.duckdb` file per dataset, copied into an in-memory database for every run |
| PostgreSQL | One database, one schema per dataset; `search_path` selects it |
| MySQL | One database per dataset, named `joinery_<dataset>` |
| SQL Server | One database per dataset, named `joinery_<dataset>` |

`python -m joinery export --dataset shop --dialect postgres` prints the script provisioning uses; the Datasets page offers the same scripts for download. Types are mapped per engine: for example, `decimal(10,2)` becomes `numeric(10,2)` in PostgreSQL, timestamps become `DATETIME` in MySQL and `DATETIME2(0)` in SQL Server, and surrogate keys become identity columns, `AUTO_INCREMENT` or sequences.

## Behaviour per engine

| | SQLite and DuckDB | PostgreSQL, MySQL and SQL Server |
|---|---|---|
| Isolation | A private copy per run, in a separate process | One transaction per run, always rolled back |
| DDL | Allowed | Allowed in PostgreSQL and SQL Server (rolled back); MySQL allows only temporary tables |
| Transaction control | Allowed (`BEGIN`, `COMMIT`, savepoints) | Savepoints only; Joinery owns the transaction |
| Timeout | Progress handler, CPU limit and kill | `statement_timeout`, `max_execution_time` or the driver timeout |
| Plans | Tree, advice and bytecode (SQLite); text (DuckDB) | Tree and advice (PostgreSQL JSON); text (MySQL `EXPLAIN FORMAT=TREE`, SQL Server `SHOWPLAN_TEXT`) |

## Dialects in lessons

Each example's `sql` is written for SQLite. An example marked `portable: true` is plain standard SQL that every engine should accept; otherwise it carries `variants` for the dialects where syntax differs. Validation runs, for each engine, the variant if there is one, or the base SQL if the example is portable, and skips the rest. Exercises are graded on SQLite.

The [Reference page](../content/dialects.yaml) compares 24 features across the five engines, including row limiting, outer and lateral joins, set operations, recursive CTEs, window functions, `QUALIFY`, `FILTER`, `RETURNING`, upserts and `MERGE`, string concatenation, quoting, booleans, regular expressions, JSON, date truncation, series generation, string aggregation, `IS DISTINCT FROM`, transactional DDL, default isolation levels, partial indexes, generated columns and plan inspection. It was reviewed against SQLite 3.53, PostgreSQL 18, MySQL 9.7, SQL Server 2025 and DuckDB 1.5 in October 2026.
