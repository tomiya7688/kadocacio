"""Low-cost manager decisions for tactics and substitutions.

The manager observes accurate match state, but Intelligence controls how well
that information is weighted. Aggressiveness changes review frequency and the
threshold for acting; deliberately, it is not a simple strength multiplier.
"""

from __future__ import annotations

from dataclasses import dataclass
import random

from scripts.core.settings import clamp
from scripts.core.stat_scale import normalize_player_stat


TACTIC_SCALE = ("ULTRA_DEFEND", "DEFEND", "BALANCE", "ATTACK", "ULTRA_ATTACK")


def manager_stat(value: object, default: float) -> float:
    return normalize_player_stat(value, default)


@dataclass(frozen=True)
class ManagerProfile:
    name: str
    tactic_aggression: float
    substitution_aggression: float
    intelligence: float

    @property
    def active(self) -> bool:
        return bool(self.name.strip())


def review_interval(profile: ManagerProfile, rng: random.Random) -> float:
    """Return match-clock seconds until the next review."""
    base = 310.0 - profile.tactic_aggression * 165.0
    return rng.uniform(base * 0.82, base * 1.18)


def tactic_target(
    profile: ManagerProfile,
    score_delta: int,
    shot_delta: int,
    possession_share: float,
    field_progress: float,
    match_progress: float,
    rng: random.Random,
) -> float:
    """Estimate the useful point on the 0=defend .. 4=attack scale."""
    late = clamp((match_progress - 0.48) / 0.52, 0.0, 1.0)
    urgency = -score_delta * (0.62 + late * 1.02)
    evidence = -shot_delta * 0.10 + (0.50 - possession_share) * 0.62
    territory = (0.50 - field_progress) * 0.30
    accurate = 2.0 + urgency + evidence + territory
    # A weak manager still reacts in broadly the right direction, but reads
    # short-term match noise less reliably. A high-aggression manager acts on
    # that noise more often, which is why aggression is not always beneficial.
    noise = rng.uniform(-1.15, 1.15) * (1.0 - profile.intelligence) * (
        0.72 + profile.tactic_aggression * 0.58
    )
    return clamp(accurate + noise, 0.0, 4.0)


def choose_tactic(
    profile: ManagerProfile,
    current_tactic: str,
    target: float,
    match_progress: float,
    rng: random.Random,
) -> str | None:
    current_index = TACTIC_SCALE.index(current_tactic) if current_tactic in TACTIC_SCALE else 2
    utilities: list[tuple[float, str]] = []
    for index, tactic in enumerate(TACTIC_SCALE):
        fit = 1.0 - abs(index - target) / 4.0
        stability = 0.08 if index == current_index else 0.0
        noise = rng.uniform(-0.30, 0.30) * (1.0 - profile.intelligence)
        utilities.append((fit + stability + noise, tactic))
    best_utility, best = max(utilities, key=lambda item: item[0])
    current_fit = 1.0 - abs(current_index - target) / 4.0 + 0.08
    improvement = best_utility - current_fit
    threshold = 0.24 - profile.tactic_aggression * 0.17
    threshold -= clamp((match_progress - 0.78) / 0.22, 0.0, 1.0) * 0.07
    if best == current_tactic or improvement < threshold:
        return None
    return best


def substitution_fatigue_threshold(profile: ManagerProfile, match_progress: float) -> float:
    """Stamina ratio below which a change becomes attractive.

    Aggressive managers act earlier and can therefore waste a useful player;
    conservative managers risk waiting too long.
    """
    return clamp(
        0.30 + profile.substitution_aggression * 0.39 + match_progress * 0.12,
        0.30,
        0.81,
    )
