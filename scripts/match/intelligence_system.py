from __future__ import annotations

import math
import random
from typing import TypeVar


Action = TypeVar("Action")


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def blended_judgment(specialist_skill: float, intelligence: float, specialist_weight: float = 0.68) -> float:
    """Combine knowing how to execute an action with knowing when to use it."""
    specialist_weight = clamp01(specialist_weight)
    return clamp01(specialist_skill * specialist_weight + intelligence * (1.0 - specialist_weight))


def perceived_utility(
    utility: float,
    intelligence: float,
    rng: random.Random,
    noise_span: float = 0.24,
) -> float:
    """Cheap utility-AI perception: low intelligence adds more evaluation noise."""
    intelligence = clamp01(intelligence)
    noise = noise_span * (1.0 - intelligence) + 0.012
    return utility + rng.uniform(-noise, noise)


def choose_utility_action(
    utilities: dict[Action, float],
    intelligence: float,
    rng: random.Random,
) -> Action:
    return max(
        utilities,
        key=lambda action: perceived_utility(utilities[action], intelligence, rng),
    )


def strategic_possession_risk(
    intelligence: float,
    field_progress: float,
    pressure: float,
    dribble_quality: float,
    interception_risk: float,
) -> tuple[float, float]:
    """Return pass and dribble risk penalties for the current field situation.

    This is a one-step strategic layer above raw action execution. Intelligent
    players protect possession more strongly near their own goal, while good
    dribblers still retain the option to escape pressure themselves.
    """
    intelligence = clamp01(intelligence)
    own_goal_danger = clamp01((0.46 - clamp01(field_progress)) / 0.46)
    pressure = clamp01(pressure)
    pass_penalty = clamp01(interception_risk) * intelligence * (0.16 + own_goal_danger * 0.48)
    dribble_penalty = (
        pressure * (1.0 - clamp01(dribble_quality)) * intelligence
        * (0.14 + own_goal_danger * 0.52)
    )
    return pass_penalty, dribble_penalty


def slide_tackle_utility(
    distance: float,
    closing_speed: float,
    steal_skill: float,
    ball_control: float,
    safe_play: float,
    intelligence: float,
    goal_danger: float,
    rng: random.Random,
) -> float:
    """Risk-adjusted value of leaving the feet instead of standing up the attacker."""
    timing = clamp01(1.0 - abs(distance - 48.0) / 34.0)
    advantage = (clamp01(steal_skill) - clamp01(ball_control)) * 0.42
    closing_bonus = clamp01(closing_speed / 210.0) * 0.10
    foul_risk = (1.0 - clamp01(safe_play)) * (0.18 + clamp01(closing_speed / 250.0) * 0.22)
    base = 0.20 + timing * 0.34 + advantage + closing_bonus + clamp01(goal_danger) * 0.25 - foul_risk
    return perceived_utility(base, intelligence, rng, noise_span=0.16)


def slide_start_probability(utility: float, dt: float) -> float:
    """Convert a useful slide decision into a low-frequency per-step hazard."""
    if utility < 0.50:
        return 0.0
    rate_per_second = 0.05 + min(0.30, (utility - 0.50) * 0.80)
    return 1.0 - math.exp(-rate_per_second * max(0.0, dt))


def header_attempt_utility(
    purpose: str,
    distance: float,
    predicted_height: float,
    reading: float,
    intelligence: float,
    goal_distance: float,
    rng: random.Random,
) -> float:
    reach_timing = clamp01(1.0 - distance / 135.0)
    useful_height = clamp01((predicted_height - 25.0) / 65.0)
    if purpose == "SHOOT":
        situation = clamp01(1.0 - goal_distance / 330.0) * 0.42
    elif purpose == "BLOCK":
        situation = 0.42
    else:
        situation = 0.26
    base = 0.16 + reach_timing * 0.22 + useful_height * 0.16 + reading * 0.18 + situation
    return perceived_utility(base, intelligence, rng, noise_span=0.12)
