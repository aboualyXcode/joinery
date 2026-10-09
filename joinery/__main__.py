"""Command line interface: ``python -m joinery <command>``."""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform as host
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .config import Settings


def _serve(args: argparse.Namespace) -> int:
    from .app import create_app

    create_app(Settings.from_env()).run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


def _build(args: argparse.Namespace) -> int:
    from .datasets.build import ensure_built

    manifest = ensure_built(Settings.from_env().data_dir, force=args.force)
    for dataset_id, entry in manifest["datasets"].items():
        print(f"{dataset_id:10} {sum(entry['rows'].values()):>7,} rows  duckdb={'yes' if entry['duckdb'] else 'no'}")
    return 0


def _export(args: argparse.Namespace) -> int:
    from .datasets import get_dataset
    from .datasets.ddl import create_script

    script = create_script(get_dataset(args.dataset), args.dialect)
    if args.output:
        Path(args.output).write_text(script, encoding="utf-8")
    else:
        sys.stdout.write(script)
    return 0


def _validate(args: argparse.Namespace) -> int:
    from .service import Platform
    from .validation import validate

    settings = Settings.from_env()
    if args.engine not in settings.engines:
        settings = settings.with_overrides(engines=tuple(dict.fromkeys(settings.engines + (args.engine,))))
    report = validate(Platform(settings), args.engine, args.lesson, args.jobs)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['engine']}: {report['examples']} examples, {report['exercises']} exercises checked, "
              f"{report['skipped']} examples skipped (no {report['engine']} variant)")
        for failure in report["failures"]:
            print(f"  FAIL {failure['kind']} {failure['lesson']}/{failure['id']}: {failure['message']}")
        print("OK" if not report["failures"] else f"{len(report['failures'])} failure(s)")
    return 1 if report["failures"] else 0


def _provision(args: argparse.Namespace) -> int:
    from .provision import provision

    password = args.sandbox_password or os.environ.get("JOINERY_SANDBOX_PASSWORD")
    if not password:
        print("Set --sandbox-password or JOINERY_SANDBOX_PASSWORD.", file=sys.stderr)
        return 2
    for line in provision(args.engine, args.admin_dsn, password):
        print(line)
    return 0


def _doctor(_args: argparse.Namespace) -> int:
    import importlib.util

    settings = Settings.from_env()
    version = tuple(int(part) for part in sqlite3.sqlite_version.split("."))
    checks = [
        ("Joinery", __version__, True),
        ("Python", host.python_version(), sys.version_info >= (3, 12)),
        ("SQLite", sqlite3.sqlite_version, version >= (3, 45)),
        ("Sandbox (POSIX resource limits)", "available" if importlib.util.find_spec("resource") else "missing",
         importlib.util.find_spec("resource") is not None),
        ("Web client", str(settings.web_dir), (settings.web_dir / "index.html").exists()),
        ("Engines enabled", ", ".join(settings.engines), True),
    ]
    for module, label in (("duckdb", "DuckDB driver"), ("psycopg", "PostgreSQL driver"),
                          ("pymysql", "MySQL driver"), ("mssql_python", "SQL Server driver")):
        checks.append((label, "installed" if importlib.util.find_spec(module) else "not installed", True))
    width = max(len(name) for name, _value, _ok in checks)
    for name, value, ok in checks:
        print(f"{'ok ' if ok else 'BAD'} {name:<{width}}  {value}")
    return 0 if all(ok for _name, _value, ok in checks) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="joinery", description="Interactive SQL learning platform.")
    parser.add_argument("--version", action="version", version=f"joinery {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the development server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--debug", action="store_true")
    serve.set_defaults(handler=_serve)
    build = sub.add_parser("build-datasets", help="build the sample dataset images")
    build.add_argument("--force", action="store_true", help="rebuild even if the images are current")
    build.set_defaults(handler=_build)
    export = sub.add_parser("export", help="print a dataset as a SQL script for one dialect")
    export.add_argument("--dataset", required=True)
    export.add_argument("--dialect", default="sqlite", choices=("sqlite", "postgres", "mysql", "mssql", "duckdb"))
    export.add_argument("--output", help="write to this file instead of stdout")
    export.set_defaults(handler=_export)
    validate = sub.add_parser("validate", help="run every lesson example and exercise")
    validate.add_argument("--engine", default="sqlite")
    validate.add_argument("--lesson")
    validate.add_argument("--jobs", type=int, default=4)
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(handler=_validate)
    provision = sub.add_parser("provision", help="load datasets into a server engine (experimental)")
    provision.add_argument("--engine", required=True, choices=("postgres", "mysql", "mssql"))
    provision.add_argument("--admin-dsn", required=True)
    provision.add_argument("--sandbox-password")
    provision.set_defaults(handler=_provision)
    doctor = sub.add_parser("doctor", help="check the environment")
    doctor.set_defaults(handler=_doctor)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
