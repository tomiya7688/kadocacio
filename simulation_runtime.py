from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field


# Match.update() already divides visible matches into at most 0.05 second
# physics steps.  Headless callers must use the same step; advancing only the
# clock makes a nominal 90 minute match contain far fewer AI decisions.
FIXED_PHYSICS_DT = 0.05
# A regulation match needs 10,800 live-play steps.  Restarts now pause the
# match clock while their movement/referee simulation continues, so headless
# callers must leave additional physics-step room without shortening the game.
MAX_FULL_MATCH_STEPS = 18_000
INACTIVE_COMMANDS = frozenset(("待機", "ポジションへ戻る", "ポジションを保つ"))


@dataclass(frozen=True)
class SimulationLimits:
    wall_time_limit: float | None = None
    max_steps: int | None = None
    target_game_time: float | None = None
    sample_every_steps: int = 18


@dataclass
class TeamTelemetry:
    command_counts: Counter[str] = field(default_factory=Counter)
    player_samples: int = 0
    active_samples: int = 0
    nearest_teammate_total: float = 0.0
    nearest_teammate_samples: int = 0
    crowded_player_samples: int = 0
    team_width_total: float = 0.0
    team_shape_samples: int = 0
    ball_distance_total: float = 0.0
    ball_distance_samples: int = 0
    takeaways: int = 0
    turnovers: int = 0

    def as_dict(self) -> dict[str, object]:
        sample_count = max(1, self.player_samples)
        shape_count = max(1, self.team_shape_samples)
        return {
            "command_counts": dict(self.command_counts.most_common()),
            "action_diversity": len(self.command_counts),
            "active_ratio": self.active_samples / sample_count,
            "average_nearest_teammate_distance": self.nearest_teammate_total / max(1, self.nearest_teammate_samples),
            "crowded_player_ratio": self.crowded_player_samples / sample_count,
            "average_team_width": self.team_width_total / shape_count,
            "average_distance_to_ball": self.ball_distance_total / max(1, self.ball_distance_samples),
            "takeaways": self.takeaways,
            "turnovers": self.turnovers,
        }


class MatchTelemetry:
    """Low-overhead observations taken outside the Match decision engine.

    The collector intentionally does not change AI decisions.  It can therefore
    be attached to rendered matches, headless tests and tuner matches alike.
    """

    def __init__(self, match, *, crowd_radius: float = 92.0) -> None:
        self.match = match
        self.crowd_radius = float(crowd_radius)
        self.teams = tuple(match.teams)
        self.team_data = tuple(TeamTelemetry() for _ in self.teams)
        self._last_control_team_index: int | None = None

    def _team_index(self, team) -> int | None:
        for index, candidate in enumerate(self.teams):
            if team is candidate:
                return index
        return None

    def observe_control(self) -> None:
        owner = getattr(self.match.ball, "owner", None)
        if owner is None:
            return
        current_index = self._team_index(owner.team)
        if current_index is None:
            return
        if self._last_control_team_index is not None and current_index != self._last_control_team_index:
            self.team_data[current_index].takeaways += 1
            self.team_data[self._last_control_team_index].turnovers += 1
        self._last_control_team_index = current_index

    def sample(self) -> None:
        ball_pos = self.match.ball.pos
        for team_index, team in enumerate(self.teams):
            data = self.team_data[team_index]
            players = tuple(team.players)
            if players:
                ys = [player.pos.y for player in players]
                data.team_width_total += max(ys) - min(ys)
                data.team_shape_samples += 1
            for player in players:
                command = getattr(player.action_command, "value", str(player.action_command))
                command = str(command)
                data.command_counts[command] += 1
                data.player_samples += 1
                if command not in INACTIVE_COMMANDS:
                    data.active_samples += 1
                distances = [player.pos.distance_to(other.pos) for other in players if other is not player]
                nearest = min(distances) if distances else 0.0
                data.nearest_teammate_total += nearest
                data.nearest_teammate_samples += 1
                if nearest < self.crowd_radius:
                    data.crowded_player_samples += 1
                data.ball_distance_total += player.pos.distance_to(ball_pos)
                data.ball_distance_samples += 1

    def team_metrics(self, team) -> dict[str, object]:
        index = self._team_index(team)
        return self.team_data[index].as_dict() if index is not None else {}


@dataclass(frozen=True)
class SimulationResult:
    reason: str
    steps: int
    elapsed_seconds: float
    game_time: float
    fulltime: bool


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
