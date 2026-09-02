"""Outcome metadata for one headless match run."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationResult:
    """Explain why a simulation ended and how far it progressed."""

    reason: str
    steps: int
    elapsed_seconds: float
    game_time: float
    fulltime: bool


__all__ = ("SimulationResult",)
