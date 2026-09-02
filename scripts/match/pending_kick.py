"""Deferred ball contact created by a kick animation."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.core.simulation_geometry import Vec2
from scripts.match.player import Player
from scripts.match.player_commands import PlayerCommand


@dataclass
class PendingKick:
    """Remember one kick until its animation reaches the contact frame."""

    player: Player
    command: PlayerCommand
    target_player: Player | None = None
    set_piece_skill: float = 0.0
    target_point: Vec2 | None = None


__all__ = ("PendingKick",)
