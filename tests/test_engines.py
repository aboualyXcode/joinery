import importlib.util
import unittest
from pathlib import Path

from joinery.config import Settings
from joinery.datasets.build import ensure_built
from joinery.engines import PostgresEngine, SqliteEngine, build_engines
from joinery.engines.server import MssqlEngine, _mysql_params
from joinery.sandbox.worker import DEFAULT_LIMITS
from tests.helpers import RUNNER

DATA_DIR = Path(__file__).resolve().parent.parent / "var" / "datasets"
MANIFEST = ensure_built(DATA_DIR)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self.rowcount = -1
        self._rows = []

    def execute(self, sql):
        self.conn.log.append(sql)
        self.description, self._rows, self.rowcount = None, [], -1
        if "boom" in sql:
            raise RuntimeError("relation \"boom\" does not exist")
        if "pg_sleep" in sql:
            raise RuntimeError("canceling statement due to statement timeout")
        if sql.startswith("SHOW server_version"):
            self.description, self._rows = [("server_version",)], [("18.6",)]
        elif sql.startswith("SELECT"):
            self.description, self._rows = [("n",)], [(1,), (2,)]
        elif sql.startswith("UPDATE"):
            self.rowcount = 3

    def fetchone(self):
        return self._rows.pop(0)

    def fetchmany(self, size):
        out, self._rows = self._rows[:size], self._rows[size:]
        return out


class FakeConnection:
    def __init__(self):
        self.log, self.rolled_back, self.closed = [], False, False

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class SqliteEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = SqliteEngine(RUNNER, DATA_DIR, MANIFEST, DEFAULT_LIMITS)

    def test_runs_against_a_dataset(self):
        out = self.engine.run("joinlab", [{"id": "q", "sql": "SELECT name FROM teams ORDER BY id"}], timeout_ms=2000)
        self.assertTrue(out["ok"])
        self.assertEqual(out["batches"][0]["statements"][0]["rows"], [["Comets"], ["Herons"], ["Owls"], ["Foxes"]])

    def test_unknown_dataset(self):
        out = self.engine.run("nope", [{"sql": "SELECT 1"}], timeout_ms=1000)
        self.assertEqual(out["error"]["type"], "UnknownDataset")

    def test_describe(self):
        info = self.engine.describe()
        self.assertEqual(info["id"], "sqlite")
        self.assertFalse(info["experimental"])


@unittest.skipUnless(importlib.util.find_spec("duckdb"), "duckdb is not installed")
class DuckdbEngineTests(unittest.TestCase):
    def test_runs_against_a_dataset(self):
        settings = Settings(engines=("duckdb",), data_dir=DATA_DIR)
        engine = build_engines(settings, RUNNER, MANIFEST)["duckdb"]
        out = engine.run("joinlab", [{"sql": "SELECT count(*) FROM players"}], timeout_ms=5000)
        self.assertEqual(out["batches"][0]["statements"][0]["rows"], [[7]])

    def test_external_access_is_disabled(self):
        settings = Settings(engines=("duckdb",), data_dir=DATA_DIR)
        engine = build_engines(settings, RUNNER, MANIFEST)["duckdb"]
        out = engine.run("joinlab", [{"sql": "SELECT * FROM read_csv('/etc/passwd')"}], timeout_ms=5000)
        self.assertIsNotNone(out["batches"][0]["statements"][0]["error"])


class ServerEngineTests(unittest.TestCase):
    def make(self, cls=PostgresEngine):
        conn = FakeConnection()
        return cls("postgresql://x", DEFAULT_LIMITS, connect=lambda *_: conn), conn

    def test_session_setup_savepoints_and_rollback(self):
        engine, conn = self.make()
        out = engine.run("shop", [{"sql": "SELECT n FROM t; UPDATE t SET a = 1"}], timeout_ms=3000)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["engine_version"], "18.6")
        self.assertIn("SET LOCAL statement_timeout = 3000", conn.log)
        self.assertIn("SET LOCAL search_path = shop", conn.log)
        self.assertIn("SAVEPOINT joinery_sp1", conn.log)
        self.assertIn("RELEASE SAVEPOINT joinery_sp2", conn.log)
        results = out["batches"][0]["statements"]
        self.assertEqual(results[0]["rows"], [[1], [2]])
        self.assertEqual(results[1]["changes"], 3)
        self.assertTrue(conn.rolled_back and conn.closed)

    def test_blocked_statements_never_reach_the_server(self):
        engine, conn = self.make()
        out = engine.run("shop", [{"sql": "COMMIT; SELECT 1"}], timeout_ms=3000)
        first = out["batches"][0]["statements"][0]
        self.assertEqual(first["error"]["type"], "Blocked")
        self.assertNotIn("COMMIT", conn.log)
        self.assertTrue(conn.rolled_back)

    def test_errors_roll_back_to_the_savepoint(self):
        engine, conn = self.make()
        out = engine.run("shop", [{"id": "a", "sql": "SELECT boom"}, {"id": "b", "sql": "SELECT 1"}], timeout_ms=3000)
        self.assertIn("ROLLBACK TO SAVEPOINT joinery_sp1", conn.log)
        self.assertIsNotNone(out["batches"][0]["statements"][0]["error"])
        self.assertIsNone(out["batches"][1]["statements"][0]["error"])

    def test_timeouts_are_recognised(self):
        engine, _conn = self.make()
        out = engine.run("shop", [{"sql": "SELECT pg_sleep(10)"}], timeout_ms=3000)
        self.assertEqual(out["batches"][0]["statements"][0]["error"]["type"], "Timeout")

    def test_dataset_names_must_be_identifiers(self):
        engine, conn = self.make()
        out = engine.run("shop; DROP SCHEMA x", [{"sql": "SELECT 1"}], timeout_ms=3000)
        self.assertEqual(out["error"]["type"], "UnknownDataset")
        self.assertEqual(conn.log, [])

    def test_mssql_uses_save_transaction(self):
        engine = MssqlEngine("Server=x", DEFAULT_LIMITS, connect=lambda *_: FakeConnection())
        self.assertEqual(engine.savepoint_sql("s1"), ("SAVE TRANSACTION s1", "ROLLBACK TRANSACTION s1", None))

    def test_mysql_dsn_parsing(self):
        params = _mysql_params("mysql://sand%40box:p%3Ass@db.internal:3307")
        self.assertEqual(params, {"host": "db.internal", "port": 3307, "user": "sand@box", "password": "p:ss"})


class SettingsTests(unittest.TestCase):
    def test_defaults_and_overrides(self):
        settings = Settings.from_env({"JOINERY_ENGINES": "sqlite", "JOINERY_TIMEOUT_MS": "1500"})
        self.assertEqual(settings.engines, ("sqlite",))
        self.assertEqual(settings.timeout_ms, 1500)
        self.assertEqual(settings.sandbox_limits["timeout_ms"], 1500)

    def test_auto_enables_server_engines_with_a_dsn(self):
        settings = Settings.from_env({"JOINERY_POSTGRES_DSN": "postgresql://u:p@h/db"})
        self.assertIn("postgres", settings.engines)
        self.assertIn("sqlite", settings.engines)

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(ValueError):
            Settings.from_env({"JOINERY_TIMEOUT_MS": "fast"})
        with self.assertRaises(ValueError):
            Settings.from_env({"JOINERY_ENGINES": "sqlite,oracle"})
        with self.assertRaises(ValueError):
            Settings.from_env({"JOINERY_MAX_ROWS": "0"})


if __name__ == "__main__":
    unittest.main()
