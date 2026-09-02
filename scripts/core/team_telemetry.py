"""Aggregated observations for one simulated team."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class TeamTelemetry:
    """Accumulate low-cost command, spacing and possession statistics."""

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


__all__ = ("TeamTelemetry",)
