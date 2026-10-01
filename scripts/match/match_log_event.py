"""Immutable observation of one message emitted by the match engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatchLogEvent:
    sequence: int
    game_time: float
    simulation_elapsed: float
    text: str

    def to_payload(self) -> dict:
        """Return detached JSON values in chronological sequence order."""
        return {
            "sequence": self.sequence,
            "game_time": self.game_time,
            "simulation_elapsed": self.simulation_elapsed,
            "text": self.text,
        }
