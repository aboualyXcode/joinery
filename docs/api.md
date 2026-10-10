# HTTP API

All endpoints are under `/api`, accept and return JSON, and send `Cache-Control: no-store`. POST bodies must use `Content-Type: application/json` and are limited to 256 KiB. Errors look like `{"error": {"type": "...", "message": "..."}}` with a 4xx or 5xx status.

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Liveness: version and enabled engines |
| `GET /api/meta` | Engines, datasets and limits |
| `GET /api/curriculum` | Modules and lesson summaries |
| `GET /api/lessons/<id>` | A lesson with rendered HTML, examples and exercises (without solutions) |
| `GET /api/datasets/<id>` | Schema, row counts and ERD positions |
| `GET /api/datasets/<id>/export?dialect=postgres` | A script that recreates the dataset |
| `GET /api/dialects` | The engine reference and feature matrix |
| `POST /api/run` | Run a script |
| `POST /api/explain` | Plan, advice, bytecode and work metrics for one statement |
| `POST /api/steps` | Logical stages with intermediate results |
| `POST /api/exercises/<id>/check` | Grade an answer |
| `GET /api/exercises/<id>/solution` | The reference solution |

## Run

```http
POST /api/run
{"sql": "SELECT status, count(*) AS orders FROM orders GROUP BY status", "dataset": "shop", "engine": "sqlite"}
```

```json
{
  "engine": "sqlite", "engine_version": "3.45.1", "dataset": "shop",
  "statements": [{
    "index": 0, "sql": "SELECT status, count(*) AS orders FROM orders GROUP BY status", "kind": "rows",
    "columns": ["status", "orders"], "rows": [["cancelled", 145], ["delivered", 1472]],
    "row_count": 6, "truncated": false, "changes": 0, "elapsed_ms": 0.9, "vm_steps": 22900, "error": null
  }],
  "skipped": 0, "error": null, "warnings": [], "elapsed_ms": 41.2
}
```

When a statement fails, its `error` has `type`, `message`, `code` and an `explanation` with `title`, `detail`, `hint`, `suggestions` and the `position` of the offending text.

## Explain

`{"sql": "...", "dataset": "shop", "setup": "CREATE INDEX i ON orders (customer_id)"}` returns `tree` (nodes with `label`, `kind`, `table`, `index`, `severity`, `note`, `children`), `advice`, `bytecode`, `bytecode_summary` and `metrics` (`row_count`, `elapsed_ms`, `vm_steps`). The statement is executed for the metrics and any changes it makes are undone.

## Steps

`{"sql": "...", "dataset": "shop"}` returns `supported`, `written_order`, `logical_order` and `stages`. Each stage has `clause`, `title`, `description`, `sql`, `columns`, `rows`, `row_count`, and for filter stages `kept` (one boolean per displayed row), `kept_count` and `input_count`.

## Check

`{"sql": "..."}` returns `passed`, `summary`, `details`, `hint`, `expected` and `actual` previews, `warnings`, and `error` if the SQL failed.

## Explore data

`GET /api/explore` returns `content/explore.yaml` as loaded and validated: the engine map (`stations` and `edges`), the `flows`, the `failures` with their paths, message patterns, demos and comparisons, the `symptoms`, the query-map `queries` and the lab and playground `presets`.

## Visualize

`POST /api/visualize` takes the same body as Steps, for one statement, and returns everything the query map draws:

- `dependencies`: `nodes` of kind `table`, `cte`, `subquery`, `function`, `missing` or `query`, each with `rows`, `work`, and `status` (`ok`, `error` where a failure starts, `blocked` downstream of one); subqueries also carry `role` (`derived`, `scalar`, `in`, `not-in`, `exists`, `not-exists`) and `correlated`. `edges` are `reads`, `filters`, `value`, `writes` or `recursive`, with `broken` when their source failed. Statements other than `SELECT`, `INSERT`, `UPDATE` and `DELETE` return `supported: false` and a `reason`.
- `steps`: the Steps response, with `vm_steps` per stage.
- `plan`: the Explain response, or an `error`.
