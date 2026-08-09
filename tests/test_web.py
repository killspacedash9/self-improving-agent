"""Tests for the web front-end feature: drawing canvas."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestDrawingCanvas(unittest.TestCase):
    def setUp(self):
        self.index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.style = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    def test_draw_button_exists(self):
        self.assertIn('id="drawBtn"', self.index)
        self.assertIn("Draw", self.index)

    def test_canvas_modal_exists(self):
        self.assertIn('id="drawModal"', self.index)
        self.assertIn('id="drawCanvas"', self.index)

    def test_app_js_has_drawing_handlers(self):
        self.assertIn("openDrawing", self.app)
        self.assertIn("closeDrawing", self.app)
        self.assertIn("clearDrawing", self.app)

    def test_style_has_canvas_rules(self):
        self.assertIn("#drawCanvas", self.style)


if __name__ == "__main__":
    unittest.main()
