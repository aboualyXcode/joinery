"""Every lesson example runs and every exercise is gradeable, on the real engine."""

import unittest
from pathlib import Path

from joinery.config import Settings
from joinery.content import load_content
from joinery.service import Platform
from joinery.validation import validate

ROOT = Path(__file__).resolve().parent.parent
ENGINES = ("sqlite", "postgres", "mysql", "mssql", "duckdb")


class CurriculumTests(unittest.TestCase):
    content = load_content(ROOT / "content")

    def test_every_example_and_exercise_validates(self):
        settings = Settings(data_dir=ROOT / "var" / "datasets", content_dir=ROOT / "content",
                            web_dir=ROOT / "web" / "dist", engines=("sqlite",), rate_limit=0)
        report = validate(Platform(settings), jobs=6)
        self.assertEqual(report["failures"], [], report["failures"][:5])
        self.assertGreaterEqual(report["examples"], 120)
        self.assertGreaterEqual(report["exercises"], 60)

    def test_curriculum_shape(self):
        self.assertEqual([m["id"] for m in self.content.modules],
                         ["foundations", "combining", "changing", "analytics", "performance", "production"])
        for lesson in self.content.lessons.values():
            with self.subTest(lesson=lesson["id"]):
                self.assertTrue(lesson["exercises"], "every lesson has exercises")
                self.assertTrue(lesson["references"], "every lesson cites documentation")
                self.assertTrue(set(lesson["dialect_notes"]) <= set(ENGINES))
                for reference in lesson["references"]:
                    self.assertTrue(reference["url"].startswith("https://"), reference)

    def test_dialect_reference_covers_every_engine(self):
        self.assertEqual([e["id"] for e in self.content.dialects["engines"]], list(ENGINES))
        for feature in self.content.dialects["features"]:
            with self.subTest(feature=feature["id"]):
                self.assertEqual(set(feature["support"]), set(ENGINES))
                for cell in feature["support"].values():
                    self.assertIn(cell["level"], ("yes", "partial", "no"))

    def test_widgets_used_by_lessons(self):
        widgets = {s["widget"]["type"] for l in self.content.lessons.values() for s in l["sections"] if s["widget"]}
        self.assertEqual(widgets, {"join-visualizer", "isolation-simulator", "index-lab", "query-journey",
                                   "processing-order", "erd"})


if __name__ == "__main__":
    unittest.main()
