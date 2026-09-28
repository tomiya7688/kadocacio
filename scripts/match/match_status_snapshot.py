"""Immutable, renderer-independent state for the in-match scoreboard."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatchStatusSnapshot:
    home_short_name: str
    away_short_name: str
    home_score: int
    away_score: int
    game_time: float
    state: str
    banner: str
    banner_timer: float
    speed_multiplier: int


__all__ = ("MatchStatusSnapshot",)
