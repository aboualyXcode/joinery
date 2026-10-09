"""Runtime configuration, read once from ``JOINERY_*`` environment variables.

See docs/configuration.md for every setting and its default.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from .sandbox.worker import DEFAULT_LIMITS

ROOT = Path(__file__).resolve().parent.parent
ENGINE_IDS = ("sqlite", "duckdb", "postgres", "mysql", "mssql")
_DSN_VARS = {"postgres": "JOINERY_POSTGRES_DSN", "mysql": "JOINERY_MYSQL_DSN", "mssql": "JOINERY_MSSQL_DSN"}


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _number(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "var" / "datasets"
    content_dir: Path = ROOT / "content"
    web_dir: Path = ROOT / "web" / "dist"
    engines: tuple[str, ...] = ("sqlite",)
    timeout_ms: int = 3000
    max_rows: int = 500
    max_sql_chars: int = 20_000
    max_concurrency: int = 4
    rate_limit: int = 120
    trust_proxy: bool = False
    web_fonts: bool = True
    log_sql: bool = False
    postgres_dsn: str | None = None
    mysql_dsn: str | None = None
    mssql_dsn: str | None = None

    @property
    def sandbox_limits(self) -> dict:
        return {**DEFAULT_LIMITS, "max_rows": self.max_rows, "timeout_ms": self.timeout_ms}

    def with_overrides(self, **changes) -> Settings:
        return replace(self, **changes)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        dsns = {engine: env.get(var) or None for engine, var in _DSN_VARS.items()}
        raw = env.get("JOINERY_ENGINES", "auto").strip().lower()
        if raw in ("", "auto"):
            engines = ["sqlite"]
            if importlib.util.find_spec("duckdb") is not None:
                engines.append("duckdb")
            engines += [engine for engine, dsn in dsns.items() if dsn]
        else:
            engines = [part.strip() for part in raw.split(",") if part.strip()]
            unknown = [e for e in engines if e not in ENGINE_IDS]
            if unknown:
                raise ValueError(f"JOINERY_ENGINES has unknown engines: {', '.join(unknown)}")
        defaults = cls()
        return cls(
            data_dir=Path(env.get("JOINERY_DATA_DIR") or defaults.data_dir),
            content_dir=Path(env.get("JOINERY_CONTENT_DIR") or defaults.content_dir),
            web_dir=Path(env.get("JOINERY_WEB_DIR") or defaults.web_dir),
            engines=tuple(dict.fromkeys(engines)),
            timeout_ms=_number(env, "JOINERY_TIMEOUT_MS", defaults.timeout_ms, 100, 30_000),
            max_rows=_number(env, "JOINERY_MAX_ROWS", defaults.max_rows, 10, 5_000),
            max_sql_chars=_number(env, "JOINERY_MAX_SQL_CHARS", defaults.max_sql_chars, 100, 100_000),
            max_concurrency=_number(env, "JOINERY_MAX_CONCURRENCY", defaults.max_concurrency, 1, 64),
            rate_limit=_number(env, "JOINERY_RATE_LIMIT", defaults.rate_limit, 0, 100_000),
            trust_proxy=_flag(env, "JOINERY_TRUST_PROXY", defaults.trust_proxy),
            web_fonts=_flag(env, "JOINERY_WEB_FONTS", defaults.web_fonts),
            log_sql=_flag(env, "JOINERY_LOG_SQL", defaults.log_sql),
            postgres_dsn=dsns["postgres"],
            mysql_dsn=dsns["mysql"],
            mssql_dsn=dsns["mssql"],
        )
