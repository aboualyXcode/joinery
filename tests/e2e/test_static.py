"""Smoke-test the published preview: the static client replaying recorded
responses, served from a subpath exactly as GitHub Pages serves it.

Build it first, then point JOINERY_STATIC_SITE at it:

    npm run build:static
    python -m joinery snapshot --out web/site/snapshots
    JOINERY_STATIC_SITE=web/site python -m unittest tests.e2e.test_static
"""

import functools
import os
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE = os.environ.get("JOINERY_STATIC_SITE")
PREFIX = "/joinery"


class SubpathHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        return super().translate_path(path[len(PREFIX):] if path.startswith(PREFIX + "/") else "/__outside__")

    def log_message(self, *args):
        pass


@unittest.skipUnless(SITE, "set JOINERY_STATIC_SITE to a built static site")
class StaticPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        handler = functools.partial(SubpathHandler, directory=str(Path(SITE).resolve()))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}{PREFIX}/"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.problems = []
        self.page.on("pageerror", lambda exc: self.problems.append(str(exc)))

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.problems, [])

    def open(self, route):
        self.page.goto(f"{self.base}#/{route}")

    def test_home_loads_from_the_subpath_with_the_banner(self):
        self.open("")
        self.page.locator(".static-banner").wait_for()
        self.page.locator(".engine-teaser svg.engine-map").wait_for()

    def test_recorded_examples_and_diagrams_replay(self):
        self.open("learn/select-basics")
        example = self.page.locator(".example").first
        example.get_by_role("button", name="Run", exact=True).click()
        example.locator("table.data").wait_for()
        example.get_by_role("button", name="Visualize").click()
        example.locator(".query-map svg.band").wait_for()
        self.open("explore/failures/unique-violation")
        self.page.get_by_role("button", name="Reproduce it on SQLite").click()
        self.page.locator(".timeline .t-failed").wait_for()
        self.open("explore/query?preset=broken-cte")
        self.page.locator(".dep-node.status-error").wait_for()
        self.open("labs/joins")
        self.page.locator(".joinviz svg").first.wait_for()

    def test_unrecorded_sql_explains_how_to_run_it(self):
        self.open("playground")
        editor = self.page.locator(".playground textarea")
        editor.fill("SELECT 42 AS answer")
        editor.press("Control+Enter")
        self.assertIn("replays results recorded", self.page.locator(".callout.error").inner_text())


if __name__ == "__main__":
    unittest.main()
