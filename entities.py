from __future__ import annotations

import random
from collections import deque
from copy import deepcopy

import pygame

from player_commands import PlayerCommand, command_spec
from player_style_system import STYLE_FIELDS, combined_preference, normalize_player_type, type_preference
from physical_system import venue_ability_factor
from skill_system import SKILL_COMMAND, SKILL_COOLDOWN, normalized_skills
from settings import BASE_TACTIC_KEYS, FIELD, GRAVITY, TACTICS, percentage_stat, player_stat
from stamina_system import (
    RECOVERY_ACTIONS,
    command_stamina_cost,
    command_stamina_drain,
    fatigue_error_multiplier,
    fatigue_multiplier,
    stamina_capacity,
    stamina_recovery_rate,
)
from technique_system import mistake_error_multiplier, mistake_success_multiplier
from jump_system import execute_jump_plan


class Player:
    def __init__(
        self,
        team: "Team",
        number: int,
        name: str,
        slot: tuple[str, float, float],
        data: dict | None = None,
    ):
        self.team = team
        self.number = number
        self.name = name
        self.role, self.home_x, self.home_y = slot
        self.data = data or {}
        self.grid_x = int(self.data.get("position_x", 0))
        self.grid_y = int(self.data.get("position_y", 0))
        raw = self.data.get("raw", {})
        self.player_type = normalize_player_type(raw.get("PlayerType", ""), self.role)
        self.shot_power = player_stat(raw, "ShotPower")
        self.shot_accuracy = player_stat(raw, "ShotAccuracy")
        self.pass_accuracy = player_stat(raw, "PassAccuracy")
        self.pass_power = player_stat(raw, "PassPower")
        self.dash_speed = player_stat(raw, "DashSpeed", legacy_key="Speed")
        self.walk_speed = player_stat(raw, "WalkSpeed", legacy_key="Speed")
        self.dribble_speed = player_stat(raw, "DribbleSpeed", legacy_key="Speed")
        self.kick_motion_speed = player_stat(raw, "KickMotionSpeed", legacy_key="Speed")
        self.stamina_capacity_stat = player_stat(raw, "MaxStamina", legacy_key="Stamina")
        self.stamina_recovery = player_stat(raw, "StaminaRecovery", legacy_key="Stamina")
        self.stamina_management = player_stat(raw, "StaminaManagement", legacy_key="Stamina")
        self.fatigue_resistance = player_stat(raw, "FatigueResistance", legacy_key="Stamina")
        self.mistake_avoidance = player_stat(raw, "MistakeAvoidance", legacy_key="Technique")
        self.dribble_technique = player_stat(raw, "DribbleTechnique", legacy_key="Technique")
        self.trap_technique = player_stat(raw, "TrapTechnique", legacy_key="Technique")
        self.pass_interception = player_stat(raw, "PassInterception", legacy_key="Technique")
        self.goal_stopping = player_stat(raw, "GoalStopping", legacy_key="Technique")
        self.shooting_technique = player_stat(raw, "ShootingTechnique", legacy_key="Technique")
        self.passing_technique = player_stat(raw, "PassingTechnique", legacy_key="Technique")
        self.steal_technique = player_stat(raw, "StealTechnique", legacy_key="Technique")
        self.jump_height = player_stat(raw, "JumpHeight", legacy_key="Jump")
        self.jump_accuracy = player_stat(raw, "JumpAccuracy", legacy_key="Jump")
        self.jump_speed = player_stat(raw, "JumpSpeed", legacy_key="Jump")
        self.jump_judgment = player_stat(raw, "JumpJudgment", legacy_key="Jump")
        self.heading_power = player_stat(raw, "HeadingPower", legacy_key="Jump")
        self.heading_accuracy = player_stat(raw, "HeadingAccuracy", legacy_key="Jump")
        self.heading_judgment = player_stat(raw, "HeadingJudgment", legacy_key="Jump")
        self.collision_physical = player_stat(raw, "CollisionPhysical", legacy_key="Physical")
        self.dribble_physical = player_stat(raw, "DribblePhysical", legacy_key="Physical")
        self.physical_play_quality = player_stat(raw, "PhysicalPlayQuality", legacy_key="Physical")
        self.mental = player_stat(raw, "Mental", legacy_key="Mental")
        self.intelligence = player_stat(raw, "Intelligence", legacy_key="Mental")
        self.base_confidence = player_stat(raw, "Confidence", legacy_key="Mental")
        # Team discipline is the default only.  An explicit player value remains
        # independent so a flexible player can exist in a disciplined team and
        # vice versa.  Neither value is an ability score or fatigue-adjusted.
        self.tactical_discipline = percentage_stat(
            raw,
            "TacticalDiscipline",
            default=self.team.tactical_discipline * 100.0,
        )
        self.safe_play = player_stat(raw, "SafePlay", legacy_key="Mental")
        self.free_kick_skill = player_stat(raw, "FreeKickSkill", legacy_key="Mental")
        self.penalty_kick_skill = player_stat(raw, "PenaltyKickSkill", legacy_key="Mental")
        self.goal_kick_skill = player_stat(raw, "GoalKickSkill", legacy_key="Mental")
        self.throw_in_skill = player_stat(raw, "ThrowInSkill", legacy_key="Mental")
        self.corner_kick_skill = player_stat(raw, "CornerKickSkill", legacy_key="Mental")
        for behavior, field in STYLE_FIELDS.items():
            default = 50 + type_preference(self.player_type, behavior) * 1200
            parameter = player_stat(raw, field, default=default, legacy_key=field)
            setattr(self, behavior, combined_preference(self.player_type, behavior, parameter))
        self.skills = normalized_skills(raw.get("Skills", []))
        self.stamina_max = stamina_capacity(self.stamina_capacity_stat)
        self.stamina = self.stamina_max
        self.confidence = self.base_confidence
        self.tactical_loyalty = self.tactical_discipline
        self.zone_awareness = self.tactical_discipline
        self.position_awareness = self.tactical_discipline
        self.aggressiveness = 0.50
        self.alertness: dict[Player, float] = {}
        self.personal_tactic = self.team.tactic if self.team.tactic in BASE_TACTIC_KEYS else "BALANCE"
        self.personal_tactic_timer = self.team.rng.uniform(1.5, 4.0)
        self.zone_rank = 0.0
        self.pos = pygame.Vector2()
        self.target = pygame.Vector2()
        self.command_target = pygame.Vector2()
        self.action_command = PlayerCommand.HOLD_POSITION
        self.movement_command = PlayerCommand.IDLE
        self.technique_command = PlayerCommand.IDLE
        self.skill_command = PlayerCommand.IDLE
        self.action_timer = 0.0
        self.technique_timer = 0.0
        self.skill_timer = 0.0
        self.skill_cooldowns = {skill: 0.0 for skill in self.skills}
        self.skill_consider_cooldowns = {skill: 0.0 for skill in self.skills}
        # Almost every skill is normally ready.  Tracking only non-zero timers
        # avoids decrementing dozens of zero entries for every player at 20 Hz.
        self._active_skill_cooldowns: set[str] = set()
        self._active_skill_consider_cooldowns: set[str] = set()
        self.kick_motion_active = False
        self.kick_motion_elapsed = 0.0
        self.kick_motion_duration = 0.0
        self.kick_motion_progress = 0.0
        self.kick_recovery_timer = 0.0
        self.command_history: deque[str] = deque(maxlen=32)
        self.skill = team.rng.uniform(0.88, 1.12)
        self.z = 0.0
        self.vertical_speed = 0.0
        self.jump_cooldown = 0.0
        self.jump_ascending = False
        self.jump_peak_height = 0.0
        self.jump_ascent_time = 0.0
        self.jump_ascent_gravity = GRAVITY
        self.roam = pygame.Vector2()
        self.roam_target = pygame.Vector2()
        self.roam_timer = team.rng.uniform(0.4, 1.8)
        self.last_trap_style = ""
        self.last_pass_type = ""
        self.last_shot_type = ""
        self.keeper_read_y = 0.0
        self.keeper_read_shot_serial = -1
        self.keeper_wrong_read = False
        self.last_header_type = ""
        self.last_slide_kick = ""
        self.venue_role = "NEUTRAL"
        self.motion_velocity = pygame.Vector2()
        self.collision_cooldown = 0.0
        self.knockback_timer = 0.0
        self.knockback_velocity = pygame.Vector2()
        self.slide_foul_checked = False
        self.yellow_cards = 0
        self.sent_off = False
        self.slide_timer = 0.0
        self.slide_duration = 0.62
        self.slide_cooldown = 0.0
        self.slide_direction = pygame.Vector2(self.team.direction, 0)
        self.slide_kick_used = False
        self.slide_foul_checked = False
        self.motion_velocity.update(0, 0)
        self.collision_cooldown = 0.0
        self.heading_motion = ""
        self.heading_purpose = PlayerCommand.IDLE
        self.heading_direction = pygame.Vector2(self.team.direction, 0)
        self.heading_motion_timer = 0.0
        self.fall_after_landing = False
        self.fallen_timer = 0.0
        self.roulette_timer = 0.0
        self.roulette_direction = pygame.Vector2(self.team.direction, 0)
        self.roulette_success = 0.0
        self.cruyff_timer = 0.0
        self.cruyff_direction = pygame.Vector2(-self.team.direction, 0)
        self.razor_dribble_timer = 0.0
        self.high_speed_dribble_timer = 0.0
        self.toughness_dynamo_timer = 0.0
        self.steel_heart_timer = 0.0
        self.post_play_timer = 0.0
        self.shadow_striker_timer = 0.0
        self.chasing_timer = 0.0
        self.one_side_cut_timer = 0.0
        self.relax_timer = 0.0
        self.tricky_feint_timer = 0.0
        self.tricky_feint_direction = pygame.Vector2(self.team.direction, 0)
        self.demon_press_timer = 0.0
        self.simulation_timer = 0.0
        self.one_trap_shot_timer = 0.0
        self.super_save_timer = 0.0
        self.keeper_attack_timer = 0.0
        self.ai_rethink_timer = 0.0
        self.ai_decision_context = None
        self.ai_cached_action = PlayerCommand.HOLD_POSITION
        self.ai_cached_target = pygame.Vector2()
        self.ai_cached_locomotion = PlayerCommand.WALK
        self.combination_timer = 0.0
        self.combination_partner: Player | None = None
        self.combination_target = pygame.Vector2()
        self.combination_quality = 0.0
        self._fatigue_cache_stamina = None
        self._fatigue_cache_max = None
        self._fatigue_cache_resistance = None
        self._fatigue_cache_value = 1.0
        self._venue_cache_role = None
        self._venue_cache_mental = None
        self._venue_cache_steel_heart = None
        self._venue_cache_value = 1.0
        self._tactical_cache_key = None
        self._tactical_cache_raw_key = None
        self._tactical_cache_value = None
        self.reset_position()

    def reset_position(self) -> None:
        world_x = self.home_x if self.team.direction == 1 else 1.0 - self.home_x
        self.pos.update(FIELD.left + world_x * FIELD.width, FIELD.top + self.home_y * FIELD.height)
        self.target.update(self.pos)
        self.z = 0.0
        self.vertical_speed = 0.0
        self.jump_cooldown = 0.0
        self.jump_ascending = False
        self.jump_peak_height = 0.0
        self.jump_ascent_time = 0.0
        self.jump_ascent_gravity = GRAVITY
        self.slide_timer = 0.0
        self.slide_cooldown = 0.0
        self.slide_direction.update(self.team.direction, 0)
        self.slide_kick_used = False
        self.knockback_timer = 0.0
        self.knockback_velocity.update(0, 0)
        self.heading_motion = ""
        self.heading_purpose = PlayerCommand.IDLE
        self.heading_direction.update(self.team.direction, 0)
        self.heading_motion_timer = 0.0
        self.fall_after_landing = False
        self.fallen_timer = 0.0
        self.roulette_timer = 0.0
        self.roulette_direction.update(self.team.direction, 0)
        self.roulette_success = 0.0
        self.cruyff_timer = 0.0
        self.cruyff_direction.update(-self.team.direction, 0)
        self.razor_dribble_timer = 0.0
        self.high_speed_dribble_timer = 0.0
        self.toughness_dynamo_timer = 0.0
        self.steel_heart_timer = 0.0
        self.post_play_timer = 0.0
        self.shadow_striker_timer = 0.0
        self.chasing_timer = 0.0
        self.one_side_cut_timer = 0.0
        self.relax_timer = 0.0
        self.tricky_feint_timer = 0.0
        self.tricky_feint_direction.update(self.team.direction, 0)
        self.demon_press_timer = 0.0
        self.simulation_timer = 0.0
        self.one_trap_shot_timer = 0.0
        self.super_save_timer = 0.0
        self.keeper_attack_timer = 0.0
        self.ai_rethink_timer = 0.0
        self.ai_decision_context = None
        self.combination_timer = 0.0
        self.combination_partner = None
        self.combination_target.update(self.pos)
        self.combination_quality = 0.0
        self._fatigue_cache_stamina = None
        self._fatigue_cache_max = None
        self._fatigue_cache_resistance = None
        self._venue_cache_role = None
        self._venue_cache_mental = None
        self._venue_cache_steel_heart = None
        self._tactical_cache_key = None
        self._tactical_cache_raw_key = None
        self._tactical_cache_value = None
        self.roam.update(0, 0)
        self.roam_target.update(0, 0)
        self.roam_timer = self.team.rng.uniform(0.4, 1.8)
        self.reset_commands()

    def reset_commands(self) -> None:
        self.action_command = PlayerCommand.GUARD_GOAL if self.is_keeper else PlayerCommand.HOLD_POSITION
        self.movement_command = PlayerCommand.IDLE
        self.technique_command = PlayerCommand.IDLE
        self.skill_command = PlayerCommand.IDLE
        self.action_timer = 0.0
        self.technique_timer = 0.0
        self.skill_timer = 0.0
        self.kick_motion_active = False
        self.kick_motion_elapsed = 0.0
        self.kick_motion_duration = 0.0
        self.kick_motion_progress = 0.0
        self.kick_recovery_timer = 0.0
        self.command_target.update(self.pos)

    def reset_stamina(self) -> None:
        self.stamina = self.stamina_max

    def reset_match_state(self) -> None:
        """Restore JSON-defined starting values without affecting later kickoffs."""
        self.reset_stamina()
        self.confidence = self.base_confidence
        self.tactical_loyalty = self.tactical_discipline
        self.zone_awareness = self.tactical_discipline
        self.position_awareness = self.tactical_discipline
        self.aggressiveness = 0.50
        self.alertness.clear()
        self.personal_tactic = self.team.tactic if self.team.tactic in BASE_TACTIC_KEYS else "BALANCE"
        self.personal_tactic_timer = self.team.rng.uniform(1.5, 4.0)

    def adjust_confidence(self, amount: float) -> None:
        self.confidence = max(0.0, min(1.0, self.confidence + amount))

    def alertness_for(self, opponent: "Player") -> float:
        return self.alertness.get(opponent, 0.50)

    @property
    def stamina_ratio(self) -> float:
        return self.stamina / self.stamina_max if self.stamina_max > 0 else 0.0

    @property
    def fatigue_factor(self) -> float:
        if (
            self.stamina != self._fatigue_cache_stamina
            or self.stamina_max != self._fatigue_cache_max
            or self.fatigue_resistance != self._fatigue_cache_resistance
        ):
            self._refresh_fatigue_cache()
        return self._fatigue_cache_value

    def _refresh_fatigue_cache(self) -> None:
        self._fatigue_cache_stamina = self.stamina
        self._fatigue_cache_max = self.stamina_max
        self._fatigue_cache_resistance = self.fatigue_resistance
        ratio = self.stamina / self.stamina_max if self.stamina_max > 0 else 0.0
        self._fatigue_cache_value = fatigue_multiplier(ratio, self.fatigue_resistance)

    @property
    def fatigue_error_factor(self) -> float:
        return fatigue_error_multiplier(self.stamina_ratio, self.fatigue_resistance)

    @property
    def venue_factor(self) -> float:
        steel_heart_active = self.steel_heart_timer > 0.0
        if (
            self.venue_role != self._venue_cache_role
            or self.mental != self._venue_cache_mental
            or steel_heart_active != self._venue_cache_steel_heart
        ):
            self._refresh_venue_cache(steel_heart_active)
        return self._venue_cache_value

    def _refresh_venue_cache(self, steel_heart_active: bool | None = None) -> None:
        if steel_heart_active is None:
            steel_heart_active = self.steel_heart_timer > 0.0
        self._venue_cache_role = self.venue_role
        self._venue_cache_mental = self.mental
        self._venue_cache_steel_heart = steel_heart_active
        self._venue_cache_value = (
            1.0
            if steel_heart_active and self.venue_role == "AWAY"
            else venue_ability_factor(self.venue_role, self.mental)
        )

    @property
    def mistake_error_factor(self) -> float:
        ability = self.effective_stat(self.mistake_avoidance)
        return mistake_error_multiplier(ability) * self.fatigue_error_factor

    @property
    def technique_success_factor(self) -> float:
        ability = self.effective_stat(self.mistake_avoidance)
        return mistake_success_multiplier(ability) * self.fatigue_factor

    def effective_stat(self, ability: float) -> float:
        # These multipliers are queried hundreds of thousands of times in a
        # match. Check their source values inline and only enter the more
        # expensive property calculation when stamina or venue state changed.
        if (
            self.stamina != self._fatigue_cache_stamina
            or self.stamina_max != self._fatigue_cache_max
            or self.fatigue_resistance != self._fatigue_cache_resistance
        ):
            self._refresh_fatigue_cache()
        steel_heart_active = self.steel_heart_timer > 0.0
        if (
            self.venue_role != self._venue_cache_role
            or self.mental != self._venue_cache_mental
            or steel_heart_active != self._venue_cache_steel_heart
        ):
            self._refresh_venue_cache(steel_heart_active)
        return max(0.0, min(1.0, ability * self._fatigue_cache_value * self._venue_cache_value))

    @property
    def effective_intelligence(self) -> float:
        """Intelligence is venue-aware but deliberately unaffected by stamina."""
        steel_heart_active = self.steel_heart_timer > 0.0
        if (
            self.venue_role != self._venue_cache_role
            or self.mental != self._venue_cache_mental
            or steel_heart_active != self._venue_cache_steel_heart
        ):
            self._refresh_venue_cache(steel_heart_active)
        return max(0.0, min(1.0, self.intelligence * self._venue_cache_value))

    def spend_stamina(self, command: PlayerCommand, scale: float = 1.0) -> None:
        cost = command_stamina_cost(command) * max(0.0, scale)
        self.stamina = max(0.0, self.stamina - cost)

    def update_stamina(self, dt: float) -> None:
        drain = command_stamina_drain(self.action_command, self.movement_command)
        if self.toughness_dynamo_timer > 0.0 and self.action_command in (
            PlayerCommand.DRIBBLE,
            PlayerCommand.KEEP_BALL,
            PlayerCommand.SKILL_SPRINT_CARRY,
            PlayerCommand.SKILL_TIGHT_TOUCH,
        ):
            drain = max(0.0, drain - 0.32)
        recovery = 0.0
        if self.movement_command in (PlayerCommand.IDLE, PlayerCommand.WALK) and self.action_command in RECOVERY_ACTIONS:
            recovery_scale = 1.0 if self.movement_command is PlayerCommand.IDLE else 0.45
            recovery = stamina_recovery_rate(self.stamina_recovery) * recovery_scale
        if self.relax_timer > 0.0:
            drain = 0.0
            recovery = stamina_recovery_rate(self.stamina_recovery) * 6.0
        self.stamina = max(0.0, min(self.stamina_max, self.stamina + (recovery - drain) * dt))

    def should_conserve_stamina(self) -> bool:
        reserve_ratio = 0.08 + self.stamina_management * 0.32
        return self.stamina_ratio <= reserve_ratio

    @property
    def stamina_conservation(self) -> float:
        reserve_ratio = 0.08 + self.stamina_management * 0.32
        if self.stamina_ratio >= reserve_ratio:
            return 0.0
        shortage = (reserve_ratio - self.stamina_ratio) / max(0.01, reserve_ratio)
        return max(0.0, min(1.0, shortage * (0.45 + self.stamina_management * 0.55)))

    def can_use_intense_action(self, emergency: bool = False) -> bool:
        if self.stamina <= 0.0:
            return False
        if not self.should_conserve_stamina():
            return True
        return emergency and self.stamina_ratio > 0.04

    def can_dash(self, action: PlayerCommand | None = None, emergency: bool = False) -> bool:
        if self.stamina <= 0.0:
            return False
        if not self.should_conserve_stamina():
            return True
        emergency_actions = {
            PlayerCommand.RECEIVE_PASS,
            PlayerCommand.BLOCK_SHOT,
            PlayerCommand.SAVE,
            PlayerCommand.SKILL_EARLY_READ_SAVE,
            PlayerCommand.SKILL_RELENTLESS_PRESS,
        }
        return (emergency or action in emergency_actions) and self.stamina_ratio > 0.04

    def tick_commands(self, dt: float) -> None:
        self.collision_cooldown = self.collision_cooldown - dt if self.collision_cooldown > dt else 0.0
        self.slide_cooldown = self.slide_cooldown - dt if self.slide_cooldown > dt else 0.0
        self.knockback_timer = self.knockback_timer - dt if self.knockback_timer > dt else 0.0
        self.roulette_timer = self.roulette_timer - dt if self.roulette_timer > dt else 0.0
        self.cruyff_timer = self.cruyff_timer - dt if self.cruyff_timer > dt else 0.0
        self.razor_dribble_timer = self.razor_dribble_timer - dt if self.razor_dribble_timer > dt else 0.0
        self.high_speed_dribble_timer = self.high_speed_dribble_timer - dt if self.high_speed_dribble_timer > dt else 0.0
        self.toughness_dynamo_timer = self.toughness_dynamo_timer - dt if self.toughness_dynamo_timer > dt else 0.0
        self.steel_heart_timer = self.steel_heart_timer - dt if self.steel_heart_timer > dt else 0.0
        self.post_play_timer = self.post_play_timer - dt if self.post_play_timer > dt else 0.0
        self.shadow_striker_timer = self.shadow_striker_timer - dt if self.shadow_striker_timer > dt else 0.0
        self.chasing_timer = self.chasing_timer - dt if self.chasing_timer > dt else 0.0
        self.one_side_cut_timer = self.one_side_cut_timer - dt if self.one_side_cut_timer > dt else 0.0
        self.relax_timer = self.relax_timer - dt if self.relax_timer > dt else 0.0
        self.tricky_feint_timer = self.tricky_feint_timer - dt if self.tricky_feint_timer > dt else 0.0
        self.demon_press_timer = self.demon_press_timer - dt if self.demon_press_timer > dt else 0.0
        self.simulation_timer = self.simulation_timer - dt if self.simulation_timer > dt else 0.0
        self.one_trap_shot_timer = self.one_trap_shot_timer - dt if self.one_trap_shot_timer > dt else 0.0
        self.super_save_timer = self.super_save_timer - dt if self.super_save_timer > dt else 0.0
        self.keeper_attack_timer = self.keeper_attack_timer - dt if self.keeper_attack_timer > dt else 0.0
        self.combination_timer = self.combination_timer - dt if self.combination_timer > dt else 0.0
        if self.combination_timer <= 0.0:
            self.combination_partner = None
            self.combination_quality = 0.0
        for skill in tuple(self._active_skill_cooldowns):
            remaining = self.skill_cooldowns[skill] - dt
            if remaining > 0.0:
                self.skill_cooldowns[skill] = remaining
            else:
                self.skill_cooldowns[skill] = 0.0
                self._active_skill_cooldowns.discard(skill)
        for skill in tuple(self._active_skill_consider_cooldowns):
            remaining = self.skill_consider_cooldowns[skill] - dt
            if remaining > 0.0:
                self.skill_consider_cooldowns[skill] = remaining
            else:
                self.skill_consider_cooldowns[skill] = 0.0
                self._active_skill_consider_cooldowns.discard(skill)
        self.action_timer = self.action_timer - dt if self.action_timer > dt else 0.0
        self.technique_timer = self.technique_timer - dt if self.technique_timer > dt else 0.0
        self.skill_timer = self.skill_timer - dt if self.skill_timer > dt else 0.0
        if self.technique_timer <= 0.0:
            self.technique_command = PlayerCommand.IDLE
        if self.skill_timer <= 0.0:
            self.skill_command = PlayerCommand.IDLE
        if not self.kick_motion_active and self.kick_recovery_timer > 0.0:
            self.kick_recovery_timer = self.kick_recovery_timer - dt if self.kick_recovery_timer > dt else 0.0
            self.kick_motion_progress = self.kick_recovery_timer / 0.16
        elif not self.kick_motion_active:
            self.kick_motion_progress = 0.0
        if self.slide_timer > 0.0:
            previous = self.slide_timer
            self.slide_timer = self.slide_timer - dt if self.slide_timer > dt else 0.0
            if previous > 0.0 and self.slide_timer <= 0.0:
                self.fallen_timer = max(self.fallen_timer, 0.24)
        if self.heading_motion_timer > 0.0:
            self.heading_motion_timer = self.heading_motion_timer - dt if self.heading_motion_timer > dt else 0.0
            if self.heading_motion_timer <= 0.0 and self.heading_motion == "STANDING":
                self.heading_motion = ""
        if self.fallen_timer > 0.0 and not self.airborne and not self.slide_active:
            self.fallen_timer = self.fallen_timer - dt if self.fallen_timer > dt else 0.0
            if self.fallen_timer <= 0.0 and self.heading_motion == "FALLEN":
                self.heading_motion = ""

    @property
    def slide_active(self) -> bool:
        return self.slide_timer > 0.0

    @property
    def slide_progress(self) -> float:
        return 1.0 - self.slide_timer / self.slide_duration if self.slide_duration > 0 else 1.0

    @property
    def diving_header_active(self) -> bool:
        return self.heading_motion == "DIVING" and self.airborne

    @property
    def ground_motion_active(self) -> bool:
        return self.slide_active or self.fallen_timer > 0.0 or self.heading_motion == "FALLEN" or self.relax_timer > 0.0

    def start_slide(self, target: pygame.Vector2 | tuple[float, float]) -> bool:
        if self.slide_active or self.slide_cooldown > 0.0 or self.airborne or self.fallen_timer > 0.0:
            return False
        direction = pygame.Vector2(target) - self.pos
        if direction.length_squared() < 0.0001:
            direction.update(self.team.direction, 0)
        else:
            direction = direction.normalize()
        self.slide_direction.update(direction)
        self.slide_timer = self.slide_duration
        self.slide_cooldown = 3.0
        self.slide_kick_used = False
        self.slide_foul_checked = False
        return True

    def has_skill(self, skill: str) -> bool:
        return skill in self.skills

    def can_consider_skill(self, skill: str) -> bool:
        """Return whether normal AI evaluation can currently activate a skill.

        Forced set-piece decisions deliberately bypass the consideration timer,
        so this lightweight guard is only used by ordinary open-play AI.
        """
        return (
            skill in self.skills
            and self.skill_command is PlayerCommand.IDLE
            and self.skill_cooldowns.get(skill, 0.0) <= 0.0
            and self.skill_consider_cooldowns.get(skill, 0.0) <= 0.0
        )

    def activate_skill(self, skill: str, duration: float | None = None) -> bool:
        command = SKILL_COMMAND.get(skill)
        if command is None or skill not in self.skills or self.skill_cooldowns.get(skill, 0.0) > 0.0:
            return False
        self.skill_command = command
        self.skill_timer = command_spec(command).commitment if duration is None else duration
        self.skill_cooldowns[skill] = SKILL_COOLDOWN[skill]
        self._active_skill_cooldowns.add(skill)
        self.command_history.append(f"skill:{command.name}")
        return True

    def start_knockback(self, direction: pygame.Vector2, speed: float) -> None:
        self.knockback_timer = 0.42
        self.knockback_velocity = pygame.Vector2(direction) * max(45.0, speed)
        self.issue_action(PlayerCommand.STAGGER, self.pos + direction * 18, duration=0.42, force=True)
        self.set_movement(PlayerCommand.IDLE)

    def start_roulette(self, direction: pygame.Vector2, success: float) -> None:
        self.roulette_timer = 0.68
        self.roulette_direction = pygame.Vector2(direction)
        self.roulette_success = max(0.0, min(1.0, success))

    def start_heading_motion(self, diving: bool, target: pygame.Vector2 | tuple[float, float]) -> None:
        direction = pygame.Vector2(target) - self.pos
        if direction.length_squared() < 0.0001:
            direction.update(self.team.direction, 0)
        else:
            direction = direction.normalize()
        self.heading_direction.update(direction)
        self.heading_motion = "DIVING" if diving else "STANDING"
        self.heading_motion_timer = 0.82 if diving else 0.48
        self.fall_after_landing = diving

    def issue_action(
        self,
        command: PlayerCommand,
        target: pygame.Vector2 | tuple[float, float] | None = None,
        duration: float | None = None,
        force: bool = False,
    ) -> bool:
        current_spec = command_spec(self.action_command)
        next_spec = command_spec(command)
        if not force and command is not self.action_command and self.action_timer > 0 and next_spec.priority < current_spec.priority:
            return False
        if command is not self.action_command:
            self.action_command = command
            self.command_history.append(f"action:{command.name}")
        if target is not None:
            self.command_target.update(target)
        commitment = next_spec.commitment if duration is None else duration
        self.action_timer = max(self.action_timer, commitment)
        return True

    def set_movement(self, command: PlayerCommand, emergency: bool = False) -> None:
        if command not in (PlayerCommand.IDLE, PlayerCommand.WALK, PlayerCommand.DASH):
            raise ValueError(f"Not a movement command: {command}")
        if command is PlayerCommand.DASH and not self.can_dash(self.action_command, emergency=emergency):
            command = PlayerCommand.WALK
        if command is not self.movement_command:
            self.movement_command = command
            self.command_history.append(f"movement:{command.name}")

    def use_technique(self, command: PlayerCommand, duration: float | None = None) -> None:
        if command is not self.technique_command:
            self.technique_command = command
            self.command_history.append(f"technique:{command.name}")
        commitment = command_spec(command).commitment if duration is None else duration
        self.technique_timer = max(self.technique_timer, commitment)

    @property
    def kick_contact_time(self) -> float:
        venue_speed = max(0.0, min(1.0, self.kick_motion_speed * self.venue_factor))
        base_time = 0.74 - venue_speed * 0.60
        contact_time = min(1.50, base_time / max(0.45, self.fatigue_factor))
        return min(contact_time, 0.30) if self.slide_active else contact_time

    def start_kick_motion(self) -> None:
        self.kick_motion_active = True
        self.kick_motion_elapsed = 0.0
        self.kick_motion_duration = self.kick_contact_time
        self.kick_motion_progress = 0.0
        self.kick_recovery_timer = 0.0
        self.use_technique(PlayerCommand.KICK, self.kick_motion_duration + 0.16)

    def advance_kick_motion(self, dt: float) -> bool:
        if not self.kick_motion_active:
            return False
        self.kick_motion_elapsed += dt
        self.kick_motion_progress = min(1.0, self.kick_motion_elapsed / max(0.001, self.kick_motion_duration))
        return self.kick_motion_progress >= 1.0

    def finish_kick_motion(self) -> None:
        self.kick_motion_active = False
        self.kick_motion_progress = 1.0
        self.kick_recovery_timer = 0.16

    def cancel_kick_motion(self) -> None:
        self.kick_motion_active = False
        self.kick_motion_elapsed = 0.0
        self.kick_motion_duration = 0.0
        self.kick_motion_progress = 0.0
        self.kick_recovery_timer = 0.0

    @property
    def is_keeper(self) -> bool:
        return self.role == "GK"

    @property
    def airborne(self) -> bool:
        return self.z > 0.5

    def jump(self, desired_height: float) -> bool:
        if self.airborne or self.jump_cooldown > 0.0:
            return False
        actual_height, ascent_time = execute_jump_plan(
            desired_height,
            self.effective_stat(self.jump_height),
            self.effective_stat(self.jump_accuracy),
            self.effective_stat(self.jump_speed),
            self.mistake_error_factor,
            self.team.rng,
        )
        self.jump_peak_height = actual_height
        self.jump_ascent_time = ascent_time
        self.jump_ascent_gravity = 2.0 * actual_height / max(0.01, ascent_time * ascent_time)
        self.vertical_speed = 2.0 * actual_height / max(0.01, ascent_time)
        self.jump_ascending = True
        fall_time = pow(2.0 * actual_height / GRAVITY, 0.5)
        self.jump_cooldown = ascent_time + fall_time + 0.16
        return True

    def update_vertical(self, dt: float) -> None:
        self.jump_cooldown = max(0.0, self.jump_cooldown - dt)
        if self.airborne or self.vertical_speed > 0.0:
            gravity = self.jump_ascent_gravity if self.jump_ascending else GRAVITY
            next_speed = self.vertical_speed - gravity * dt
            self.z += (self.vertical_speed + next_speed) * 0.5 * dt
            self.vertical_speed = next_speed
            if self.jump_ascending and self.vertical_speed <= 0.0:
                self.z = self.jump_peak_height
                self.vertical_speed = 0.0
                self.jump_ascending = False
            if self.z <= 0.0:
                self.z = 0.0
                self.vertical_speed = 0.0
                self.jump_ascending = False
                if self.fall_after_landing:
                    self.heading_motion = "FALLEN"
                    self.fallen_timer = max(self.fallen_timer, 0.68)
                    self.fall_after_landing = False

    def update_roaming(self, dt: float, has_possession: bool) -> None:
        if self.is_keeper:
            self.roam.update(0, 0)
            return
        settings = self.team.tactical_settings(self)
        freedom = settings["freedom"]
        freedom *= 0.68 + self.aggressiveness * 0.74
        freedom *= 1.18 - self.tactical_loyalty * 0.28
        lateral_base = {"DF": 62, "MF": 88, "FW": 104}.get(self.role, 70)
        forward_base = {"DF": 34, "MF": 52, "FW": 68}.get(self.role, 42)
        self.roam_timer -= dt
        if self.roam_timer <= 0:
            lateral_limit = lateral_base * freedom
            forward_limit = forward_base * freedom
            forward_low = -forward_limit * (0.55 if has_possession else 0.85)
            forward_high = forward_limit * (1.15 if has_possession else 0.70)
            self.roam_target.update(
                self.team.rng.uniform(forward_low, forward_high),
                self.team.rng.uniform(-lateral_limit, lateral_limit),
            )
            self.roam_timer = self.team.rng.uniform(1.1, 2.8)
        blend = min(1.0, dt * (0.85 + freedom * 0.35))
        self.roam += (self.roam_target - self.roam) * blend


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
    ):
        self.name = name
        self.short_name = short_name
        self.primary = primary
        self.secondary = secondary
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


class Ball:
    def __init__(self) -> None:
        self.pos = pygame.Vector2(FIELD.center)
        self.vel = pygame.Vector2()
        self.owner: Player | None = None
        self.last_touch: Player | None = None
        self.intended: Player | None = None
        self.pickup_lock = 0.0
        self.z = 0.0
        self.vertical_speed = 0.0
        self.control_offset = pygame.Vector2(10, 0)
        self.curve_acceleration = 0.0
        self.curve_vector = pygame.Vector2()
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
        self.intended_destination = pygame.Vector2(FIELD.center)
        self.eye_contact_bonus = 0.0
        self.catch_forbidden = False
        self.last_keeper_response = ""
        # A short claim window after a tackle-induced spill.  The tackling
        # side reacts first without making ownership automatic.
        self.recovery_team: Team | None = None
        self.recovery_timer = 0.0
