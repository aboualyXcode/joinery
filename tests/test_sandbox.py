import os
import tempfile
import time
import unittest

from tests.helpers import FIXTURE, RUNNER, run, statements


class SandboxExecutionTests(unittest.TestCase):
    def test_select_returns_columns_rows_and_counts(self):
        [res] = statements(run("SELECT name, score FROM t ORDER BY id"))
        self.assertEqual(res["columns"], ["name", "score"])
        self.assertEqual(res["rows"], [["ada", 9.5], ["grace", 8.25], ["linus", None]])
        self.assertEqual(res["row_count"], 3)
        self.assertIsNone(res["error"])

    def test_script_reports_each_statement_and_changes(self):
        res = statements(run("UPDATE t SET score = 0 WHERE score < 9; SELECT count(*) FROM t WHERE score = 0"))
        self.assertEqual(res[0]["changes"], 1)
        self.assertEqual(res[1]["rows"], [[1]])

    def test_every_run_starts_from_a_pristine_copy(self):
        statements(run("DELETE FROM t"))
        [res] = statements(run("SELECT count(*) FROM t"))
        self.assertEqual(res["rows"], [[3]])

    def test_error_stops_the_batch_and_is_reported(self):
        res = statements(run("SELECT 1; SELECT nope FROM t; SELECT 3"))
        self.assertEqual(len(res), 2)
        self.assertIn("no such column", res[1]["error"]["message"])
        self.assertEqual(res[1]["error"]["code"], "SQLITE_ERROR")

    def test_row_cap_and_count(self):
        sql = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 2000) SELECT i FROM n"
        [res] = statements(run(sql))
        self.assertEqual(res["row_count"], 2000)
        self.assertEqual(len(res["rows"]), 500)
        self.assertTrue(res["truncated"])

    def test_values_are_json_safe(self):
        [res] = statements(run("SELECT x'00ff', 9007199254740993, 1e999, 'x'"))
        blob, big, inf, text = res["rows"][0]
        self.assertEqual(blob, {"blob": "00ff", "bytes": 2})
        self.assertEqual(big, "9007199254740993")
        self.assertEqual(inf, "Infinity")
        self.assertEqual(text, "x")

    def test_double_quoted_strings_are_identifiers(self):
        [res] = statements(run('SELECT * FROM t WHERE name = "ada"'))
        self.assertIn("no such column", res["error"]["message"])

    def test_foreign_keys_are_enforced(self):
        res = statements(run(
            "CREATE TABLE p (id INTEGER PRIMARY KEY); CREATE TABLE c (p_id INTEGER REFERENCES p (id));"
            "INSERT INTO c VALUES (42)"
        ))
        self.assertIn("FOREIGN KEY constraint failed", res[-1]["error"]["message"])

    def test_trigger_bodies_run_as_one_statement(self):
        res = statements(run(
            "CREATE TABLE log (msg TEXT);"
            "CREATE TRIGGER t_upd AFTER UPDATE ON t BEGIN INSERT INTO log VALUES ('changed'); END;"
            "UPDATE t SET score = 1; SELECT count(*) FROM log"
        ))
        self.assertEqual(len(res), 4)
        self.assertEqual(res[-1]["rows"], [[3]])

    def test_explain_returns_plan_bytecode_and_analysis(self):
        out = run("SELECT * FROM t WHERE name = 'ada'", explain=True, analyze=True, split=False)
        [res] = statements(out)
        self.assertTrue(any("SEARCH t USING" in row[3] for row in res["plan"]))
        self.assertTrue(any(row[1] == "ResultRow" for row in res["bytecode"]))
        self.assertEqual(res["analyze"]["row_count"], 1)

    def test_analyze_undoes_changes(self):
        job = {"engine": "sqlite", "dataset_path": FIXTURE, "batches": [
            {"id": "x", "sql": "DELETE FROM t", "explain": True, "analyze": True, "split": False},
            {"id": "y", "sql": "SELECT count(*) FROM t"},
        ]}
        out = RUNNER.run(job, timeout_ms=2000)
        self.assertEqual(out["batches"][0]["statements"][0]["analyze"]["changes"], 3)
        self.assertEqual(out["batches"][1]["statements"][0]["rows"], [[3]])

    def test_statement_limit(self):
        out = run("SELECT 1;" * 60)
        self.assertFalse(out["ok"])
        self.assertIn("too many statements", out["error"]["message"])


class SandboxSecurityTests(unittest.TestCase):
    def assert_refused(self, sql):
        res = statements(run(sql))
        self.assertIsNotNone(res[-1]["error"], sql)
        self.assertRegex(res[-1]["error"]["message"], "not authorized|authorization denied")

    def test_attach_and_detach_are_refused(self):
        self.assert_refused("ATTACH DATABASE ':memory:' AS other")
        self.assert_refused("ATTACH DATABASE '/etc/passwd' AS other")

    def test_vacuum_into_cannot_write_files(self):
        target = os.path.join(tempfile.mkdtemp(), "escape.db")
        self.assert_refused(f"VACUUM INTO '{target}'")
        self.assertFalse(os.path.exists(target))

    def test_dangerous_pragmas_are_refused(self):
        for pragma in ("writable_schema = ON", "hard_heap_limit = 0", "max_page_count = 99999999",
                       "journal_mode = WAL", "temp_store_directory = '/tmp'", "mmap_size = 1000000"):
            self.assert_refused(f"PRAGMA {pragma}")

    def test_introspection_pragmas_are_allowed(self):
        [res] = statements(run("PRAGMA table_info(t)"))
        self.assertIsNone(res["error"])
        self.assertEqual([row[1] for row in res["rows"]], ["id", "name", "score"])

    def test_extensions_cannot_load(self):
        self.assert_refused("SELECT load_extension('/tmp/evil.so')")

    def test_runaway_query_times_out(self):
        started = time.monotonic()
        [res] = statements(run(
            "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT count(*) FROM r",
            timeout_ms=500,
        ))
        self.assertEqual(res["error"]["type"], "Timeout")
        self.assertLess(time.monotonic() - started, 3)

    def test_huge_values_are_refused(self):
        [res] = statements(run("SELECT length(randomblob(500000000))"))
        self.assertIn("too big", res["error"]["message"])

    def test_database_growth_is_capped(self):
        sql = ("CREATE TABLE big (x TEXT);"
               "INSERT INTO big WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 100000)"
               " SELECT randomblob(900) FROM r")
        res = statements(run(sql, timeout_ms=5000))
        self.assertIn("full", res[-1]["error"]["message"])

    def test_memory_is_capped(self):
        sql = ("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 400000)"
               " SELECT count(*) FROM (SELECT randomblob(800) AS b FROM r ORDER BY b)")
        [res] = statements(run(sql, timeout_ms=8000))
        self.assertIsNotNone(res["error"])
        self.assertIn(res["error"]["type"], ("OperationalError", "ResourceLimit", "Timeout"))

    def test_worker_environment_is_scrubbed(self):
        os.environ["JOINERY_SECRET_FOR_TEST"] = "do-not-leak"
        try:
            [res] = statements(run("SELECT 1"))
            self.assertIsNone(res["error"])
        finally:
            del os.environ["JOINERY_SECRET_FOR_TEST"]

    def test_unknown_engine_is_rejected(self):
        out = RUNNER.run({"engine": "oracle", "batches": [{"sql": "SELECT 1"}]}, timeout_ms=1000)
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main()
