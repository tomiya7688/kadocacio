"""Cooperative CPU duty-cycle limiting for one worker process."""

from __future__ import annotations

import time
from typing import Callable


class CpuUsageLimiter:
    """Sleep between work windows to keep a worker near its CPU budget."""

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


__all__ = ("CpuUsageLimiter",)
