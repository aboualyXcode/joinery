import unittest
from pathlib import Path

from joinery.datasets import get_dataset
from joinery.datasets.build import ensure_built
from joinery.engines import SqliteEngine
from joinery.sandbox.worker import DEFAULT_LIMITS
from joinery.sqltools.stepper import assemble, batches_for, plan_steps
from tests.helpers import RUNNER

DATA_DIR = Path(__file__).resolve().parent.parent / "var" / "datasets"
ENGINE = SqliteEngine(RUNNER, DATA_DIR, ensure_built(DATA_DIR), DEFAULT_LIMITS)


def schema(dataset_id):
    return {t.name: t.column_names for t in get_dataset(dataset_id).tables}


def step(sql, dataset="shop"):
    plan = plan_steps(sql, schema(dataset))
    if not plan.supported:
        return assemble(plan, {})
    return assemble(plan, ENGINE.run(dataset, batches_for(plan), timeout_ms=8000))


class StepperTests(unittest.TestCase):
    def test_full_pipeline_runs_in_logical_order(self):
        out = step(
            "SELECT c.country, count(*) AS orders FROM orders o JOIN customers c ON c.id = o.customer_id "
            "WHERE o.status = 'delivered' GROUP BY c.country HAVING count(*) > 20 ORDER BY orders DESC LIMIT 3"
        )
        self.assertTrue(out["supported"])
        self.assertEqual(out["logical_order"], ["FROM", "WHERE", "GROUP BY", "HAVING", "SELECT", "ORDER BY", "LIMIT"])
        self.assertEqual(out["written_order"], ["SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT"])
        stages = {s["id"]: s for s in out["stages"]}
        for stage in out["stages"]:
            self.assertIsNone(stage["error"], stage)
        self.assertIn("o.status", stages["from"]["columns"])
        self.assertIn("c.country", stages["from"]["columns"])
        where = stages["where"]
        self.assertEqual(where["input_count"], stages["from"]["row_count"])
        self.assertEqual(sum(where["kept"]), sum(1 for r, k in zip(where["rows"], where["kept"]) if k))
        self.assertLess(where["kept_count"], where["input_count"])
        self.assertEqual(stages["having"]["input_count"], stages["group"]["row_count"])
        self.assertEqual(stages["limit"]["kept_count"], 3)
        self.assertEqual(stages["limit"]["kept"][:4], [True, True, True, False][: len(stages["limit"]["kept"])])

    def test_group_by_ordinals_and_aliases_are_resolved(self):
        out = step("SELECT status AS s, count(*) FROM orders GROUP BY 1 ORDER BY s")
        group = next(s for s in out["stages"] if s["id"] == "group")
        self.assertIsNone(group["error"])
        self.assertEqual(group["columns"][0], "status")

    def test_aggregate_without_group_by(self):
        out = step("SELECT count(*), round(avg(unit_price), 2) FROM products WHERE is_active")
        group = next(s for s in out["stages"] if s["id"] == "group")
        self.assertEqual(group["title"], "Aggregate")
        self.assertEqual(group["row_count"], 1)

    def test_window_functions_are_not_grouping(self):
        out = step("SELECT name, rank() OVER (ORDER BY unit_price DESC) AS r FROM products")
        self.assertNotIn("group", [s["id"] for s in out["stages"]])
        select = next(s for s in out["stages"] if s["id"] == "select")
        self.assertIn("Window functions", select["description"])

    def test_ctes_become_stages(self):
        out = step("WITH big AS (SELECT * FROM orders WHERE id > 1700) SELECT count(*) FROM big")
        self.assertEqual(out["stages"][0]["id"], "cte-big")
        self.assertEqual(out["stages"][0]["row_count"], 98)

    def test_compound_queries(self):
        out = step("SELECT name FROM teams UNION SELECT name FROM players ORDER BY name", "joinlab")
        ids = [s["id"] for s in out["stages"]]
        self.assertEqual(ids, ["branch-1", "branch-2", "combine"])
        self.assertEqual(out["stages"][-1]["row_count"], 11)

    def test_update_preview(self):
        out = step("UPDATE players SET role = 'reserve' WHERE team_id IS NULL", "joinlab")
        self.assertEqual(out["stages"][0]["row_count"], 2)
        self.assertEqual(out["stages"][1]["rows"][0][3], "reserve")

    def test_delete_preview(self):
        out = step("DELETE FROM players WHERE team_id = 1", "joinlab")
        self.assertEqual(out["stages"][1]["rows"], [[5]])

    def test_unsupported_statements_explain_why(self):
        for sql in ("SELECT 1; SELECT 2", "INSERT INTO teams (name, city) VALUES ('a', 'b')", "VALUES (1)", "SELECT 'oops"):
            out = step(sql, "joinlab")
            self.assertFalse(out["supported"], sql)
            self.assertTrue(out["reason"])

    def test_select_without_from(self):
        out = step("SELECT 1 + 1 AS two")
        self.assertEqual(out["stages"][0]["rows"], [[2]])

    def test_where_with_null_counts_as_removed(self):
        out = step("SELECT name, team_id FROM players WHERE team_id > 1", "joinlab")
        where = next(s for s in out["stages"] if s["id"] == "where")
        self.assertEqual(where["kept_count"], 3)
        self.assertEqual(where["input_count"], 7)


if __name__ == "__main__":
    unittest.main()
