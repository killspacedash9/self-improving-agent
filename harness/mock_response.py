"""Canned agent response for the offline demo (--mock).

This is what DeepSeek would return for the task "Add a random-proverb
quote() method to TinyMind, with tests." It lets you exercise the full
improvement loop (apply → syntax check → test → journal → commit → push)
without an API key.
"""

RESPONSE = {
    "summary": "Add a random-proverb quote() method to TinyMind, with tests.",
    "files": {
        "src/tinymind.py": '''"""TinyMind — a tiny, friendly mind that greets people and remembers facts.

This is the sample product living inside the self-improving repository.
The repository agent (Aster) owns this file: it can extend, refactor, and
improve TinyMind in response to feature requests and bug reports filed
through the chat window.
"""

from __future__ import annotations

import random


class TinyMind:
    """A tiny mind with a greeting, a memory for facts, and a todo list."""

    PROVERBS = [
        "A journey of a thousand miles begins with a single commit.",
        "The best time to test was yesterday; the next best time is now.",
        "He who ships without tests ships twice.",
        "A refactor a day keeps the bugs away.",
        "Even the largest codebase started as an empty repository.",
    ]

    def __init__(self) -> None:
        self.facts: dict[str, str] = {}
        self.todos: list[str] = []

    def greet(self, name: str | None = None) -> str:
        """Greet a visitor. Unknown visitors get a mysterious greeting."""
        name = (name or "").strip()
        if not name:
            return "Hello, mysterious stranger."
        return f"Hello, {name}! I am TinyMind."

    def version(self) -> str:
        """Return the current version of TinyMind."""
        return "0.1.0"

    def remember(self, topic: str, fact: str) -> None:
        """Store a fact under a topic (case-insensitive)."""
        self.facts[topic.strip().lower()] = fact

    def recall(self, topic: str) -> str:
        """Recall a fact, or admit ignorance."""
        return self.facts.get(topic.strip().lower(), f"I know nothing about {topic}.")

    def add_todo(self, item: str) -> None:
        """Add an item to the todo list."""
        self.todos.append(item)

    def todos_list(self) -> list[str]:
        """Return the current todo list."""
        return list(self.todos)

    def quote(self) -> str:
        """Return a random proverb from the built-in collection."""
        return random.choice(self.PROVERBS)


def version() -> str:
    """Module-level convenience wrapper."""
    return TinyMind().version()
''',
        "tests/test_tinymind.py": '''"""Tests for TinyMind — the sample product Aster improves."""

import unittest

from src.tinymind import TinyMind


class TestTinyMind(unittest.TestCase):
    def test_greet_named(self):
        self.assertEqual(TinyMind().greet("Ada"), "Hello, Ada! I am TinyMind.")

    def test_greet_unknown(self):
        self.assertEqual(TinyMind().greet(), "Hello, mysterious stranger.")
        self.assertEqual(TinyMind().greet("   "), "Hello, mysterious stranger.")

    def test_version(self):
        self.assertRegex(TinyMind().version(), r"^\\d+\\.\\d+\\.\\d+$")

    def test_remember_and_recall(self):
        mind = TinyMind()
        mind.remember("python", "a friendly snake")
        self.assertEqual(mind.recall("Python"), "a friendly snake")
        self.assertIn("nothing", mind.recall("quantum"))

    def test_todos(self):
        mind = TinyMind()
        mind.add_todo("improve yourself")
        self.assertEqual(mind.todos_list(), ["improve yourself"])

    def test_quote(self):
        mind = TinyMind()
        for _ in range(50):
            q = mind.quote()
            self.assertIsInstance(q, str)
            self.assertTrue(q)
            self.assertIn(q, TinyMind.PROVERBS)


if __name__ == "__main__":
    unittest.main()
''',
    },
    "soul_lessons": [
        "A well-scoped feature request with acceptance criteria is the easiest to satisfy.",
    ],
}
