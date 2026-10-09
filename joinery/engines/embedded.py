"""Embedded engines that run inside the process sandbox: SQLite and DuckDB."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from ..sandbox import SandboxRunner
from .base import Engine, failure


class SqliteEngine(Engine):
    id = "sqlite"
    name = "SQLite"
    dialect = "sqlite"

    def __init__(self, runner: SandboxRunner, data_dir: Path, manifest: dict, limits: dict) -> None:
        self.runner = runner
        self.data_dir = data_dir
        self.manifest = manifest
        self.limits = limits

    def version(self) -> str:
        return sqlite3.sqlite_version

    def image(self, dataset_id: str) -> Path | None:
        entry = self.manifest["datasets"].get(dataset_id)
        return self.data_dir / entry["sqlite"] if entry else None

    def run(self, dataset_id: str, batches: list[dict], *, timeout_ms: int) -> dict:
        image = self.image(dataset_id)
        if image is None:
            return failure("UnknownDataset", f"There is no dataset called {dataset_id}.")
        job = {"engine": "sqlite", "dataset_path": str(image), "limits": self.limits, "batches": batches}
        return self.runner.run(job, timeout_ms=timeout_ms)


class DuckdbEngine(Engine):
    id = "duckdb"
    name = "DuckDB"
    dialect = "duckdb"
    experimental = True

    def __init__(self, runner: SandboxRunner, data_dir: Path, manifest: dict, limits: dict) -> None:
        self.runner = runner
        self.data_dir = data_dir
        self.manifest = manifest
        self.limits = limits
        spec = importlib.util.find_spec("duckdb")
        self._package_root = str(Path(spec.origin).resolve().parent.parent) if spec and spec.origin else None

    def available(self) -> bool:
        return self._package_root is not None and all(
            entry.get("duckdb") for entry in self.manifest["datasets"].values()
        )

    def version(self) -> str:
        try:
            from importlib.metadata import version

            return version("duckdb")
        except Exception:
            return "not installed"

    def run(self, dataset_id: str, batches: list[dict], *, timeout_ms: int) -> dict:
        entry = self.manifest["datasets"].get(dataset_id)
        if not entry or not entry.get("duckdb") or not self.available():
            return failure("EngineUnavailable", "DuckDB is not installed on this server.")
        job = {
            "engine": "duckdb",
            "dataset_path": str(self.data_dir / entry["duckdb"]),
            "extra_paths": [self._package_root],
            "limits": self.limits,
            "batches": batches,
        }
        return self.runner.run(job, timeout_ms=timeout_ms)
