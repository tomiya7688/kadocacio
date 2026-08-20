from __future__ import annotations

import random
from enum import Enum


class TrapStyle(str, Enum):
    RIGHT_FOOT = "右足トラップ"
    LEFT_FOOT = "左足トラップ"
    RIGHT_KNEE = "右膝トラップ"
    LEFT_KNEE = "左膝トラップ"
    CHEST = "胸トラップ"


def mistake_error_multiplier(ability: float) -> float:
    """Scale direction/read errors: a high ability makes mistakes less frequent."""
    ability = max(0.0, min(1.0, ability))
    return 1.30 - ability * 0.55


def mistake_success_multiplier(ability: float) -> float:
    """Scale binary technique checks without making any action infallible."""
    ability = max(0.0, min(1.0, ability))
    return 0.80 + ability * 0.32


def choose_trap_style(height: float, lateral_velocity: float, rng: random.Random) -> TrapStyle:
    """Choose the receiving surface from ball height and approach side."""
    prefer_right = lateral_velocity >= 0.0
    if rng.random() < 0.18:
        prefer_right = not prefer_right
    if height <= 19.0:
        return TrapStyle.RIGHT_FOOT if prefer_right else TrapStyle.LEFT_FOOT
    if height <= 47.0:
        return TrapStyle.RIGHT_KNEE if prefer_right else TrapStyle.LEFT_KNEE
    return TrapStyle.CHEST


def trap_touch_offset(style: TrapStyle, attack_direction: int, lateral_velocity: float) -> tuple[float, float]:
    """Each receiving surface settles the ball in a slightly different direction."""
    if style is TrapStyle.RIGHT_FOOT:
        return attack_direction * 10.0, 6.0
    if style is TrapStyle.LEFT_FOOT:
        return attack_direction * 10.0, -6.0
    if style is TrapStyle.RIGHT_KNEE:
        return attack_direction * 16.0, 4.0
    if style is TrapStyle.LEFT_KNEE:
        return attack_direction * 16.0, -4.0
    chest_side = 2.5 if lateral_velocity >= 0.0 else -2.5
    return attack_direction * 6.0, chest_side


def trap_success_chance(
    trap_ability: float,
    mistake_ability: float,
    fatigue_factor: float,
    incoming_speed: float,
    ball_height: float,
    interception_ability: float | None = None,
) -> float:
    trap_ability = max(0.0, min(1.0, trap_ability))
    mistake_ability = max(0.0, min(1.0, mistake_ability))
    if interception_ability is None:
        base = 0.47 + trap_ability * 0.43
    else:
        interception = max(0.0, min(1.0, interception_ability))
        base = 0.20 + trap_ability * 0.35 + interception * 0.36
    speed_penalty = max(0.0, min(0.43, (incoming_speed - 150.0) / 760.0))
    height_penalty = max(0.0, min(0.10, (ball_height - 58.0) / 500.0))
    chance = (base - speed_penalty - height_penalty) * mistake_success_multiplier(mistake_ability)
    return max(0.06, min(0.97, chance * max(0.32, fatigue_factor)))


def interception_reach(ability: float) -> float:
    ability = max(0.0, min(1.0, ability))
    return 72.0 + ability * 188.0
