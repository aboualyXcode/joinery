import unittest

from joinery.sqltools.errors import explain_error
from joinery.sqltools.lint import lint
from joinery.sqltools.plans import aliases_for, annotate_bytecode, postgres_tree, sqlite_tree
from tests.helpers import make_image, run, statements

TABLES = {"orders": ["id", "customer_id", "status", "ordered_at"], "customers": ["id", "email", "country"]}
IMAGE = make_image(
    "CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT, country TEXT);"
    "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, status TEXT, ordered_at TEXT);"
    "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 400)"
    " INSERT INTO customers SELECT i, 'c' || i || '@example.com', 'US' FROM n;"
    "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 2000)"
    " INSERT INTO orders SELECT i, 1 + i % 400, 'paid', '2026-01-01' FROM n;"
    "ANALYZE;", "plans")


def explain(sql, setup=""):
    batches = [{"id": "setup", "sql": setup}] if setup else []
    batches.append({"id": "main", "sql": sql, "split": False, "explain": True, "analyze": True})
    from tests.helpers import RUNNER
    out = RUNNER.run({"engine": "sqlite", "dataset_path": IMAGE, "batches": batches}, timeout_ms=3000)
    return out["batches"][-1]["statements"][0]


def kinds(nodes):
    out = []
    for node in nodes:
        out.append(node["kind"])
        out.extend(kinds(node["children"]))
    return out


class PlanTests(unittest.TestCase):
    rows = {"orders": 2000, "customers": 400}

    def test_index_turns_scan_into_search(self):
        sql = "SELECT * FROM orders WHERE customer_id = 7"
        before, _ = sqlite_tree(explain(sql)["plan"], self.rows)
        after, _ = sqlite_tree(explain(sql, "CREATE INDEX idx_orders_customer ON orders (customer_id)")["plan"], self.rows)
        self.assertEqual(kinds(before), ["scan"])
        self.assertEqual(kinds(after), ["search"])
        self.assertEqual(after[0]["index"], "idx_orders_customer")

    def test_unindexed_join_gets_advice(self):
        sql = "SELECT count(*) FROM orders a JOIN orders b ON a.customer_id = b.customer_id"
        res = explain(sql)
        tree, advice = sqlite_tree(res["plan"], self.rows, aliases_for(sql))
        self.assertTrue(any("orders" in a["message"] and "customer_id" in a["message"] for a in advice), advice)
        self.assertTrue(all(n["table"] == "orders" for n in tree if n["table"]), tree)

    def test_primary_key_join_is_already_good(self):
        sql = "SELECT c.email, o.id FROM customers c JOIN orders o ON o.customer_id = c.id"
        tree, _advice = sqlite_tree(explain(sql)["plan"], self.rows, aliases_for(sql))
        self.assertIn("search", kinds(tree))
        self.assertEqual(aliases_for(sql), {"c": "customers", "o": "orders"})

    def test_sort_and_correlated_subqueries_are_flagged(self):
        res = explain("SELECT id, (SELECT count(*) FROM orders o WHERE o.customer_id = c.id) AS n "
                      "FROM customers c ORDER BY country")
        tree, advice = sqlite_tree(res["plan"], self.rows)
        self.assertIn("correlated", kinds(tree))
        self.assertIn("sort", kinds(tree))
        self.assertTrue(any("correlated" in a["message"].lower() for a in advice))

    def test_bytecode_annotation_finds_the_loop(self):
        program, summary = annotate_bytecode(explain("SELECT id FROM orders")["bytecode"])
        self.assertEqual(summary["loops"], 1)
        nxt = next(op for op in program if op["opcode"] == "Next")
        self.assertIsNotNone(nxt["loop_to"])
        self.assertTrue(nxt["note"])

    def test_analyze_reports_work(self):
        cheap = explain("SELECT * FROM orders WHERE id = 5")["analyze"]["vm_steps"]
        costly = explain("SELECT * FROM orders WHERE status = 'x'")["analyze"]["vm_steps"]
        self.assertGreater(costly, cheap * 10)

    def test_postgres_json_is_normalized(self):
        plan = [{"Plan": {"Node Type": "Hash Join", "Total Cost": 120.5, "Plan Rows": 2000, "Actual Rows": 2000,
                          "Plans": [{"Node Type": "Seq Scan", "Relation Name": "orders", "Plan Rows": 50000,
                                     "Actual Rows": 2000, "Filter": "(status = 'paid')"},
                                    {"Node Type": "Hash", "Plans": [{"Node Type": "Index Scan",
                                                                     "Relation Name": "customers",
                                                                     "Index Name": "customers_pkey"}]}]}}]
        tree, advice = postgres_tree(plan)
        self.assertEqual(tree[0]["kind"], "join")
        self.assertEqual(tree[0]["children"][0]["severity"], "warn")
        self.assertEqual(tree[0]["children"][1]["children"][0]["index"], "customers_pkey")
        self.assertTrue(any("estimated" in a["message"] for a in advice))


class ErrorTests(unittest.TestCase):
    def explain(self, sql):
        [res] = statements(run(sql, dataset=IMAGE))
        return explain_error(res["error"], sql, TABLES)

    def test_unknown_table_suggests_names(self):
        info = self.explain("SELECT * FROM order")
        self.assertIn("Syntax error", info["title"])
        info = self.explain("SELECT * FROM ordrs")
        self.assertEqual(info["title"], "Unknown table")
        self.assertEqual(info["suggestions"], ["orders"])
        self.assertEqual(info["position"], {"start": 14, "end": 19})

    def test_double_quoted_strings(self):
        info = self.explain('SELECT * FROM orders WHERE status = "paid"')
        self.assertIn("Double quotes", info["title"])

    def test_unknown_column_suggestions(self):
        info = self.explain("SELECT custmer_id FROM orders")
        self.assertEqual(info["suggestions"], ["customer_id"])

    def test_ambiguous_and_aggregate_errors(self):
        self.assertEqual(self.explain("SELECT id FROM orders JOIN customers ON 1")["title"], "Ambiguous column")
        self.assertIn("Aggregate", self.explain("SELECT * FROM orders WHERE count(*) > 1")["title"])
        self.assertIn("Window", self.explain(
            "SELECT id FROM orders WHERE row_number() OVER (ORDER BY id) < 3")["title"])

    def test_syntax_hints(self):
        info = self.explain("SELECT id, status, FROM orders")
        self.assertIn("trailing comma", info["hint"])
        self.assertIn("LIMIT", self.explain("SELECT TOP 5 * FROM orders")["hint"])

    def test_unknown_functions_point_to_sqlite_equivalents(self):
        self.assertIn("strftime", self.explain("SELECT year(ordered_at) FROM orders")["hint"])

    def test_timeouts_and_constraints(self):
        self.assertEqual(explain_error({"type": "Timeout", "message": ""}, "", {})["title"], "The query took too long")
        info = explain_error({"type": "IntegrityError", "message": "CHECK constraint failed: ck_orders_status"}, "",
                             {}, {"ck_orders_status": "status IN ('paid')"})
        self.assertIn("status IN ('paid')", info["detail"])
        self.assertIsNone(explain_error(None, "", {}))


class LintTests(unittest.TestCase):
    def rules(self, sql):
        return [f["rule"] for f in lint(sql)]

    def test_rules_fire(self):
        cases = {
            "SELECT * FROM t WHERE a = NULL": "null-comparison",
            "SELECT * FROM t WHERE a NOT IN (SELECT b FROM u)": "not-in-subquery",
            "SELECT * FROM t JOIN u ON t.id = u.t_id": "select-star-join",
            "SELECT a.x, b.y FROM a, b": "cartesian-product",
            "SELECT * FROM t WHERE name LIKE '%son'": "leading-wildcard",
            "SELECT * FROM t LIMIT 5": "limit-without-order",
            "DELETE FROM t": "missing-where",
            "SELECT * FROM t WHERE lower(email) = 'x'": "function-on-column",
            "SELECT a FROM t UNION SELECT a FROM u": "union-distinct",
            "SELECT * FROM t ORDER BY id LIMIT 10 OFFSET 5000": "large-offset",
            "SELECT country, count(*) FROM t GROUP BY country HAVING country = 'US'": "having-without-aggregate",
        }
        for sql, rule in cases.items():
            self.assertIn(rule, self.rules(sql), sql)

    def test_clean_queries_stay_quiet(self):
        for sql in ("SELECT id, status FROM orders WHERE customer_id = 7 ORDER BY id LIMIT 10",
                    "SELECT country, count(*) FROM customers GROUP BY country HAVING count(*) > 5",
                    "UPDATE orders SET status = 'paid' WHERE id = 3",
                    "SELECT a FROM t UNION ALL SELECT a FROM u",
                    "SELECT * FROM t WHERE a IS NULL"):
            self.assertEqual(self.rules(sql), [], sql)

    def test_positions_point_into_scripts(self):
        sql = "SELECT 1;\nSELECT * FROM t WHERE a = NULL"
        finding = lint(sql)[0]
        self.assertEqual(sql[finding["start"]:finding["end"]], "=")


if __name__ == "__main__":
    unittest.main()
