import re
import tempfile
import unittest
from pathlib import Path

from joinery.app import create_app
from joinery.config import Settings
from joinery.content.explore import ExploreError, geometry_problems, load_explore, match_failure
from joinery.datasets import dataset_ids
from joinery.service import Platform
from joinery.snapshot import record, snapshot_key

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = Settings(data_dir=ROOT / "var" / "datasets", content_dir=ROOT / "content",
                    web_dir=ROOT / "tests" / "no-web", engines=("sqlite",), rate_limit=0)
PLATFORM = Platform(SETTINGS)
EXPLORE = PLATFORM.explore


def nodes(graph):
    return {n["id"]: n for n in graph["nodes"]}


def edges(graph):
    return {(e["from"], e["to"], e["kind"]) for e in graph["edges"]}


class ExploreDataTests(unittest.TestCase):
    def test_the_map_is_valid_and_clean(self):
        self.assertGreaterEqual(len(EXPLORE["stations"]), 18)
        self.assertEqual(geometry_problems({s["id"]: s for s in EXPLORE["stations"]}, EXPLORE["edges"]), [])
        self.assertGreaterEqual(len(EXPLORE["failures"]), 30)
        self.assertEqual({s["id"] for s in EXPLORE["symptoms"]}, {"fails", "slow", "hangs", "wrong"})

    def test_bad_data_is_rejected(self):
        source = (ROOT / "content" / "explore.yaml").read_text()
        broken = Path(tempfile.mkdtemp()) / "explore.yaml"
        broken.write_text(source.replace("path: [parser, session, pool, app]", "path: [parser, pool, app]", 1))
        with self.assertRaises(ExploreError):
            load_explore(broken, set(dataset_ids()))
        stations = {"a": {"x": 0, "y": 0}, "b": {"x": 400, "y": 0}, "c": {"x": 200, "y": 0}}
        self.assertIn("edge a-b runs through c", geometry_problems(stations, [{"from": "a", "to": "b", "bend": None}]))

    def test_every_demo_reproduces_its_own_error(self):
        for failure in EXPLORE["failures"]:
            demo = failure.get("demo")
            if not demo or failure["kind"] == "wrong":
                continue
            with self.subTest(failure=failure["id"]):
                result = PLATFORM.run(demo["sql"], demo["dataset"])
                error = result["error"]
                self.assertIsNotNone(error, "the demo should fail")
                self.assertEqual(match_failure(EXPLORE, error["message"]), failure["id"], error["message"])

    def test_sample_messages_match_their_own_entry(self):
        for failure in EXPLORE["failures"]:
            for engine, message in failure.get("messages", {}).items():
                if message.startswith("("):
                    continue
                with self.subTest(failure=failure["id"], engine=engine):
                    self.assertEqual(match_failure(EXPLORE, message), failure["id"])

    def test_comparisons_run_and_differ(self):
        for failure in EXPLORE["failures"]:
            compare = failure.get("compare")
            if not compare:
                continue
            with self.subTest(failure=failure["id"]):
                if failure["kind"] == "wrong":
                    wrong = PLATFORM.run(compare["slow"]["sql"], compare["dataset"])["statements"][0]
                    right = PLATFORM.run(compare["fast"]["sql"], compare["dataset"])["statements"][0]
                    self.assertNotEqual(wrong["rows"], right["rows"])
                else:
                    slow = PLATFORM.explain(compare["slow"]["sql"], compare["dataset"], setup=compare["slow"].get("setup"))
                    fast = PLATFORM.explain(compare["fast"]["sql"], compare["dataset"], setup=compare["fast"].get("setup"))
                    self.assertGreater(slow["metrics"]["vm_steps"], fast["metrics"]["vm_steps"])


class DependencyTests(unittest.TestCase):
    def graph(self, query_id=None, sql=None, dataset="shop"):
        if query_id:
            query = next(q for q in EXPLORE["queries"] if q["id"] == query_id)
            sql, dataset = query["sql"], query["dataset"]
        return PLATFORM.visualize(sql, dataset)

    def test_chained_ctes(self):
        graph = self.graph("spend-tiers")["dependencies"]
        found = edges(graph)
        self.assertIn(("table:order_items", "cte:order_totals", "reads"), found)
        self.assertIn(("cte:order_totals", "cte:customer_spend", "reads"), found)
        self.assertIn(("table:orders", "cte:customer_spend", "reads"), found)
        self.assertIn(("cte:customer_spend", "query", "reads"), found)
        self.assertGreater(nodes(graph)["cte:order_totals"]["rows"], 1000)
        self.assertEqual(nodes(graph)["query"]["rows"], 3)

    def test_recursion_and_correlation(self):
        chart = self.graph("org-chart")["dependencies"]
        self.assertIn(("cte:chain", "cte:chain", "recursive"), edges(chart))
        self.assertTrue(nodes(chart)["cte:chain"]["recursive"])
        per = nodes(self.graph("per-customer")["dependencies"])
        sub = next(n for n in per.values() if n["kind"] == "subquery")
        self.assertTrue(sub["correlated"])
        self.assertEqual(sub["role"], "scalar")
        anti = nodes(self.graph("never-ordered")["dependencies"])
        self.assertEqual(next(n for n in anti.values() if n["kind"] == "subquery")["role"], "not-exists")

    def test_failures_propagate_downstream(self):
        graph = nodes(self.graph("broken-cte")["dependencies"])
        self.assertEqual(graph["cte:paid"]["status"], "ok")
        self.assertEqual(graph["cte:late"]["status"], "error")
        self.assertIn("delivred_at", graph["cte:late"]["error"]["message"])
        self.assertEqual(graph["cte:late_paid"]["status"], "blocked")
        self.assertEqual(graph["query"]["status"], "blocked")
        missing = nodes(self.graph(sql="SELECT * FROM ordrs")["dependencies"])
        self.assertEqual(missing["missing:ordrs"]["status"], "error")
        self.assertEqual(missing["query"]["status"], "blocked")

    def test_writes_and_uncorrelated_subqueries(self):
        graph = self.graph(sql="UPDATE orders SET status = 'paid' WHERE id IN (SELECT order_id FROM payments WHERE amount > 100)")
        deps = graph["dependencies"]
        self.assertIn(("query", "table:orders", "writes"), edges(deps))
        sub = next(n for n in deps["nodes"] if n["kind"] == "subquery")
        self.assertEqual(sub["role"], "in")
        self.assertGreater(sub["rows"], 0)
        self.assertEqual(graph["steps"]["statement"], "update")

    def test_visualize_bundles_stages_and_plan(self):
        graph = self.graph("country-orders")
        self.assertTrue(all("vm_steps" in s for s in graph["steps"]["stages"]))
        self.assertTrue(graph["plan"]["tree"])
        self.assertEqual(self.graph(sql="CREATE TABLE x (a INT)")["dependencies"]["supported"], False)


class SnapshotTests(unittest.TestCase):
    def test_key_is_stable(self):
        self.assertEqual(snapshot_key("/api/run", {"sql": "SELECT 1", "dataset": "joinlab"}), "61af01a76bcec8d1e918b76d7c23604970f5e576")
        self.assertEqual(snapshot_key("/api/run", {"sql": "SELECT 1", "dataset": "joinlab", "engine": "sqlite"}),
                         snapshot_key("/api/run", {"sql": "SELECT 1", "dataset": "joinlab", "setup": None}))

    def test_recording_without_examples(self):
        out = Path(tempfile.mkdtemp())
        stats = record(create_app(SETTINGS), out, include_examples=False)
        self.assertGreater(stats["files"], 150)
        self.assertIn('"static":true', (out / "get" / "meta.json").read_text())
        demo = next(f for f in EXPLORE["failures"] if f["id"] == "unknown-column")["demo"]
        key = snapshot_key("/api/run", {"sql": demo["sql"], "dataset": demo["dataset"]})
        self.assertTrue(re.search("no such column", (out / "post" / f"{key}.json").read_text()))


if __name__ == "__main__":
    unittest.main()
