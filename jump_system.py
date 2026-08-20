from __future__ import annotations

import random


def maximum_jump_height(ability: float) -> float:
    """Maximum body lift in world units for a normalized JumpHeight stat."""
    ability = max(0.0, min(1.0, ability))
    return 18.0 + ability * 74.0


def jump_apex_time(ability: float) -> float:
    """Seconds needed to reach the selected apex for a normalized JumpSpeed stat."""
    ability = max(0.0, min(1.0, ability))
    return 0.64 - ability * 0.40


def jump_prediction_quality(judgment: float, reading_technique: float) -> float:
    judgment = max(0.0, min(1.0, judgment))
    reading_technique = max(0.0, min(1.0, reading_technique))
    return judgment * 0.64 + reading_technique * 0.36


def prediction_error_scales(quality: float, mistake_error: float) -> tuple[float, float]:
    quality = max(0.0, min(1.0, quality))
    remaining = 1.0 - quality
    return 8.0 + remaining * 58.0 * mistake_error, 4.0 + remaining * 31.0 * mistake_error


def execute_jump_plan(
    desired_height: float,
    height_ability: float,
    accuracy_ability: float,
    speed_ability: float,
    mistake_error: float,
    rng: random.Random,
) -> tuple[float, float]:
    """Return actual apex and ascent time after execution error is applied."""
    maximum = maximum_jump_height(height_ability)
    desired = max(7.0, min(maximum, desired_height))
    accuracy = max(0.0, min(1.0, accuracy_ability))
    height_sigma = (1.0 - accuracy) * (5.0 + desired * 0.24) * mistake_error
    actual_height = max(5.0, min(maximum, desired + rng.gauss(0.0, height_sigma)))
    base_time = jump_apex_time(speed_ability)
    timing_sigma = (1.0 - accuracy) * 0.12 * mistake_error
    actual_time = base_time * max(0.76, min(1.28, 1.0 + rng.gauss(0.0, timing_sigma)))
    return actual_height, actual_time


def heading_ball_speed(
    power_ability: float,
    judgment_ability: float,
    desired_distance: float,
    rng: random.Random,
) -> float:
    power = max(0.0, min(1.0, power_ability))
    judgment = max(0.0, min(1.0, judgment_ability))
    ideal_force = max(0.36, min(1.0, desired_distance / 330.0))
    chosen_force = ideal_force * judgment + rng.uniform(0.34, 1.0) * (1.0 - judgment)
    return 132.0 + power * (92.0 + chosen_force * 122.0)


def heading_error_sigma(accuracy_ability: float, distance: float, mistake_error: float) -> float:
    accuracy = max(0.0, min(1.0, accuracy_ability))
    return (7.0 + distance * 0.065) * (1.18 - accuracy * 0.96) * mistake_error
