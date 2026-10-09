# Project structure

```text
joinery/
├── joinery/                    Python package
│   ├── __main__.py             command line: serve, build-datasets, export, validate, provision, doctor
│   ├── app.py                  Flask app: routes, input validation, security headers, static client
│   ├── service.py              Platform: runs, explanations, stepper, exercises and plan checks
│   ├── config.py               settings from JOINERY_* environment variables
│   ├── security.py             CSP and security headers, per-client rate limiter
│   ├── grading.py              result comparison and feedback
│   ├── validation.py           runs every example and exercise against an engine
│   ├── provision.py            loads datasets into server engines and creates the sandbox login
│   ├── content/loader.py       curriculum loading, validation and Markdown rendering
│   ├── datasets/
│   │   ├── model.py            Column, Index, Table and Dataset
│   │   ├── generators/         one deterministic generator per dataset
│   │   ├── ddl.py              DDL and INSERT scripts for each dialect
│   │   └── build.py            SQLite and DuckDB images plus a fingerprinted manifest
│   ├── engines/
│   │   ├── base.py             the Engine interface
│   │   ├── embedded.py         SQLite and DuckDB, run through the sandbox
│   │   ├── server.py           PostgreSQL, MySQL and SQL Server
│   │   └── guard.py            statement guard for shared server engines
│   ├── sandbox/
│   │   ├── worker.py           the isolated child process (standard library only)
│   │   └── runner.py           spawns, limits and supervises workers
│   └── sqltools/
│       ├── tokenizer.py        dialect-aware lexical scanner
│       ├── split.py            statement splitter
│       ├── stepper.py          logical-stage decomposition
│       ├── plans.py            plan trees, advice and bytecode notes
│       ├── errors.py           plain-language error explanations
│       └── lint.py             advisory lint rules
├── content/
│   ├── curriculum.yaml         modules and lesson order
│   ├── dialects.yaml           engine reference and feature matrix
│   └── lessons/                26 lessons
├── web/
│   ├── index.html              page template; the build fills in hashed asset names
│   ├── src/                    TypeScript client (api, router, lib, components, views, data)
│   ├── styles/app.css          the whole stylesheet, light and dark
│   ├── static/favicon.svg
│   └── test/                   Node unit tests
├── scripts/build-web.mjs       esbuild bundling
├── tests/                      Python tests; tests/e2e drives the client with Playwright
├── docs/                       these documents and the screenshots
├── .github/                    CI, engines, CodeQL and Dependabot configuration
├── Dockerfile, compose.yaml    container image and local stacks
├── Makefile                    everyday commands
├── pyproject.toml              package metadata and ruff settings
├── package.json, tsconfig.json client tooling
└── requirements*.txt           pinned Python dependencies
```

Generated and local-only paths are ignored by git: `var/` (dataset images), `web/dist/` (the built client) and `node_modules/`.
