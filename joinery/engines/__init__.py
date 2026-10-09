"""Pluggable SQL engines behind one batch-execution interface."""

from __future__ import annotations

from ..config import Settings
from ..sandbox import SandboxRunner
from .base import Engine, failure
from .embedded import DuckdbEngine, SqliteEngine
from .server import MssqlEngine, MysqlEngine, PostgresEngine, ServerEngine

ENGINE_ORDER = ("sqlite", "duckdb", "postgres", "mysql", "mssql")


def build_engines(settings: Settings, runner: SandboxRunner, manifest: dict) -> dict[str, Engine]:
    """Instantiate the enabled engines that can actually run here."""
    limits = settings.sandbox_limits
    engines: dict[str, Engine] = {}
    for engine_id in ENGINE_ORDER:
        if engine_id not in settings.engines:
            continue
        if engine_id == "sqlite":
            engines[engine_id] = SqliteEngine(runner, settings.data_dir, manifest, limits)
        elif engine_id == "duckdb":
            duck = DuckdbEngine(runner, settings.data_dir, manifest, limits)
            if duck.available():
                engines[engine_id] = duck
        elif engine_id == "postgres" and settings.postgres_dsn:
            engines[engine_id] = PostgresEngine(settings.postgres_dsn, limits)
        elif engine_id == "mysql" and settings.mysql_dsn:
            engines[engine_id] = MysqlEngine(settings.mysql_dsn, limits)
        elif engine_id == "mssql" and settings.mssql_dsn:
            engines[engine_id] = MssqlEngine(settings.mssql_dsn, limits)
    return engines


__all__ = ["DuckdbEngine", "Engine", "MssqlEngine", "MysqlEngine", "PostgresEngine", "ServerEngine",
           "SqliteEngine", "build_engines", "failure"]
