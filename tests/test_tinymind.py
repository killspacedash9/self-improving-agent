"""Tests for TinyMind — the sample product Aster improves."""

import unittest

from src.tinymind import TinyMind


class TestTinyMind(unittest.TestCase):
    def test_greet_named(self):
        self.assertEqual(TinyMind().greet("Ada"), "Hello, Ada! I am TinyMind.")

    def test_greet_unknown(self):
        self.assertEqual(TinyMind().greet(), "Hello, mysterious stranger.")
        self.assertEqual(TinyMind().greet("   "), "Hello, mysterious stranger.")

    def test_version(self):
        self.assertRegex(TinyMind().version(), r"^\d+\.\d+\.\d+$")

    def test_remember_and_recall(self):
        mind = TinyMind()
        mind.remember("python", "a friendly snake")
        self.assertEqual(mind.recall("Python"), "a friendly snake")
        self.assertIn("nothing", mind.recall("quantum"))

    def test_todos(self):
        mind = TinyMind()
        mind.add_todo("improve yourself")
        self.assertEqual(mind.todos_list(), ["improve yourself"])


if __name__ == "__main__":
    unittest.main()
