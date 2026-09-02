"""Analytical pre-match forecast without running virtual matches."""

from __future__ import annotations

import math
from dataclasses import dataclass

from scripts.match.player import Player
from scripts.match.team import Team
from scripts.core.settings import clamp, player_stat


TACTIC_EFFECTS = {
    "ULTRA_ATTACK": (1.20, 1.22),
    "ATTACK": (1.10, 1.10),
    "BALANCE": (1.00, 1.00),
    "DEFEND": (0.90, 0.89),
    "ULTRA_DEFEND": (0.78, 0.80),
    "NO_INSTRUCTION": (1.00, 1.03),
    "RANDOM": (1.03, 1.13),
}


@dataclass(frozen=True)
class TeamForecast:
    attack: float
    defense: float
    keeper: float
    control: float
    endurance: float
    intelligence: float
    manager: float
    bench: float


def _weighted(values: list[tuple[float, float]], default: float = 0.5) -> float:
    total_weight = sum(weight for _, weight in values)
    return sum(value * weight for value, weight in values) / total_weight if total_weight else default


def _mean(values: list[float], default: float = 0.5) -> float:
    return sum(values) / len(values) if values else default


def _player_attack(player: Player) -> float:
    return (
        player.effective_stat(player.shooting_technique) * 0.25
        + player.effective_stat(player.shot_accuracy) * 0.20
        + player.effective_stat(player.shot_power) * 0.13
        + player.effective_stat(player.dribble_technique) * 0.15
        + player.effective_stat(player.goal_poaching) * 0.15
        + player.effective_stat(player.dash_speed) * 0.12
    )


def _player_control(player: Player) -> float:
    return (
        player.effective_stat(player.passing_technique) * 0.27
        + player.effective_stat(player.pass_accuracy) * 0.24
        + player.effective_stat(player.pass_power) * 0.10
        + player.effective_stat(player.trap_technique) * 0.15
        + player.effective_stat(player.mistake_avoidance) * 0.14
        + player.effective_stat(player.support) * 0.10
    )


def _player_defense(player: Player) -> float:
    return (
        player.effective_stat(player.steal_technique) * 0.23
        + player.effective_stat(player.pass_interception) * 0.20
        + player.effective_stat(player.shot_blocking) * 0.17
        + player.effective_stat(player.man_marking) * 0.12
        + player.effective_stat(player.zone_marking) * 0.10
        + player.effective_stat(player.collision_physical) * 0.10
        + player.effective_stat(player.safe_play) * 0.08
    )


def _keeper_strength(keeper: Player) -> float:
    return (
        keeper.effective_stat(keeper.goal_stopping) * 0.38
        + keeper.effective_stat(keeper.jump_judgment) * 0.17
        + keeper.effective_stat(keeper.jump_accuracy) * 0.13
        + keeper.effective_stat(keeper.jump_height) * 0.10
        + keeper.effective_stat(keeper.mistake_avoidance) * 0.12
        + keeper.effective_intelligence * 0.10
    )


def _bench_strength(team: Team) -> float:
    if not team.bench:
        return 0.0
    keys = (
        "ShotAccuracy", "PassingTechnique", "PassInterception", "DashSpeed",
        "MaxStamina", "MistakeAvoidance", "Intelligence",
    )
    ratings = [
        _mean([player_stat(record.get("raw", {}), key) for key in keys])
        for record in team.bench
    ]
    return _mean(sorted(ratings, reverse=True)[:3], 0.0)


def evaluate_team(team: Team) -> TeamForecast:
    active = [player for player in team.players if not player.sent_off]
    outfield = [player for player in active if not player.is_keeper]
    attack_weights = {"FW": 1.45, "MF": 1.00, "DF": 0.42, "GK": 0.05}
    defense_weights = {"FW": 0.24, "MF": 0.76, "DF": 1.38, "GK": 0.05}
    control_weights = {"FW": 0.72, "MF": 1.34, "DF": 0.82, "GK": 0.20}
    attack = _weighted([(_player_attack(player), attack_weights.get(player.role, 0.7)) for player in outfield])
    defense = _weighted([(_player_defense(player), defense_weights.get(player.role, 0.7)) for player in outfield])
    control = _weighted([(_player_control(player), control_weights.get(player.role, 0.8)) for player in outfield])
    keeper = _keeper_strength(team.keeper)
    endurance = _mean([
        player.effective_stat(player.stamina_capacity_stat) * 0.52
        + player.effective_stat(player.stamina_management) * 0.28
        + player.effective_stat(player.fatigue_resistance) * 0.20
        for player in active
    ])
    intelligence = _mean([player.effective_intelligence for player in active])

    role_counts = {role: sum(player.role == role for player in outfield) for role in ("FW", "MF", "DF")}
    # Unusual formations stay legal, but missing an entire line has a measurable
    # structural cost that raw ability averages alone cannot represent.
    if role_counts["MF"] == 0:
        control *= 0.87
        attack *= 0.94
    if role_counts["DF"] == 0:
        defense *= 0.76
    if role_counts["FW"] == 0:
        attack *= 0.84

    manager = 0.0
    if team.manager.strip():
        overreaction = abs(team.manager_tactic_aggression - 0.43) * 0.035
        manager = 0.018 + team.manager_intelligence * 0.072 - overreaction
        if team.bench:
            manager += team.manager_substitution_aggression * 0.018
    return TeamForecast(
        clamp(attack, 0.0, 1.0), clamp(defense, 0.0, 1.0), clamp(keeper, 0.0, 1.0),
        clamp(control, 0.0, 1.0), clamp(endurance, 0.0, 1.0),
        clamp(intelligence, 0.0, 1.0), manager, _bench_strength(team),
    )


def expected_goals(home: Team, away: Team) -> tuple[float, float]:
    home_rating = evaluate_team(home)
    away_rating = evaluate_team(away)
    home_attack_tactic, home_exposure = TACTIC_EFFECTS.get(home.tactic, (1.0, 1.0))
    away_attack_tactic, away_exposure = TACTIC_EFFECTS.get(away.tactic, (1.0, 1.0))

    def one_side(attacker: TeamForecast, defender: TeamForecast, attack_tactic: float, exposure: float) -> float:
        creation = attacker.attack * 0.48 + attacker.control * 0.25 + attacker.intelligence * 0.12
        creation += attacker.endurance * 0.08 + attacker.manager + attacker.bench * 0.035
        resistance = defender.defense * 0.45 + defender.keeper * 0.34
        resistance += defender.control * 0.08 + defender.intelligence * 0.08 + defender.manager * 0.55
        log_advantage = (creation - resistance) * 2.30
        return 1.18 * math.exp(log_advantage) * attack_tactic * exposure

    home_xg = one_side(home_rating, away_rating, home_attack_tactic, away_exposure)
    away_xg = one_side(away_rating, home_rating, away_attack_tactic, home_exposure)
    if home.venue_role == "HOME":
        home_xg *= 1.11
        away_xg *= 0.96
    elif away.venue_role == "HOME":
        away_xg *= 1.11
        home_xg *= 0.96
    return clamp(home_xg, 0.16, 4.8), clamp(away_xg, 0.16, 4.8)


def outcome_probabilities(home: Team, away: Team) -> tuple[float, float, float]:
    home_xg, away_xg = expected_goals(home, away)
    maximum_goals = 12
    home_scores = [math.exp(-home_xg) * home_xg ** goals / math.factorial(goals) for goals in range(maximum_goals + 1)]
    away_scores = [math.exp(-away_xg) * away_xg ** goals / math.factorial(goals) for goals in range(maximum_goals + 1)]
    home_win = draw = away_win = 0.0
    for home_goals, home_probability in enumerate(home_scores):
        for away_goals, away_probability in enumerate(away_scores):
            probability = home_probability * away_probability
            if home_goals > away_goals:
                home_win += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away_win += probability
    total = home_win + draw + away_win
    raw = (home_win / total, draw / total, away_win / total)
    # Lineups never describe every source of football variance (form, weather,
    # small injuries). Calibrating 12% toward a neutral football prior avoids
    # misleading 100/0 forecasts while preserving the ordering and venue edge.
    reliability = 0.88
    prior = (0.36, 0.28, 0.36)
    return tuple(raw[index] * reliability + prior[index] * (1.0 - reliability) for index in range(3))


def percentage_triplet(probabilities: tuple[float, float, float]) -> tuple[int, int, int]:
    raw = [probability * 100.0 for probability in probabilities]
    result = [int(value) for value in raw]
    remaining = 100 - sum(result)
    order = sorted(range(3), key=lambda index: raw[index] - result[index], reverse=True)
    for index in order[:remaining]:
        result[index] += 1
    return result[0], result[1], result[2]
