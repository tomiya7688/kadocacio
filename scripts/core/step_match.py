"""Minimal match interface required by a realtime simulation driver."""

from __future__ import annotations

from typing import Protocol


class StepMatch(Protocol):
    """A match-like object that advances in deterministic fixed steps."""

    state: str
    speed_multiplier: int

    def update_step(self, dt: float) -> None: ...


__all__ = ("StepMatch",)
