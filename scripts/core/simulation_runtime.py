from __future__ import annotations

import time

from scripts.core.match_telemetry import INACTIVE_COMMANDS, MatchTelemetry
from scripts.core.cpu_usage_limiter import CpuUsageLimiter
from scripts.core.simulation_limits import SimulationLimits
from scripts.core.simulation_result import SimulationResult
from scripts.core.team_telemetry import TeamTelemetry


# Match.update() already divides visible matches into at most 0.05 second
# physics steps.  Headless callers must use the same step; advancing only the
# clock makes a nominal 90 minute match contain far fewer AI decisions.
FIXED_PHYSICS_DT = 0.05
# A regulation match needs 10,800 live-play steps.  Restarts now pause the
# match clock while their movement/referee simulation continues, so headless
# callers must leave additional physics-step room without shortening the game.
MAX_FULL_MATCH_STEPS = 18_000
def advance_match_fixed(match, dt: float = FIXED_PHYSICS_DT) -> None:
    """Advance physics, timers, AI and the match clock by the same amount."""
    if dt <= 0.0 or dt > FIXED_PHYSICS_DT + 1e-9:
        raise ValueError(f"fixed physics dt must be in 0..{FIXED_PHYSICS_DT}")
    match.update_step(dt)


def run_headless_match(
    match,
    limits: SimulationLimits | None = None,
    telemetry: MatchTelemetry | None = None,
) -> SimulationResult:
    """Run the real Match engine without creating a window or renderer."""
    limits = limits or SimulationLimits()
    sample_every = max(1, int(limits.sample_every_steps))
    deadline = None
    if limits.wall_time_limit is not None:
        deadline = time.perf_counter() + max(0.0, float(limits.wall_time_limit))
    started = time.perf_counter()
    cpu_limiter = CpuUsageLimiter(limits.cpu_duty_cycle)
    steps = 0
    reason = "fulltime"
    while match.state != "FULLTIME":
        if deadline is not None and time.perf_counter() >= deadline:
            reason = "wall_time_limit"
            break
        if limits.max_steps is not None and steps >= max(0, int(limits.max_steps)):
            reason = "max_steps"
            break
        if limits.target_game_time is not None and match.game_time >= float(limits.target_game_time):
            reason = "target_game_time"
            break
        advance_match_fixed(match)
        steps += 1
        cpu_limiter.throttle()
        if telemetry is not None:
            telemetry.observe_control()
            if steps % sample_every == 0:
                telemetry.sample()
    return SimulationResult(
        reason=reason,
        steps=steps,
        elapsed_seconds=time.perf_counter() - started,
        game_time=float(match.game_time),
        fulltime=match.state == "FULLTIME",
    )
