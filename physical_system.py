from __future__ import annotations

import math
import random


def venue_ability_factor(venue_role: str, mental: float) -> float:
    """Return the match ability multiplier for HOME/NEUTRAL/AWAY."""
    mental = max(0.0, min(1.0, mental))
    if venue_role == "HOME":
        return 1.03
    if venue_role == "AWAY":
        return 0.86 + mental * 0.14
    return 1.0


def collision_strength(
    collision_physical: float,
    physical_play_quality: float,
    movement_speed: float,
    dribble_physical: float = 0.0,
) -> float:
    """Score a shoulder-to-shoulder contest without turning it into an attack."""
    physical = collision_physical * 0.62 + physical_play_quality * 0.28 + dribble_physical * 0.10
    momentum = min(1.0, max(0.0, movement_speed) / 210.0)
    return 0.18 + physical * 1.32 + momentum * (0.18 + physical_play_quality * 0.22)


def dribble_protection(dribble_physical: float, physical_play_quality: float) -> float:
    dribble_physical = max(0.0, min(1.0, dribble_physical))
    physical_play_quality = max(0.0, min(1.0, physical_play_quality))
    return dribble_physical * 0.70 + physical_play_quality * 0.30


def foul_chance(safe_play: float, dangerousness: float, physical_play_quality: float) -> float:
    """Probability that one completed contact is judged a foul."""
    safe_play = max(0.0, min(1.0, safe_play))
    dangerousness = max(0.0, min(1.5, dangerousness))
    physical_play_quality = max(0.0, min(1.0, physical_play_quality))
    chance = 0.05 + dangerousness * 0.34
    chance *= 1.24 - safe_play * 0.84
    chance *= 1.12 - physical_play_quality * 0.32
    return max(0.015, min(0.64, chance))


def choose_card(
    safe_play: float,
    dangerousness: float,
    rng: random.Random,
) -> str:
    """Return an empty string, YELLOW, or RED after a foul."""
    safe_play = max(0.0, min(1.0, safe_play))
    dangerousness = max(0.0, min(1.5, dangerousness))
    red_chance = max(0.0, dangerousness - 0.82) * (0.13 - safe_play * 0.08)
    yellow_chance = (0.13 + dangerousness * 0.36) * (1.0 - safe_play * 0.58)
    roll = rng.random()
    if roll < red_chance:
        return "RED"
    if roll < red_chance + yellow_chance:
        return "YELLOW"
    return ""


def collision_knockback(winner_score: float, loser_score: float, relative_speed: float) -> float:
    ratio = winner_score / max(0.15, loser_score)
    speed_factor = min(1.0, max(0.0, relative_speed) / 230.0)
    return max(4.0, min(30.0, 5.0 + math.sqrt(ratio) * 8.0 + speed_factor * 12.0))
