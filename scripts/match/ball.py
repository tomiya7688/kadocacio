"""Free-flight and possession state for the match ball."""

from __future__ import annotations

import random
from collections import deque
from copy import deepcopy
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from scripts.match.player import Player
    from scripts.match.team import Team


class Ball:
    def __init__(self) -> None:
        self.pos = Vec2(FIELD.center)
        self.vel = Vec2()
        self.owner: Player | None = None
        self.last_touch: Player | None = None
        self.intended: Player | None = None
        self.pickup_lock = 0.0
        self.z = 0.0
        self.vertical_speed = 0.0
        self.control_offset = Vec2(10, 0)
        self.curve_acceleration = 0.0
        self.curve_vector = Vec2()
        self.knuckle_amplitude = 0.0
        self.knuckle_phase = 0.0
        self.flight_type = ""
        self.shot_serial = 0
        self.flight_serial = 0
        self.shot_deception = 0.0
        # Explicit shot result chosen at contact.  This lets misses have readable
        # causes instead of every inaccurate shot being the same Gaussian drift.
        self.shot_outcome = ""
        self.shot_miss_announced = False
        self.pass_outcome = ""
        self.pass_brake = 0.0
        self.intended_destination = Vec2(FIELD.center)
        self.eye_contact_bonus = 0.0
        self.catch_forbidden = False
        self.last_keeper_response = ""
        # A short claim window after a tackle-induced spill.  The tackling
        # side reacts first without making ownership automatic.
        self.recovery_team: Team | None = None
        self.recovery_timer = 0.0


__all__ = ("Ball",)
