"""Immutable, renderer-independent result of one completed match."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatchResult:
    home_score: int
    away_score: int
    home_shots: int
    away_shots: int
    home_possession: float
    away_possession: float
    goal_scorers: tuple[tuple[int, str], ...]
    game_time: float

    @property
    def winner(self) -> str:
        if self.home_score > self.away_score:
            return "HOME"
        if self.away_score > self.home_score:
            return "AWAY"
        return "DRAW"

    def to_payload(self) -> dict:
        """Return detached values that existing league workers can serialize."""
        return {
            "home_score": self.home_score,
            "away_score": self.away_score,
            "home_shots": self.home_shots,
            "away_shots": self.away_shots,
            "home_possession": self.home_possession,
            "away_possession": self.away_possession,
            "goal_scorers": list(self.goal_scorers),
            "game_time": self.game_time,
        }


__all__ = ("MatchResult",)
