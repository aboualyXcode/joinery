"""Shared helpers for the test suite."""

from __future__ import annotations

import os
import sqlite3
import tempfile

from joinery.sandbox import SandboxRunner

_IMAGE_DIR = tempfile.mkdtemp(prefix="joinery-tests-")
RUNNER = SandboxRunner(max_concurrency=4)


def make_image(script: str, name: str = "fixture") -> str:
    """Create a small SQLite database image and return its path."""
    con = sqlite3.connect(":memory:")
    con.executescript(script)
    path = os.path.join(_IMAGE_DIR, f"{name}.sqlite")
    with open(path, "wb") as handle:
        handle.write(con.serialize())
    con.close()
    return path


FIXTURE = make_image(
    """
    CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, score REAL);
    INSERT INTO t (name, score) VALUES ('ada', 9.5), ('grace', 8.25), ('linus', NULL);
    """
)


def run(sql: str, *, timeout_ms: int = 2000, dataset: str | None = FIXTURE, **batch) -> dict:
    job = {"engine": "sqlite", "dataset_path": dataset, "batches": [{"id": "main", "sql": sql, **batch}]}
    return RUNNER.run(job, timeout_ms=timeout_ms)


def statements(result: dict) -> list[dict]:
    assert result["ok"], result
    return result["batches"][0]["statements"]
