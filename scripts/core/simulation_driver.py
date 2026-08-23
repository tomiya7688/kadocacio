"""Frontend-independent scheduling for a rendered match simulation.

The match engine owns football state and fixed physics.  A frontend only feeds
real elapsed time into this driver and renders the latest completed state.  The
small wall-time budget prevents fast-forward from monopolising the UI thread;
no physics step is skipped inside the retained backlog.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Protocol


class StepMatch(Protocol):
    state: str
    speed_multiplier: int

    def update_step(self, dt: float) -> None: ...


@dataclass
class RealtimeSimulationDriver:
    fixed_step: float = 0.05
    wall_time_budget: float = 0.008
    max_backlog: float = 1.5
    clock: Callable[[], float] = time.perf_counter
    pending_time: float = 0.0
    last_step_count: int = 0
    dropped_time: float = 0.0
    _match_identity: int | None = field(default=None, init=False, repr=False)

    def reset(self, match: StepMatch | None = None) -> None:
        self.pending_time = 0.0
        self.last_step_count = 0
        self.dropped_time = 0.0
        self._match_identity = id(match) if match is not None else None

    def advance(self, match: StepMatch, real_dt: float) -> int:
        identity = id(match)
        if identity != self._match_identity:
            self.reset(match)
        self.last_step_count = 0
        if match.state != "PLAYING":
            self.pending_time = 0.0
            return 0
        if real_dt <= 0.0:
            return 0

        requested = max(0.0, float(real_dt)) * max(0.0, float(match.speed_multiplier))
        backlog = self.pending_time + requested
        if backlog > self.max_backlog:
            self.dropped_time += backlog - self.max_backlog
            backlog = self.max_backlog
        self.pending_time = backlog

        started = self.clock()
        while self.pending_time > 0.0001 and match.state == "PLAYING":
            step = min(self.fixed_step, self.pending_time)
            match.update_step(step)
            self.pending_time -= step
            self.last_step_count += 1
            if self.last_step_count > 0 and self.clock() - started >= self.wall_time_budget:
                break

        if match.state != "PLAYING":
            self.pending_time = 0.0
        return self.last_step_count


__all__ = ("RealtimeSimulationDriver", "StepMatch")
