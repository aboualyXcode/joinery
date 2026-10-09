# Writing lessons and exercises

Lessons live in `content/lessons/<id>.yaml`. `content/curriculum.yaml` lists the modules and the order of their lessons. Everything is validated at startup and by `python -m joinery validate`.

## A lesson

```yaml
id: joins                        # must match the file name: lowercase words joined by hyphens
title: Joins
module: combining                # a module id from curriculum.yaml
level: beginner                  # beginner, intermediate or advanced
minutes: 30
dataset: joinlab                 # default dataset for examples and exercises
summary: One or two sentences shown in the course index.
objectives:
  - Match rows across tables with `JOIN ... ON`
sections:
  - title: Matching rows across tables
    body: |
      Markdown. Raw HTML is disabled. Fenced ```sql blocks are highlighted.
    widget: {type: join-visualizer}   # optional
    examples:
      - id: join-inner                # unique across the whole curriculum
        title: Players with their team
        sql: |
          SELECT p.name, t.name FROM players AS p JOIN teams AS t ON t.id = p.team_id;
        portable: true                # plain standard SQL: also validated on other engines
        expect: {rows: 5}             # optional: row count of the last statement
        mode: steps                   # optional: run (default), steps or plan as the primary button
        dataset: shop                 # optional: overrides the lesson dataset
        setup: CREATE INDEX ...;      # optional: runs first (used by plan examples)
        variants:                     # optional: per-dialect SQL shown in tabs
          mysql: |
            SELECT ...
exercises:
  - id: joins-never-ordered
    title: Customers who never ordered
    dataset: shop
    prompt: Markdown describing exactly which columns to return.
    starter: SELECT ...               # must NOT pass; validation checks this
    solution: SELECT ...              # must pass; never sent to the browser unless requested
    check: {order_matters: false}     # see below
    hints:
      - "Inline Markdown, revealed one at a time."
dialect_notes:
  postgres: Markdown about how PostgreSQL differs.
references:
  - title: SQLite join syntax
    url: https://www.sqlite.org/syntax/join-clause.html
```

Quote any list item that contains a colon followed by a space, or YAML reads it as a mapping.

## Checks

| Option | Effect |
|---|---|
| `mode: result` (default) | Compares the result of the last statement that returns rows with the solution's. |
| `mode: state` with `verify: <query>` | Runs the learner's script, then `verify`, and compares that with running the solution followed by `verify`. Use it for INSERT, UPDATE, DELETE and DDL. |
| `order_matters: true` | Rows must be in the solution's order. Only use it when the prompt asks for an order. |
| `check_names: true` | Column names must match too (case-insensitively). State the names in the prompt. |
| `plan: {searched: [orders]}` | After the result matches, the plan must reach each listed table with an index SEARCH. Use it for performance exercises, where a slow query returns the same rows. |

Numbers compare with six-decimal tolerance, and integers equal their floating-point twins. Write prompts that pin down columns, filters and rounding, and give each solution a deterministic result: add tie-breakers whenever you use `LIMIT`.

## Widgets

| Type | What it shows |
|---|---|
| `processing-order` | A query numbered by evaluation order, with a live stepper |
| `join-visualizer` | The join lab |
| `isolation-simulator` | The transaction isolation simulator |
| `index-lab` | The index lab |
| `query-journey` | Parser to storage, for a query the learner types |
| `erd` | The diagram of the lesson's dataset |

## Workflow

1. Write the lesson and add its id to `curriculum.yaml`.
2. Run `python -m joinery validate --lesson <id>` until it reports OK.
3. Run `make dev` and read the lesson in the browser. Run each example, try each exercise's starter, hints and solution.
4. Run `make check`.

Style: write for a working developer, explain *why* before *how*, use the sample data's story, and prefer short sections with an example each. Cite the engine's official documentation in `references`.
