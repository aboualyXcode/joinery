"""Build dataset images into the data directory.

SQLite images are serialized database files that the sandbox deserializes
into a private in-memory copy for every run. When the optional ``duckdb``
package is installed, a DuckDB file is built next to each image. A manifest
records a fingerprint of the generator code, so images rebuild automatically
after the definitions change.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from . import BUILDERS, get_dataset
from .ddl import create_script
from .model import Dataset

log = logging.getLogger(__name__)
FORMAT_VERSION = 1


def fingerprint() -> str:
    digest = hashlib.sha256(f"{FORMAT_VERSION}:{sqlite3.sqlite_version}".encode())
    root = Path(__file__).parent
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def sqlite_image(dataset: Dataset) -> bytes:
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(create_script(dataset, "sqlite", include_data=False))
        for table in dataset.ordered_tables():
            marks = ", ".join("?" for _ in table.columns)
            con.executemany(f"INSERT INTO {table.name} VALUES ({marks})", table.rows)
        con.commit()
        problems = con.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise ValueError(f"{dataset.id}: foreign key violations {problems[:5]}")
        con.execute("ANALYZE")
        con.commit()
        con.execute("VACUUM")
        return con.serialize()
    finally:
        con.close()


def _duckdb_value(value: object, base_type: str) -> object:
    if value is None:
        return None
    if base_type == "date":
        return date.fromisoformat(str(value))
    if base_type == "timestamp":
        return datetime.fromisoformat(str(value))
    return value


def duckdb_file(dataset: Dataset, path: Path) -> None:
    import duckdb

    from ..sqltools.split import statement_texts

    tmp = path.with_name(path.name + ".tmp")
    for leftover in (tmp, Path(str(tmp) + ".wal")):
        if leftover.exists():
            leftover.unlink()
    con = duckdb.connect(str(tmp))
    try:
        for statement in statement_texts(create_script(dataset, "duckdb", include_data=False), "duckdb"):
            con.execute(statement)
        for table in dataset.ordered_tables():
            if not table.rows:
                continue
            types = [c.base_type for c in table.columns]
            rows = [[_duckdb_value(v, t) for v, t in zip(row, types, strict=True)] for row in table.rows]
            marks = ", ".join("?" for _ in table.columns)
            con.executemany(f"INSERT INTO {table.name} VALUES ({marks})", rows)
        con.execute("CHECKPOINT")
    finally:
        con.close()
    os.replace(tmp, path)


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


@contextlib.contextmanager
def _locked(directory: Path):
    with open(directory / ".build.lock", "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _duckdb_available() -> bool:
    try:
        import duckdb  # noqa: F401
    except ImportError:
        return False
    return True


def _manifest_if_current(data_dir: Path, want_duckdb: bool) -> dict | None:
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("fingerprint") != fingerprint() or set(manifest.get("datasets", {})) != set(BUILDERS):
        return None
    for entry in manifest["datasets"].values():
        if not (data_dir / entry["sqlite"]).exists():
            return None
        if want_duckdb and not (entry.get("duckdb") and (data_dir / entry["duckdb"]).exists()):
            return None
    return manifest


def ensure_built(data_dir: Path, *, force: bool = False) -> dict:
    """Build any missing or outdated images and return the manifest.

    A current manifest is read without taking the build lock, so prebuilt
    images work on a read-only filesystem.
    """
    want_duckdb = _duckdb_available()
    if not force:
        current = _manifest_if_current(data_dir, want_duckdb)
        if current is not None:
            return current
    data_dir.mkdir(parents=True, exist_ok=True)
    with _locked(data_dir):
        if not force:
            current = _manifest_if_current(data_dir, want_duckdb)
            if current is not None:
                return current
        datasets = {}
        for dataset_id in BUILDERS:
            dataset = get_dataset(dataset_id)
            _write_atomic(data_dir / f"{dataset_id}.sqlite", sqlite_image(dataset))
            entry: dict = {"sqlite": f"{dataset_id}.sqlite", "duckdb": None,
                           "rows": {t.name: len(t.rows) for t in dataset.tables}}
            if want_duckdb:
                try:
                    duckdb_file(dataset, data_dir / f"{dataset_id}.duckdb")
                    entry["duckdb"] = f"{dataset_id}.duckdb"
                except Exception:  # an optional engine must never block startup
                    log.exception("could not build the DuckDB image for %s", dataset_id)
            datasets[dataset_id] = entry
            log.info("built dataset %s", dataset_id)
        manifest = {"fingerprint": fingerprint(), "sqlite_version": sqlite3.sqlite_version, "datasets": datasets}
        (data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest
