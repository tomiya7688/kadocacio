"""Limits supplied to one headless match run."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationLimits:
    """Termination, sampling and CPU-budget settings for a simulation."""

    wall_time_limit: float | None = None
    max_steps: int | None = None
    target_game_time: float | None = None
    sample_every_steps: int = 18
    cpu_duty_cycle: float = 1.0


__all__ = ("SimulationLimits",)
