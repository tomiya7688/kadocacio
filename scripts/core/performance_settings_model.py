"""Serializable performance preferences for one game process."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PerformanceSettings:
    """User-selected CPU, GPU and background simulation preferences."""

    cpu_limit_percent: int = 100
    gpu_rendering: bool = True
    league_simulation_mode: str = "PRECISE"

    def normalize(self) -> "PerformanceSettings":
        # Imported lazily to keep the value object independent from file I/O
        # while preserving the public performance_settings compatibility API.
        from scripts.core.performance_settings import (
            normalize_cpu_limit,
            normalize_league_simulation_mode,
        )

        self.cpu_limit_percent = normalize_cpu_limit(self.cpu_limit_percent)
        self.gpu_rendering = bool(self.gpu_rendering)
        self.league_simulation_mode = normalize_league_simulation_mode(self.league_simulation_mode)
        return self


__all__ = ("PerformanceSettings",)
