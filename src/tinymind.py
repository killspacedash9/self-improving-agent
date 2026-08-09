"""TinyMind — a tiny, friendly mind that greets people and remembers facts.

This is the sample product living inside the self-improving repository.
The repository agent (Aster) owns this file: it can extend, refactor, and
improve TinyMind in response to feature requests and bug reports filed
through the chat window.
"""

from __future__ import annotations

import random


class TinyMind:
    """A tiny mind with a greeting, a memory for facts, and a todo list."""

    PROVERBS: list[str] = [
        "A journey of a thousand miles begins with a single step.",
        "Actions speak louder than words.",
        "A rolling stone gathers no moss.",
        "Don't count your chickens before they hatch.",
        "The early bird catches the worm.",
        "Every cloud has a silver lining.",
        "Rome wasn't built in a day.",
        "When in Rome, do as the Romans do.",
        "Haste makes waste.",
        "A picture is worth a thousand words.",
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

    def fact_count(self) -> int:
        """Return how many facts are currently stored."""
        return len(self.facts)

    def add_todo(self, item: str) -> None:
        """Add an item to the todo list."""
        self.todos.append(item)

    def todos_list(self) -> list[str]:
        """Return the current todo list."""
        return list(self.todos)

    def clear_todos(self) -> None:
        """Remove all items from the todo list."""
        self.todos.clear()

    def proverb(self) -> str:
        """Return a random proverb from TinyMind's collection."""
        return random.choice(self.PROVERBS)


def version() -> str:
    """Module-level convenience wrapper."""
    return TinyMind().version()
