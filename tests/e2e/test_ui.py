"""Browser tests: drive the built client in Chromium with Playwright.

    npm run build
    JOINERY_E2E=1 python -m unittest discover -s tests/e2e -t .

Add JOINERY_SCREENSHOTS=1 to refresh the images in docs/screenshots.
"""

from __future__ import annotations

import os
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENABLED = os.environ.get("JOINERY_E2E") == "1"
SCREENSHOTS = os.environ.get("JOINERY_SCREENSHOTS") == "1"


@unittest.skipUnless(ENABLED, "set JOINERY_E2E=1 to run the browser tests")
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        from werkzeug.serving import make_server

        from joinery.app import create_app
        from joinery.config import Settings

        if not (ROOT / "web" / "dist" / "index.html").exists():
            raise unittest.SkipTest("build the web client first: npm run build")
        settings = Settings(data_dir=ROOT / "var" / "datasets", content_dir=ROOT / "content",
                            web_dir=ROOT / "web" / "dist", engines=("sqlite",), rate_limit=0, web_fonts=False)
        cls.server = make_server("127.0.0.1", 0, create_app(settings), threaded=True)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1360, "height": 900}, color_scheme="light")
        self.page = self.context.new_page()
        self.page.set_default_timeout(15_000)
        self.problems: list[str] = []
        self.page.on("pageerror", lambda error: self.problems.append(f"page error: {error}"))
        self.page.on("console", lambda msg: self.problems.append(f"console {msg.type}: {msg.text}")
                     if msg.type == "error" else None)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.problems, [], "the page logged errors (CSP violations show up here too)")

    def open(self, route: str) -> None:
        self.page.goto(f"{self.base}/#/{route}")

    def test_home_runs_the_sample_query_stage_by_stage(self):
        self.open("")
        self.page.get_by_role("heading", name="You write SELECT first").wait_for()
        self.page.get_by_role("button", name="Run it stage by stage").click()
        tabs = self.page.locator(".stage-tab")
        tabs.first.wait_for()
        self.assertEqual(tabs.count(), 7)
        self.assertIn("FROM", tabs.nth(0).inner_text())
        tabs.nth(1).click()
        self.assertGreater(self.page.locator(".stage-panel tr.removed").count(), 0)
        self.assertGreater(self.page.locator(".stage-panel tr.kept").count(), 0)
        tabs.nth(1).press("ArrowRight")
        self.assertEqual(tabs.nth(2).get_attribute("aria-selected"), "true")
        self.page.get_by_role("button", name="Reorder by evaluation").click()
        self.page.locator(".clauses.logical").wait_for()  # applied inside a view transition

    def test_lesson_example_runs_on_the_engine(self):
        self.open("learn/joins")
        example = self.page.locator("#example-join-inner")
        example.get_by_role("button", name="Run", exact=True).click()
        example.locator("table.data tbody tr").first.wait_for()
        self.assertEqual(example.locator("table.data tbody tr").count(), 5)

    def test_exercise_feedback_and_progress(self):
        self.open("learn/filtering")
        exercise = self.page.locator("#exercise-filtering-missing-city")
        exercise.get_by_role("button", name="Check answer").click()
        exercise.locator(".verdict.fail").wait_for()
        exercise.locator("textarea").fill("SELECT id, email FROM customers WHERE city IS NULL")
        exercise.get_by_role("button", name="Check answer").click()
        exercise.locator(".verdict.pass").wait_for()
        self.assertIn("Solved", exercise.locator(".exercise-status").inner_text())
        self.page.wait_for_function("document.querySelector('.progress-link').textContent.startsWith('1 /')")

    def test_playground_explains_errors_plans_and_stages(self):
        self.open("playground")
        editor = self.page.locator(".playground textarea")
        editor.fill("SELECT id, email FROM custmers LIMIT 5")
        editor.press("Control+Enter")
        error = self.page.locator(".callout.error")
        error.wait_for()
        self.assertIn("Unknown table", error.inner_text())
        error.get_by_role("button", name="customers").click()
        self.assertIn("FROM customers", editor.input_value())
        self.page.get_by_role("button", name="Run", exact=True).click()
        self.page.locator(".output table.data").wait_for()
        self.page.get_by_role("button", name="Explain plan").click()
        self.page.locator(".plan-tree").wait_for()
        self.page.get_by_role("button", name="Step through").click()
        self.page.locator(".stage-tab").first.wait_for()

    def test_dataset_diagram_and_table_detail(self):
        self.open("datasets/shop")
        tables = self.page.locator("svg.erd .erd-table")
        tables.first.wait_for()
        self.assertEqual(tables.count(), 9)
        self.page.locator('svg.erd .erd-table[data-table="orders"]').click()
        self.page.locator(".table-detail h3", has_text="orders").wait_for()
        self.assertIn("customer_id", self.page.locator(".table-detail").inner_text())

    def test_join_lab_matches_the_engine(self):
        self.open("labs/joins")
        self.page.get_by_role("button", name="Full", exact=True).click()
        self.page.locator(".jv-result h4", has_text="8 rows").wait_for()
        self.page.get_by_role("button", name="Run this SQL on the engine").click()
        self.page.locator(".jv-engine .agree").wait_for()
        self.assertGreater(self.page.locator(".jv-lines path.pair.active").count(), 0)

    def test_isolation_simulator(self):
        self.open("labs/isolation")
        self.page.get_by_role("button", name="Lost update").click()
        self.page.get_by_role("button", name="Read committed", exact=True).click()
        self.page.get_by_role("button", name="Show all steps").click()
        self.assertIn("lost", self.page.locator(".iso-verdict").inner_text())
        self.page.get_by_role("button", name="Repeatable read", exact=True).click()
        self.assertIn("Prevented", self.page.locator(".iso-verdict").inner_text())

    def test_index_lab_turns_a_scan_into_a_search(self):
        self.open("labs/indexes")
        self.page.locator(".index-lab .segmented").nth(1).get_by_role("button", name="customer_id").click()
        self.page.get_by_role("button", name="Compare plans").click()
        self.page.locator(".lab-compare .agree").wait_for()
        self.assertIn("SEARCH", self.page.locator(".lab-compare .two-up section").nth(1).inner_text())

    def test_query_journey(self):
        self.open("labs/journey")
        self.page.get_by_role("button", name="Trace the query").click()
        self.page.get_by_role("button", name="Optimizer").click()
        self.page.locator(".journey-panel .plan-tree").wait_for()

    def test_reference_matrix_and_filter(self):
        self.open("reference")
        rows = self.page.locator("table.matrix tbody tr")
        rows.first.wait_for()
        self.assertGreaterEqual(rows.count(), 24)
        self.page.get_by_label("Filter features").fill("json")
        self.assertEqual(self.page.locator("table.matrix tbody tr:visible").count(), 1)

    def test_shortcut_theme_and_not_found(self):
        self.open("playground")
        editor = self.page.locator(".playground textarea")
        editor.fill("SELECT 1 AS one")
        editor.press("Control+Enter")
        self.page.locator(".output table.data").wait_for()
        self.page.get_by_role("button", name="Colour theme").click()
        self.assertEqual(self.page.evaluate("document.documentElement.dataset.theme"), "light")
        self.open("nowhere")
        self.page.get_by_role("heading", name="There is no page here").wait_for()

    def test_mobile_layout_has_no_horizontal_scroll(self):
        context = self.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        page = context.new_page()
        for route in ("", "learn/aggregation", "playground", "labs/joins"):
            page.goto(f"{self.base}/#/{route}")
            page.locator("main h1").first.wait_for()
            page.wait_for_timeout(300)
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth - window.innerWidth"), 1, route)
        context.close()

    @unittest.skipUnless(SCREENSHOTS, "set JOINERY_SCREENSHOTS=1 to refresh docs/screenshots")
    def test_zz_screenshots(self):
        out = ROOT / "docs" / "screenshots"
        out.mkdir(parents=True, exist_ok=True)
        self.open("")
        self.page.get_by_role("button", name="Run it stage by stage").click()
        self.page.locator(".stage-tab").nth(1).click()
        self.page.wait_for_timeout(300)
        self.page.screenshot(path=str(out / "home-stepper.png"))
        self.open("learn/aggregation")
        example = self.page.locator("#example-agg-loyal-customers")
        example.get_by_role("button", name="Step through").click()
        example.locator(".stage-tab").nth(3).click()
        example.scroll_into_view_if_needed()
        self.page.wait_for_timeout(300)
        self.page.screenshot(path=str(out / "lesson-steps.png"))
        dark = self.browser.new_context(viewport={"width": 1360, "height": 900}, color_scheme="dark")
        page = dark.new_page()
        page.goto(f"{self.base}/#/playground")
        page.locator(".playground textarea").fill(
            "SELECT c.email, count(o.id) AS orders\nFROM customers AS c\nJOIN orders AS o ON o.customer_id = c.id\n"
            "WHERE c.country = 'SE'\nGROUP BY c.email\nORDER BY orders DESC;")
        page.get_by_role("button", name="Explain plan").click()
        page.locator(".plan-tree").wait_for()
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "playground-plan-dark.png"))
        dark.close()
        self.open("datasets/shop")
        self.page.locator('svg.erd .erd-table[data-table="orders"]').hover()
        self.page.wait_for_timeout(300)
        self.page.screenshot(path=str(out / "dataset-erd.png"))
        self.open("labs/joins")
        self.page.get_by_role("button", name="Left", exact=True).click()
        self.page.wait_for_timeout(400)
        self.page.screenshot(path=str(out / "join-lab.png"))
        self.open("labs/isolation")
        self.page.get_by_role("button", name="Write skew").click()
        self.page.get_by_role("button", name="Show all steps").click()
        self.page.wait_for_timeout(200)
        self.page.screenshot(path=str(out / "isolation-lab.png"))
        mobile = self.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=2)
        page = mobile.new_page()
        page.goto(f"{self.base}/#/learn/joins")
        page.locator("article.lesson h1").wait_for()
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "mobile-lesson.png"))
        mobile.close()


if __name__ == "__main__":
    unittest.main()
