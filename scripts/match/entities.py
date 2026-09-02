"""Compatibility exports for match entities.

New code should import each class from player, team or ball directly.
"""

from scripts.match.ball import Ball
from scripts.match.player import Player
from scripts.match.team import Team

__all__ = ("Ball", "Player", "Team")
