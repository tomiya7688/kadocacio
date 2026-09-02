"""Roster, tactics and match totals for one football team."""

from __future__ import annotations

import random
from collections import deque
from copy import deepcopy

from scripts.match.player_commands import PlayerCommand, command_spec
from scripts.match.player_style_system import STYLE_FIELDS, combined_preference, normalize_player_type, type_preference
from scripts.match.physical_system import venue_ability_factor
from scripts.match.skill_system import SKILL_COMMAND, SKILL_COOLDOWN, normalized_skills
from scripts.core.settings import BASE_TACTIC_KEYS, FIELD, GRAVITY, TACTICS, percentage_stat, player_stat
from scripts.match.stamina_system import (
    RECOVERY_ACTIONS,
    command_stamina_cost,
    command_stamina_drain,
    fatigue_error_multiplier,
    fatigue_multiplier,
    stamina_capacity,
    stamina_recovery_rate,
)
from scripts.match.technique_system import mistake_error_multiplier, mistake_success_multiplier
from scripts.match.jump_system import execute_jump_plan
from scripts.core.simulation_geometry import Vec2
from scripts.core.stat_scale import denormalize_player_stat
from scripts.team.uniform_data import normalize_uniform, runtime_uniform

from scripts.match.player import Player

class Team:
    def __init__(
        self,
        name: str,
        short_name: str,
        primary: tuple[int, int, int],
        secondary: tuple[int, int, int],
        direction: int,
        rng: random.Random,
        player_records: list[dict] | None = None,
        bench_records: list[dict] | None = None,
        manager: str = "",
        manager_tactic_aggression: float = 0.375,
        manager_substitution_aggression: float = 0.375,
        manager_intelligence: float = 0.542,
        source: str = "",
        tactic: str = "BALANCE",
        zone_near: int = 3,
        zone_far: int = 7,
        tactical_discipline: float = 0.5,
        home_court: str = "",
        uniform_data: dict | None = None,
    ):
        self.name = name
        self.short_name = short_name
        self.primary = primary
        self.secondary = secondary
        self.uniform_data = normalize_uniform(uniform_data)
        self.uniform = runtime_uniform(self.uniform_data, primary, secondary)
        self.direction = direction
        self.rng = rng
        self.manager = manager
        self.manager_tactic_aggression = max(0.0, min(1.0, manager_tactic_aggression))
        self.manager_substitution_aggression = max(0.0, min(1.0, manager_substitution_aggression))
        self.manager_intelligence = max(0.0, min(1.0, manager_intelligence))
        self.source = source
        self.tactic = tactic
        self.initial_tactic = tactic
        self.zone_near = zone_near
        self.zone_far = zone_far
        self.tactical_discipline = max(0.0, min(1.0, tactical_discipline))
        self.home_court = home_court or f"{name}ホーム"
        self.venue_role = "NEUTRAL"
        self.score = 0
        self.shots = 0
        self.possession = 0.0
        if player_records is None:
            raise ValueError(f"{name}: JSONの先発選手データがありません")
        self._starting_player_records = deepcopy(player_records)
        self._starting_bench_records = deepcopy(bench_records or [])
        self.bench = deepcopy(self._starting_bench_records)
        self.substituted_out: list[Player] = []
        self.substitutions_used = 0
        self.manager_tactic_changes = 0
        self.pending_tactic: str | None = None
        self.pending_substitution: tuple[Player, dict] | None = None
        self.manager_next_review = 0.0
        self.manager_last_change = -9999.0
        self.players = [
            Player(self, record["number"], record["name"], record["slot"], record)
            for record in player_records
        ]
        self.assign_zone_ranks()

    def reset_roster(self) -> None:
        """Restore the JSON lineup before a new match after substitutions."""
        self.bench = deepcopy(self._starting_bench_records)
        self.players = [
            Player(self, record["number"], record["name"], record["slot"], record)
            for record in deepcopy(self._starting_player_records)
        ]
        for player in self.players:
            player.venue_role = self.venue_role
        self.assign_zone_ranks()

    def assign_zone_ranks(self) -> None:
        outfield = [player for player in self.players if not player.is_keeper]
        minimum = min(player.home_x for player in outfield)
        maximum = max(player.home_x for player in outfield)
        span = max(0.001, maximum - minimum)
        for player in self.players:
            player.zone_rank = 0.0 if player.is_keeper else (player.home_x - minimum) / span

    @property
    def keeper(self) -> Player:
        return next(player for player in self.players if player.is_keeper)

    def tactical_settings(self, player: Player | None = None) -> dict:
        if self.tactic in BASE_TACTIC_KEYS:
            selected = TACTICS[self.tactic]
        elif player is not None and player.personal_tactic in BASE_TACTIC_KEYS:
            selected = TACTICS[player.personal_tactic]
        else:
            selected = TACTICS["BALANCE"]
        if player is None:
            return selected
        raw_key = (
            self.tactic,
            player.personal_tactic,
            self.tactical_discipline,
            player.tactical_loyalty,
        )
        if player._tactical_cache_raw_key == raw_key and player._tactical_cache_value is not None:
            return player._tactical_cache_value
        cache_key = (
            self.tactic,
            player.personal_tactic,
            round(self.tactical_discipline, 2),
            round(player.tactical_loyalty, 2),
        )
        player._tactical_cache_raw_key = raw_key
        if player._tactical_cache_key == cache_key and player._tactical_cache_value is not None:
            return player._tactical_cache_value
        balance = TACTICS["BALANCE"]
        # Team-wide discipline determines how rigidly the common instruction is
        # maintained; personal loyalty determines how closely this player follows
        # it.  Low values are intentionally more flexible, not worse abilities.
        combined_discipline = (
            self.tactical_discipline * 0.55 + player.tactical_loyalty * 0.45
        )
        fidelity = 0.18 + combined_discipline * 0.82
        if self.tactic == "RANDOM":
            fidelity = max(0.72, fidelity)
        mixed = {}
        for key, value in selected.items():
            if key == "label" or not isinstance(value, (int, float)):
                mixed[key] = value
            else:
                mixed[key] = balance[key] + (value - balance[key]) * fidelity
        mixed["pressers"] = max(1, round(mixed["pressers"]))
        player._tactical_cache_key = cache_key
        player._tactical_cache_value = mixed
        return mixed


__all__ = ("Team",)
