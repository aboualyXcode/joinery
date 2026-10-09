# Contributing

Thank you for helping make Joinery better. Lessons, exercises, bug fixes, engine support and accessibility improvements are all welcome.

## Getting started

```sh
python3 -m venv .venv && . .venv/bin/activate
make setup
make dev
```

## Before you open a pull request

1. `make check` passes: ruff, the type check, Python and TypeScript tests, curriculum validation and the build.
2. `make e2e` passes if you changed the client.
3. New behaviour has tests. Sandbox and security changes need a test that attempts the abuse they prevent.
4. Content changes pass `python -m joinery validate`, and you have read the lesson in the browser.
5. Documentation reflects the change.

Write commit messages as a short imperative summary ("Add a lesson on window frames"), with a body explaining why when it is not obvious.

## Guides

- [Writing lessons and exercises](docs/authoring-lessons.md)
- [Adding a dataset](docs/adding-datasets.md)
- [Adding an engine or dialect](docs/adding-dialects.md)
- [Architecture](docs/architecture.md) and [security model](docs/security.md)

## Reporting problems

Open an issue with the steps to reproduce, what you expected and what happened. For anything that could affect the safety of a deployment, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
