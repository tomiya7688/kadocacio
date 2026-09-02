"""Read-only telemetry collection for one match."""

from __future__ import annotations

from scripts.core.team_telemetry import TeamTelemetry


INACTIVE_COMMANDS = frozenset(("待機", "ポジションへ戻る", "ポジションを保つ"))


class MatchTelemetry:
    """Observe a match without changing any AI decision or physics state."""

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


__all__ = ("INACTIVE_COMMANDS", "MatchTelemetry")
