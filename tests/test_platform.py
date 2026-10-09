import json
import unittest
from pathlib import Path

from joinery.app import create_app
from joinery.config import Settings
from joinery.content import ContentError, load_content
from joinery.grading import compare
from joinery.security import RateLimiter
from joinery.service import Platform
from joinery.validation import validate

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "content"
SETTINGS = Settings(data_dir=ROOT / "var" / "datasets", content_dir=FIXTURE, web_dir=ROOT / "tests" / "no-web",
                    engines=("sqlite",), rate_limit=0)


def result(rows, columns=("a",)):
    return {"columns": list(columns), "rows": [list(r) for r in rows], "row_count": len(rows)}


class GradingTests(unittest.TestCase):
    def test_numbers_compare_with_tolerance_and_types(self):
        self.assertTrue(compare(result([[1.0000001], [2]]), result([[1], [2.0]]))["passed"])

    def test_order_only_matters_when_asked(self):
        self.assertTrue(compare(result([[1], [2]]), result([[2], [1]]))["passed"])
        verdict = compare(result([[1], [2]]), result([[2], [1]]), order_matters=True)
        self.assertFalse(verdict["passed"])
        self.assertIn("wrong order", verdict["summary"])

    def test_row_and_column_mismatches_explain_themselves(self):
        self.assertIn("Too many rows", compare(result([[1]]), result([[1], [1]]))["hint"])
        self.assertIn("column", compare(result([[1]]), result([[1, 2]], ("a", "b")))["summary"])
        verdict = compare(result([["x", 1]], ("k", "v")), result([["x", 2]], ("k", "v")))
        self.assertIn("expected ('x', 1)", verdict["details"][0])

    def test_names(self):
        self.assertTrue(compare(result([[1]], ("total",)), result([[1]], ("count(*)",)))["passed"])
        self.assertFalse(compare(result([[1]], ("total",)), result([[1]], ("n",)), check_names=True)["passed"])


class ContentTests(unittest.TestCase):
    def test_fixture_loads_and_renders(self):
        content = load_content(FIXTURE)
        lesson = content.lessons["sample-lesson"]
        self.assertEqual(lesson["number"], "1.1")
        self.assertIn("<code>rows</code>", lesson["sections"][0]["html"])
        self.assertNotIn("solution", json.dumps(lesson["exercises"]))
        self.assertEqual(content.examples["sample-teams"].sql_for("postgres"), "SELECT name FROM teams ORDER BY id")
        self.assertIsNone(content.examples["sample-error"].sql_for("mysql"))

    def test_invalid_content_is_rejected(self):
        broken = Path(self._tmp()) / "content"
        (broken / "lessons").mkdir(parents=True)
        (broken / "curriculum.yaml").write_text("modules: [{id: m, title: M, lessons: [x]}]")
        (broken / "lessons" / "x.yaml").write_text("id: x\ntitle: X\nlevel: expert\ndataset: shop\nsummary: s\nsections: []")
        with self.assertRaises(ContentError):
            load_content(broken)

    def _tmp(self):
        import tempfile

        return tempfile.mkdtemp()


class PlatformTests(unittest.TestCase):
    platform = Platform(SETTINGS)

    def test_validation_passes_for_the_fixture(self):
        report = validate(self.platform)
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["examples"], 2)
        self.assertEqual(report["exercises"], 2)

    def test_check_feedback(self):
        wrong = self.platform.check("sample-free-agents", "SELECT name FROM players")
        self.assertFalse(wrong["passed"])
        self.assertEqual(wrong["expected"]["row_count"], 2)
        broken = self.platform.check("sample-free-agents", "SELECT nam FROM players")
        self.assertIsNotNone(broken["error"]["explanation"])
        state = self.platform.check("sample-rename", "UPDATE teams SET name = 'Kites' WHERE id = 3")
        self.assertTrue(state["passed"])


class ApiTests(unittest.TestCase):
    app = create_app(SETTINGS)

    def setUp(self):
        self.client = self.app.test_client()

    def post(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def test_health_meta_and_security_headers(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.json["status"], "ok")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        meta = self.client.get("/api/meta").json
        self.assertEqual(meta["engines"][0]["id"], "sqlite")
        self.assertEqual(len(meta["datasets"]), 5)

    def test_run_returns_results_warnings_and_explanations(self):
        body = self.post("/api/run", {"sql": "SELECT * FROM players WHERE team_id = NULL", "dataset": "joinlab"}).json
        self.assertEqual(body["statements"][0]["row_count"], 0)
        self.assertEqual(body["warnings"][0]["rule"], "null-comparison")
        body = self.post("/api/run", {"sql": "SELECT * FROM player", "dataset": "joinlab"}).json
        self.assertEqual(body["error"]["explanation"]["suggestions"], ["players"])

    def test_explain_and_steps(self):
        plan = self.post("/api/explain", {"sql": "SELECT * FROM orders WHERE customer_id = 3", "dataset": "shop",
                                          "setup": "CREATE INDEX i ON orders (customer_id)"}).json
        self.assertEqual(plan["tree"][0]["kind"], "search")
        self.assertGreater(plan["bytecode_summary"]["instructions"], 5)
        steps = self.post("/api/steps", {"sql": "SELECT role, count(*) FROM players GROUP BY role",
                                         "dataset": "joinlab"}).json
        self.assertEqual([s["id"] for s in steps["stages"]], ["from", "group", "select"])

    def test_lessons_datasets_and_exports(self):
        self.assertEqual(self.client.get("/api/curriculum").json["modules"][0]["id"], "basics")
        self.assertEqual(self.client.get("/api/lessons/sample-lesson").json["id"], "sample-lesson")
        self.assertEqual(self.client.get("/api/lessons/nope").status_code, 404)
        schema = self.client.get("/api/datasets/shop").json
        self.assertIn("orders", [t["name"] for t in schema["tables"]])
        export = self.client.get("/api/datasets/joinlab/export?dialect=postgres")
        self.assertIn("attachment", export.headers["Content-Disposition"])
        self.assertIn(b"GENERATED BY DEFAULT AS IDENTITY", export.data)
        self.assertEqual(self.client.get("/api/datasets/joinlab/export?dialect=oracle").status_code, 400)

    def test_exercise_endpoints(self):
        check = self.post("/api/exercises/sample-free-agents/check",
                          {"sql": "SELECT name FROM players WHERE team_id IS NULL"}).json
        self.assertTrue(check["passed"])
        self.assertIn("solution", self.client.get("/api/exercises/sample-free-agents/solution").json)

    def test_input_validation(self):
        self.assertEqual(self.client.post("/api/run", data="SELECT 1").status_code, 415)
        self.assertEqual(self.post("/api/run", {"sql": 1}).status_code, 400)
        self.assertEqual(self.post("/api/run", {"sql": "x" * 30_000}).status_code, 413)
        self.assertEqual(self.post("/api/run", {"sql": "SELECT 1", "dataset": "nope"}).status_code, 404)
        self.assertEqual(self.post("/api/run", {"sql": "SELECT 1", "engine": "oracle"}).status_code, 400)
        self.assertEqual(self.post("/api/run", {"sql": "  "}).status_code, 400)

    def test_missing_web_client_is_explained(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"npm run build", response.data)


class RateLimitTests(unittest.TestCase):
    def test_sliding_window(self):
        limiter = RateLimiter(2)
        self.assertTrue(limiter.allow("a", now=0)[0])
        self.assertTrue(limiter.allow("a", now=1)[0])
        allowed, retry = limiter.allow("a", now=2)
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)
        self.assertTrue(limiter.allow("b", now=2)[0])
        self.assertTrue(limiter.allow("a", now=61)[0])

    def test_api_returns_429(self):
        app = create_app(SETTINGS.with_overrides(rate_limit=1))
        client = app.test_client()
        payload = json.dumps({"sql": "SELECT 1", "dataset": "joinlab"})
        self.assertEqual(client.post("/api/run", data=payload, content_type="application/json").status_code, 200)
        response = client.post("/api/run", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)


if __name__ == "__main__":
    unittest.main()
