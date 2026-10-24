"""Renderer-independent page state for completed-match record lists."""
from __future__ import annotations


class FulltimePagination:
    """Keep record pages in bounds and reset them when the match changes."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._match = None
        self.pages = {"scorers": 0, "results": 0}

    def bind(self, match: object) -> None:
        if self._match is not match:
            self.reset()
            self._match = match

    @staticmethod
    def count(total: int, size: int) -> int:
        return max(1, (total + size - 1) // size)

    def change(self, section: str, total: int, size: int, step: int = 0) -> None:
        self.pages[section] = max(0, min(self.count(total, size) - 1, self.pages[section] + step))
