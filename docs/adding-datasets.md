# Adding a dataset

A dataset is a Python module in `joinery/datasets/generators/` with a `build()` function that returns a `Dataset`: tables, typed columns, keys, rows and ERD positions. The same definition produces the SQLite image the sandbox loads, the optional DuckDB file, and the downloadable scripts for every dialect.

## Steps

1. Create `joinery/datasets/generators/<id>.py`. Generate rows with a seeded `random.Random`, never the clock, and iterate over lists rather than sets so the output is identical on every run. `common.py` has names, cities and helpers.
2. Describe each table with `Table(name, doc, columns, rows, indexes, position)` and each column with `Column(name, type, ...)`. Types are `integer`, `bigint`, `decimal(p,s)`, `varchar(n)`, `text`, `boolean`, `date`, `timestamp` and `json`. Use `primary_key`, `identity` (a surrogate key new rows may omit), `unique`, `references="table.column"`, `check` (portable SQL) and `default`.
3. Order rows so referenced rows come first; self-references must point at earlier rows.
4. Choose ERD positions in canvas units (tables are 236 units wide; each column is 21 units tall).
5. Register the builder in `joinery/datasets/__init__.py`.
6. Run `python -m unittest tests.test_datasets` and `python -m joinery build-datasets`. Images rebuild automatically because the manifest fingerprints the generator code.

The tests check that generation is deterministic, that the image satisfies every foreign key and CHECK constraint, that primary keys are unique and that every dialect's script renders every table. Avoid table and column names that are reserved words in any supported engine (for example `user`, `order`, `plan`, `key`), because the scripts do not quote identifiers.
