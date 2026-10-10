# Changelog

## Unreleased

- Explore: an engine map of 19 components with five animated flows; a failure map of 33 failures traced from where they start to where you notice them, with symptom fans, a paste-a-message matcher, 16 live reproductions and 10 side-by-side comparisons; a query map; and a relationship explorer with a join path finder
- Visualize in every editor: bottlenecks, the dependency graph with failure propagation, rows kept per stage shaded by work, and the plan as a tree
- Every error shows where it starts and links to its trace; failing scripts show a statement timeline
- 18 more lesson sections carry a diagram
- `POST /api/visualize`, `GET /api/explore` and `python -m joinery snapshot`
- A static preview published to GitHub Pages

## 0.1.0 (2026-10-09)

First release.

- A 26-lesson SQL course in six modules with 126 runnable examples and 66 graded exercises
- A playground, a logical-order stepper, execution plans with index advice and annotated bytecode, error explanations and lint warnings
- Join, isolation, index and query-journey labs, entity relationship diagrams and a dialect reference
- Five deterministic sample datasets with downloadable scripts for SQLite, PostgreSQL, MySQL, SQL Server and DuckDB
- A process sandbox for SQLite and DuckDB; experimental PostgreSQL, MySQL and SQL Server engines
- Docker, Compose, CI, CodeQL and Dependabot configuration
