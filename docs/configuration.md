# Configuration

Joinery reads its settings from environment variables once, at startup. Invalid values stop the server with a message naming the variable.

| Variable | Default | Meaning |
|---|---|---|
| `JOINERY_ENGINES` | `auto` | Comma-separated engines to enable: `sqlite`, `duckdb`, `postgres`, `mysql`, `mssql`. `auto` enables SQLite, DuckDB when the `duckdb` package is installed, and each server engine whose DSN is set. SQLite must stay enabled because exercises are graded on it. |
| `JOINERY_TIMEOUT_MS` | `3000` | Time limit for one run, 100 to 30,000. The stepper gets twice as long because it runs one query per stage. |
| `JOINERY_MAX_ROWS` | `500` | Rows returned per statement, 10 to 5,000. Row counts are still exact up to 100,000. |
| `JOINERY_MAX_SQL_CHARS` | `20000` | Longest accepted SQL text, 100 to 100,000. |
| `JOINERY_MAX_CONCURRENCY` | `4` | Sandbox processes running at once per server process, 1 to 64. Extra requests wait up to 10 seconds, then get HTTP 503. |
| `JOINERY_RATE_LIMIT` | `120` | POST requests per minute per client; `0` disables the limiter. |
| `JOINERY_TRUST_PROXY` | `false` | Trust one `X-Forwarded-For` and `X-Forwarded-Proto` hop. Enable only behind a reverse proxy you control. |
| `JOINERY_WEB_FONTS` | `true` | Load Atkinson Hyperlegible from Google Fonts. With `false`, the page uses system fonts and the CSP allows no third-party origins. |
| `JOINERY_LOG_SQL` | `false` | Reserved for logging submitted SQL; Joinery logs request metadata only. |
| `JOINERY_DATA_DIR` | `var/datasets` | Where dataset images are built and read. The Docker image prebuilds them so the container can be read-only. |
| `JOINERY_CONTENT_DIR` | `content` | The curriculum directory. |
| `JOINERY_WEB_DIR` | `web/dist` | The built client. If it is missing, `/` explains how to build it and the API still works. |
| `JOINERY_POSTGRES_DSN` | unset | Connection URL for the PostgreSQL sandbox role. |
| `JOINERY_MYSQL_DSN` | unset | `mysql://user:password@host:port` for the MySQL sandbox user. |
| `JOINERY_MSSQL_DSN` | unset | ODBC-style connection string for the SQL Server sandbox login, without `Database=`. |
| `JOINERY_SANDBOX_PASSWORD` | unset | Password that `python -m joinery provision` sets for the sandbox login. |

The sandbox's internal limits (512 MiB address space, 192 MiB SQLite heap, 32 MiB of database growth, 1 MB values, 50 statements per run) are constants in `joinery/sandbox/worker.py`; see [security.md](security.md) before changing them.

`python -m joinery doctor` prints the Python and SQLite versions, whether the sandbox is supported, whether the client is built and which engine drivers are installed.
