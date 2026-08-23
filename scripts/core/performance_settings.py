"""Shared, frontend-independent performance preferences.

The CPU percentage is an application work-budget limit, not an OS process
quota.  It limits worker processes and per-frame simulation work while keeping
the exact fixed-step match engine in use.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from scripts.core.paths import PERFORMANCE_SETTINGS_PATH


CPU_LIMIT_OPTIONS = (10, 25, 50, 75, 100)
DEFAULT_CPU_LIMIT_PERCENT = 100
LEAGUE_SIMULATION_MODES = {
    "ULTRA_PRECISE": {
        "label": "超精密モード",
        "description": "戦術判断を現在より高頻度で更新。最も重い",
        "ai_rethink_multiplier": 0.65,
    },
    "PRECISE": {
        "label": "精密モード",
        "description": "現在と同じ判断・更新頻度。デフォルト",
        "ai_rethink_multiplier": 1.0,
    },
    "NORMAL": {
        "label": "通常モード",
        "description": "戦術判断の更新頻度を少し抑える",
        "ai_rethink_multiplier": 1.6,
    },
    "LIGHT": {
        "label": "軽量モード",
        "description": "戦術判断の更新頻度をさらに抑える。最も軽い",
        "ai_rethink_multiplier": 2.4,
    },
}
DEFAULT_LEAGUE_SIMULATION_MODE = "PRECISE"


def normalize_cpu_limit(value: object) -> int:
    try:
        numeric = int(float(value))
    except (TypeError, ValueError):
        numeric = DEFAULT_CPU_LIMIT_PERCENT
    return max(10, min(100, numeric))


def limited_worker_count(full_budget: int, cpu_limit_percent: object) -> int:
    """Scale a previously safe worker budget without ever returning zero."""
    budget = max(1, int(full_budget))
    limit = normalize_cpu_limit(cpu_limit_percent)
    return max(1, min(budget, int(budget * limit / 100.0 + 0.5)))


def worker_duty_cycle(full_budget: int, cpu_limit_percent: object, active_workers: int) -> float:
    """Share the requested total CPU budget across the selected workers."""
    total_core_budget = max(1, int(full_budget)) * normalize_cpu_limit(cpu_limit_percent) / 100.0
    return max(0.05, min(1.0, total_core_budget / max(1, int(active_workers))))


def simulation_wall_time_budget(cpu_limit_percent: object, *, full_budget: float = 0.008) -> float:
    """Return the maximum main-thread simulation time spent in one frame."""
    return max(0.0008, float(full_budget) * normalize_cpu_limit(cpu_limit_percent) / 100.0)


def next_cpu_limit(current: object) -> int:
    value = normalize_cpu_limit(current)
    for option in CPU_LIMIT_OPTIONS:
        if option > value:
            return option
    return CPU_LIMIT_OPTIONS[0]


def normalize_league_simulation_mode(value: object) -> str:
    mode = str(value or "").strip().upper()
    return mode if mode in LEAGUE_SIMULATION_MODES else DEFAULT_LEAGUE_SIMULATION_MODE


def league_simulation_profile(value: object) -> dict[str, object]:
    return dict(LEAGUE_SIMULATION_MODES[normalize_league_simulation_mode(value)])


@dataclass
class PerformanceSettings:
    cpu_limit_percent: int = DEFAULT_CPU_LIMIT_PERCENT
    gpu_rendering: bool = True
    league_simulation_mode: str = DEFAULT_LEAGUE_SIMULATION_MODE

    def normalize(self) -> "PerformanceSettings":
        self.cpu_limit_percent = normalize_cpu_limit(self.cpu_limit_percent)
        self.gpu_rendering = bool(self.gpu_rendering)
        self.league_simulation_mode = normalize_league_simulation_mode(self.league_simulation_mode)
        return self


class CpuUsageLimiter:
    """Cooperative per-process duty-cycle limiter for headless workers."""

    def __init__(
        self,
        duty_cycle: float = 1.0,
        *,
        window_seconds: float = 0.02,
        wall_clock: Callable[[], float] = time.perf_counter,
        cpu_clock: Callable[[], float] = time.process_time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.duty_cycle = max(0.05, min(1.0, float(duty_cycle)))
        self.window_seconds = max(0.005, float(window_seconds))
        self.wall_clock = wall_clock
        self.cpu_clock = cpu_clock
        self.sleeper = sleeper
        self.wall_started = wall_clock()
        self.cpu_started = cpu_clock()

    def throttle(self) -> None:
        if self.duty_cycle >= 0.999:
            return
        now = self.wall_clock()
        wall_elapsed = now - self.wall_started
        if wall_elapsed < self.window_seconds:
            return
        cpu_elapsed = max(0.0, self.cpu_clock() - self.cpu_started)
        required_wall_time = cpu_elapsed / self.duty_cycle
        delay = required_wall_time - wall_elapsed
        if delay > 0.0:
            self.sleeper(delay)
        self.wall_started = self.wall_clock()
        self.cpu_started = self.cpu_clock()


def load_performance_settings(path: Path = PERFORMANCE_SETTINGS_PATH) -> PerformanceSettings:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return PerformanceSettings()
    if not isinstance(payload, dict):
        return PerformanceSettings()
    return PerformanceSettings(
        cpu_limit_percent=payload.get("CPU使用率上限", payload.get("cpu_limit_percent", DEFAULT_CPU_LIMIT_PERCENT)),
        gpu_rendering=payload.get("GPU描画", payload.get("gpu_rendering", True)),
        league_simulation_mode=payload.get(
            "リーグ裏試合モード",
            payload.get("league_simulation_mode", DEFAULT_LEAGUE_SIMULATION_MODE),
        ),
    ).normalize()


def save_performance_settings(
    settings: PerformanceSettings,
    path: Path = PERFORMANCE_SETTINGS_PATH,
) -> None:
    settings.normalize()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "CPU使用率上限": settings.cpu_limit_percent,
        "GPU描画": settings.gpu_rendering,
        "リーグ裏試合モード": settings.league_simulation_mode,
        "説明": "CPU値は同時試合数と1フレーム内の演算量に対する上限です。GPUは画面描画に使用します。",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = (
    "CPU_LIMIT_OPTIONS",
    "DEFAULT_CPU_LIMIT_PERCENT",
    "DEFAULT_LEAGUE_SIMULATION_MODE",
    "LEAGUE_SIMULATION_MODES",
    "PerformanceSettings",
    "CpuUsageLimiter",
    "limited_worker_count",
    "load_performance_settings",
    "next_cpu_limit",
    "league_simulation_profile",
    "normalize_league_simulation_mode",
    "normalize_cpu_limit",
    "save_performance_settings",
    "simulation_wall_time_budget",
    "worker_duty_cycle",
)
