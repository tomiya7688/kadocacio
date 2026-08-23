from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

from scripts.match.entities import Ball, Player, Team
from scripts.match.intelligence_system import (
    blended_judgment,
    choose_utility_action,
    header_attempt_utility,
    perceived_utility,
    strategic_possession_risk,
    slide_start_probability,
    slide_tackle_utility,
)
from scripts.match.jump_system import (
    heading_ball_speed,
    heading_error_sigma,
    jump_apex_time,
    jump_prediction_quality,
    maximum_jump_height,
    prediction_error_scales,
)
from scripts.match.manager_system import (
    ManagerProfile,
    choose_tactic as choose_manager_tactic,
    review_interval as manager_review_interval,
    substitution_fatigue_threshold,
    tactic_target as manager_tactic_target,
)
from scripts.match.player_commands import PlayerCommand, dribble_movement_speed, movement_speed
from scripts.match.physical_system import (
    choose_card,
    collision_knockback,
    collision_strength,
    dribble_protection,
    foul_chance,
)
from scripts.match.prediction_system import expected_goals, outcome_probabilities, percentage_triplet
from scripts.core.settings import (
    AWAY_BLUE, AWAY_DARK, BASE_TACTIC_KEYS, FIELD, GAME_CLOCK_RATE, GOAL_HALF_HEIGHT, GOAL_HEIGHT,
    GRAVITY, HOME_DARK, HOME_RED, KEEPER_BALL_REACH, MATCH_SECONDS, OUTFIELD_BALL_REACH,
    PENALTY_AREA_DEPTH, PENALTY_AREA_WIDTH, PENALTY_SPOT_DISTANCE, PLAYER_CONTACT_DISTANCE,
    PLAYER_VISUAL_SCALE, SLIDE_START_MAX_DISTANCE, SLIDE_START_MIN_DISTANCE,
    SLIDE_TACKLE_REACH, STANDING_TACKLE_REACH, TACTICS, clamp, darken_color, safe_normalize,
    player_stat,
)
from scripts.match.skill_system import (
    ARC_CURVE,
    OVERHEAD_VOLLEY,
    LAST_CHANCE_CANNON,
    FORTRESS_BLOCK,
    RECOVERY_CHASE,
    TURNOVER_COUNTER,
    VACANT_COVER,
    HEEL_REVERSE_TURN,
    ONE_TOUCH_RELAY,
    RELENTLESS_PRESS,
    CARRY_SHOT,
    SIGNAL_LINK,
    CHANCE_SENSOR,
    SAVING_AURA,
    AERIAL_HEADER,
    SPRINT_CARRY,
    CLOSE_LOCK,
    POWER_SLIDE,
    WOBBLE_BALL,
    SWEEPER_KEEPER,
    MAGIC_PLACE_KICK,
    SPIN_TURN,
    BLIND_FEED,
    OVERLOAD,
    ONE_WAY_BLOCK,
    SET_AND_SHOOT,
    PIVOT_KEEP,
    CANNON_MIDDLE,
    TIGHT_TOUCH,
    BACKLINE_HUNTER,
    FUTURE_READ,
    SLIDE_FINISH,
    SKILL_COMMAND,
    STABLE_CORE,
    UNBREAKABLE_HEART,
    EARLY_READ_SAVE,
    ENERGY_KEEP,
    ILLUSION_STEP,
    HALFWAY_CANNON,
    COOLDOWN_REST,
    DIRECT_VOLLEY,
    should_activate,
)
from scripts.match.stamina_system import command_stamina_cost
from scripts.core.simulation_geometry import Vec2
from scripts.team.team_data import discover_team_choices
from scripts.match.technique_system import (
    choose_trap_style,
    interception_reach,
    trap_success_chance,
    trap_touch_offset,
)


SHOT_ON_TARGET = "ON_TARGET"
SHOT_WIDE = "WIDE"
SHOT_POST = "POST"
SHOT_KEEPER_FRIENDLY = "KEEPER_FRIENDLY"
SHOT_OVER = "OVER"
PASS_CLEAN = "CLEAN"
PASS_WRONG_DIRECTION = "WRONG_DIRECTION"
PASS_DANGEROUS_LANE = "DANGEROUS_LANE"
PASS_OVERHIT = "OVERHIT"
PASS_UNDERHIT = "UNDERHIT"


def kick_power_output(normalized_power: float) -> float:
    """Turn the normalized kick stat into restrained physical output."""
    power = clamp(normalized_power, 0.0, 1.0)
    return 0.06 + pow(power, 1.35) * 0.88


def score_pass_candidate(
    owner: "Player",
    candidate: "Player",
    *,
    lane_clearance: float,
    nearest_opponent_distance: float,
    forward_weight: float,
    pass_power: float,
    passing: float,
    intelligence: float,
    decision: float,
    rng: random.Random,
) -> float:
    delta = candidate.pos - owner.pos
    distance = delta.length()
    progress = delta.x * owner.team.direction
    receiver_support = 1.0 if candidate.action_command in (
        PlayerCommand.SUPPORT,
        PlayerCommand.TRIANGLE_SUPPORT,
        PlayerCommand.RECEIVE_PASS,
    ) else 0.0
    receiver_intelligence = candidate.effective_intelligence
    receiver_reliability = 0.34 + receiver_intelligence * 0.56 + receiver_support * 0.14
    touchline_clearance = min(candidate.pos.y - FIELD.top, FIELD.bottom - candidate.pos.y)
    base = progress * forward_weight - distance * 0.16
    base += nearest_opponent_distance * (0.28 + passing * 0.38)
    base += lane_clearance * (0.34 + decision * 0.34 + intelligence * 0.12)
    base += receiver_reliability * 72.0
    if distance > 165 and lane_clearance > 48:
        base += (distance - 165) * pass_power * passing * 0.12
    if touchline_clearance < 46:
        base -= (46.0 - touchline_clearance) * 0.66
    random_span = 34 - decision * 24
    return base + rng.uniform(-random_span, random_span)


def offside_position_active(
    *,
    team_direction: int,
    attacker_x: float,
    passer_x: float,
    offside_line: float,
    in_opponent_half: bool,
) -> bool:
    if not in_opponent_half:
        return False
    forward_progress = attacker_x - passer_x
    if forward_progress <= 0.0:
        return False
    if team_direction == 1:
        return attacker_x > offside_line and attacker_x > passer_x
    return attacker_x < offside_line and attacker_x < passer_x


@dataclass
class PendingKick:
    player: Player
    command: PlayerCommand
    target_player: Player | None = None
    set_piece_skill: float = 0.0
    target_point: Vec2 | None = None


@dataclass
class PassRoute:
    destination: Vec2
    flight_time: float
    interception_risk: float
    receiver_margin: float
    touchline_margin: float
    lane_clearance: float
    opponent_clearance: float


class Match:
    def __init__(
        self,
        home_choice: dict | None = None,
        away_choice: dict | None = None,
        venue_mode: str = "HOME",
        *,
        ai_rethink_multiplier: float = 1.0,
    ) -> None:
        self.rng = random.Random()
        # Only tactical replanning frequency changes between headless league
        # modes. Movement, ball physics, contacts and the game clock stay 20 Hz.
        self.ai_rethink_multiplier = clamp(float(ai_rethink_multiplier), 0.5, 3.0)
        if home_choice is None or away_choice is None:
            defaults = discover_team_choices()
            home_choice = home_choice or next((choice for choice in defaults if "夕張kadoka" in choice["name"]), defaults[0])
            away_choice = away_choice or next((choice for choice in defaults if choice["name"] == "AOBA UNITED"), defaults[1] if len(defaults) > 1 else defaults[0])
        home_short = home_choice["short"]
        away_short = away_choice["short"]
        self.home = self.build_team(home_choice, 1, home_short)
        if home_choice["primary"] == away_choice["primary"]:
            if home_choice["primary"] == AWAY_BLUE:
                away_primary, away_secondary = HOME_RED, HOME_DARK
            else:
                away_primary, away_secondary = AWAY_BLUE, AWAY_DARK
        else:
            away_primary = away_choice["primary"]
            away_secondary = away_choice.get("secondary", darken_color(away_primary))
        self.away = self.build_team(away_choice, -1, away_short, away_primary, away_secondary)
        self.home_choice = home_choice
        self.away_choice = away_choice
        self.teams = (self.home, self.away)
        self.venue_mode = venue_mode if venue_mode in ("HOME", "NEUTRAL", "AWAY") else "HOME"
        if self.venue_mode == "HOME":
            self.home.venue_role, self.away.venue_role = "HOME", "AWAY"
            self.venue_name = self.home.home_court
        elif self.venue_mode == "AWAY":
            self.home.venue_role, self.away.venue_role = "AWAY", "HOME"
            self.venue_name = self.away.home_court
        else:
            self.home.venue_role = self.away.venue_role = "NEUTRAL"
            self.venue_name = "中立地コート"
        for team in self.teams:
            for player in team.players:
                player.venue_role = team.venue_role
        self.ball = Ball()
        self._pre_match_prediction: tuple[float, float, float] | None = None
        self.header_claim_serial = {self.home: -1, self.away: -1}
        self.header_intercept_cooldown = {self.home: 0.0, self.away: 0.0}
        self.state = "TITLE"
        self.game_time = 0.0
        # Total physics time since kickoff, including time spent arranging
        # restarts.  League matches synchronize their pace with this value,
        # while game_time remains each match's independent playing clock.
        self.simulation_elapsed = 0.0
        self.halftime_done = False
        self.decision_timer = 0.0
        self.stoppage_timer = 0.0
        self.banner = ""
        self.banner_timer = 0.0
        self.speed_multiplier = 1
        self.pending_kick: PendingKick | None = None
        self._selected_pass_owner: Player | None = None
        self._selected_pass_target: Player | None = None
        self._selected_pass_route: PassRoute | None = None
        self.throw_in_team: Team | None = None
        self.throw_in_spot = Vec2(FIELD.center)
        self.thrower: Player | None = None
        self.restart_type = ""
        self.restart_team: Team | None = None
        self.restart_spot = Vec2(FIELD.center)
        self.restart_taker: Player | None = None
        self.restart_approach = Vec2(FIELD.center)
        self.restart_elapsed = 0.0
        self.set_piece_targets: dict[Player, Vec2] = {}
        self.corner_attacking_team: Team | None = None
        self.corner_defending_team: Team | None = None
        self.corner_attackers: list[Player] = []
        self.corner_defenders: list[Player] = []
        self.corner_counter_players: list[Player] = []
        self.corner_phase_timer = 0.0
        self.referee_pos = Vec2(FIELD.centerx, FIELD.centery + 100)
        self.referee_target = Vec2(FIELD.center)
        self.referee_active = False
        self.referee_timer = 0.0
        self.referee_card = ""
        self.referee_player: Player | None = None
        self.foul_count = 0
        self.card_count = 0
        self.physical_collision_count = 0
        self.slide_attempts = 0
        self.header_attempts = 0
        self.header_attempt_counts = {"SHOOT": 0, "INTERCEPT": 0, "BLOCK": 0}
        self.knockback_contacts: set[tuple[int, int]] = set()
        self.knockback_pair_cooldowns: dict[tuple[int, int], float] = {}
        self.skill_activation_counts: dict[str, int] = {}
        self.skill_attempt_counts: dict[str, int] = {}
        self.skill_failure_counts: dict[str, int] = {}
        self.keeper_response_counts = {"CATCH": 0, "PUNCH": 0, "TRAP": 0}
        self.shot_outcome_counts = {
            SHOT_ON_TARGET: 0,
            SHOT_WIDE: 0,
            SHOT_POST: 0,
            SHOT_KEEPER_FRIENDLY: 0,
            SHOT_OVER: 0,
        }
        self.pass_outcome_counts = {
            PASS_CLEAN: 0,
            PASS_WRONG_DIRECTION: 0,
            PASS_DANGEROUS_LANE: 0,
            PASS_OVERHIT: 0,
            PASS_UNDERHIT: 0,
        }
        self.catenaccio_timer = {self.home: 0.0, self.away: 0.0}
        self.catenaccio_cooldown = {self.home: 0.0, self.away: 0.0}
        self.counterattack_timer = {self.home: 0.0, self.away: 0.0}
        self.dynamic_state_timer = 0.0
        self.possession_stagnation = 0.0
        self.possession_anchor = Vec2(FIELD.center)
        self.possession_anchor_owner: Player | None = None
        self.restart_counts = {"THROW_IN": 0, "FREE_KICK": 0, "PENALTY_KICK": 0, "GOAL_KICK": 0, "CORNER_KICK": 0}
        self.events: deque[tuple[int, str]] = deque(maxlen=8)
        self.goal_scorers: list[tuple[int, str]] = []
        self.kickoff_team = self.home
        self.reset_positions(self.home)

    def build_team(
        self,
        choice: dict,
        direction: int,
        short_name: str,
        primary: tuple[int, int, int] | None = None,
        secondary: tuple[int, int, int] | None = None,
    ) -> Team:
        primary = primary or choice["primary"]
        secondary = secondary or choice.get("secondary", darken_color(primary))
        return Team(
            choice["name"],
            short_name,
            primary,
            secondary,
            direction,
            self.rng,
            player_records=choice.get("starters"),
            bench_records=choice.get("bench"),
            manager=choice.get("manager", ""),
            manager_tactic_aggression=choice.get("manager_tactic_aggression", 0.375),
            manager_substitution_aggression=choice.get("manager_substitution_aggression", 0.375),
            manager_intelligence=choice.get("manager_intelligence", 0.542),
            source=choice.get("source", ""),
            tactic=choice.get("tactic", "BALANCE"),
            zone_near=choice.get("zone_near", 3),
            zone_far=choice.get("zone_far", 7),
            tactical_discipline=choice.get("tactical_discipline", 0.5),
            home_court=choice.get("home_court", ""),
        )

    def start_new(self) -> None:
        self.home.score = self.away.score = 0
        self.home.shots = self.away.shots = 0
        self.home.possession = self.away.possession = 0.0
        self.speed_multiplier = 1
        self.game_time = 0.0
        self.simulation_elapsed = 0.0
        self.halftime_done = False
        self.events.clear()
        self.goal_scorers.clear()
        self.foul_count = 0
        self.card_count = 0
        self.physical_collision_count = 0
        self.slide_attempts = 0
        self.header_attempts = 0
        self.header_claim_serial = {self.home: -1, self.away: -1}
        self.header_intercept_cooldown = {self.home: 0.0, self.away: 0.0}
        self.header_attempt_counts = {"SHOOT": 0, "INTERCEPT": 0, "BLOCK": 0}
        self.knockback_contacts.clear()
        self._selected_pass_owner = None
        self._selected_pass_target = None
        self._selected_pass_route = None
        self.knockback_pair_cooldowns.clear()
        self.skill_activation_counts.clear()
        self.skill_attempt_counts.clear()
        self.skill_failure_counts.clear()
        self.keeper_response_counts = {"CATCH": 0, "PUNCH": 0, "TRAP": 0}
        self.shot_outcome_counts = {kind: 0 for kind in self.shot_outcome_counts}
        self.pass_outcome_counts = {kind: 0 for kind in self.pass_outcome_counts}
        self.catenaccio_timer = {self.home: 0.0, self.away: 0.0}
        self.catenaccio_cooldown = {self.home: 0.0, self.away: 0.0}
        self.counterattack_timer = {self.home: 0.0, self.away: 0.0}
        self.dynamic_state_timer = 0.0
        self.possession_stagnation = 0.0
        self.possession_anchor.update(FIELD.center)
        self.possession_anchor_owner = None
        self.restart_counts = {kind: 0 for kind in self.restart_counts}
        for team in self.teams:
            team.reset_roster()
            team.tactic = team.initial_tactic
            team.substitutions_used = 0
            team.manager_tactic_changes = 0
            team.substituted_out.clear()
            team.pending_tactic = None
            team.pending_substitution = None
            team.manager_last_change = -9999.0
            team.manager_next_review = 150.0 + self.rng.uniform(0.0, 90.0)
            for player in team.players:
                player.reset_match_state()
                for skill in player.skill_cooldowns:
                    player.skill_cooldowns[skill] = 0.0
                    player.skill_consider_cooldowns[skill] = 0.0
                player._active_skill_cooldowns.clear()
                player._active_skill_consider_cooldowns.clear()
                player.yellow_cards = 0
                player.sent_off = False
        self.state = "PLAYING"
        self.add_event("キックオフ！")
        self._pre_match_prediction = None
        self.show_banner("KICK OFF", 2.8)
        self.reset_positions(self.home)

    def add_event(self, text: str) -> None:
        self.events.appendleft((int(self.game_time // 60), text))

    @staticmethod
    def manager_profile(team: Team) -> ManagerProfile:
        return ManagerProfile(
            team.manager,
            team.manager_tactic_aggression,
            team.manager_substitution_aggression,
            team.manager_intelligence,
        )

    @staticmethod
    def role_rating(player: Player) -> float:
        attributes = {
            "FW": (
                player.shot_power, player.shot_accuracy, player.shooting_technique,
                player.dribble_technique, player.dash_speed,
            ),
            "MF": (
                player.pass_accuracy, player.pass_power, player.passing_technique,
                player.dribble_technique, player.stamina_management,
            ),
            "DF": (
                player.steal_technique, player.pass_interception, player.shot_blocking,
                player.collision_physical, player.dash_speed,
            ),
            "GK": (
                player.goal_stopping, player.jump_judgment, player.jump_height,
                player.pass_accuracy, player.passing_technique,
            ),
        }.get(player.role, (player.dash_speed, player.passing_technique))
        return sum(player.effective_stat(value) for value in attributes) / len(attributes)

    @staticmethod
    def bench_role_rating(record: dict, role: str) -> float:
        raw = record.get("raw", {})
        keys = {
            "FW": ("ShotPower", "ShotAccuracy", "ShootingTechnique", "DribbleTechnique", "DashSpeed"),
            "MF": ("PassAccuracy", "PassPower", "PassingTechnique", "DribbleTechnique", "StaminaManagement"),
            "DF": ("StealTechnique", "PassInterception", "ShotBlocking", "CollisionPhysical", "DashSpeed"),
            "GK": ("GoalStopping", "JumpJudgment", "JumpHeight", "PassAccuracy", "PassingTechnique"),
        }.get(role, ("DashSpeed", "PassingTechnique"))
        return sum(player_stat(raw, key) for key in keys) / len(keys)

    def review_manager_team(self, team: Team) -> None:
        profile = self.manager_profile(team)
        if not profile.active:
            return
        opponent = self.away if team is self.home else self.home
        match_progress = clamp(self.game_time / MATCH_SECONDS, 0.0, 1.0)

        if (
            team.pending_tactic is None
            and self.game_time - team.manager_last_change
            >= 250.0 - profile.tactic_aggression * 115.0
        ):
            possession_total = team.possession + opponent.possession
            possession_share = team.possession / possession_total if possession_total > 0.0 else 0.5
            target = manager_tactic_target(
                profile,
                team.score - opponent.score,
                team.shots - opponent.shots,
                possession_share,
                clamp(self.team_progress(team, self.ball.pos.x), 0.0, 1.0),
                match_progress,
                self.rng,
            )
            selected = choose_manager_tactic(
                profile, team.tactic, target, match_progress, self.rng,
            )
            if selected is not None:
                team.pending_tactic = selected
                self.add_event(f"{team.manager}監督が戦術変更を準備")

        if (
            team.pending_substitution is None
            and team.substitutions_used < 3
            and team.bench
            and match_progress >= 0.12
        ):
            threshold = substitution_fatigue_threshold(profile, match_progress)
            choices: list[tuple[float, Player, dict]] = []
            for outgoing in team.players:
                if outgoing.sent_off or outgoing.stamina_ratio >= threshold:
                    continue
                current_rating = self.role_rating(outgoing)
                for reserve in team.bench:
                    reserve_rating = self.bench_role_rating(reserve, outgoing.role)
                    fatigue_need = threshold - outgoing.stamina_ratio
                    improvement = reserve_rating - current_rating
                    utility = fatigue_need * 1.18 + improvement * 0.52
                    utility += match_progress * 0.07
                    utility += self.rng.uniform(-0.20, 0.20) * (1.0 - profile.intelligence)
                    choices.append((utility, outgoing, reserve))
            if choices:
                utility, outgoing, reserve = max(choices, key=lambda item: item[0])
                required = 0.14 - profile.substitution_aggression * 0.10
                if utility >= required:
                    team.pending_substitution = (outgoing, reserve)
                    self.add_event(f"{team.manager}監督が交代を準備")

    def update_manager_ai(self) -> None:
        for team in self.teams:
            profile = self.manager_profile(team)
            if not profile.active or self.game_time < team.manager_next_review:
                continue
            team.manager_next_review = self.game_time + manager_review_interval(profile, self.rng)
            self.review_manager_team(team)

    def execute_substitution(self, team: Team, outgoing: Player, reserve: dict) -> bool:
        if (
            team.substitutions_used >= 3
            or outgoing not in team.players
            or outgoing.sent_off
            or reserve not in team.bench
        ):
            return False
        record = dict(reserve)
        record["raw"] = dict(reserve.get("raw", {}))
        record["position_x"] = outgoing.grid_x
        record["position_y"] = outgoing.grid_y
        record["slot"] = (outgoing.role, outgoing.home_x, outgoing.home_y)
        record["raw"]["PositionX"] = outgoing.grid_x
        record["raw"]["PositionY"] = outgoing.grid_y
        incoming = Player(team, record["number"], record["name"], record["slot"], record)
        incoming.venue_role = team.venue_role
        incoming.pos.update(outgoing.pos)
        incoming.target.update(outgoing.target)
        incoming.command_target.update(outgoing.command_target)
        index = team.players.index(outgoing)
        team.players[index] = incoming
        team.bench.remove(reserve)
        team.substituted_out.append(outgoing)
        team.substitutions_used += 1
        team.assign_zone_ranks()
        for player_team in self.teams:
            for player in player_team.players:
                previous_alertness = player.alertness.pop(outgoing, None)
                if player.team is not team and previous_alertness is not None:
                    player.alertness[incoming] = previous_alertness
        if self.ball.owner is outgoing:
            self.ball.owner = incoming
        if self.ball.last_touch is outgoing:
            self.ball.last_touch = incoming
        if self.ball.intended is outgoing:
            self.ball.intended = incoming
        self._shape_position_cache = {}
        self._support_context_cache = {}
        self._pressure_context_cache = {}
        self.add_event(f"{team.short_name}交代 {outgoing.name}→{incoming.name}")
        return True

    def apply_pending_manager_changes(self, trigger: str) -> None:
        for team in self.teams:
            if team.pending_tactic is not None:
                old_tactic = team.tactic
                team.tactic = team.pending_tactic
                team.pending_tactic = None
                team.manager_last_change = self.game_time
                team.manager_tactic_changes += 1
                for player in team.players:
                    if team.tactic in BASE_TACTIC_KEYS:
                        player.personal_tactic = team.tactic
                    player._tactical_cache_key = None
                    player._tactical_cache_raw_key = None
                    player._tactical_cache_value = None
                    player.ai_rethink_timer = 0.0
                old_label = TACTICS.get(old_tactic, TACTICS["BALANCE"])["label"]
                new_label = TACTICS.get(team.tactic, TACTICS["BALANCE"])["label"]
                self.add_event(f"{team.short_name}戦術 {old_label}→{new_label}（{trigger}）")
            if team.pending_substitution is not None:
                outgoing, reserve = team.pending_substitution
                team.pending_substitution = None
                self.execute_substitution(team, outgoing, reserve)

    def show_banner(self, text: str, duration: float) -> None:
        self.banner = text
        self.banner_timer = duration

    def team_strength(self, team: Team) -> float:
        players = [player for player in team.players if not player.is_keeper]
        if not players:
            return 0.0
        attack = (
            sum(player.effective_stat(player.shooting_technique) for player in players) / len(players) * 0.50
            + sum(player.effective_stat(player.passing_technique) for player in players) / len(players) * 0.30
            + sum(player.effective_stat(player.shot_power) for player in players) / len(players) * 0.20
        )
        defense = (
            sum(player.effective_stat(player.goal_stopping) for player in players) / len(players) * 0.35
            + sum(player.effective_stat(player.trap_technique) for player in players) / len(players) * 0.35
            + sum(player.effective_stat(player.steal_technique) for player in players) / len(players) * 0.15
            + sum(player.effective_stat(player.safe_play) for player in players) / len(players) * 0.15
        )
        tactic_bonus = {
            "ULTRA_ATTACK": 0.18,
            "ATTACK": 0.10,
            "BALANCE": 0.0,
            "DEFEND": -0.06,
            "ULTRA_DEFEND": -0.12,
        }.get(team.tactic, 0.0)
        venue_bonus = 0.08 if team.venue_role == "HOME" else 0.0
        return attack * 0.66 + defense * 0.34 + tactic_bonus + venue_bonus

    def predict_result(self) -> tuple[int, int]:
        home_expectation, away_expectation = expected_goals(self.home, self.away)
        return int(round(home_expectation)), int(round(away_expectation))

    def predicted_probabilities(self) -> tuple[float, float, float]:
        if self._pre_match_prediction is None:
            self._pre_match_prediction = outcome_probabilities(self.home, self.away)
        return self._pre_match_prediction

    def predicted_result_text(self) -> str:
        home_percent, draw_percent, away_percent = percentage_triplet(self.predicted_probabilities())
        home_name = self.home.name.replace("_", " ")
        away_name = self.away.name.replace("_", " ")
        return f"{home_name} {home_percent}%　引き分け {draw_percent}%　{away_name} {away_percent}%"

    def try_activate_player_skill(
        self,
        player: Player,
        skill: str,
        situation_quality: float,
        execution_quality: float,
        duration: float | None = None,
        force_decision: bool = False,
    ) -> bool:
        command = SKILL_COMMAND.get(skill)
        if command is None or skill not in player.skills:
            return False
        if skill in (SAVING_AURA, EARLY_READ_SAVE, SWEEPER_KEEPER) and not player.is_keeper:
            return False
        if player.skill_command is not PlayerCommand.IDLE:
            return False
        if not force_decision and player.skill_consider_cooldowns.get(skill, 0.0) > 0.0:
            return False
        if not force_decision:
            player.skill_consider_cooldowns[skill] = 0.55
            player._active_skill_consider_cooldowns.add(skill)
        stamina_cost = command_stamina_cost(command)
        conservation = player.stamina_conservation
        if player.stamina < stamina_cost and situation_quality < 0.90:
            return False
        if conservation > 0.0:
            expensive = clamp(stamina_cost / 5.8, 0.0, 1.0)
            situation_quality *= 1.0 - conservation * (0.30 + expensive * 0.48)
        # Confidence changes willingness, while Intelligence still decides
        # whether the situation is actually suitable.
        situation_quality *= 0.82 + player.confidence * 0.36
        if not should_activate(
            player.skills,
            player.skill_cooldowns,
            skill,
            player.effective_intelligence,
            situation_quality,
            execution_quality,
            self.rng,
        ):
            return False
        if not player.activate_skill(skill, duration):
            return False
        player.spend_stamina(player.skill_command)
        self.skill_attempt_counts[skill] = self.skill_attempt_counts.get(skill, 0) + 1
        intelligence = player.effective_intelligence
        success_quality = clamp(execution_quality * 0.76 + intelligence * 0.14 + player.technique_success_factor * 0.10, 0.0, 1.0)
        success_probability = clamp(0.14 + success_quality * 0.80, 0.14, 0.96)
        if self.rng.random() >= success_probability:
            player.skill_command = PlayerCommand.IDLE
            player.skill_timer = 0.0
            self.skill_failure_counts[skill] = self.skill_failure_counts.get(skill, 0) + 1
            return False
        self.skill_activation_counts[skill] = self.skill_activation_counts.get(skill, 0) + 1
        return True

    def reset_positions(self, kickoff_team: Team) -> None:
        self.cancel_pending_kick()
        self.throw_in_team = None
        self.thrower = None
        self.restart_type = ""
        self.restart_team = None
        self.restart_taker = None
        self.set_piece_targets.clear()
        self.restart_elapsed = 0.0
        self.clear_corner_context()
        self.referee_active = False
        self.referee_card = ""
        self.referee_player = None
        self.stoppage_timer = 0.0
        for team in self.teams:
            for player in team.players:
                player.reset_position()
        self.ball.pos.update(FIELD.center)
        self.ball.vel.update(0, 0)
        candidates = [player for player in kickoff_team.players if player.role == "FW"]
        if not candidates:
            # Unconventional formations such as 10-0-0 are legal in the team
            # editor.  Let the nearest outfield player take the kickoff when
            # the lineup contains no registered forward.
            candidates = [player for player in kickoff_team.players if not player.is_keeper]
        if not candidates:
            candidates = list(kickoff_team.players)
        owner = min(candidates, key=lambda player: player.pos.distance_to(FIELD.center))
        owner.pos.update(FIELD.centerx - kickoff_team.direction * 12, FIELD.centery)
        self.ball.owner = owner
        self.ball.last_touch = owner
        self.ball.intended = None
        self.ball.pickup_lock = 0.0
        self.ball.z = 4.0
        self.ball.vertical_speed = 0.0
        self.ball.control_offset.update(owner.team.direction * 10, 0)
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.flight_type = ""
        self.ball.shot_deception = 0.0
        self.ball.shot_outcome = ""
        self.ball.shot_miss_announced = False
        self.ball.pass_outcome = ""
        self.ball.pass_brake = 0.0
        self.ball.intended_destination.update(FIELD.center)
        self.ball.eye_contact_bonus = 0.0
        self.ball.catch_forbidden = False
        self.ball.last_keeper_response = ""
        self.ball.recovery_team = None
        self.ball.recovery_timer = 0.0
        self.decision_timer = 0.8
        owner.issue_action(PlayerCommand.KEEP_BALL, self.ball.pos, duration=0.6, force=True)
        owner.set_movement(PlayerCommand.IDLE)

    def change_owner(
        self,
        player: Player,
        control_offset: Vec2 | tuple[float, float] | None = None,
    ) -> None:
        previous_owner = self.ball.owner
        if self.pending_kick and self.pending_kick.player is not player:
            self.cancel_pending_kick()
        self.ball.owner = player
        self.ball.last_touch = player
        self.ball.intended = None
        self.ball.vel.update(0, 0)
        self.ball.z = 5.0
        self.ball.vertical_speed = 0.0
        if control_offset is None:
            control_offset = (player.team.direction * 10, 0)
        self.ball.control_offset.update(control_offset)
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.flight_type = ""
        self.ball.shot_deception = 0.0
        self.ball.shot_outcome = ""
        self.ball.shot_miss_announced = False
        self.ball.pass_outcome = ""
        self.ball.pass_brake = 0.0
        self.ball.intended_destination.update(player.pos)
        self.ball.eye_contact_bonus = 0.0
        self.ball.catch_forbidden = False
        self.ball.last_keeper_response = ""
        self.ball.recovery_team = None
        self.ball.recovery_timer = 0.0
        self.decision_timer = self.rng.uniform(0.42, 0.9)
        if player.stamina_conservation > 0.0:
            self.decision_timer *= 1.0 - player.stamina_conservation * (0.48 + player.stamina_management * 0.28)
        opponent_goal_x = FIELD.right if player.team.direction == 1 else FIELD.left
        goal_line_distance = abs(opponent_goal_x - player.pos.x)
        if not player.is_keeper and goal_line_distance < 72:
            inward_y = clamp(FIELD.centery - player.pos.y, -105, 105)
            cutback = Vec2(
                player.pos.x - player.team.direction * (34 + (72 - goal_line_distance) * 0.34),
                player.pos.y + inward_y * 0.62,
            )
            player.target.update(cutback)
            player.issue_action(PlayerCommand.DRIBBLE, cutback, duration=0.12, force=True)
            self.decision_timer = min(self.decision_timer, 0.035)
        if previous_owner is not None and previous_owner.team is not player.team:
            player.adjust_confidence(0.014)
            previous_owner.adjust_confidence(-0.010)
            counter_quality = blended_judgment(
                player.effective_stat(player.passing_technique) * 0.52 + player.effective_stat(player.dash_speed) * 0.48,
                player.effective_intelligence,
                0.66,
            )
            if self.try_activate_player_skill(player, TURNOVER_COUNTER, 0.70, counter_quality, duration=0.78):
                self.counterattack_timer[player.team] = 4.6
        if player.technique_command is PlayerCommand.HEADER or player.action_command in (
            PlayerCommand.HEADER,
            PlayerCommand.SKILL_AERIAL_HEADER,
            PlayerCommand.BLOCK_SHOT,
            PlayerCommand.INTERCEPT_PASS,
        ):
            player.heading_purpose = PlayerCommand.IDLE
            if player.heading_motion == "STANDING":
                player.heading_motion = ""
            player.technique_command = PlayerCommand.IDLE
            player.technique_timer = 0.0
            player.issue_action(PlayerCommand.KEEP_BALL, player.pos, duration=0.18, force=True)

    def cancel_pending_kick(self) -> None:
        if self.pending_kick:
            self.pending_kick.player.cancel_kick_motion()
            self.pending_kick = None

    def begin_kick(
        self,
        owner: Player,
        command: PlayerCommand,
        target_player: Player | None = None,
        target_point: Vec2 | tuple[float, float] | None = None,
        set_piece_skill: float = 0.0,
        display_command: PlayerCommand | None = None,
    ) -> bool:
        if self.pending_kick is not None or self.ball.owner is not owner:
            return False
        if target_point is None:
            target_point = target_player.pos if target_player else owner.pos
        owner.issue_action(display_command or command, target_point, force=True)
        owner.set_movement(PlayerCommand.IDLE)
        owner.spend_stamina(command)
        owner.start_kick_motion()
        self.pending_kick = PendingKick(
            owner, command, target_player, set_piece_skill, Vec2(target_point)
        )
        self.ball.vel.update(0, 0)
        self.decision_timer = owner.kick_contact_time
        return True

    def update_pending_kick(self, dt: float) -> None:
        pending = self.pending_kick
        if pending is None:
            return
        owner = pending.player
        if self.ball.owner is not owner:
            self.cancel_pending_kick()
            return
        if not owner.advance_kick_motion(dt):
            return

        self.pending_kick = None
        owner.finish_kick_motion()
        if pending.command in (PlayerCommand.PASS, PlayerCommand.THROUGH_PASS, PlayerCommand.CROSS):
            if pending.target_player is not None:
                if pending.target_player is not None and self.is_offside_pass(owner, pending.target_player):
                    self.start_offside_free_kick(owner, pending.target_player)
                    return
                self._release_pass(
                    owner, pending.target_player, pending.set_piece_skill, pending.target_point
                )
        elif pending.command is PlayerCommand.KEEPER_PUNT:
            if pending.target_player is not None:
                self._release_keeper_punt(owner, pending.target_player)
        elif pending.command is PlayerCommand.SHOOT:
            self._release_shot(owner, pending.set_piece_skill)
        elif pending.command is PlayerCommand.CLEAR:
            self._release_clear(owner, pending.target_player)

    def team_progress(self, team: Team, world_x: float) -> float:
        if team.direction == 1:
            return (world_x - FIELD.left) / FIELD.width
        return (FIELD.right - world_x) / FIELD.width

    def offside_line(self, attacking_team: Team) -> float:
        opponents = [player for player in (self.away.players if attacking_team is self.home else self.home.players) if not player.sent_off]
        if not opponents:
            return FIELD.left if attacking_team.direction == 1 else FIELD.right
        ordered = sorted(opponents, key=lambda player: player.pos.x, reverse=attacking_team.direction == 1)
        if len(ordered) < 2:
            return ordered[0].pos.x if ordered else (FIELD.left if attacking_team.direction == 1 else FIELD.right)
        return ordered[1].pos.x

    def is_offside_pass(self, owner: Player, target: Player) -> bool:
        if owner.team is not target.team or owner.is_keeper or target.is_keeper or target.sent_off:
            return False
        if target is owner:
            return False
        if (target.pos.x - owner.pos.x) * owner.team.direction <= 0.0:
            return False
        if self.team_progress(owner.team, target.pos.x) <= 0.50:
            return False
        line = self.offside_line(owner.team)
        return offside_position_active(
            team_direction=owner.team.direction,
            attacker_x=target.pos.x,
            passer_x=owner.pos.x,
            offside_line=line,
            in_opponent_half=self.team_progress(owner.team, target.pos.x) > 0.50,
        )

    def start_offside_free_kick(self, owner: Player, target: Player) -> None:
        defending_team = self.away if owner.team is self.home else self.home
        self.start_set_piece("FREE_KICK", defending_team, Vec2(target.pos))
        self.add_event(f"{target.name}のオフサイド")
        self.show_banner("FREE KICK", 0.72)

    def progress_to_world_x(self, team: Team, progress: float) -> float:
        if team.direction == 1:
            return FIELD.left + progress * FIELD.width
        return FIELD.right - progress * FIELD.width

    def update_dynamic_player_states(self, dt: float) -> None:
        self.dynamic_state_timer -= dt
        if self.dynamic_state_timer > 0.0:
            return
        interval = 0.40 * self.ai_rethink_multiplier
        self.dynamic_state_timer += interval
        late_match = clamp((self.game_time - MATCH_SECONDS * 0.64) / (MATCH_SECONDS * 0.36), 0.0, 1.0)
        for team in self.teams:
            opponent_team = self.away if team is self.home else self.home
            score_delta = team.score - opponent_team.score
            has_ball = self.ball.owner is not None and self.ball.owner.team is team
            for player in team.players:
                player.personal_tactic_timer -= interval
                if team.tactic == "RANDOM" and player.personal_tactic_timer <= 0.0:
                    player.personal_tactic = self.rng.choice(BASE_TACTIC_KEYS)
                    player.personal_tactic_timer = self.rng.uniform(4.0, 11.0)
                elif team.tactic == "NO_INSTRUCTION" and player.personal_tactic_timer <= 0.0:
                    attack_need = clamp(-score_delta * 0.26 + late_match * max(0, -score_delta) * 0.34, -0.25, 0.72)
                    protect_need = clamp(score_delta * 0.22 + late_match * max(0, score_delta) * 0.34, -0.25, 0.70)
                    role_attack = 0.13 if player.role == "FW" else -0.08 if player.is_keeper else 0.0
                    role_defend = 0.15 if player.role in ("DF", "GK") else -0.06
                    tactic_utilities = {
                        "ULTRA_ATTACK": 0.18 + attack_need * 0.72 + player.confidence * 0.18 + role_attack,
                        "ATTACK": 0.38 + attack_need * 0.55 + player.confidence * 0.10 + role_attack,
                        "BALANCE": 0.58 + (1.0 - late_match) * 0.10,
                        "DEFEND": 0.38 + protect_need * 0.55 + role_defend,
                        "ULTRA_DEFEND": 0.16 + protect_need * 0.72 + role_defend,
                    }
                    player.personal_tactic = choose_utility_action(
                        tactic_utilities,
                        player.effective_intelligence,
                        self.rng,
                    )
                    player.personal_tactic_timer = self.rng.uniform(3.5, 7.5)
                elif team.tactic in BASE_TACTIC_KEYS:
                    player.personal_tactic = team.tactic

                confidence_target = clamp(
                    player.base_confidence + score_delta * 0.035 + (0.018 if has_ball else -0.006),
                    0.05,
                    0.98,
                )
                player.confidence += (confidence_target - player.confidence) * 0.012
                loyalty_target = player.tactical_discipline
                loyalty_target += clamp(score_delta * late_match * 0.06, -0.18, 0.14)
                if team.tactic == "RANDOM":
                    loyalty_target -= 0.22
                player.tactical_loyalty += (clamp(loyalty_target, 0.0, 1.0) - player.tactical_loyalty) * 0.08

                style_drive = (
                    player.pressing + player.overlap + player.diagonal_run
                    + player.run_into_space + player.goal_poaching
                ) / 5.0
                tactic = team.tactical_settings(player)
                tactic_drive = clamp((tactic["push"] - 0.52) / 0.48, 0.0, 1.0)
                urgency = clamp(-score_delta * late_match * 0.14, -0.16, 0.30)
                aggression_target = clamp(
                    0.24 + style_drive * 0.28 + player.confidence * 0.24 + tactic_drive * 0.16 + urgency,
                    0.08,
                    0.98,
                )
                player.aggressiveness += (aggression_target - player.aggressiveness) * 0.10
                random_disorder = 0.17 if team.tactic == "RANDOM" else 0.0
                zone_target = clamp(
                    0.18 + player.tactical_loyalty * 0.53 + player.effective_intelligence * 0.25
                    - player.aggressiveness * 0.10 - random_disorder,
                    0.05,
                    0.98,
                )
                position_target = clamp(
                    0.20 + player.tactical_loyalty * 0.49 + player.effective_intelligence * 0.23
                    - player.aggressiveness * 0.12 - random_disorder,
                    0.05,
                    0.98,
                )
                player.zone_awareness += (zone_target - player.zone_awareness) * 0.12
                player.position_awareness += (position_target - player.position_awareness) * 0.12

                for opponent in opponent_team.players:
                    threat = (
                        opponent.shooting_technique * 0.24 + opponent.shot_power * 0.16
                        + opponent.passing_technique * 0.17 + opponent.dribble_technique * 0.18
                        + opponent.confidence * 0.12
                        + self.team_progress(opponent.team, opponent.pos.x) * 0.13
                    )
                    if self.ball.owner is opponent:
                        threat += 0.24
                    threat += clamp(1.0 - player.pos.distance_to(opponent.pos) / 620.0, 0.0, 1.0) * 0.12
                    perception_noise = self.rng.uniform(-0.20, 0.20) * (1.0 - player.effective_intelligence)
                    target_alertness = clamp(threat + perception_noise, 0.02, 1.0)
                    current = player.alertness.get(opponent, 0.50)
                    player.alertness[opponent] = current + (target_alertness - current) * 0.18

    def most_alert_opponent(self, player: Player, fallback: Player) -> Player:
        opponents = [
            opponent for team in self.teams if team is not player.team
            for opponent in team.players if not opponent.sent_off
        ]
        return max(
            opponents,
            key=lambda opponent: (
                player.alertness_for(opponent) * 1.18
                - clamp(player.pos.distance_to(opponent.pos) / 900.0, 0.0, 0.72)
                - sum(
                    teammate is not player
                    and teammate.action_command is PlayerCommand.MARK
                    and teammate.command_target.distance_to(opponent.pos) < 72
                    for teammate in player.team.players
                ) * (0.20 + player.effective_intelligence * 0.20)
            ),
            default=fallback,
        )

    def shape_position(self, player: Player, has_possession: bool) -> Vec2:
        cache = getattr(self, "_shape_position_cache", None)
        cache_key = (player, bool(has_possession))
        if cache is not None and cache_key in cache:
            return Vec2(cache[cache_key])
        team = player.team
        settings = team.tactical_settings(player)
        zone_near = (team.zone_near - 0.5) / 10.0
        zone_far = (team.zone_far - 0.5) / 10.0
        base_progress = zone_near + (zone_far - zone_near) * player.zone_rank
        base_progress = clamp(
            base_progress + settings["bias"] * (0.30 + player.tactical_loyalty * 0.70),
            zone_near,
            zone_far,
        )
        ball_progress = clamp(self.team_progress(team, self.ball.pos.x), 0.0, 1.0)
        if ball_progress < zone_near:
            zone_shift = (ball_progress - zone_near) * settings["retreat"]
        elif ball_progress > zone_far:
            zone_shift = (ball_progress - zone_far) * settings["push"]
        else:
            zone_center = (zone_near + zone_far) / 2
            zone_shift = (ball_progress - zone_center) * 0.16
        zone_shift *= 0.34 + player.zone_awareness * 0.66
        if has_possession:
            zone_shift += 0.012 * settings["push"]
            if self.counterattack_timer.get(team, 0.0) > 0.0:
                zone_shift += 0.075
        flexible_progress = clamp(base_progress * 0.45 + ball_progress * 0.55, 0.045, 0.955)
        base_progress = flexible_progress + (base_progress - flexible_progress) * player.position_awareness
        roam_scale = 1.18 - player.position_awareness * 0.52
        target_progress = clamp(base_progress + zone_shift + player.roam.x * roam_scale / FIELD.width, 0.045, 0.955)
        catenaccio_quality = 0.0
        if not has_possession and self.catenaccio_timer.get(team, 0.0) > 0.0:
            catenaccio_quality = blended_judgment(
                (player.effective_stat(player.steal_technique) + player.effective_stat(player.physical_play_quality)) * 0.5,
                player.effective_intelligence,
                0.64,
            )
            target_progress = clamp(target_progress - 0.045 - catenaccio_quality * 0.075, 0.035, 0.955)
        base_x = self.progress_to_world_x(team, target_progress)
        base_y = FIELD.top + player.home_y * FIELD.height
        width_scale = settings["width"]
        role_lateral = {"DF": 1.0, "MF": 0.85, "FW": 0.70}.get(player.role, 0.8)
        ball_lateral_shift = (
            (self.ball.pos.y - FIELD.centery) * settings["lateral"] * role_lateral
            * (0.35 + player.zone_awareness * 0.65)
        )
        y = (
            FIELD.centery + (base_y - FIELD.centery) * width_scale
            + ball_lateral_shift + player.roam.y * roam_scale
        )
        if catenaccio_quality > 0.0:
            y += (FIELD.centery - y) * (0.10 + catenaccio_quality * 0.20)
        result = Vec2(clamp(base_x, FIELD.left + 20, FIELD.right - 20), clamp(y, FIELD.top + 18, FIELD.bottom - 18))
        if cache is not None:
            cache[cache_key] = Vec2(result)
        return result

    @staticmethod
    def distance_to_pass_lane(point: Vec2, start: Vec2, end: Vec2) -> float:
        lane = end - start
        if lane.length_squared() < 0.0001:
            return point.distance_to(start)
        progress = clamp((point - start).dot(lane) / lane.length_squared(), 0.0, 1.0)
        return point.distance_to(start + lane * progress)

    def goal_event_urgency(
        self,
        team: Team,
        point: Vec2 | None = None,
        player: Player | None = None,
    ) -> tuple[float, float]:
        """Return attacking and defending urgency around either goal.

        This is intentionally independent of stamina.  Stamina management may
        choose an economical way to react, but must not decide that a likely
        goal is less important than preserving energy.
        """
        uses_live_ball = point is None
        point = Vec2(point if point is not None else self.ball.pos)
        movement_cache = getattr(self, "_movement_goal_urgency_cache", None)
        cached_base = movement_cache.get(team) if uses_live_ball and movement_cache is not None else None
        if cached_base is not None:
            attacking, defending, attack_bonus, defense_bonus = cached_base
            if player is not None:
                reachable = clamp(1.10 - player.pos.distance_to(point) / 660.0, 0.12, 1.0)
                attacking *= reachable
                defending *= reachable
            return clamp(attacking + attack_bonus, 0.0, 1.0), clamp(defending + defense_bonus, 0.0, 1.0)
        own_goal_x = FIELD.left if team.direction == 1 else FIELD.right
        opponent_goal_x = FIELD.right if team.direction == 1 else FIELD.left
        lateral = abs(point.y - FIELD.centery)
        centrality = clamp(1.0 - max(0.0, lateral - GOAL_HALF_HEIGHT * 0.55) / 235.0, 0.0, 1.0)

        def proximity(goal_x: float) -> float:
            return clamp(1.0 - abs(point.x - goal_x) / 490.0, 0.0, 1.0) * centrality

        attacking = proximity(opponent_goal_x)
        defending = proximity(own_goal_x)
        attack_bonus = 0.0
        defense_bonus = 0.0
        if self.ball.owner is None and self.ball.vel.length_squared() > 1.0:
            attack_bonus = 0.10 if self.ball.vel.x * team.direction > 0 else 0.0
            defense_bonus = 0.14 if self.ball.vel.x * team.direction < 0 else 0.0
        if uses_live_ball and movement_cache is not None:
            movement_cache[team] = (attacking, defending, attack_bonus, defense_bonus)
        if player is not None:
            reachable = clamp(1.10 - player.pos.distance_to(point) / 660.0, 0.12, 1.0)
            attacking *= reachable
            defending *= reachable
        return clamp(attacking + attack_bonus, 0.0, 1.0), clamp(defending + defense_bonus, 0.0, 1.0)

    def ball_is_shot(self) -> bool:
        return "シュート" in self.ball.flight_type

    def prepare_keeper_read(self, keeper: Player) -> None:
        if keeper.keeper_read_shot_serial == self.ball.shot_serial:
            return
        keeper.keeper_read_shot_serial = self.ball.shot_serial
        goal_x = FIELD.left + 8 if keeper.team.direction == 1 else FIELD.right - 8
        if abs(self.ball.vel.x) < 0.001:
            flight_time = 0.0
            true_y = self.ball.pos.y
        else:
            flight_time = max(0.0, (goal_x - self.ball.pos.x) / self.ball.vel.x)
            true_y = self.ball.pos.y + self.ball.vel.y * flight_time
        stopping = keeper.effective_stat(keeper.goal_stopping)
        if keeper.skill_command is PlayerCommand.IDLE:
            early_window = clamp(flight_time / 1.20, 0.0, 1.0)
            super_execution = blended_judgment(
                stopping * 0.62 + keeper.effective_stat(keeper.jump_judgment) * 0.38,
                keeper.effective_intelligence,
                0.76,
            )
            if self.try_activate_player_skill(
                keeper,
                EARLY_READ_SAVE,
                0.38 + early_window * 0.46 + self.ball.shot_deception * 0.10,
                super_execution,
                duration=max(0.82, min(1.55, flight_time + 0.32)),
            ):
                keeper.super_save_timer = max(0.82, min(1.55, flight_time + 0.32))
        super_active = keeper.super_save_timer > 0.0
        deception_weight = 0.24 if super_active else 0.52
        keeper_friendly = self.ball.shot_outcome == SHOT_KEEPER_FRIENDLY
        read_quality = clamp(
            stopping + (0.24 if super_active else 0.0)
            - self.ball.shot_deception * deception_weight + 0.30
            + (0.22 if keeper_friendly else 0.0),
            0.0,
            1.0,
        )
        wrong_chance = clamp(
            0.48 - stopping * 0.43 + self.ball.shot_deception * (0.07 if super_active else 0.17)
            - (0.24 if super_active else 0.0),
            0.01,
            0.58,
        )
        if keeper_friendly:
            wrong_chance *= 0.18
        keeper.keeper_wrong_read = self.rng.random() < wrong_chance
        if keeper.keeper_wrong_read:
            predicted_y = FIELD.centery - (true_y - FIELD.centery)
        else:
            predicted_y = true_y
        read_error = (18 + (1.0 - read_quality) * 132) * keeper.mistake_error_factor
        if super_active:
            read_error *= 0.42
        if keeper_friendly:
            read_error *= 0.44
        predicted_y += self.rng.gauss(0.0, read_error)
        keeper.keeper_read_y = clamp(predicted_y, FIELD.centery - 122, FIELD.centery + 122)
        if super_active:
            keeper.jump(28 + stopping * 38)
            keeper.issue_action(
                PlayerCommand.SKILL_EARLY_READ_SAVE,
                (goal_x, keeper.keeper_read_y),
                duration=keeper.super_save_timer,
                force=True,
            )
            keeper.use_technique(PlayerCommand.SAVE, duration=keeper.super_save_timer)

    def keeper_attack_is_safe(self, keeper: Player) -> tuple[bool, float]:
        owner = self.ball.owner
        if owner is None or owner.team is not keeper.team:
            return False, 0.0
        ball_progress = clamp(self.team_progress(keeper.team, self.ball.pos.x), 0.0, 1.0)
        opponents = [
            player for team in self.teams if team is not keeper.team
            for player in team.players if not player.sent_off
        ]
        deepest_threat = min((self.team_progress(keeper.team, player.pos.x) for player in opponents), default=1.0)
        nearest_threat = min((keeper.pos.distance_to(player.pos) for player in opponents), default=999.0)
        if owner is keeper:
            # After winning the ball during an attack participation run, keep the
            # permission only long enough to distribute it while pressure is low.
            safety = clamp((ball_progress - 0.12) * 1.6, 0.0, 0.70)
            safety += clamp((nearest_threat - 115) / 600.0, 0.0, 0.30)
            return ball_progress > 0.14 and nearest_threat > 115, clamp(safety, 0.0, 1.0)
        safety = clamp((ball_progress - 0.54) * 1.55, 0.0, 0.65)
        safety += clamp((deepest_threat - 0.24) * 1.30, 0.0, 0.28)
        safety += clamp((nearest_threat - 260) / 900.0, 0.0, 0.16)
        safe = ball_progress > 0.60 and deepest_threat > 0.20 and nearest_threat > 250
        return safe, clamp(safety, 0.0, 1.0)

    @staticmethod
    def goalkeeper_penalty_bounds(team: Team, inset: float = 0.0) -> tuple[float, float, float, float]:
        """Return the playable inside edge of a team's own penalty-area lines."""
        top = FIELD.centery - PENALTY_AREA_WIDTH * 0.5 + inset
        bottom = FIELD.centery + PENALTY_AREA_WIDTH * 0.5 - inset
        if team.direction == 1:
            left = FIELD.left + inset
            right = FIELD.left + PENALTY_AREA_DEPTH - inset
        else:
            left = FIELD.right - PENALTY_AREA_DEPTH + inset
            right = FIELD.right - inset
        return left, right, top, bottom

    def point_in_own_penalty_area(
        self,
        team: Team,
        point: Vec2 | tuple[float, float],
        margin: float = 0.0,
    ) -> bool:
        left, right, top, bottom = self.goalkeeper_penalty_bounds(team, -margin)
        return left <= point[0] <= right and top <= point[1] <= bottom

    def clamp_to_goalkeeper_area(
        self,
        team: Team,
        point: Vec2 | tuple[float, float],
        inset: float = 12.0,
    ) -> Vec2:
        left, right, top, bottom = self.goalkeeper_penalty_bounds(team, inset)
        return Vec2(clamp(point[0], left, right), clamp(point[1], top, bottom))

    def keeper_can_use_hands(self, keeper: Player) -> bool:
        """Hands are legal only in the box and not for a deliberate team back-pass."""
        if not self.point_in_own_penalty_area(keeper.team, self.ball.pos):
            return False
        last_touch = self.ball.last_touch
        if last_touch is None or last_touch is keeper or last_touch.team is not keeper.team:
            return True
        deliberate_back_pass = self.ball.intended is keeper or any(
            token in self.ball.flight_type
            for token in ("パス", "スローイン", "ゴールキック", "コーナーキック")
        )
        return not deliberate_back_pass

    def behavior_quality(self, player: Player, behavior: str, specialist: float | None = None) -> float:
        preference = player.effective_stat(getattr(player, behavior))
        if specialist is not None:
            preference = preference * 0.58 + player.effective_stat(specialist) * 0.42
        return blended_judgment(preference, player.effective_intelligence, 0.66)

    def cached_off_ball_decision(self, player: Player, context: tuple, chooser) -> tuple:
        """Throttle tactical replanning while keeping movement physics at 20 Hz.

        High-intelligence players reconsider sooner. Ownership and tactical mode
        are part of the context, so a turnover invalidates the cache immediately.
        """
        same_owner = (
            player.ai_decision_context is not None
            and len(player.ai_decision_context) > 1
            and len(context) > 1
            and player.ai_decision_context[1] is context[1]
        )
        if player.ai_rethink_timer > 0.0 and same_owner:
            return (
                player.ai_cached_action,
                Vec2(player.ai_cached_target),
                player.ai_cached_locomotion,
            )
        action, target, locomotion = chooser()
        player.ai_decision_context = context
        player.ai_cached_action = action
        player.ai_cached_target.update(target)
        player.ai_cached_locomotion = locomotion
        player.ai_rethink_timer = (
            0.12 + (1.0 - player.effective_intelligence) * 0.16
        ) * self.ai_rethink_multiplier
        return action, Vec2(target), locomotion

    def update_possession_stagnation(self, dt: float) -> None:
        """Track a possession that remains in roughly the same patch of grass."""
        owner = self.ball.owner
        if owner is None:
            self.possession_stagnation = max(0.0, self.possession_stagnation - dt * 3.0)
            self.possession_anchor_owner = None
            return
        if owner is not self.possession_anchor_owner:
            self.possession_anchor_owner = owner
            self.possession_anchor.update(owner.pos)
            self.possession_stagnation = 0.0
            return
        anchor_distance = owner.pos.distance_to(self.possession_anchor)
        if anchor_distance <= 92:
            self.possession_stagnation = min(12.0, self.possession_stagnation + dt)
        else:
            self.possession_anchor.update(owner.pos)
            self.possession_stagnation = max(0.0, self.possession_stagnation - dt * 2.2)

    def attacking_support_context(self, player: Player, owner: Player) -> tuple[int, float]:
        """Return the player's stable support priority and local friendly congestion."""
        cache = getattr(self, "_support_context_cache", None)
        cache_key = (player.team, owner)
        if cache is not None and cache_key in cache:
            ranks, congestion = cache[cache_key]
            return ranks.get(player, len(ranks)), congestion
        teammates = [
            teammate for teammate in player.team.players
            if teammate is not owner and not teammate.is_keeper and not teammate.sent_off
        ]
        ranked = sorted(
            teammates,
            key=lambda teammate: (
                teammate.pos.distance_to(owner.pos) * 0.62
                - self.behavior_quality(teammate, "support", teammate.passing_technique) * 92
                - (18 if teammate.role == "MF" else 8 if teammate.role == "DF" else 0)
                + teammate.grid_x * 0.001
            ),
        )
        rank = ranked.index(player) if player in ranked else len(ranked)
        nearby = sum(teammate.pos.distance_to(owner.pos) < 165 for teammate in teammates)
        congestion = clamp((nearby - 2) / 5.0, 0.0, 1.0)
        if cache is not None:
            cache[cache_key] = ({teammate: index for index, teammate in enumerate(ranked)}, congestion)
        return rank, congestion

    def support_location_value(self, player: Player, owner: Player, target: Vec2) -> tuple[float, float]:
        """Marginal utility of adding this player to a proposed support location."""
        occupancy = 0.0
        nearest_friend = 240.0
        for teammate in player.team.players:
            if teammate is player or teammate is owner or teammate.sent_off:
                continue
            current_distance = teammate.pos.distance_to(target)
            target_distance = teammate.target.distance_to(target)
            nearest_friend = min(nearest_friend, current_distance, target_distance)
            current_claim = clamp((100 - current_distance) / 70.0, 0.0, 1.0)
            moving_claim = clamp((92 - target_distance) / 64.0, 0.0, 1.0)
            if teammate.action_command in (PlayerCommand.SUPPORT, PlayerCommand.TRIANGLE_SUPPORT, PlayerCommand.CREATE_PASS_LANE):
                moving_claim *= 1.18
            occupancy += max(current_claim, moving_claim * 0.88)
        opponents = [
            opponent for team in self.teams if team is not player.team
            for opponent in team.players if not opponent.sent_off
        ]
        # This is only a cheap off-ball support estimate; the real pass engine
        # evaluates every defender again before releasing the ball.  The six
        # defenders nearest the proposed location preserve the important local
        # pressure while avoiding dozens of low-impact lane projections.
        nearby_opponents = sorted(
            opponents,
            key=lambda opponent: opponent.pos.distance_squared_to(target),
        )[:6]
        opponent_clearance = min((opponent.pos.distance_to(target) for opponent in nearby_opponents), default=180.0)
        lane_clearance = min(
            (self.distance_to_pass_lane(opponent.pos, owner.pos, target) for opponent in nearby_opponents),
            default=150.0,
        )
        availability = clamp((nearest_friend - 42) / 115.0, 0.0, 1.0)
        value = 0.16 + availability * 0.30
        value += clamp(opponent_clearance / 180.0, 0.0, 1.0) * 0.15
        value += clamp(lane_clearance / 125.0, 0.0, 1.0) * 0.13
        value -= occupancy * (0.30 + player.effective_intelligence * 0.20)
        return clamp(value, -1.15, 0.72), occupancy

    def spread_attacking_target(
        self,
        player: Player,
        owner: Player,
        target: Vec2,
        support_rank: int,
        congestion: float,
    ) -> Vec2:
        """Preserve width and repel duplicate attacking targets during stale possession."""
        stagnation = clamp((self.possession_stagnation - 1.2) / 4.8, 0.0, 1.0)
        spread_need = max(congestion, stagnation)
        result = Vec2(target)
        if support_rank >= 2 and spread_need > 0.0:
            width_ratio = clamp((player.grid_x - 1) / 14.0, 0.0, 1.0)
            width_lane = FIELD.top + 42 + width_ratio * (FIELD.height - 84)
            result.y += (width_lane - result.y) * (0.34 + spread_need * 0.46)
            # Some players stay available behind the ball while others threaten
            # forward space; this prevents one horizontal swarm around the owner.
            lane_role = (player.grid_x + support_rank) % 3
            longitudinal = (-84, 72, 132)[lane_role]
            desired_x = owner.pos.x + player.team.direction * longitudinal
            result.x += (desired_x - result.x) * (0.24 + spread_need * 0.36)
        repulsion = Vec2()
        for teammate in player.team.players:
            if teammate is player or teammate is owner or teammate.sent_off:
                continue
            delta = result - teammate.pos
            distance = delta.length()
            minimum = 78 if support_rank < 2 else 112
            if distance < minimum:
                if distance < 0.01:
                    direction = Vec2(0, -1 if (player.grid_x + support_rank) % 2 else 1)
                else:
                    direction = delta / distance
                repulsion += direction * (minimum - distance)
        result += repulsion * (0.34 + player.effective_intelligence * 0.30)
        result.x = clamp(result.x, FIELD.left + 20, FIELD.right - 20)
        result.y = clamp(result.y, FIELD.top + 20, FIELD.bottom - 20)
        return result

    def open_space_target(self, player: Player, origin: Vec2, forward: float = 100.0) -> Vec2:
        opponents = [
            opponent for team in self.teams if team is not player.team
            for opponent in team.players if not opponent.sent_off
        ]
        # Run destinations are a coarse tactical choice and are reconsidered a
        # few times per second. Nearby pressure matters much more than a player
        # on the far side of the pitch; final dribble/pass/tackle checks remain
        # exact and still include every opponent.
        opponents = sorted(
            opponents,
            key=lambda opponent: opponent.pos.distance_squared_to(origin),
        )[:6]
        teammates = [
            teammate for teammate in player.team.players
            if teammate is not player and not teammate.sent_off
        ]
        intelligence = player.effective_intelligence
        run_quality = self.behavior_quality(player, "run_into_space", player.dash_speed)
        candidates = []
        for forward_scale, side_scale in ((1.0, -1.0), (1.0, 1.0), (0.65, -1.45), (0.65, 1.45), (1.35, 0.0)):
            candidate = Vec2(
                origin.x + player.team.direction * forward * forward_scale,
                origin.y + 68 * side_scale,
            )
            candidate.x = clamp(candidate.x, FIELD.left + 24, FIELD.right - 24)
            candidate.y = clamp(candidate.y, FIELD.top + 24, FIELD.bottom - 24)
            openness = min((candidate.distance_to(opponent.pos) for opponent in opponents), default=160.0)
            friendly_clearance = min((candidate.distance_to(teammate.pos) for teammate in teammates), default=180.0)
            target_claims = sum(
                teammate.target.distance_to(candidate) < 96
                and teammate.action_command in (
                    PlayerCommand.SUPPORT, PlayerCommand.TRIANGLE_SUPPORT,
                    PlayerCommand.OVERLAP, PlayerCommand.DIAGONAL_RUN, PlayerCommand.RUN_INTO_SPACE,
                )
                for teammate in teammates
            )
            progress = self.team_progress(player.team, candidate.x)
            score = openness * (0.58 + run_quality * 0.54) + progress * 70
            score += clamp(friendly_clearance, 0.0, 170.0) * (0.24 + intelligence * 0.20)
            score -= target_claims * (42 + intelligence * 48)
            score = perceived_utility(score, intelligence, self.rng, noise_span=38.0)
            candidates.append((score, candidate))
        return max(candidates, key=lambda item: item[0])[1]

    def receiver_continuation_value(
        self,
        owner: Player,
        candidate: Player,
        destination: Vec2,
    ) -> float:
        """Estimate whether a receiver will have a useful second action.

        This is a shallow, inexpensive look-ahead rather than a simulated play.
        It prevents an apparently clean pass from repeatedly finding a receiver
        who is immediately boxed in with no forward or lateral exit.
        """
        opponents = [
            opponent for team in self.teams if team is not owner.team
            for opponent in team.players if not opponent.sent_off
        ]
        opponents = sorted(
            opponents,
            key=lambda opponent: opponent.pos.distance_squared_to(destination),
        )[:6]
        options: list[float] = []
        for forward_scale, side_scale in ((1.0, 0.0), (0.78, -1.0), (0.78, 1.0), (0.28, -1.35), (0.28, 1.35)):
            next_point = Vec2(
                destination.x + owner.team.direction * 96 * forward_scale,
                destination.y + 72 * side_scale,
            )
            next_point.x = clamp(next_point.x, FIELD.left + 24, FIELD.right - 24)
            next_point.y = clamp(next_point.y, FIELD.top + 28, FIELD.bottom - 28)
            openness = min((next_point.distance_to(opponent.pos) for opponent in opponents), default=180.0)
            lane_clearance = min(
                (self.distance_to_pass_lane(opponent.pos, destination, next_point) for opponent in opponents),
                default=145.0,
            )
            progress = clamp(
                (next_point.x - destination.x) * owner.team.direction / 96.0,
                -0.2,
                1.0,
            )
            options.append(
                clamp(openness / 175.0, 0.0, 1.0) * 0.55
                + clamp(lane_clearance / 118.0, 0.0, 1.0) * 0.27
                + max(0.0, progress) * 0.18
            )
        if not options:
            return 0.0
        receiver_skill = (
            candidate.effective_stat(candidate.passing_technique) * 0.42
            + candidate.effective_stat(candidate.dribble_technique) * 0.34
            + candidate.effective_intelligence * 0.24
        )
        awareness = blended_judgment(receiver_skill, owner.effective_intelligence, 0.46)
        # Less intelligent passers see the general pressure; smart passers can
        # identify the receiver's best viable continuation.
        average_option = sum(options) / len(options)
        return average_option + (max(options) - average_option) * (0.18 + awareness * 0.76)

    def defensive_intercept_target(self, player: Player, owner: Player) -> Vec2:
        """Choose a likely and dangerous passing lane without a search tree."""
        receivers = [
            candidate for candidate in owner.team.players
            if candidate is not owner and not candidate.sent_off
        ]
        if not receivers:
            return Vec2(owner.pos)
        intelligence = player.effective_intelligence
        interception = self.behavior_quality(player, "interception", player.pass_interception)
        own_goal = Vec2(
            FIELD.left if player.team.direction == 1 else FIELD.right,
            FIELD.centery,
        )
        best_score = -9999.0
        best_target = Vec2(owner.pos)
        for receiver in receivers:
            lane = receiver.pos - owner.pos
            if lane.length_squared() < 16.0:
                continue
            fraction = clamp(
                (player.pos - owner.pos).dot(lane) / lane.length_squared(),
                0.20,
                0.78,
            )
            intercept_point = owner.pos + lane * fraction
            arrival_distance = player.pos.distance_to(intercept_point)
            receiver_progress = clamp(
                (receiver.pos.x - owner.pos.x) * owner.team.direction / 280.0,
                -0.25,
                1.0,
            )
            goal_threat = clamp(1.0 - receiver.pos.distance_to(own_goal) / 760.0, 0.0, 1.0)
            receiver_space = min(
                (
                    receiver.pos.distance_to(defender.pos)
                    for defender in player.team.players
                    if defender is not player and not defender.sent_off
                ),
                default=180.0,
            )
            claimed = sum(
                teammate is not player
                and teammate.action_command is PlayerCommand.INTERCEPT_PASS
                and teammate.command_target.distance_to(intercept_point) < 82
                for teammate in player.team.players
            )
            score = receiver_progress * 72 + goal_threat * 94
            score += clamp(receiver_space / 180.0, 0.0, 1.0) * 34
            score += player.alertness_for(receiver) * 42
            score -= arrival_distance * (0.34 + (1.0 - interception) * 0.18)
            score -= claimed * (38 + intelligence * 54)
            score = perceived_utility(score, intelligence, self.rng, noise_span=31.0)
            if score > best_score:
                best_score = score
                best_target = intercept_point
        return best_target

    def shot_lane_quality(self, owner: Player, opponents: list[Player]) -> float:
        """Judge several goal channels so a central blocker is not the whole picture."""
        goal_x = FIELD.right if owner.team.direction == 1 else FIELD.left
        outfield_opponents = [opponent for opponent in opponents if not opponent.is_keeper]
        lane_qualities = []
        for offset in (-0.62, 0.0, 0.62):
            target = Vec2(goal_x, FIELD.centery + GOAL_HALF_HEIGHT * offset)
            clearance = min(
                (self.distance_to_pass_lane(opponent.pos, owner.pos, target) for opponent in outfield_opponents),
                default=150.0,
            )
            lane_qualities.append(clamp(clearance / 92.0, 0.0, 1.0))
        center_quality = lane_qualities[1]
        shooting_judgment = blended_judgment(
            owner.effective_stat(owner.shooting_technique),
            owner.effective_intelligence,
            0.60,
        )
        return center_quality + (max(lane_qualities) - center_quality) * (0.18 + shooting_judgment * 0.78)

    def plan_combination_run(
        self,
        passer: Player,
        receiver: Player,
        destination: Vec2,
        flight_time: float,
    ) -> None:
        """Give the passer one cheap follow-up intention after releasing a pass.

        This is deliberately a shallow plan rather than a search tree. Passing,
        support behaviour and Intelligence all affect the selected continuation,
        and low Intelligence leaves more evaluation noise.
        """
        if passer.is_keeper or passer.sent_off:
            return
        intelligence = passer.effective_intelligence
        passing = passer.effective_stat(passer.passing_technique)
        support = passer.effective_stat(passer.support)
        quality = clamp(passing * 0.34 + support * 0.24 + intelligence * 0.42, 0.0, 1.0)
        opponents = [
            opponent for team in self.teams if team is not passer.team
            for opponent in team.players if not opponent.sent_off
        ]
        candidates: list[tuple[float, Vec2]] = []
        forward = 54 + quality * 96
        for side in (-1.0, 0.0, 1.0):
            candidate = Vec2(
                destination.x + passer.team.direction * forward,
                destination.y + side * (54 + quality * 42),
            )
            candidate.x = clamp(candidate.x, FIELD.left + 24, FIELD.right - 24)
            candidate.y = clamp(candidate.y, FIELD.top + 28, FIELD.bottom - 28)
            openness = min((candidate.distance_to(opponent.pos) for opponent in opponents), default=180.0)
            receiver_spacing = candidate.distance_to(receiver.pos)
            progress = self.team_progress(passer.team, candidate.x)
            score = openness * (0.52 + quality * 0.42)
            score += clamp(receiver_spacing, 45.0, 165.0) * 0.16
            score += progress * (34 + intelligence * 42)
            score = perceived_utility(score, intelligence, self.rng, noise_span=32.0)
            candidates.append((score, candidate))
        _, target = max(candidates, key=lambda item: item[0])
        passer.combination_partner = receiver
        passer.combination_target.update(target)
        passer.combination_quality = quality
        passer.combination_timer = max(0.8, flight_time + 1.35 + intelligence * 0.45)
        # The completed kick command must not suppress the planned follow-up.
        passer.action_timer = 0.0

    def choose_attacking_run(
        self,
        player: Player,
        shape: Vec2,
        owner: Player,
    ) -> tuple[PlayerCommand, Vec2, PlayerCommand]:
        intelligence = player.effective_intelligence
        conservation = player.stamina_conservation
        attacking_progress = clamp(self.team_progress(player.team, player.pos.x), 0.0, 1.0)
        goal_urgency, _ = self.goal_event_urgency(player.team, owner.pos, player)
        effective_conservation = conservation * (1.0 - goal_urgency * 0.92)
        support_rank, friendly_congestion = self.attacking_support_context(player, owner)
        stale_possession = clamp((self.possession_stagnation - 1.2) / 4.8, 0.0, 1.0)
        side = -1.0 if player.grid_x <= 8 else 1.0
        if support_rank == 1:
            side *= -1.0
        support_radius = 58 if support_rank == 0 else 92 + min(4, support_rank) * 12
        support_target = owner.pos + Vec2(
            -player.team.direction * support_radius,
            side * (54 + min(3, support_rank) * 18),
        )
        triangle_radius = 82 if support_rank <= 1 else 116 + min(4, support_rank) * 10
        triangle_target = owner.pos + Vec2(
            -player.team.direction * triangle_radius,
            side * (96 + min(3, support_rank) * 16),
        )
        support_marginal, support_occupancy = self.support_location_value(player, owner, support_target)
        triangle_marginal, triangle_occupancy = self.support_location_value(player, owner, triangle_target)
        if (
            player.can_consider_skill(BACKLINE_HUNTER)
            and player.role in ("FW", "MF")
            and attacking_progress >= 0.54
        ):
            opponents = [
                opponent for team in self.teams if team is not player.team
                for opponent in team.players if not opponent.sent_off
            ]
            marker = min(opponents, key=lambda opponent: opponent.pos.distance_squared_to(player.pos))
            behind_marker = marker.pos + Vec2(player.team.direction * (38 + player.goal_poaching * 48), 0)
            shadow_situation = clamp((attacking_progress - 0.48) * 1.5, 0.0, 1.0)
            shadow_situation += clamp((110 - player.pos.distance_to(marker.pos)) / 220.0, 0.0, 0.34)
            shadow_execution = self.behavior_quality(player, "lose_mark", player.shooting_technique)
            if self.try_activate_player_skill(
                player,
                BACKLINE_HUNTER,
                shadow_situation,
                shadow_execution,
                duration=1.15,
            ):
                behind_marker.y += (-1 if player.grid_x <= 8 else 1) * 34
                player.shadow_striker_timer = 3.0
                behind_marker.x = clamp(behind_marker.x, FIELD.left + 20, FIELD.right - 20)
                behind_marker.y = clamp(behind_marker.y, FIELD.top + 24, FIELD.bottom - 24)
                return PlayerCommand.SKILL_BACKLINE_HUNTER, behind_marker, PlayerCommand.DASH

        if player.can_consider_skill(OVERLOAD):
            numerical_target = self.open_space_target(player, shape, 82)
            nearby_friends = sum(
                teammate.pos.distance_to(numerical_target) < 150
                for teammate in player.team.players if teammate is not player and not teammate.sent_off
            )
            nearby_opponents = sum(
                opponent.pos.distance_to(numerical_target) < 150
                for team in self.teams if team is not player.team
                for opponent in team.players if not opponent.sent_off
            )
            number_edge = nearby_friends - nearby_opponents
        else:
            numerical_target = shape
            number_edge = -1
        if number_edge >= 1:
            numerical_execution = self.behavior_quality(player, "support", player.passing_technique)
            if self.try_activate_player_skill(
                player,
                OVERLOAD,
                0.38 + min(3, number_edge) * 0.16,
                numerical_execution,
                duration=1.05,
            ):
                return PlayerCommand.SKILL_OVERLOAD, numerical_target, PlayerCommand.WALK
        qualities = {
            PlayerCommand.SUPPORT: self.behavior_quality(player, "support", player.passing_technique),
            PlayerCommand.TRIANGLE_SUPPORT: self.behavior_quality(player, "triangle", player.passing_technique),
            PlayerCommand.LOSE_MARK: self.behavior_quality(player, "lose_mark", player.dash_speed),
            PlayerCommand.OVERLAP: self.behavior_quality(player, "overlap", player.dash_speed),
            PlayerCommand.DIAGONAL_RUN: self.behavior_quality(player, "diagonal_run", player.dash_speed),
            PlayerCommand.RUN_INTO_SPACE: self.behavior_quality(player, "run_into_space", player.dash_speed),
            PlayerCommand.WAIT_IN_FRONT_OF_GOAL: self.behavior_quality(player, "goal_poaching", player.shooting_technique),
        }
        utilities = {
            command: 0.18 + quality * 0.76 for command, quality in qualities.items()
        }
        if player.role == "DF":
            utilities[PlayerCommand.SUPPORT] += 0.16
            utilities[PlayerCommand.OVERLAP] -= 0.10
            utilities[PlayerCommand.WAIT_IN_FRONT_OF_GOAL] -= 0.42
        elif player.role == "FW":
            utilities[PlayerCommand.WAIT_IN_FRONT_OF_GOAL] += 0.22
            utilities[PlayerCommand.RUN_INTO_SPACE] += 0.14
        # Support remains valuable, but its marginal value falls as teammates
        # occupy or commit to the same location. Empty alternative lanes gain the
        # displaced value instead of applying a fixed supporter count.
        utilities[PlayerCommand.SUPPORT] += support_marginal
        utilities[PlayerCommand.TRIANGLE_SUPPORT] += triangle_marginal
        duplicate_pressure = max(support_occupancy, triangle_occupancy)
        redistribute = clamp(
            duplicate_pressure * 0.34 + friendly_congestion * 0.20 + stale_possession * 0.30,
            0.0, 0.78,
        )
        utilities[PlayerCommand.RUN_INTO_SPACE] += redistribute * 0.46
        utilities[PlayerCommand.DIAGONAL_RUN] += redistribute * 0.38
        utilities[PlayerCommand.LOSE_MARK] += redistribute * 0.28
        if player.role in ("MF", "DF"):
            utilities[PlayerCommand.OVERLAP] += redistribute * 0.22
        if goal_urgency > 0.0:
            utilities[PlayerCommand.RUN_INTO_SPACE] += goal_urgency * (0.28 + intelligence * 0.20)
            utilities[PlayerCommand.LOSE_MARK] += goal_urgency * 0.24
            utilities[PlayerCommand.WAIT_IN_FRONT_OF_GOAL] += goal_urgency * 0.26
            utilities[PlayerCommand.SUPPORT] += goal_urgency * 0.12
        if abs(shape.y - self.ball.pos.y) > 145:
            utilities[PlayerCommand.DIAGONAL_RUN] += 0.12
            utilities[PlayerCommand.RUN_INTO_SPACE] += 0.08
        for command in (
            PlayerCommand.LOSE_MARK,
            PlayerCommand.OVERLAP,
            PlayerCommand.DIAGONAL_RUN,
            PlayerCommand.RUN_INTO_SPACE,
        ):
            utilities[command] -= effective_conservation * 0.48
        utilities[PlayerCommand.SUPPORT] += effective_conservation * 0.18
        utilities[PlayerCommand.TRIANGLE_SUPPORT] += effective_conservation * 0.20
        command = choose_utility_action(utilities, intelligence, self.rng)
        if command is PlayerCommand.SUPPORT:
            target = support_target
        elif command is PlayerCommand.TRIANGLE_SUPPORT:
            target = triangle_target
        elif command is PlayerCommand.LOSE_MARK:
            opponents = [opponent for team in self.teams if team is not player.team for opponent in team.players if not opponent.sent_off]
            marker = min(opponents, key=lambda opponent: opponent.pos.distance_squared_to(player.pos))
            escape = safe_normalize(player.pos - marker.pos)
            target = shape + escape * (48 + qualities[command] * 58) + Vec2(player.team.direction * 34, 0)
        elif command is PlayerCommand.OVERLAP:
            target = Vec2(
                max(shape.x, owner.pos.x + 88) if player.team.direction == 1 else min(shape.x, owner.pos.x - 88),
                shape.y,
            )
        elif command is PlayerCommand.DIAGONAL_RUN:
            target = player.pos + Vec2(player.team.direction * 112, side * -104)
        elif command is PlayerCommand.RUN_INTO_SPACE:
            target = self.open_space_target(player, shape, 112)
        else:
            goal_x = FIELD.right if player.team.direction == 1 else FIELD.left
            target = Vec2(goal_x - player.team.direction * (76 + (1.0 - qualities[command]) * 58), FIELD.centery + side * 72)
        quality = qualities[command]
        target += player.roam * (1.0 - quality) * 0.22
        target = self.spread_attacking_target(
            player, owner, target, support_rank, friendly_congestion,
        )
        intense = command in (
            PlayerCommand.LOSE_MARK,
            PlayerCommand.OVERLAP,
            PlayerCommand.DIAGONAL_RUN,
            PlayerCommand.RUN_INTO_SPACE,
        )
        locomotion = PlayerCommand.DASH if intense and player.can_dash(command, emergency=goal_urgency > 0.48) else PlayerCommand.WALK
        return command, target, locomotion

    def choose_defensive_action(
        self,
        player: Player,
        shape: Vec2,
        owner: Player,
        is_presser: bool,
        press_allowed: bool,
        pressure_rank: dict[Player, int] | None = None,
    ) -> tuple[PlayerCommand, Vec2, PlayerCommand]:
        intelligence = player.effective_intelligence
        zone = self.behavior_quality(player, "zone_marking", player.physical_play_quality)
        man = self.behavior_quality(player, "man_marking", player.steal_technique)
        press = self.behavior_quality(player, "pressing", player.steal_technique)
        block = self.behavior_quality(player, "shot_blocking", player.pass_interception)
        intercept = self.behavior_quality(player, "interception", player.pass_interception)
        marked_opponent = self.most_alert_opponent(player, owner)
        alertness = player.alertness_for(marked_opponent)
        danger = clamp((0.58 - self.team_progress(player.team, owner.pos.x)) / 0.45, 0.0, 1.0)
        distance = player.pos.distance_to(owner.pos)
        _, direct_goal_danger = self.goal_event_urgency(player.team, owner.pos, player)
        goal_emergency = max(danger, direct_goal_danger)
        if (
            player.can_consider_skill(VACANT_COVER)
            and player.role in ("DF", "MF")
        ):
            vacancies = []
            for teammate in player.team.players:
                if teammate is player or teammate.is_keeper or teammate.sent_off:
                    continue
                teammate_shape = self.shape_position(teammate, False)
                displacement = teammate.pos.distance_to(teammate_shape)
                cover_distance = player.pos.distance_to(teammate_shape)
                if displacement > 180 and cover_distance < 220:
                    vacancies.append((displacement - cover_distance * 0.35, teammate_shape, displacement, cover_distance))
            if vacancies:
                _, vacancy, displacement, cover_distance = max(vacancies, key=lambda item: item[0])
                cover_execution = self.behavior_quality(player, "zone_marking")
                if self.try_activate_player_skill(
                    player,
                    VACANT_COVER,
                    clamp(0.30 + (displacement - 180) / 300.0 + (220 - cover_distance) / 550.0, 0.30, 0.76),
                    cover_execution,
                    duration=1.0,
                ):
                    return PlayerCommand.SKILL_VACANT_COVER, vacancy, PlayerCommand.DASH if player.can_dash(PlayerCommand.COVER) else PlayerCommand.WALK

        owner_has_passed = (owner.pos.x - player.pos.x) * owner.team.direction > 24
        if player.can_consider_skill(RECOVERY_CHASE) and owner_has_passed and distance < 145:
            chase_execution = blended_judgment(
                player.effective_stat(player.dash_speed),
                player.effective_intelligence,
                0.70,
            )
            if self.try_activate_player_skill(player, RECOVERY_CHASE, 0.48 + (145 - distance) / 330.0, chase_execution, duration=1.15):
                player.chasing_timer = 1.15
                return PlayerCommand.SKILL_RECOVERY_CHASE, Vec2(owner.pos), PlayerCommand.DASH

        if player.can_consider_skill(ONE_WAY_BLOCK) and is_presser and distance < 112:
            cut_execution = self.behavior_quality(player, "man_marking", player.steal_technique)
            if self.try_activate_player_skill(
                player,
                ONE_WAY_BLOCK,
                0.36 + (112 - distance) / 190.0,
                cut_execution,
                duration=0.92,
            ):
                player.one_side_cut_timer = 0.92
                cut_side = -1.0 if owner.pos.y < FIELD.centery else 1.0
                cut_target = owner.pos + Vec2(owner.team.direction * 24, cut_side * 28)
                return PlayerCommand.SKILL_ONE_WAY_BLOCK, cut_target, PlayerCommand.DASH if player.can_dash(PlayerCommand.PRESS) else PlayerCommand.WALK
        utilities = {
            PlayerCommand.COVER: 0.26 + zone * 0.72,
            PlayerCommand.MARK: 0.24 + man * 0.64 + alertness * 0.18,
            PlayerCommand.PRESS: 0.16 + press * 0.78 + (0.36 if is_presser and press_allowed else -0.24) + danger * 0.15,
            PlayerCommand.BLOCK_SHOT: 0.10 + block * 0.64 + danger * 0.38,
            PlayerCommand.INTERCEPT_PASS: 0.16 + intercept * 0.72 + (0.08 if is_presser else 0.0),
        }
        if goal_emergency > 0.35:
            close_enough = clamp(1.15 - distance / 460.0, 0.0, 1.0)
            utilities[PlayerCommand.BLOCK_SHOT] += goal_emergency * (0.38 + close_enough * 0.34)
            utilities[PlayerCommand.PRESS] += goal_emergency * close_enough * 0.42
            utilities[PlayerCommand.COVER] -= goal_emergency * 0.16
            utilities[PlayerCommand.MARK] -= goal_emergency * 0.08
        utilities[PlayerCommand.PRESS] -= clamp(distance / 520.0, 0.0, 0.28)
        if player.stamina_conservation > 0.0:
            conservation = player.stamina_conservation * (1.0 - goal_emergency * 0.94)
            utilities[PlayerCommand.PRESS] -= conservation * 0.22
            utilities[PlayerCommand.COVER] += conservation * 0.16
        command = choose_utility_action(utilities, intelligence, self.rng)
        if (
            command is PlayerCommand.PRESS
            and player.can_consider_skill(RELENTLESS_PRESS)
            and distance < 155
        ):
            press_execution = blended_judgment(
                press * 0.58 + player.effective_stat(player.steal_technique) * 0.42,
                intelligence,
                0.72,
            )
            if self.try_activate_player_skill(
                player,
                RELENTLESS_PRESS,
                0.36 + press * 0.34 + clamp((155 - distance) / 240.0, 0.0, 0.24),
                press_execution,
                duration=0.95,
            ):
                player.demon_press_timer = 0.95
                command = PlayerCommand.SKILL_RELENTLESS_PRESS
        own_goal = Vec2(FIELD.left if player.team.direction == 1 else FIELD.right, FIELD.centery)
        if command is PlayerCommand.COVER:
            target = shape
            locomotion = PlayerCommand.WALK
        elif command is PlayerCommand.MARK:
            target = marked_opponent.pos + safe_normalize(own_goal - marked_opponent.pos) * (32 + man * 34)
            target = shape.lerp(target, 0.46 + man * 0.36)
            locomotion = PlayerCommand.WALK
        elif command in (PlayerCommand.PRESS, PlayerCommand.SKILL_RELENTLESS_PRESS):
            if pressure_rank is None:
                pressure_ranked = sorted(
                    [candidate for candidate in player.team.players if not candidate.is_keeper and not candidate.sent_off],
                    key=lambda candidate: candidate.pos.distance_squared_to(owner.pos),
                )
                player_pressure_rank = pressure_ranked.index(player) if player in pressure_ranked else len(pressure_ranked)
            else:
                player_pressure_rank = pressure_rank.get(player, len(pressure_rank))
            target = owner.pos + owner.motion_velocity * (0.04 + press * 0.10)
            if player_pressure_rank > 0:
                side = -1.0 if (player.grid_x + player_pressure_rank) % 2 else 1.0
                stale = clamp((self.possession_stagnation - 1.0) / 4.0, 0.0, 1.0)
                target += Vec2(
                    -owner.team.direction * (18 + min(3, player_pressure_rank) * 9),
                    side * (34 + min(3, player_pressure_rank) * 15 + stale * 20),
                )
            locomotion = PlayerCommand.DASH
        elif command is PlayerCommand.BLOCK_SHOT:
            target = owner.pos.lerp(own_goal, clamp(0.12 + block * 0.15, 0.12, 0.27))
            locomotion = PlayerCommand.DASH if danger > 0.58 else PlayerCommand.WALK
        else:
            target = self.defensive_intercept_target(player, owner)
            locomotion = PlayerCommand.DASH
        if not player.can_dash(command, emergency=goal_emergency > 0.46):
            locomotion = PlayerCommand.WALK
        target.x = clamp(target.x, FIELD.left + 20, FIELD.right - 20)
        target.y = clamp(target.y, FIELD.top + 20, FIELD.bottom - 20)
        return command, target, locomotion

    def choose_owner_carry_skill(
        self,
        player: Player,
        nearest_opponent: Player,
        opponent_distance: float,
    ) -> tuple[PlayerCommand, Vec2, PlayerCommand] | None:
        side = 1.0 if player.pos.y <= FIELD.centery else -1.0
        opponent_goal_x = FIELD.right if player.team.direction == 1 else FIELD.left
        goal_line_distance = abs(opponent_goal_x - player.pos.x)
        if goal_line_distance < 72:
            # Do not keep pushing against the end line and drift into a corner.
            # Turn back into the field and angle toward the mouth of the goal;
            # the decision pass below can then shoot or cut the ball back.
            inward_y = clamp(FIELD.centery - player.pos.y, -105, 105)
            target = Vec2(
                player.pos.x - player.team.direction * (34 + (72 - goal_line_distance) * 0.34),
                player.pos.y + inward_y * 0.62,
            )
            return PlayerCommand.DRIBBLE, target, PlayerCommand.WALK
        if player.tricky_feint_timer > 0.0:
            target = player.pos + player.tricky_feint_direction * 82
            return PlayerCommand.SKILL_ILLUSION_STEP, target, PlayerCommand.WALK
        if player.cruyff_timer > 0.0:
            target = player.pos + player.cruyff_direction * 72
            return PlayerCommand.SKILL_HEEL_REVERSE_TURN, target, PlayerCommand.WALK
        if player.post_play_timer > 0.0:
            target = player.pos + Vec2(-player.team.direction * 26, side * 18)
            return PlayerCommand.SKILL_PIVOT_KEEP, target, PlayerCommand.WALK
        if player.razor_dribble_timer > 0.0:
            target = player.pos + Vec2(player.team.direction * 76, side * 22)
            return PlayerCommand.SKILL_TIGHT_TOUCH, target, PlayerCommand.WALK
        if player.high_speed_dribble_timer > 0.0:
            target = self.open_space_target(player, player.pos, 138)
            return PlayerCommand.SKILL_SPRINT_CARRY, target, PlayerCommand.DASH
        if player.toughness_dynamo_timer > 0.0:
            target = player.pos + Vec2(player.team.direction * 82, side * 20)
            locomotion = PlayerCommand.DASH if player.can_dash(PlayerCommand.DRIBBLE) else PlayerCommand.WALK
            return PlayerCommand.SKILL_ENERGY_KEEP, target, locomotion
        if player.skill_command is not PlayerCommand.IDLE:
            return None

        intelligence = player.effective_intelligence
        dribble_skills = {
            skill for skill in (ILLUSION_STEP, HEEL_REVERSE_TURN, TIGHT_TOUCH, SPRINT_CARRY, ENERGY_KEEP)
            if player.can_consider_skill(skill)
        }
        post_ready = player.can_consider_skill(PIVOT_KEEP)
        if not dribble_skills and not post_ready:
            return None
        dribbling = (
            blended_judgment(
                player.effective_stat(player.dribble_technique),
                intelligence,
                0.72,
            )
            if dribble_skills
            else 0.0
        )
        passing = (
            blended_judgment(
                player.effective_stat(player.passing_technique),
                intelligence,
                0.70,
            )
            if post_ready
            else 0.0
        )
        options: dict[str, float] = {}
        if ILLUSION_STEP in dribble_skills and 18 < opponent_distance < 92:
            options[ILLUSION_STEP] = 0.38 + dribbling * 0.40 + player.confidence * 0.16
        if HEEL_REVERSE_TURN in dribble_skills and 22 < opponent_distance < 76:
            options[HEEL_REVERSE_TURN] = 0.42 + dribbling * 0.34 + clamp((76 - opponent_distance) / 110.0, 0.0, 0.22)
        if post_ready and opponent_distance < 64:
            options[PIVOT_KEEP] = 0.38 + passing * 0.32 + player.effective_stat(player.dribble_physical) * 0.22
        if TIGHT_TOUCH in dribble_skills and opponent_distance < 92:
            options[TIGHT_TOUCH] = 0.34 + dribbling * 0.46
        if SPRINT_CARRY in dribble_skills and opponent_distance > 92:
            options[SPRINT_CARRY] = 0.31 + dribbling * 0.31 + clamp((opponent_distance - 92) / 240.0, 0.0, 0.24)
        if ENERGY_KEEP in dribble_skills and player.stamina_conservation > 0.18:
            options[ENERGY_KEEP] = 0.26 + player.stamina_conservation * 0.52 + dribbling * 0.18
        if not options:
            return None
        selected = choose_utility_action(options, intelligence, self.rng)
        execution = dribbling if selected not in (PIVOT_KEEP, ENERGY_KEEP) else (passing if selected == PIVOT_KEEP else player.effective_stat(player.stamina_management))
        if not self.try_activate_player_skill(player, selected, options[selected], execution, duration=1.05):
            return None
        if selected == ILLUSION_STEP:
            escape_side = safe_normalize(player.pos - nearest_opponent.pos)
            player.tricky_feint_direction = safe_normalize(
                Vec2(player.team.direction, side * 0.78) + escape_side * 0.72
            )
            player.tricky_feint_timer = 0.82
        elif selected == HEEL_REVERSE_TURN:
            escape_side = safe_normalize(player.pos - nearest_opponent.pos)
            player.cruyff_direction = safe_normalize(escape_side + Vec2(-player.team.direction * 0.85, side * 0.45))
            player.cruyff_timer = 0.72
        elif selected == PIVOT_KEEP:
            player.post_play_timer = 0.92
        elif selected == TIGHT_TOUCH:
            player.razor_dribble_timer = 1.0
        elif selected == SPRINT_CARRY:
            player.high_speed_dribble_timer = 1.15
        elif selected == ENERGY_KEEP:
            player.toughness_dynamo_timer = 2.4
        return self.choose_owner_carry_skill(player, nearest_opponent, opponent_distance)

    def enforce_goal_line_cutback(self) -> None:
        """Remove a stale forward/corner target after tackles or collisions."""
        owner = self.ball.owner
        if owner is None or owner.is_keeper or self.pending_kick is not None:
            return
        opponent_goal_x = FIELD.right if owner.team.direction == 1 else FIELD.left
        goal_line_distance = abs(opponent_goal_x - owner.pos.x)
        if goal_line_distance >= 72:
            return
        target_forward = (owner.target.x - owner.pos.x) * owner.team.direction > 1.0
        target_wider = abs(owner.target.y - FIELD.centery) > abs(owner.pos.y - FIELD.centery) + 1.0
        if not target_forward and not target_wider:
            return
        inward_y = clamp(FIELD.centery - owner.pos.y, -105, 105)
        cutback = Vec2(
            owner.pos.x - owner.team.direction * (34 + (72 - goal_line_distance) * 0.34),
            owner.pos.y + inward_y * 0.62,
        )
        owner.target.update(cutback)
        owner.issue_action(PlayerCommand.DRIBBLE, cutback, duration=0.12, force=True)
        self.decision_timer = min(self.decision_timer, 0.035)

    def update_player_movement(self, dt: float) -> None:
        # Shared values are valid for this 0.05-second physics step.  Caching
        # also makes all players evaluate the same team shape snapshot instead
        # of gaining an ordering advantage inside the loop.
        owner = self.ball.owner
        shared_context_expiry = getattr(self, "_shared_movement_context_expiry", -1.0)
        shared_context_owner = getattr(self, "_shared_movement_context_owner", None)
        refresh_shared_context = (
            self.simulation_elapsed >= shared_context_expiry
            or owner is not shared_context_owner
        )
        if refresh_shared_context:
            # Formation and broad pressure ordering do not need 20 Hz precision.
            # A 0.10-second snapshot is short enough to remain visually smooth,
            # while immediate ball, collision and scoring checks still run at 20 Hz.
            self._shape_position_cache = {}
            self._support_context_cache = {}
            self._pressure_context_cache = {}
            self._shared_movement_context_expiry = self.simulation_elapsed + 0.10
            self._shared_movement_context_owner = owner
        self._movement_goal_urgency_cache = {}
        pressure_context_cache = getattr(self, "_pressure_context_cache", {})
        for team in self.teams:
            outfield = [player for player in team.players if not player.is_keeper and not player.sent_off]
            if not outfield:
                continue
            cached_pressure = pressure_context_cache.get(team)
            if cached_pressure is None:
                pressure_order = sorted(
                    outfield,
                    key=lambda player: (
                        player.pos.distance_to(self.ball.pos)
                        / max(0.55, 0.72 + player.effective_stat(player.dash_speed) * 0.58)
                        - player.pressing * 92
                        - (player.alertness_for(owner) * 74 if owner is not None and owner.team is not team else 0.0)
                    ),
                )
                distance_pressure_rank = {
                    player: index
                    for index, player in enumerate(
                        sorted(
                            outfield,
                            key=lambda candidate: candidate.pos.distance_squared_to(
                                owner.pos if owner is not None else self.ball.pos
                            ),
                        )
                    )
                }
                pressure_context_cache[team] = (pressure_order, distance_pressure_rank)
            else:
                pressure_order, distance_pressure_rank = cached_pressure
            nearest = pressure_order[0]
            owner_team = owner.team if owner else None
            ball_progress = clamp(self.team_progress(team, self.ball.pos.x), 0.0, 1.0)
            settings = team.tactical_settings(nearest)
            press_count = max(2, int(settings["pressers"]))
            if owner_team is not None and owner_team is not team and ball_progress < 0.46:
                press_count = max(press_count, 3)
            pressing_players = pressure_order[:min(4, press_count)]
            press_limit = clamp(max(0.78, settings["press_trigger"] + 0.18), 0.0, 0.96)
            press_allowed = ball_progress <= press_limit
            tackle_recovery = (
                owner is None
                and self.ball.recovery_timer > 0.0
                and self.ball.recovery_team is team
            )
            recovery_runners = pressure_order[:2] if tackle_recovery else []
            attacking_goal_urgency, defending_goal_urgency = self.goal_event_urgency(team)
            loose_goal_urgency = max(attacking_goal_urgency, defending_goal_urgency) if owner is None else 0.0
            goal_runners: set[Player] = set()
            if loose_goal_urgency > 0.18:
                def goal_rush_score(candidate: Player) -> float:
                    arrival = candidate.pos.distance_to(self.ball.pos) / max(
                        45.0,
                        movement_speed(PlayerCommand.DASH, candidate.effective_stat(candidate.dash_speed)),
                    )
                    if defending_goal_urgency >= attacking_goal_urgency:
                        specialist = (
                            candidate.effective_stat(candidate.shot_blocking) * 0.52
                            + candidate.effective_stat(candidate.steal_technique) * 0.48
                        )
                        role_bonus = 0.22 if candidate.role == "DF" else 0.08 if candidate.role == "MF" else 0.0
                    else:
                        specialist = (
                            candidate.effective_stat(candidate.shooting_technique) * 0.58
                            + candidate.effective_stat(candidate.goal_poaching) * 0.42
                        )
                        role_bonus = 0.22 if candidate.role == "FW" else 0.09 if candidate.role == "MF" else 0.0
                    judgment = blended_judgment(specialist, candidate.effective_intelligence, 0.68)
                    return arrival - judgment * 0.42 - role_bonus

                runner_count = 3 if loose_goal_urgency > 0.58 else 2
                goal_runners = set(sorted(outfield, key=goal_rush_score)[:runner_count])
            intercept_targets: dict[Player, Vec2] = {}
            if owner is None and self.ball.intended and self.ball.intended.team is not team and self.ball.vel.length() > 55:
                intercept_candidates = []
                flight_direction = safe_normalize(self.ball.vel)
                for candidate in outfield:
                    interception = candidate.effective_stat(candidate.pass_interception)
                    intelligence = candidate.effective_intelligence
                    behavior = candidate.effective_stat(candidate.interception)
                    reading = blended_judgment(interception * 0.62 + behavior * 0.38, intelligence, 0.70)
                    future_ball = self.ball.pos + flight_direction * (42 + reading * 112)
                    distance_to_lane = candidate.pos.distance_to(future_ball)
                    if distance_to_lane <= interception_reach(reading):
                        intercept_candidates.append((distance_to_lane - reading * 82, candidate, future_ball, reading))
                intercept_candidates.sort(key=lambda item: item[0])
                max_interceptors = 2 if intercept_candidates and intercept_candidates[0][3] >= 0.72 else 1
                for _, candidate, future_ball, _ in intercept_candidates[:max_interceptors]:
                    intercept_targets[candidate] = future_ball
            if (
                owner_team is not None
                and owner_team is not team
                and self.catenaccio_timer[team] <= 0.0
                and self.catenaccio_cooldown[team] <= 0.0
            ):
                callers = [
                    player for player in outfield
                    if player.has_skill(FORTRESS_BLOCK)
                    and player.skill_cooldowns.get(FORTRESS_BLOCK, 0.0) <= 0.0
                    and player.skill_command is PlayerCommand.IDLE
                ]
                if callers:
                    caller = max(
                        callers,
                        key=lambda candidate: blended_judgment(
                            candidate.effective_stat(candidate.physical_play_quality),
                            candidate.effective_intelligence,
                            0.52,
                        ),
                    )
                    defensive_danger = clamp((0.62 - ball_progress) / 0.50, 0.0, 1.0)
                    defensive_execution = blended_judgment(
                        (caller.effective_stat(caller.steal_technique) + caller.effective_stat(caller.physical_play_quality)) * 0.5,
                        caller.effective_intelligence,
                        0.64,
                    )
                    activated = self.try_activate_player_skill(
                        caller,
                        FORTRESS_BLOCK,
                        0.22 + defensive_danger * 0.66,
                        defensive_execution,
                        duration=3.2,
                    )
                    self.catenaccio_cooldown[team] = 15.0 if activated else 2.0
                    if activated:
                        self.catenaccio_timer[team] = 5.0
            for player in team.players:
                if player.sent_off:
                    player.motion_velocity.update(0, 0)
                    continue
                previous_position = Vec2(player.pos)
                player.tick_commands(dt)
                player.update_roaming(dt, owner_team is team)
                player.ai_rethink_timer = max(0.0, player.ai_rethink_timer - dt)
                action = PlayerCommand.HOLD_POSITION
                locomotion = PlayerCommand.WALK
                ball_distance = player.pos.distance_to(self.ball.pos)
                player_attack_urgency, player_defense_urgency = self.goal_event_urgency(team, player=player)
                player_goal_urgency = max(player_attack_urgency, player_defense_urgency)
                if player.relax_timer > 0.0 and (ball_distance < 250 or player_goal_urgency > 0.16):
                    player.relax_timer = 0.0
                    if player.skill_command is PlayerCommand.SKILL_COOLDOWN_REST:
                        player.skill_command = PlayerCommand.IDLE
                        player.skill_timer = 0.0
                if (
                    not player.is_keeper
                    and player is not owner
                    and player.relax_timer <= 0.0
                    and player.skill_command is PlayerCommand.IDLE
                    and player.stamina_conservation > 0.34
                    and ball_distance > 390
                    and player not in pressing_players
                    and player_goal_urgency < 0.16
                ):
                    relax_execution = blended_judgment(
                        player.effective_stat(player.stamina_management),
                        player.effective_intelligence,
                        0.64,
                    )
                    if self.try_activate_player_skill(
                        player,
                        COOLDOWN_REST,
                        0.34 + player.stamina_conservation * 0.52,
                        relax_execution,
                        duration=3.2,
                    ):
                        player.relax_timer = 3.2
                if player.knockback_timer > 0.0:
                    player.target.update(player.pos + player.knockback_velocity * 0.08)
                    action = PlayerCommand.STAGGER
                    locomotion = PlayerCommand.IDLE
                elif player.fallen_timer > 0.0 and not player.airborne:
                    player.target.update(player.pos)
                    action = PlayerCommand.HOLD_POSITION
                    locomotion = PlayerCommand.IDLE
                elif player.relax_timer > 0.0:
                    player.target.update(player.pos)
                    action = PlayerCommand.SKILL_COOLDOWN_REST
                    locomotion = PlayerCommand.IDLE
                elif player.slide_active:
                    player.target.update(player.pos + player.slide_direction * 40)
                    action = self.pending_kick.command if self.pending_kick and self.pending_kick.player is player else PlayerCommand.SLIDE_TACKLE
                    locomotion = PlayerCommand.IDLE
                elif self.pending_kick and self.pending_kick.player is player:
                    player.target.update(player.pos)
                    action = self.pending_kick.command
                    locomotion = PlayerCommand.IDLE
                elif player.airborne and player.action_command in (
                    PlayerCommand.HEADER,
                    PlayerCommand.SKILL_AERIAL_HEADER,
                    PlayerCommand.SKILL_OVERHEAD_VOLLEY,
                    PlayerCommand.INTERCEPT_PASS,
                    PlayerCommand.BLOCK_SHOT,
                    PlayerCommand.SAVE,
                    PlayerCommand.SKILL_EARLY_READ_SAVE,
                ):
                    player.target.update(player.command_target)
                    action = player.action_command
                    locomotion = PlayerCommand.WALK
                elif player.is_keeper:
                    goal_x = FIELD.left + 24 if team.direction == 1 else FIELD.right - 24
                    goal_center = Vec2(goal_x, FIELD.centery)
                    patrol_depth = clamp(
                        46 + ball_progress * (PENALTY_AREA_DEPTH * 0.48)
                        + (30 if owner_team is team else 0),
                        42,
                        PENALTY_AREA_DEPTH * 0.68,
                    )
                    patrol_target = self.clamp_to_goalkeeper_area(
                        team,
                        (
                            goal_x + team.direction * patrol_depth,
                            FIELD.centery + (self.ball.pos.y - FIELD.centery) * 0.56,
                        ),
                    )
                    incoming_shot = (
                        owner is None
                        and self.ball_is_shot()
                        and self.ball.vel.x * team.direction < 0
                    )
                    if incoming_shot:
                        self.prepare_keeper_read(player)
                    safe_attack, attack_situation = self.keeper_attack_is_safe(player)
                    if not safe_attack:
                        player.keeper_attack_timer = 0.0
                    elif player.keeper_attack_timer <= 0.0 and player.skill_command is PlayerCommand.IDLE:
                        attack_execution = blended_judgment(
                            player.effective_stat(player.passing_technique) * 0.44
                            + player.effective_stat(player.goal_stopping) * 0.24
                            + player.position_awareness * 0.32,
                            player.effective_intelligence,
                            0.78,
                        )
                        if self.try_activate_player_skill(
                            player,
                            SWEEPER_KEEPER,
                            attack_situation,
                            attack_execution,
                            duration=4.5,
                        ):
                            player.keeper_attack_timer = 4.5
                    if player.super_save_timer > 0.0 and incoming_shot:
                        player.target.update(goal_x, player.keeper_read_y)
                        action = PlayerCommand.SKILL_EARLY_READ_SAVE
                        locomotion = PlayerCommand.DASH
                    elif incoming_shot:
                        player.target.update(goal_x, player.keeper_read_y)
                        action = PlayerCommand.SAVE
                        locomotion = PlayerCommand.DASH if player.can_dash(action, emergency=True) else PlayerCommand.WALK
                    elif owner is player:
                        # A keeper with the ball remains inside the area while the
                        # distribution utility chooses a throw, short kick or punt.
                        player.target.update(self.clamp_to_goalkeeper_area(team, player.pos))
                        action = PlayerCommand.HOLD_POSITION
                        locomotion = PlayerCommand.WALK
                    elif owner is None and self.point_in_own_penalty_area(team, self.ball.pos):
                        # Chase the predicted meeting point instead of waiting on
                        # the goal line for a loose ball to arrive.
                        prediction_time = clamp(player.pos.distance_to(self.ball.pos) / 520.0, 0.05, 0.32)
                        predicted = self.ball.pos + self.ball.vel * prediction_time
                        player.target.update(self.clamp_to_goalkeeper_area(team, predicted, inset=7.0))
                        action = PlayerCommand.RECOVER_LOOSE_BALL
                        locomotion = PlayerCommand.DASH if player.can_dash(action, emergency=player_defense_urgency > 0.34) else PlayerCommand.WALK
                    elif owner is not None and owner.team is not team and self.point_in_own_penalty_area(team, owner.pos, margin=26):
                        # Close the angle inside the box while leaving a small
                        # cushion so the keeper does not run through the attacker.
                        approach = goal_center.lerp(owner.pos, 0.78)
                        retreat = safe_normalize(goal_center - owner.pos) * 18
                        player.target.update(self.clamp_to_goalkeeper_area(team, approach + retreat, inset=7.0))
                        action = PlayerCommand.GUARD_GOAL
                        locomotion = PlayerCommand.DASH if player.can_dash(action) else PlayerCommand.WALK
                    elif player.keeper_attack_timer > 0.0 and safe_attack:
                        attack_progress = min(0.40, max(0.22, ball_progress - 0.28))
                        player.target.update(
                            self.progress_to_world_x(team, attack_progress),
                            clamp(FIELD.centery + (self.ball.pos.y - FIELD.centery) * 0.34, FIELD.centery - 150, FIELD.centery + 150),
                        )
                        action = PlayerCommand.SKILL_SWEEPER_KEEPER
                        locomotion = PlayerCommand.DASH if player.can_dash(action) else PlayerCommand.WALK
                    else:
                        player.target.update(patrol_target)
                        action = PlayerCommand.GUARD_GOAL
                elif player is owner:
                    opponents = [
                        opponent for opponent in (self.away.players if team is self.home else self.home.players)
                        if not opponent.sent_off
                    ]
                    nearest_opponent = min(opponents, key=lambda opponent: opponent.pos.distance_squared_to(player.pos))
                    opponent_distance = player.pos.distance_to(nearest_opponent.pos)
                    lateral_gap = player.pos.y - nearest_opponent.pos.y
                    if (
                        player.venue_role == "AWAY"
                        and player.steel_heart_timer <= 0.0
                        and player.skill_command is PlayerCommand.IDLE
                    ):
                        mental_execution = blended_judgment(
                            player.effective_stat(player.mental),
                            player.effective_intelligence,
                            0.66,
                        )
                        if self.try_activate_player_skill(
                            player,
                            UNBREAKABLE_HEART,
                            0.42 + (1.0 - player.venue_factor) * 2.4,
                            mental_execution,
                            duration=6.0,
                        ):
                            player.steel_heart_timer = 6.0
                    carry_skill = self.choose_owner_carry_skill(player, nearest_opponent, opponent_distance)
                    if (
                        carry_skill is None
                        and
                        player.roulette_timer <= 0.0
                        and 24 < opponent_distance < 78
                        and player.skill_command is PlayerCommand.IDLE
                    ):
                        dribble_judgment = blended_judgment(
                            player.effective_stat(player.dribble_technique),
                            player.effective_intelligence,
                            0.68,
                        )
                        pressure_quality = clamp((78 - opponent_distance) / 54.0, 0.0, 1.0)
                        if self.try_activate_player_skill(
                            player,
                            SPIN_TURN,
                            0.28 + pressure_quality * 0.62,
                            dribble_judgment,
                            duration=0.72,
                        ):
                            defender_read = blended_judgment(
                                nearest_opponent.effective_stat(nearest_opponent.steal_technique),
                                nearest_opponent.effective_intelligence,
                                0.66,
                            )
                            roulette_success = clamp(
                                0.48 + (dribble_judgment - defender_read) * 0.52 + self.rng.uniform(-0.13, 0.13),
                                0.08,
                                0.98,
                            )
                            side = 1.0 if lateral_gap >= 0 else -1.0
                            if abs(lateral_gap) < 7:
                                side = 1.0 if player.pos.y < FIELD.centery else -1.0
                            roulette_direction = Vec2(team.direction, side * 0.62).normalize()
                            player.start_roulette(roulette_direction, roulette_success)
                    if carry_skill is not None:
                        action, target, locomotion = carry_skill
                        player.target.update(target)
                    elif player.roulette_timer > 0.0:
                        phase = clamp(1.0 - player.roulette_timer / 0.68, 0.0, 1.0)
                        forward = Vec2(team.direction, 0) * (28 + player.roulette_success * 52)
                        lateral = Vec2(0, player.roulette_direction.y) * math.sin(math.pi * phase) * 54
                        player.target.update(player.pos + forward + lateral)
                        player.target.y = clamp(player.target.y, FIELD.top + 30, FIELD.bottom - 30)
                        action = PlayerCommand.SKILL_SPIN_TURN
                        locomotion = PlayerCommand.WALK
                    else:
                        if opponent_distance < 95:
                            avoid_side = 1 if lateral_gap >= 0 else -1
                            if abs(lateral_gap) < 7:
                                avoid_side = 1 if player.pos.y < FIELD.centery else -1
                            protection = dribble_protection(
                                player.effective_stat(player.dribble_physical),
                                player.effective_stat(player.physical_play_quality),
                            )
                            lane_y = player.pos.y + avoid_side * (52 - protection * 32) + player.roam.y * 0.20
                        else:
                            lane_y = player.pos.y + player.roam.y * 0.35
                        lane_y = clamp(lane_y, FIELD.top + 30, FIELD.bottom - 30)
                        carry_distance = 70 + settings["push"] * 28
                        player.target.update(player.pos.x + team.direction * carry_distance, lane_y)
                        action = PlayerCommand.KEEP_BALL if opponent_distance < 60 else PlayerCommand.DRIBBLE
                        locomotion = PlayerCommand.DASH if opponent_distance > 145 and player.can_dash(
                            action,
                            emergency=player_attack_urgency > 0.48,
                        ) else PlayerCommand.WALK
                elif owner is None and self.ball.intended is player:
                    reception_point = Vec2(self.ball.intended_destination)
                    remaining = reception_point - self.ball.pos
                    if remaining.length_squared() < 18 * 18 or remaining.dot(self.ball.vel) <= 0.0:
                        reception_point.update(self.ball.pos)
                    player.target.update(reception_point)
                    action = PlayerCommand.RECEIVE_PASS
                    locomotion = PlayerCommand.DASH
                elif player in intercept_targets:
                    player.target.update(intercept_targets[player])
                    action = PlayerCommand.INTERCEPT_PASS
                    locomotion = PlayerCommand.DASH
                elif owner is None and (player is nearest or player in recovery_runners or player in goal_runners):
                    recovery_lead = 0.08 + player.effective_intelligence * 0.10
                    if player in recovery_runners:
                        recovery_lead = max(recovery_lead, 0.14)
                    player.target.update(self.ball.pos + self.ball.vel * recovery_lead)
                    player.target.x = clamp(player.target.x, FIELD.left + 8, FIELD.right - 8)
                    player.target.y = clamp(player.target.y, FIELD.top + 8, FIELD.bottom - 8)
                    if player_defense_urgency > 0.52 and self.ball_is_shot():
                        action = PlayerCommand.BLOCK_SHOT
                        locomotion = PlayerCommand.DASH if player.can_dash(action, emergency=True) else PlayerCommand.WALK
                    elif player in recovery_runners or player in goal_runners:
                        action = PlayerCommand.RECOVER_LOOSE_BALL
                        locomotion = PlayerCommand.DASH if player.can_dash(
                            action,
                            emergency=player_goal_urgency > 0.34,
                        ) else PlayerCommand.WALK
                    elif self.ball.vel.length() > 60:
                        action = PlayerCommand.FOLLOW_BALL
                        locomotion = PlayerCommand.DASH if player.can_dash(
                            action,
                            emergency=player_goal_urgency > 0.34,
                        ) else PlayerCommand.WALK
                    else:
                        action = PlayerCommand.RECOVER_LOOSE_BALL
                        locomotion = PlayerCommand.WALK
                elif (
                    player.combination_timer > 0.0
                    and player.combination_partner is not None
                    and (
                        (owner is player.combination_partner and owner_team is team)
                        or (owner is None and self.ball.intended is player.combination_partner)
                    )
                ):
                    player.target.update(player.combination_target)
                    action = PlayerCommand.CREATE_PASS_LANE
                    locomotion = (
                        PlayerCommand.DASH
                        if player.combination_quality >= 0.52 and player.can_dash(action)
                        else PlayerCommand.WALK
                    )
                elif owner is not None and owner_team is not team and player in pressing_players and (press_allowed or player is nearest):
                    press_shape = self.shape_position(player, False)
                    action, target, locomotion = self.cached_off_ball_decision(
                        player,
                        ("press", owner, press_allowed or player is nearest),
                        lambda: self.choose_defensive_action(
                            player,
                            press_shape,
                            owner,
                            True,
                            press_allowed or player is nearest,
                            distance_pressure_rank,
                        ),
                    )
                    player.target.update(target)
                else:
                    shape = self.shape_position(player, owner_team is team)
                    player.target.update(shape)
                    if owner_team is team:
                        if owner is not None:
                            action, target, locomotion = self.cached_off_ball_decision(
                                player,
                                ("attack", owner, int(self.possession_stagnation * 2.0)),
                                lambda: self.choose_attacking_run(player, shape, owner),
                            )
                            player.target.update(target)
                        else:
                            action = PlayerCommand.SUPPORT
                    elif owner is not None:
                        action, target, locomotion = self.cached_off_ball_decision(
                            player,
                            ("defend", owner, press_allowed),
                            lambda: self.choose_defensive_action(
                                player,
                                shape,
                                owner,
                                False,
                                press_allowed,
                                distance_pressure_rank,
                            ),
                        )
                        player.target.update(target)
                    else:
                        action = PlayerCommand.RETURN_POSITION

                intense_actions = {
                    PlayerCommand.PRESS,
                    PlayerCommand.INTERCEPT_PASS,
                    PlayerCommand.FOLLOW_BALL,
                    PlayerCommand.RECOVER_LOOSE_BALL,
                    PlayerCommand.CREATE_PASS_LANE,
                    PlayerCommand.OVERLAP,
                    PlayerCommand.LOSE_MARK,
                    PlayerCommand.DIAGONAL_RUN,
                    PlayerCommand.RUN_INTO_SPACE,
                    PlayerCommand.SKILL_RELENTLESS_PRESS,
                }
                if action in intense_actions and not player.airborne and not player.can_use_intense_action():
                    ball_pursuit = action in (
                        PlayerCommand.INTERCEPT_PASS,
                        PlayerCommand.FOLLOW_BALL,
                        PlayerCommand.RECOVER_LOOSE_BALL,
                        PlayerCommand.RECEIVE_PASS,
                    )
                    if player_goal_urgency > 0.34 and player.can_use_intense_action(emergency=True):
                        pass
                    elif not ball_pursuit:
                        player.target.update(self.shape_position(player, owner_team is team))
                        action = PlayerCommand.COVER if owner is not None and owner_team is not team else PlayerCommand.RETURN_POSITION
                        locomotion = PlayerCommand.WALK
                    else:
                        locomotion = PlayerCommand.WALK

                if locomotion is PlayerCommand.DASH and not player.can_dash(
                    action,
                    emergency=player_goal_urgency > 0.34,
                ):
                    locomotion = PlayerCommand.WALK

                movement = player.target - player.pos
                distance = movement.length()
                player.issue_action(action, player.target)
                if player.knockback_timer > 0.0:
                    player.set_movement(PlayerCommand.IDLE)
                    player.pos += player.knockback_velocity * dt
                    player.knockback_velocity *= math.pow(0.08, dt)
                elif player.slide_active:
                    player.set_movement(PlayerCommand.IDLE)
                    slide_speed = 232 - player.slide_progress * 126
                    player.pos += player.slide_direction * slide_speed * dt
                elif player.fallen_timer > 0.0 and not player.airborne:
                    player.set_movement(PlayerCommand.IDLE)
                elif distance > 1.0:
                    if locomotion is PlayerCommand.WALK and distance > 165 and player.can_dash(action):
                        locomotion = PlayerCommand.DASH
                    player.set_movement(locomotion, emergency=player_goal_urgency > 0.34)
                    if player is owner and player.action_command in (
                        PlayerCommand.DRIBBLE,
                        PlayerCommand.KEEP_BALL,
                        PlayerCommand.SKILL_HEEL_REVERSE_TURN,
                        PlayerCommand.SKILL_PIVOT_KEEP,
                        PlayerCommand.SKILL_TIGHT_TOUCH,
                        PlayerCommand.SKILL_SPRINT_CARRY,
                        PlayerCommand.SKILL_ENERGY_KEEP,
                        PlayerCommand.SKILL_ILLUSION_STEP,
                    ):
                        speed = dribble_movement_speed(player.dribble_speed)
                    else:
                        ability = player.dash_speed if player.movement_command is PlayerCommand.DASH else player.walk_speed
                        speed = movement_speed(player.movement_command, ability)
                    speed *= team.tactical_settings(player)["speed"] * player.skill * player.fatigue_factor * player.venue_factor
                    if player.high_speed_dribble_timer > 0.0:
                        speed *= 1.24 + player.effective_stat(player.dribble_speed) * 0.18
                    if player.chasing_timer > 0.0:
                        speed *= 1.26 + player.effective_stat(player.dash_speed) * 0.18
                    if player.demon_press_timer > 0.0:
                        speed *= 1.18 + player.effective_stat(player.dash_speed) * 0.12
                    if self.counterattack_timer.get(team, 0.0) > 0.0 and owner_team is team:
                        speed *= 1.07
                    step = min(distance, speed * dt)
                    player.pos += safe_normalize(movement) * step
                else:
                    player.set_movement(PlayerCommand.IDLE)
                player.pos.x = clamp(player.pos.x, FIELD.left + 10, FIELD.right - 10)
                player.pos.y = clamp(player.pos.y, FIELD.top + 10, FIELD.bottom - 10)
                if player.is_keeper:
                    attack_safe_now, _ = self.keeper_attack_is_safe(player)
                    may_leave_area = player.keeper_attack_timer > 0.0 and attack_safe_now
                    if not may_leave_area:
                        player.pos.update(self.clamp_to_goalkeeper_area(team, player.pos, inset=7.0))
                player.motion_velocity = (player.pos - previous_position) / max(0.001, dt)
                player.update_stamina(dt)
        self._movement_goal_urgency_cache = None

    @staticmethod
    def collision_pair(first: Player, second: Player) -> tuple[int, int]:
        return tuple(sorted((id(first), id(second))))

    @staticmethod
    def player_is_tackling(player: Player) -> bool:
        return player.action_command in (PlayerCommand.TACKLE, PlayerCommand.SLIDE_TACKLE) or player.technique_command in (
            PlayerCommand.TACKLE,
            PlayerCommand.SLIDE_TACKLE,
        )

    def release_ball_from_knockback(
        self,
        player: Player,
        direction: Vec2,
        recovery_team: Team | None = None,
    ) -> None:
        if self.ball.owner is not player:
            return
        if self.pending_kick and self.pending_kick.player is player:
            self.cancel_pending_kick()
        self.ball.owner = None
        self.ball.last_touch = player
        self.ball.intended = None
        self.ball.eye_contact_bonus = 0.0
        self.ball.catch_forbidden = False
        self.ball.last_keeper_response = ""
        self.ball.pickup_lock = 0.16 if recovery_team is not None else 0.34
        # A tackled ball remains near the point of contact instead of being
        # carried away with the falling player.  This lets the tackler and a
        # nearby teammate continue the successful defensive play.
        contact_offset = -6 if recovery_team is not None else 12
        self.ball.pos.update(player.pos + direction * contact_offset)
        self.ball.vel = player.motion_velocity * 0.16 + direction * (46 if recovery_team is not None else 82)
        self.ball.z = 6.0
        self.ball.vertical_speed = 18.0
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.flight_type = "フィジカルこぼれ球"
        self.ball.recovery_team = recovery_team
        self.ball.recovery_timer = 1.25 if recovery_team is not None else 0.0
        self.decision_timer = 0.28

    def resolve_player_collisions(self) -> None:
        players = [player for team in self.teams for player in team.players if not player.sent_off]
        touching_now: set[tuple[int, int]] = set()
        for index, first in enumerate(players):
            for second in players[index + 1:]:
                # Most of the 231 player pairs are far apart.  Reject them on
                # each axis before allocating a Vector2, taking a square root,
                # or constructing the stable contact key.  This is an exact
                # broad phase: a pair outside this square cannot be inside the
                # circular contact distance, so collision outcomes and order
                # remain unchanged.
                if abs(second.pos.x - first.pos.x) >= PLAYER_CONTACT_DISTANCE:
                    continue
                if abs(second.pos.y - first.pos.y) >= PLAYER_CONTACT_DISTANCE:
                    continue
                delta = second.pos - first.pos
                distance = delta.length()
                if distance >= PLAYER_CONTACT_DISTANCE:
                    continue
                pair = self.collision_pair(first, second)
                touching_now.add(pair)
                normal = safe_normalize(delta) if distance > 0.01 else Vec2(0, 1)
                overlap = PLAYER_CONTACT_DISTANCE - distance

                # Every collision separates overlapping bodies. It is not a
                # knockback unless one of the two players is actually executing
                # a tackle command.
                first.pos -= normal * overlap * 0.50
                second.pos += normal * overlap * 0.50
                if first.team is second.team:
                    continue
                tackle_contact = self.player_is_tackling(first) or self.player_is_tackling(second)
                if not tackle_contact or pair in self.knockback_contacts or pair in self.knockback_pair_cooldowns:
                    continue
                relative_speed = (first.motion_velocity - second.motion_velocity).length()
                if relative_speed < 18.0:
                    continue

                first_dribble = first.dribble_physical if self.ball.owner is first else 0.0
                second_dribble = second.dribble_physical if self.ball.owner is second else 0.0
                first_score = collision_strength(
                    first.effective_stat(first.collision_physical),
                    first.effective_stat(first.physical_play_quality),
                    first.motion_velocity.length(),
                    first.effective_stat(first_dribble),
                ) * self.rng.uniform(0.90, 1.10)
                second_score = collision_strength(
                    second.effective_stat(second.collision_physical),
                    second.effective_stat(second.physical_play_quality),
                    second.motion_velocity.length(),
                    second.effective_stat(second_dribble),
                ) * self.rng.uniform(0.90, 1.10)
                winner, loser = (first, second) if first_score >= second_score else (second, first)
                winner_score, loser_score = (first_score, second_score) if winner is first else (second_score, first_score)
                if loser.skill_command is PlayerCommand.IDLE:
                    body_execution = blended_judgment(
                        loser.effective_stat(loser.collision_physical) * 0.65 + loser.effective_stat(loser.physical_play_quality) * 0.35,
                        loser.effective_intelligence,
                        0.72,
                    )
                    resisted = self.try_activate_player_skill(
                        loser,
                        STABLE_CORE,
                        clamp(0.42 + relative_speed / 520.0, 0.42, 0.88),
                        body_execution,
                        duration=0.46,
                    )
                    if resisted:
                        self.knockback_contacts.add(pair)
                        self.knockback_pair_cooldowns[pair] = 1.6
                        continue
                away_from_ball = loser.pos - self.ball.pos
                if away_from_ball.length_squared() < 0.01:
                    away_from_ball = loser.pos - winner.pos
                push_direction = safe_normalize(away_from_ball)
                knockback = collision_knockback(winner_score, loser_score, relative_speed)
                loser.start_knockback(push_direction, 78 + knockback * 3.2)
                loser.pos += push_direction * min(13.0, knockback * 0.42)
                tackling_team = winner.team if self.player_is_tackling(winner) else None
                self.release_ball_from_knockback(loser, push_direction, tackling_team)
                self.knockback_contacts.add(pair)
                self.knockback_pair_cooldowns[pair] = 1.6
                for player in (winner, loser):
                    player.pos.x = clamp(player.pos.x, FIELD.left + 10, FIELD.right - 10)
                    player.pos.y = clamp(player.pos.y, FIELD.top + 10, FIELD.bottom - 10)
                self.physical_collision_count += 1
        self.knockback_contacts.intersection_update(touching_now)

    def update_vertical_motion(self, dt: float) -> None:
        for team in self.teams:
            for player in team.players:
                if player.sent_off:
                    continue
                player.update_vertical(dt)

    def aerial_reading_technique(self, player: Player) -> float:
        if self.ball.intended is player:
            ability = player.trap_technique
        elif self.ball.intended and self.ball.intended.team is not player.team:
            ability = player.pass_interception
        elif self.ball_is_shot():
            ability = player.goal_stopping if player.is_keeper else player.pass_interception
        elif self.ball.last_touch and self.ball.last_touch.team is not player.team:
            ability = player.pass_interception
        else:
            ability = player.trap_technique
        return player.effective_stat(ability)

    def consider_aerial_jumps(self) -> None:
        if self.ball.owner is not None or self.ball.z < 22.0:
            return
        ball_speed = max(125.0, self.ball.vel.length())
        for team in self.teams:
            if self.header_claim_serial.get(team) == self.ball.flight_serial:
                continue
            candidates = sorted(
                (player for player in team.players if not player.sent_off),
                key=lambda player: player.pos.distance_squared_to(self.ball.pos),
            )[:3]
            for player in candidates:
                if player.airborne or player.jump_cooldown > 0.0:
                    continue
                incoming_shot = (
                    self.ball_is_shot()
                    and self.ball.last_touch is not None
                    and self.ball.last_touch.team is not team
                    and self.ball.vel.x * team.direction < 0
                )
                if player.is_keeper:
                    purpose = PlayerCommand.SAVE if incoming_shot else PlayerCommand.IDLE
                elif incoming_shot:
                    purpose = PlayerCommand.BLOCK_SHOT
                elif self.ball.last_touch is not None and self.ball.last_touch.team is not team:
                    defensive_third = self.team_progress(team, self.ball.pos.x) <= 0.40
                    purpose = (
                        PlayerCommand.INTERCEPT_PASS
                        if defensive_third and self.header_intercept_cooldown[team] <= 0.0
                        else PlayerCommand.IDLE
                    )
                elif self.ball.intended is player and self.ball.last_touch is not None and self.ball.last_touch.team is team:
                    goal_x = FIELD.right if team.direction == 1 else FIELD.left
                    goal_distance = abs(goal_x - player.pos.x)
                    attacking_zone = self.team_progress(team, player.pos.x) >= 0.70
                    bicycle_setup = (
                        self.ball.z >= 40
                        and (self.ball.pos.x - player.pos.x) * team.direction < 24
                        and player.has_skill(OVERHEAD_VOLLEY)
                    )
                    if goal_distance <= 315 and attacking_zone and bicycle_setup:
                        purpose = PlayerCommand.SKILL_OVERHEAD_VOLLEY
                    elif goal_distance <= 315 and attacking_zone and player.has_skill(AERIAL_HEADER):
                        purpose = PlayerCommand.SKILL_AERIAL_HEADER
                    else:
                        purpose = PlayerCommand.IDLE
                else:
                    purpose = PlayerCommand.IDLE
                if purpose is PlayerCommand.IDLE:
                    continue
                if not player.is_keeper and not player.can_use_intense_action(
                    emergency=purpose in (
                        PlayerCommand.BLOCK_SHOT,
                        PlayerCommand.SKILL_AERIAL_HEADER,
                        PlayerCommand.SKILL_OVERHEAD_VOLLEY,
                    )
                ):
                    continue
                reading = self.aerial_reading_technique(player)
                intelligence = player.effective_intelligence
                judgment = blended_judgment(player.effective_stat(player.jump_judgment), intelligence, 0.74)
                quality = jump_prediction_quality(judgment, reading)
                distance = player.pos.distance_to(self.ball.pos)
                time_to_ball = clamp(distance / ball_speed, 0.06, 0.78)
                ascent_time = jump_apex_time(player.effective_stat(player.jump_speed))
                anticipation = 0.16 + judgment * 0.19
                if time_to_ball > ascent_time + anticipation:
                    continue
                true_position = self.ball.pos + self.ball.vel * time_to_ball
                true_height = max(
                    0.0,
                    self.ball.z + self.ball.vertical_speed * time_to_ball - 0.5 * GRAVITY * time_to_ball * time_to_ball,
                )
                horizontal_error, vertical_error = prediction_error_scales(quality, player.mistake_error_factor)
                predicted_position = true_position + Vec2(
                    self.rng.gauss(0.0, horizontal_error),
                    self.rng.gauss(0.0, horizontal_error),
                )
                predicted_height = true_height + self.rng.gauss(0.0, vertical_error)
                if purpose is not PlayerCommand.SAVE:
                    goal_x = FIELD.right if team.direction == 1 else FIELD.left
                    goal_distance = abs(goal_x - predicted_position.x)
                    header_reading = blended_judgment(
                        player.effective_stat(player.heading_judgment),
                        intelligence,
                        0.70,
                    )
                    purpose_label = (
                        "SHOOT" if purpose in (PlayerCommand.SKILL_AERIAL_HEADER, PlayerCommand.SKILL_OVERHEAD_VOLLEY)
                        else "BLOCK" if purpose is PlayerCommand.BLOCK_SHOT
                        else "INTERCEPT"
                    )
                    utility = header_attempt_utility(
                        purpose_label,
                        distance,
                        predicted_height,
                        header_reading,
                        intelligence,
                        goal_distance,
                        self.rng,
                    )
                    threshold = 0.60 if purpose in (
                        PlayerCommand.SKILL_AERIAL_HEADER,
                        PlayerCommand.SKILL_OVERHEAD_VOLLEY,
                        PlayerCommand.BLOCK_SHOT,
                    ) else 0.82
                    if utility < threshold:
                        continue
                    if purpose is PlayerCommand.SKILL_AERIAL_HEADER and not self.try_activate_player_skill(
                        player,
                        AERIAL_HEADER,
                        utility,
                        (player.effective_stat(player.heading_accuracy) + player.effective_stat(player.heading_power)) * 0.5,
                        duration=0.85,
                    ):
                        continue
                    if purpose is PlayerCommand.SKILL_OVERHEAD_VOLLEY and not self.try_activate_player_skill(
                        player,
                        OVERHEAD_VOLLEY,
                        utility,
                        (
                            player.effective_stat(player.shot_accuracy)
                            + player.effective_stat(player.shot_power)
                            + player.effective_stat(player.shooting_technique)
                        ) / 3.0,
                        duration=0.92,
                    ):
                        continue
                execution_accuracy = player.effective_stat(player.jump_accuracy)
                execution_error = (1.0 - execution_accuracy) * (7.0 + distance * 0.10) * player.mistake_error_factor
                predicted_position += Vec2(
                    self.rng.gauss(0.0, execution_error),
                    self.rng.gauss(0.0, execution_error),
                )
                jump_range = 58 + judgment * 58 + reading * 28
                if player is self.ball.intended:
                    jump_range += 18
                if player.pos.distance_to(predicted_position) > jump_range:
                    continue
                contact_height = 58.0 if player.is_keeper else 47.0
                desired_apex = max(7.0, predicted_height - contact_height)
                maximum_height = maximum_jump_height(player.effective_stat(player.jump_height))
                if predicted_height > contact_height + maximum_height + 10:
                    continue
                if not player.jump(desired_apex):
                    continue
                if not player.is_keeper:
                    diving_header = player.pos.distance_to(predicted_position) > 31 + execution_accuracy * 10
                    player.start_heading_motion(diving_header, predicted_position)
                    player.heading_purpose = purpose
                    self.header_attempts += 1
                    count_key = (
                        "SHOOT" if purpose in (PlayerCommand.SKILL_AERIAL_HEADER, PlayerCommand.SKILL_OVERHEAD_VOLLEY)
                        else "BLOCK" if purpose is PlayerCommand.BLOCK_SHOT
                        else "INTERCEPT"
                    )
                    self.header_attempt_counts[count_key] += 1
                    if purpose is PlayerCommand.INTERCEPT_PASS:
                        self.header_intercept_cooldown[team] = 18.0
                    self.header_claim_serial[team] = self.ball.flight_serial
                if player.is_keeper:
                    action = PlayerCommand.SAVE
                    technique = PlayerCommand.SAVE
                elif purpose is PlayerCommand.BLOCK_SHOT:
                    action = PlayerCommand.BLOCK_SHOT
                    technique = PlayerCommand.HEADER
                elif purpose is PlayerCommand.INTERCEPT_PASS:
                    action = PlayerCommand.INTERCEPT_PASS
                    technique = PlayerCommand.HEADER
                elif purpose is PlayerCommand.SKILL_OVERHEAD_VOLLEY:
                    action = PlayerCommand.SKILL_OVERHEAD_VOLLEY
                    technique = PlayerCommand.HEADER
                else:
                    action = PlayerCommand.SKILL_AERIAL_HEADER
                    technique = PlayerCommand.HEADER
                player.spend_stamina(PlayerCommand.SAVE if player.is_keeper else PlayerCommand.HEADER)
                player.issue_action(action, predicted_position, duration=0.85, force=True)
                player.use_technique(technique, duration=0.85)
                break

    def header_ball(self, player: Player) -> None:
        purpose = player.heading_purpose
        if purpose not in (
            PlayerCommand.SKILL_AERIAL_HEADER,
            PlayerCommand.SKILL_OVERHEAD_VOLLEY,
            PlayerCommand.INTERCEPT_PASS,
            PlayerCommand.BLOCK_SHOT,
        ):
            return
        bicycle = purpose is PlayerCommand.SKILL_OVERHEAD_VOLLEY
        judgment = player.effective_stat(player.shooting_technique if bicycle else player.heading_judgment)
        intelligence = player.effective_intelligence
        decision = blended_judgment(judgment, intelligence, 0.70)
        accuracy = player.effective_stat(player.shot_accuracy if bicycle else player.heading_accuracy)
        power = player.effective_stat(player.shot_power if bicycle else player.heading_power)
        goal_x = FIELD.right + 8 if player.team.direction == 1 else FIELD.left - 8
        distance_to_goal = abs(goal_x - player.pos.x)
        target_player = None
        if purpose in (PlayerCommand.SKILL_AERIAL_HEADER, PlayerCommand.SKILL_OVERHEAD_VOLLEY):
            keeper = (self.away if player.team is self.home else self.home).keeper
            open_side = -1.0 if keeper.pos.y >= FIELD.centery else 1.0
            if self.rng.random() > 0.48 + decision * 0.47:
                open_side *= -1.0
            target = Vec2(goal_x, FIELD.centery + open_side * GOAL_HALF_HEIGHT * (0.30 + decision * 0.42))
            header_type = "オーバーヘッドボレー" if bicycle else "シュート・ヘディング"
            target_height = GOAL_HEIGHT * ((0.48 + decision * 0.22) if bicycle else (0.30 + decision * 0.28))
        else:
            spread = 215 - decision * 150
            target = Vec2(
                player.pos.x + player.team.direction * (220 + power * 185),
                clamp(FIELD.centery + self.rng.uniform(-spread, spread), FIELD.top + 32, FIELD.bottom - 32),
            )
            header_type = "ヘディングブロック" if purpose is PlayerCommand.BLOCK_SHOT else "ヘディングカット"
            target_height = 15.0

        desired_distance = player.pos.distance_to(target)
        speed = heading_ball_speed(power, judgment, desired_distance, self.rng)
        if bicycle:
            speed *= 1.18
        base_direction = safe_normalize(target - player.pos)
        perpendicular = Vec2(-base_direction.y, base_direction.x)
        direction_error = self.rng.gauss(0.0, heading_error_sigma(accuracy, desired_distance, player.mistake_error_factor))
        destination = target + perpendicular * direction_error
        direction = safe_normalize(destination - player.pos)
        self.ball.owner = None
        self.ball.flight_serial += 1
        self.ball.last_touch = player
        self.ball.intended = target_player
        self.ball.catch_forbidden = False
        self.ball.last_keeper_response = ""
        self.ball.pickup_lock = 0.16
        self.ball.pos.update(player.pos + direction * 10)
        self.ball.vel = direction * speed
        flight_time = max(0.18, desired_distance / max(120.0, speed))
        ideal_vertical = (target_height - self.ball.z + 0.5 * GRAVITY * flight_time * flight_time) / flight_time
        vertical_error = self.rng.gauss(0.0, (1.0 - accuracy) * 34 * player.mistake_error_factor)
        self.ball.vertical_speed = clamp(ideal_vertical + vertical_error, -105, 145)
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.flight_type = header_type
        self.ball.shot_deception = 0.0
        self.ball.eye_contact_bonus = 0.0
        player.last_header_type = header_type
        player.heading_purpose = PlayerCommand.IDLE
        if bicycle:
            player.start_heading_motion(True, destination)
        elif player.heading_motion != "DIVING":
            player.start_heading_motion(False, destination)
        player.issue_action(PlayerCommand.SKILL_OVERHEAD_VOLLEY if bicycle else PlayerCommand.HEADER, player.pos, duration=0.48 if bicycle else 0.38, force=True)
        player.use_technique(PlayerCommand.HEADER, duration=0.38)
        if target_player is not None:
            target_player.issue_action(PlayerCommand.RECEIVE_PASS, destination, duration=0.55, force=True)
        if purpose in (PlayerCommand.SKILL_AERIAL_HEADER, PlayerCommand.SKILL_OVERHEAD_VOLLEY):
            player.team.shots += 1
            self.ball.shot_deception = clamp(decision * player.technique_success_factor * 0.78, 0.0, 1.0)
            self.ball.shot_serial += 1
            self.add_event(f"{player.name}の{'オーバーヘッドボレー' if bicycle else 'エアリアルヘッド'}！")
        self.decision_timer = self.rng.uniform(0.32, 0.62)

    def foul_is_penalty(self, defending_team: Team, spot: Vec2) -> bool:
        in_height = abs(spot.y - FIELD.centery) <= PENALTY_AREA_WIDTH / 2
        if defending_team.direction == 1:
            return in_height and spot.x <= FIELD.left + PENALTY_AREA_DEPTH
        return in_height and spot.x >= FIELD.right - PENALTY_AREA_DEPTH

    def call_foul(self, offender: Player, victim: Player, dangerousness: float) -> None:
        spot = Vec2(victim.pos)
        restart_type = "PENALTY_KICK" if self.foul_is_penalty(offender.team, spot) else "FREE_KICK"
        restart_spot = Vec2(spot)
        if restart_type == "PENALTY_KICK":
            restart_spot.update(
                FIELD.right - PENALTY_SPOT_DISTANCE if victim.team.direction == 1 else FIELD.left + PENALTY_SPOT_DISTANCE,
                FIELD.centery,
            )
        card = choose_card(offender.effective_stat(offender.safe_play), dangerousness, self.rng)
        if card == "YELLOW":
            offender.yellow_cards += 1
            if offender.yellow_cards >= 2:
                card = "RED"
        if card == "RED":
            offender.sent_off = True
        if card:
            self.card_count += 1
        self.foul_count += 1
        self.cancel_pending_kick()
        self.ball.owner = None
        self.ball.intended = None
        self.ball.catch_forbidden = False
        self.ball.last_keeper_response = ""
        self.ball.vel.update(0, 0)
        self.ball.pos.update(restart_spot)
        self.ball.z = 0.0
        self.ball.vertical_speed = 0.0
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.flight_type = f"{restart_type}準備"
        self.restart_type = restart_type
        self.restart_team = victim.team
        self.restart_spot.update(restart_spot)
        candidates = [player for player in victim.team.players if not player.sent_off]
        if restart_type == "PENALTY_KICK":
            self.restart_taker = max(candidates, key=lambda player: player.penalty_kick_skill)
        else:
            self.restart_taker = max(candidates, key=lambda player: player.free_kick_skill - player.pos.distance_to(spot) / 4000)
        self.restart_elapsed = 0.0
        self.configure_set_piece_positions(restart_type, victim.team, restart_spot, self.restart_taker)
        self.referee_target = offender.pos.lerp(victim.pos, 0.5)
        self.referee_active = True
        self.referee_timer = 0.72 if card else 0.34
        self.referee_card = card
        self.referee_player = offender
        self.stoppage_timer = 1.45 if restart_type == "PENALTY_KICK" else 1.35
        self.restart_counts[restart_type] += 1
        card_label = " レッドカード" if card == "RED" else " イエローカード" if card == "YELLOW" else ""
        self.add_event(f"{offender.name}のファウル{card_label}")
        self.show_banner("PENALTY" if restart_type == "PENALTY_KICK" else "FREE KICK", 0.85)

    def update_referee(self, dt: float) -> bool:
        if not self.referee_active:
            return False
        movement = self.referee_target - self.referee_pos
        distance = movement.length()
        if distance > 13:
            self.referee_pos += safe_normalize(movement) * min(distance, 145 * dt)
            return True
        self.referee_timer = max(0.0, self.referee_timer - dt)
        if self.referee_timer <= 0.0:
            self.referee_active = False
        return self.referee_active

    def try_keeper_claim_from_dribbler(self, keeper: Player, owner: Player, dt: float) -> bool:
        """Contest a low ball at an attacker's feet when both are inside the box."""
        if (
            owner.team is keeper.team
            or not self.point_in_own_penalty_area(keeper.team, self.ball.pos)
            or self.ball.z > 24 * PLAYER_VISUAL_SCALE
        ):
            return False
        distance = keeper.pos.distance_to(owner.pos)
        claim_range = KEEPER_BALL_REACH * 0.92
        if distance > claim_range:
            return False
        stopping = keeper.effective_stat(keeper.goal_stopping)
        trapping = keeper.effective_stat(keeper.trap_technique)
        intelligence = keeper.effective_intelligence
        claim_quality = stopping * 0.55 + trapping * 0.23 + intelligence * 0.22
        owner_control = owner.effective_stat(owner.dribble_technique) * 0.70
        owner_control += owner.effective_stat(owner.dribble_physical) * 0.30
        contest = clamp((0.50 + claim_quality) / max(0.48, 0.54 + owner_control), 0.46, 1.75)
        contact_rate = (1.20 + claim_quality * 2.35) * contest
        keeper.issue_action(PlayerCommand.SAVE, owner.pos, duration=0.18, force=True)
        keeper.use_technique(PlayerCommand.SAVE, duration=0.18)
        if self.rng.random() >= dt * contact_rate:
            return False
        incoming_speed = max(35.0, owner.motion_velocity.length())
        if self.resolve_keeper_contact(keeper, incoming_speed):
            self.add_event(f"{keeper.name}が足元へ飛び込みボールを確保")
            return True
        return False

    def try_tackles(self, dt: float) -> None:
        owner = self.ball.owner
        if owner is None or owner.is_keeper:
            return
        opponents = [
            player for player in (self.away.players if owner.team is self.home else self.home.players)
            if not player.sent_off
        ]
        opponents.sort(key=lambda player: player.pos.distance_squared_to(owner.pos))
        for defender_index, defender in enumerate(opponents):
            if defender.fallen_timer > 0.0 or defender.sent_off:
                continue
            if defender.is_keeper:
                self.try_keeper_claim_from_dribbler(defender, owner, dt)
                if self.ball.owner is not owner:
                    return
                continue
            distance = defender.pos.distance_to(owner.pos)
            if owner.action_command is PlayerCommand.TRAP or owner.technique_command is PlayerCommand.TRAP:
                ball_control = owner.effective_stat(owner.trap_technique)
                vulnerable_bonus = 1.18
            else:
                dribble_control = owner.effective_stat(owner.dribble_technique)
                body_control = dribble_protection(
                    owner.effective_stat(owner.dribble_physical),
                    owner.effective_stat(owner.physical_play_quality),
                )
                ball_control = dribble_control * 0.68 + body_control * 0.32
                vulnerable_bonus = 1.0
                if owner.roulette_timer > 0.0:
                    ball_control = clamp(ball_control + 0.16 + owner.roulette_success * 0.34, 0.0, 1.35)
                    vulnerable_bonus = 0.72
                if owner.cruyff_timer > 0.0:
                    ball_control = clamp(ball_control + 0.30, 0.0, 1.35)
                    vulnerable_bonus *= 0.76
                if owner.post_play_timer > 0.0:
                    ball_control = clamp(ball_control + owner.effective_stat(owner.dribble_physical) * 0.26, 0.0, 1.35)
                    vulnerable_bonus *= 0.84
                if owner.razor_dribble_timer > 0.0:
                    ball_control = clamp(ball_control + 0.38, 0.0, 1.35)
                    vulnerable_bonus *= 0.70
                if owner.tricky_feint_timer > 0.0:
                    ball_control = clamp(ball_control + 0.32, 0.0, 1.35)
                    vulnerable_bonus *= 0.73
                if owner.high_speed_dribble_timer > 0.0:
                    ball_control = clamp(ball_control + 0.10, 0.0, 1.35)
            if (
                not defender.slide_active
                and defender_index == 0
                and SLIDE_START_MIN_DISTANCE < distance < SLIDE_START_MAX_DISTANCE
                and defender.can_use_intense_action()
            ):
                closing_speed = (defender.motion_velocity - owner.motion_velocity).length()
                steal = defender.effective_stat(defender.steal_technique)
                intelligence = defender.effective_intelligence
                attacking_progress = clamp(self.team_progress(owner.team, owner.pos.x), 0.0, 1.0)
                goal_danger = clamp((attacking_progress - 0.58) / 0.32, 0.0, 1.0)
                utility = slide_tackle_utility(
                    distance,
                    closing_speed,
                    steal,
                    ball_control,
                    defender.effective_stat(defender.safe_play),
                    intelligence,
                    goal_danger,
                    self.rng,
                )
                if self.rng.random() < slide_start_probability(utility, dt) and defender.start_slide(owner.pos):
                    defender.spend_stamina(PlayerCommand.SLIDE_TACKLE)
                    defender.issue_action(PlayerCommand.SLIDE_TACKLE, owner.pos, duration=defender.slide_duration, force=True)
                    defender.use_technique(PlayerCommand.SLIDE_TACKLE, duration=defender.slide_duration)
                    self.slide_attempts += 1
            use_slide = defender.slide_active
            contact_range = SLIDE_TACKLE_REACH if use_slide else STANDING_TACKLE_REACH
            if distance >= contact_range:
                continue
            killer_slide = False
            if use_slide and defender.skill_command is PlayerCommand.IDLE:
                killer_execution = blended_judgment(
                    defender.effective_stat(defender.steal_technique) * 0.55 + defender.effective_stat(defender.physical_play_quality) * 0.45,
                    defender.effective_intelligence,
                    0.70,
                )
                killer_slide = self.try_activate_player_skill(
                    defender,
                    POWER_SLIDE,
                    0.40 + clamp((SLIDE_TACKLE_REACH - distance) / max(1.0, SLIDE_TACKLE_REACH), 0.0, 0.34),
                    killer_execution,
                    duration=0.76,
                )
                if killer_slide:
                    owner.fallen_timer = max(owner.fallen_timer, 0.78)
                    spill_direction = safe_normalize(owner.pos - defender.pos)
                    self.release_ball_from_knockback(owner, spill_direction, defender.team)
            tackle_command = PlayerCommand.SLIDE_TACKLE if use_slide else PlayerCommand.TACKLE
            if use_slide and not defender.slide_foul_checked:
                defender.slide_foul_checked = True
                closing_speed = (defender.motion_velocity - owner.motion_velocity).length()
                dangerousness = clamp(0.55 + closing_speed / 440.0 + (0.16 if owner.airborne else 0.0), 0.48, 1.30)
                foul_probability = foul_chance(
                    defender.effective_stat(defender.safe_play),
                    dangerousness,
                    defender.effective_stat(defender.physical_play_quality),
                )
                if self.rng.random() < foul_probability:
                    self.call_foul(defender, owner, dangerousness)
                    return
            if not use_slide:
                if defender.technique_command is not tackle_command:
                    defender.spend_stamina(tackle_command)
                defender.issue_action(tackle_command, owner.pos, force=True)
                defender.use_technique(tackle_command)
                defender.set_movement(PlayerCommand.WALK)
            press = defender.team.tactical_settings(defender)["press"]
            tackle_factor = 1.0 if use_slide else 0.58
            steal = defender.effective_stat(defender.steal_technique)
            owner_is_dribbling = owner.action_command in (
                PlayerCommand.DRIBBLE,
                PlayerCommand.KEEP_BALL,
                PlayerCommand.SKILL_SPIN_TURN,
                PlayerCommand.SKILL_HEEL_REVERSE_TURN,
                PlayerCommand.SKILL_PIVOT_KEEP,
                PlayerCommand.SKILL_TIGHT_TOUCH,
                PlayerCommand.SKILL_SPRINT_CARRY,
                PlayerCommand.SKILL_ENERGY_KEEP,
                PlayerCommand.SKILL_ILLUSION_STEP,
            )
            if (
                not use_slide
                and owner_is_dribbling
                and distance < 21
                and defender.skill_command is PlayerCommand.IDLE
            ):
                marking_execution = blended_judgment(
                    steal,
                    defender.effective_intelligence,
                    0.68,
                )
                self.try_activate_player_skill(
                    defender,
                    CLOSE_LOCK,
                    0.44 + clamp((21 - distance) / 21.0, 0.0, 1.0) * 0.46,
                    marking_execution,
                    duration=1.15,
                )
            if owner_is_dribbling and defender.skill_command is PlayerCommand.SKILL_CLOSE_LOCK:
                marking_quality = blended_judgment(
                    steal,
                    defender.effective_intelligence,
                    0.68,
                )
                steal = clamp(steal + 0.12 + marking_quality * 0.20, 0.0, 1.30)
                tackle_factor += 0.10 + marking_quality * 0.12
            if owner_is_dribbling and defender.one_side_cut_timer > 0.0:
                cut_quality = self.behavior_quality(defender, "man_marking", defender.steal_technique)
                steal = clamp(steal + 0.10 + cut_quality * 0.16, 0.0, 1.30)
                tackle_factor += 0.08 + cut_quality * 0.10
            if killer_slide:
                tackle_factor += 0.28
            if defender.demon_press_timer > 0.0:
                steal = clamp(steal + 0.18, 0.0, 1.30)
                tackle_factor += 0.22
            steal_force = 0.25 + pow(steal, 1.25) * 1.25
            control_force = 0.25 + pow(ball_control, 1.25) * 1.25
            technique_contest = clamp(steal_force / control_force, 0.28, 2.40)
            mistake_contest = defender.technique_success_factor / max(0.48, owner.technique_success_factor)
            contact_rate = 4.8 if use_slide else 1.15
            chance = dt * contact_rate * press * defender.skill / max(0.35, owner.skill)
            chance *= defender.fatigue_factor * technique_contest * mistake_contest * vulnerable_bonus
            chance *= tackle_factor
            if self.rng.random() < chance:
                self.change_owner(defender)
                self.add_event(f"{defender.name}がスライディングで奪取" if use_slide else f"{defender.name}がボール奪取")
                if use_slide:
                    self.choose_slide_kick(defender)
                return
            if killer_slide:
                return

    def choose_slide_kick(self, player: Player) -> None:
        if not player.slide_active or player.slide_kick_used or self.pending_kick is not None or self.ball.owner is not player:
            return
        player.slide_kick_used = True
        goal_x = FIELD.right if player.team.direction == 1 else FIELD.left
        distance_to_goal = abs(goal_x - player.pos.x)
        shooting = player.effective_stat(player.shooting_technique)
        intelligence = player.effective_intelligence
        shooting_decision = blended_judgment(shooting, intelligence, 0.70)
        shot_limit = (
            150 + shooting_decision * 112
            + kick_power_output(player.effective_stat(player.shot_power)) * shooting_decision * 52
        )
        shot_situation = clamp(1.0 - distance_to_goal / max(1.0, shot_limit), 0.0, 1.0)
        sliding_shot = (
            distance_to_goal <= shot_limit
            and self.try_activate_player_skill(
                player,
                SLIDE_FINISH,
                0.42 + shot_situation * 0.58,
                (shooting + player.effective_stat(player.shot_accuracy)) * 0.5,
                duration=0.62,
            )
        )
        if sliding_shot:
            if self.shoot(player):
                player.last_slide_kick = "スライドフィニッシュ"
                self.add_event(f"{player.name}がスライドフィニッシュ！")
            return
        target = self.choose_pass_target(player)
        passing_decision = blended_judgment(
            player.effective_stat(player.passing_technique),
            intelligence,
            0.70,
        )
        opponents = self.away.players if player.team is self.home else self.home.players
        emergency_release = min(opponent.pos.distance_to(player.pos) for opponent in opponents) < 27
        if target is not None and emergency_release and self.rng.random() < 0.06 + passing_decision * 0.12:
            if self.pass_ball(player, target):
                player.last_slide_kick = "スライディングパス"
                self.add_event(f"{player.name}がスライディングからパス")

    def predicted_pass_destination(
        self,
        owner: Player,
        candidate: Player,
        flight_time: float,
    ) -> Vec2:
        intelligence = owner.effective_intelligence
        visible_velocity = Vec2(candidate.motion_velocity)
        desired = candidate.target - candidate.pos
        if desired.length_squared() > 4.0:
            desired_speed = movement_speed(
                PlayerCommand.DASH,
                candidate.effective_stat(candidate.dash_speed),
            )
            desired_velocity = safe_normalize(desired) * desired_speed
            visible_velocity = visible_velocity.lerp(desired_velocity, 0.42 + intelligence * 0.30)
        prediction_horizon = min(1.45, flight_time) * (0.32 + intelligence * 0.66)
        destination = candidate.pos + visible_velocity * prediction_horizon
        destination.x = clamp(destination.x, FIELD.left + 24, FIELD.right - 24)
        destination.y = clamp(destination.y, FIELD.top + 28, FIELD.bottom - 28)
        return destination

    def evaluate_pass_route(self, owner: Player, candidate: Player) -> PassRoute:
        passing = owner.effective_stat(owner.passing_technique)
        kick_output = kick_power_output(owner.effective_stat(owner.pass_power))
        destination = Vec2(candidate.pos)
        flight_time = 0.5
        estimated_speed = 250.0
        for _ in range(2):
            distance = owner.pos.distance_to(destination)
            estimated_speed = clamp(
                150 + distance * 0.31 + kick_output * (95 + passing * 69),
                175,
                455,
            )
            flight_time = max(0.16, distance / estimated_speed)
            destination = self.predicted_pass_destination(owner, candidate, flight_time)

        lane = destination - owner.pos
        lane_length_sq = max(1.0, lane.length_squared())
        opponents = [
            opponent for team in self.teams if team is not owner.team
            for opponent in team.players if not opponent.sent_off
        ]
        interception_risk = 0.0
        lane_clearance = 180.0
        opponent_clearance = 240.0
        for opponent in opponents:
            lane_fraction = clamp((opponent.pos - owner.pos).dot(lane) / lane_length_sq, 0.04, 0.96)
            intercept_point = owner.pos + lane * lane_fraction
            opponent_speed = movement_speed(
                PlayerCommand.DASH,
                opponent.effective_stat(opponent.dash_speed),
            ) * opponent.fatigue_factor * opponent.venue_factor
            opponent_time = opponent.pos.distance_to(intercept_point) / max(35.0, opponent_speed)
            ball_time = flight_time * lane_fraction
            timing_risk = clamp((ball_time + 0.20 - opponent_time) / 0.62, 0.0, 1.0)
            opponent_lane_distance = self.distance_to_pass_lane(opponent.pos, owner.pos, destination)
            lane_clearance = min(lane_clearance, opponent_lane_distance)
            opponent_clearance = min(opponent_clearance, opponent.pos.distance_to(destination))
            lane_risk = clamp(
                1.0 - opponent_lane_distance / 72.0,
                0.0,
                1.0,
            )
            interception_risk = max(interception_risk, timing_risk * 0.68 + lane_risk * 0.32)

        receiver_speed = movement_speed(
            PlayerCommand.DASH,
            candidate.effective_stat(candidate.dash_speed),
        ) * candidate.fatigue_factor * candidate.venue_factor
        receiver_time = candidate.pos.distance_to(destination) / max(35.0, receiver_speed)
        receiver_margin = flight_time - receiver_time
        touchline_margin = min(
            destination.x - FIELD.left,
            FIELD.right - destination.x,
            destination.y - FIELD.top,
            FIELD.bottom - destination.y,
        )
        return PassRoute(
            destination,
            flight_time,
            interception_risk,
            receiver_margin,
            touchline_margin,
            lane_clearance,
            opponent_clearance,
        )

    def choose_pass_target(self, owner: Player) -> Player | None:
        self._selected_pass_owner = owner
        self._selected_pass_target = None
        self._selected_pass_route = None
        candidates = [player for player in owner.team.players if player is not owner and not player.is_keeper and not player.sent_off]
        if not candidates:
            return None
        best_player = None
        best_score = -9999.0
        best_route: PassRoute | None = None
        forward_weight = owner.team.tactical_settings(owner)["pass_forward"]
        forward_weight *= 0.82 + owner.confidence * 0.36
        pass_power = owner.effective_stat(owner.pass_power)
        kick_output = kick_power_output(pass_power)
        passing = owner.effective_stat(owner.passing_technique)
        intelligence = owner.effective_intelligence
        decision = blended_judgment(passing, intelligence, 0.68)
        max_pass_distance = 150 + kick_output * (105 + passing * 150) + decision * 70 + intelligence * 32
        for candidate in candidates:
            delta = candidate.pos - owner.pos
            distance = delta.length()
            if distance < 42 or distance > max_pass_distance:
                continue
            route = self.evaluate_pass_route(owner, candidate)
            score = score_pass_candidate(
                owner,
                candidate,
                lane_clearance=route.lane_clearance,
                nearest_opponent_distance=route.opponent_clearance,
                forward_weight=forward_weight,
                pass_power=kick_output,
                passing=passing,
                intelligence=intelligence,
                decision=decision,
                rng=self.rng,
            )
            awareness = 0.28 + intelligence * 0.72
            score -= route.interception_risk * (78 + awareness * 220)
            if route.receiver_margin < -0.08:
                score -= abs(route.receiver_margin + 0.08) * (42 + intelligence * 92)
            else:
                score += min(0.55, route.receiver_margin) * (18 + intelligence * 30)
            if route.touchline_margin < 60:
                score -= (60 - route.touchline_margin) * (0.24 + intelligence * 0.54)
            friendly_density = sum(
                teammate is not candidate
                and (
                    teammate.pos.distance_to(route.destination) < 96
                    or teammate.target.distance_to(route.destination) < 82
                )
                for teammate in candidates
            )
            score -= friendly_density * (14 + intelligence * 38)
            if candidate.action_command in (
                PlayerCommand.LOSE_MARK, PlayerCommand.DIAGONAL_RUN,
                PlayerCommand.RUN_INTO_SPACE, PlayerCommand.CREATE_PASS_LANE,
            ):
                score += 10 + intelligence * 18
            continuation = self.receiver_continuation_value(
                owner,
                candidate,
                route.destination,
            )
            score += continuation * (18 + intelligence * 66 + decision * 24)
            if score > best_score:
                best_score = score
                best_player = candidate
                best_route = route
        if (
            best_route is not None
            and owner.effective_intelligence > 0.58
            and best_route.interception_risk > 0.86 - owner.effective_intelligence * 0.18
        ):
            return None
        self._selected_pass_target = best_player
        self._selected_pass_route = best_route
        return best_player

    def choose_keeper_distribution_target(self, keeper: Player, prefer_long: bool = False) -> Player | None:
        candidates = [
            player for player in keeper.team.players
            if player is not keeper and not player.is_keeper and not player.sent_off
        ]
        if not candidates:
            return None
        opponents = [
            player for team in self.teams if team is not keeper.team
            for player in team.players if not player.sent_off
        ]
        passing = keeper.effective_stat(keeper.passing_technique)
        intelligence = keeper.effective_intelligence
        scored: list[tuple[float, Player]] = []
        for candidate in candidates:
            distance = keeper.pos.distance_to(candidate.pos)
            openness = min((candidate.pos.distance_to(opponent.pos) for opponent in opponents), default=220.0)
            lane_clearance = min(
                (self.distance_to_pass_lane(opponent.pos, keeper.pos, candidate.pos) for opponent in opponents),
                default=180.0,
            )
            progress = (candidate.pos.x - keeper.pos.x) * keeper.team.direction
            if prefer_long:
                distance_score = -abs(distance - (470 + passing * 170)) * 0.16
                progress_score = progress * (0.26 + passing * 0.17)
            else:
                distance_score = -abs(distance - (145 + passing * 85)) * 0.24
                progress_score = progress * 0.12
            score = openness * (0.48 + passing * 0.22) + lane_clearance * (0.55 + intelligence * 0.20)
            score += distance_score + progress_score
            score = perceived_utility(score, intelligence, self.rng, noise_span=34.0)
            scored.append((score, candidate))
        return max(scored, key=lambda item: item[0])[1]

    def distribute_keeper_ball(self, keeper: Player) -> bool:
        """Choose a legal keeper distribution using intelligence and pressure."""
        if self.ball.owner is not keeper:
            return False
        short_target = self.choose_keeper_distribution_target(keeper, prefer_long=False)
        long_target = self.choose_keeper_distribution_target(keeper, prefer_long=True)
        if short_target is None and long_target is None:
            return self.clear_ball(keeper)
        opponents = [
            player for team in self.teams if team is not keeper.team
            for player in team.players if not player.sent_off
        ]
        nearest_pressure = min((keeper.pos.distance_to(player.pos) for player in opponents), default=999.0)
        passing = keeper.effective_stat(keeper.passing_technique)
        pass_power = keeper.effective_stat(keeper.pass_power)
        kick_output = kick_power_output(pass_power)
        held_in_hands = self.ball.last_keeper_response == "CATCH"
        short_distance = keeper.pos.distance_to(short_target.pos) if short_target is not None else 999.0
        long_distance = keeper.pos.distance_to(long_target.pos) if long_target is not None else 0.0
        utilities = {
            PlayerCommand.PASS: (
                0.56 + passing * 0.34 + clamp((nearest_pressure - 90) / 320.0, 0.0, 0.25)
                - clamp((short_distance - 250) / 320.0, 0.0, 0.22)
                if short_target is not None else -2.0
            ),
            PlayerCommand.KEEPER_THROW: (
                0.62 + passing * 0.22 + clamp((260 - short_distance) / 420.0, 0.0, 0.24)
                if held_in_hands and short_target is not None else -2.0
            ),
            PlayerCommand.KEEPER_PUNT: (
                0.38 + kick_output * 0.34 + passing * 0.18
                + clamp((long_distance - 280) / 650.0, 0.0, 0.28)
                + clamp((120 - nearest_pressure) / 360.0, 0.0, 0.16)
                if long_target is not None else -2.0
            ),
        }
        choice = choose_utility_action(utilities, keeper.effective_intelligence, self.rng)
        if choice is PlayerCommand.KEEPER_THROW and short_target is not None:
            self._release_keeper_throw(keeper, short_target)
            return True
        if choice is PlayerCommand.KEEPER_PUNT and long_target is not None:
            if held_in_hands:
                self.ball.last_keeper_response = "TRAP"
                self.ball.control_offset.update(keeper.team.direction * 7, 0)
            return self.begin_kick(
                keeper,
                PlayerCommand.KEEPER_PUNT,
                target_player=long_target,
                target_point=long_target.pos,
            )
        if short_target is not None:
            # Place a caught ball at the feet before the short-kick animation.
            if held_in_hands:
                self.ball.last_keeper_response = "TRAP"
            return self.pass_ball(keeper, short_target)
        return self.clear_ball(keeper)

    def _release_keeper_throw(self, keeper: Player, target: Player) -> None:
        distance = keeper.pos.distance_to(target.pos)
        passing = keeper.effective_stat(keeper.passing_technique)
        accuracy = keeper.effective_stat(keeper.pass_accuracy)
        lead = Vec2(keeper.team.direction * min(42.0, distance * 0.12), 0)
        destination = target.pos + lead
        direction = safe_normalize(destination - keeper.pos)
        perpendicular = Vec2(-direction.y, direction.x)
        destination += perpendicular * self.rng.gauss(0.0, (5 + distance * 0.035) * (1.10 - accuracy))
        direction = safe_normalize(destination - keeper.pos)
        speed = clamp(205 + distance * 0.42 + passing * 95, 230, 410)
        flight_time = max(0.25, distance / speed)
        self.ball.owner = None
        self.ball.flight_serial += 1
        self.ball.last_touch = keeper
        self.ball.intended = target
        self.ball.pickup_lock = 0.20
        self.ball.pos.update(keeper.pos + direction * 12)
        self.ball.vel = direction * speed
        self.ball.z = 24.0
        self.ball.vertical_speed = clamp(
            (8.0 - self.ball.z + 0.5 * GRAVITY * flight_time * flight_time) / flight_time,
            24,
            142,
        )
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.flight_type = "GKスロー"
        self.ball.last_keeper_response = ""
        self.ball.catch_forbidden = False
        keeper.spend_stamina(PlayerCommand.KEEPER_THROW)
        keeper.issue_action(PlayerCommand.KEEPER_THROW, destination, duration=0.46, force=True)
        keeper.use_technique(PlayerCommand.KEEPER_THROW, duration=0.46)
        target.issue_action(PlayerCommand.RECEIVE_PASS, destination, duration=0.72, force=True)
        self.decision_timer = self.rng.uniform(0.35, 0.62)
        self.add_event(f"{keeper.name}が味方へスロー")

    def _release_keeper_punt(self, keeper: Player, target: Player) -> None:
        self._release_pass(keeper, target)
        distance = keeper.pos.distance_to(target.pos)
        direction = safe_normalize(self.ball.vel)
        pass_power = keeper.effective_stat(keeper.pass_power)
        kick_output = kick_power_output(pass_power)
        passing = keeper.effective_stat(keeper.passing_technique)
        self.ball.vel = direction * clamp(315 + kick_output * 170 + distance * 0.055, 330, 590)
        self.ball.vertical_speed = clamp(112 + kick_output * 62 + passing * 25 + distance * 0.030, 120, 218)
        self.ball.z = max(self.ball.z, 12.0)
        self.ball.flight_type = "GKロングキック"
        keeper.last_pass_type = self.ball.flight_type
        self.add_event(f"{keeper.name}がロングキック")

    def choose_no_look_target(self, owner: Player) -> Player | None:
        opponents = [
            opponent for team in self.teams if team is not owner.team
            for opponent in team.players if not opponent.sent_off
        ]
        candidates = []
        intelligence = owner.effective_intelligence
        for candidate in owner.team.players:
            if candidate is owner or candidate.sent_off:
                continue
            delta = candidate.pos - owner.pos
            distance = delta.length()
            progress = delta.x * owner.team.direction
            if not 42 <= distance <= 300 or progress > 90:
                continue
            openness = min((candidate.pos.distance_to(opponent.pos) for opponent in opponents), default=160.0)
            sideways = abs(delta.y)
            score = openness * 0.68 + sideways * 0.20 - abs(progress) * 0.06 - distance * 0.08
            score = perceived_utility(score, intelligence, self.rng, noise_span=34.0)
            candidates.append((score, candidate))
        return max(candidates, key=lambda item: item[0])[1] if candidates else None

    def pass_ball(self, owner: Player, target: Player, route: PassRoute | None = None) -> bool:
        distance = owner.pos.distance_to(target.pos)
        route = route or self.evaluate_pass_route(owner, target)
        forward_progress = (target.pos.x - owner.pos.x) * owner.team.direction
        if owner.skill_command is PlayerCommand.IDLE and distance <= 310:
            facing_situation = 0.38
            if target.action_command in (
                PlayerCommand.SUPPORT,
                PlayerCommand.TRIANGLE_SUPPORT,
                PlayerCommand.RECEIVE_PASS,
            ):
                facing_situation += 0.24
            eye_execution = blended_judgment(
                owner.effective_stat(owner.passing_technique) * 0.55 + target.effective_stat(target.trap_technique) * 0.45,
                owner.effective_intelligence,
                0.68,
            )
            self.try_activate_player_skill(
                owner,
                SIGNAL_LINK,
                facing_situation,
                eye_execution,
                duration=owner.kick_contact_time + 0.62,
            )
        if abs(owner.pos.y - FIELD.centery) > FIELD.height * 0.30 and forward_progress > 80:
            pass_command = PlayerCommand.CROSS
        elif forward_progress > 150 and distance > 180:
            pass_command = PlayerCommand.THROUGH_PASS
        else:
            pass_command = PlayerCommand.PASS
        if self.begin_kick(owner, pass_command, target, route.destination):
            target.issue_action(
                PlayerCommand.RECEIVE_PASS,
                route.destination,
                duration=owner.kick_contact_time + route.flight_time + 0.25,
                force=True,
            )
            return True
        return False

    def choose_pass_outcome(self, owner: Player, pass_accuracy: float) -> str:
        execution = clamp(pass_accuracy * owner.technique_success_factor, 0.0, 1.0)
        mistake_chance = clamp(
            0.012 + pow(1.0 - execution, 1.55) * 0.62 * owner.mistake_error_factor,
            0.008,
            0.72,
        )
        if self.rng.random() >= mistake_chance:
            return PASS_CLEAN
        roll = self.rng.random()
        if roll < 0.27:
            return PASS_WRONG_DIRECTION
        if roll < 0.51:
            return PASS_DANGEROUS_LANE
        if roll < 0.76:
            return PASS_OVERHIT
        return PASS_UNDERHIT

    def _release_pass(
        self,
        owner: Player,
        target: Player,
        set_piece_skill: float = 0.0,
        planned_destination: Vec2 | None = None,
    ) -> None:
        pass_accuracy = owner.effective_stat(owner.pass_accuracy)
        pass_power = owner.effective_stat(owner.pass_power)
        kick_output = kick_power_output(pass_power)
        passing = max(owner.effective_stat(owner.passing_technique), set_piece_skill)
        intelligence = owner.effective_intelligence
        active_skill = owner.skill_command
        route = self.evaluate_pass_route(owner, target)
        destination = Vec2(planned_destination) if planned_destination is not None else route.destination
        distance = owner.pos.distance_to(destination)
        opponents = self.away.players if owner.team is self.home else self.home.players
        closest_lane_opponent = min(
            opponents,
            key=lambda opponent: self.distance_to_pass_lane(opponent.pos, owner.pos, destination),
            default=None,
        )
        lane_clearance = (
            self.distance_to_pass_lane(closest_lane_opponent.pos, owner.pos, destination)
            if closest_lane_opponent is not None else 180.0
        )
        congestion = 1.0 - clamp(lane_clearance / 105.0, 0.0, 1.0)
        original_lane = destination - owner.pos
        lane_progress = 0.5
        if original_lane.length_squared() > 0.0001:
            lane_progress = clamp(
                (closest_lane_opponent.pos - owner.pos).dot(original_lane) / original_lane.length_squared()
                if closest_lane_opponent is not None else 0.5,
                0.0,
                1.0,
            )
        obstacle_ahead = lane_clearance < 52 and 0.08 < lane_progress < 0.92
        touchline_clearance = min(
            destination.x - FIELD.left,
            FIELD.right - destination.x,
            destination.y - FIELD.top,
            FIELD.bottom - destination.y,
        )
        if touchline_clearance < 40:
            destination.x = clamp(destination.x, FIELD.left + 42, FIELD.right - 42)
            destination.y = clamp(destination.y, FIELD.top + 42, FIELD.bottom - 42)
        base_direction = safe_normalize(destination - owner.pos)
        perpendicular = Vec2(-base_direction.y, base_direction.x)
        pass_outcome = self.choose_pass_outcome(owner, pass_accuracy)
        if pass_outcome == PASS_DANGEROUS_LANE and closest_lane_opponent is None:
            pass_outcome = PASS_WRONG_DIRECTION
        if pass_outcome == PASS_WRONG_DIRECTION:
            wrong_angle = self.rng.choice((-1.0, 1.0)) * self.rng.uniform(17.0, 48.0)
            wrong_distance = distance * self.rng.uniform(0.82, 1.14)
            destination = owner.pos + base_direction.rotate(wrong_angle) * wrong_distance
        elif pass_outcome == PASS_DANGEROUS_LANE and closest_lane_opponent is not None:
            danger_point = closest_lane_opponent.pos + closest_lane_opponent.motion_velocity * 0.16
            destination = owner.pos + safe_normalize(danger_point - owner.pos) * distance
        error_scale = clamp(1.0 - pass_accuracy, 0.0, 1.0)
        if active_skill is PlayerCommand.SKILL_BLIND_FEED:
            error_scale *= 0.72 + (1.0 - passing) * 0.22
        error_sigma = (2.0 + distance * 0.025) * error_scale * owner.mistake_error_factor
        if pass_outcome == PASS_CLEAN:
            destination += perpendicular * self.rng.gauss(0, error_sigma)
        destination.x = clamp(destination.x, FIELD.left - 80, FIELD.right + 80)
        destination.y = clamp(destination.y, FIELD.top - 80, FIELD.bottom + 80)
        direction = safe_normalize(destination - owner.pos)
        target.issue_action(
            PlayerCommand.RECEIVE_PASS,
            destination,
            duration=max(0.45, route.flight_time + 0.28),
            force=True,
        )
        if pass_outcome == PASS_CLEAN:
            self.plan_combination_run(owner, target, destination, route.flight_time)
        self.ball.owner = None
        self.ball.flight_serial += 1
        self.ball.last_touch = owner
        self.ball.intended = target
        self.ball.catch_forbidden = False
        self.ball.last_keeper_response = ""
        self.ball.pass_outcome = pass_outcome
        self.ball.intended_destination.update(destination)
        self.pass_outcome_counts[pass_outcome] += 1
        self.ball.eye_contact_bonus = (
            clamp(0.18 + passing * 0.34 + target.effective_stat(target.trap_technique) * 0.18, 0.0, 0.62)
            if active_skill is PlayerCommand.SKILL_SIGNAL_LINK
            else 0.0
        )
        self.ball.pickup_lock = 0.18
        self.ball.pos.update(owner.pos + direction * 12)
        ideal_power = clamp(0.34 + distance / 470.0 + congestion * 0.16, 0.32, 1.0)
        judged_power = ideal_power * passing + self.rng.uniform(0.34, 1.0) * (1.0 - passing)
        ball_speed = clamp(150 + distance * 0.31 + kick_output * (62 + judged_power * 102), 175, 455)
        long_factor = clamp((distance - 180) / 220.0, 0.0, 1.0)
        touchline_difficulty = clamp((72 - route.touchline_margin) / 72.0, 0.0, 1.0)
        receiver_difficulty = clamp(-route.receiver_margin / 0.75, 0.0, 1.0)
        reception_difficulty = clamp(
            route.interception_risk * 0.48
            + touchline_difficulty * 0.30
            + receiver_difficulty * 0.34,
            0.0,
            1.0,
        )
        friendly_quality = clamp(
            passing * 0.36 + pass_accuracy * 0.28 + intelligence * 0.36,
            0.0,
            1.0,
        )
        self.ball.pass_brake = clamp(
            (long_factor * 0.20 + reception_difficulty * 0.72)
            * friendly_quality * (0.28 + intelligence * 0.72),
            0.0,
            0.88,
        )
        if route.receiver_margin < 0.0 and pass_outcome == PASS_CLEAN:
            ball_speed *= 1.0 - min(0.20, -route.receiver_margin * 0.18) * friendly_quality
        normal_power_error = self.rng.gauss(0.0, (1.0 - pass_accuracy) * 0.055)
        ball_speed *= clamp(1.0 + normal_power_error, 0.88, 1.12)
        if pass_outcome == PASS_OVERHIT:
            ball_speed *= self.rng.uniform(1.25, 1.48)
            self.ball.pass_brake = 0.0
        elif pass_outcome == PASS_UNDERHIT:
            ball_speed *= self.rng.uniform(0.54, 0.72)
            self.ball.pass_brake = max(self.ball.pass_brake, 0.36)
        elif pass_outcome in (PASS_WRONG_DIRECTION, PASS_DANGEROUS_LANE):
            self.ball.pass_brake *= 0.35
        if congestion > 0.55 or touchline_clearance < 52:
            ball_speed *= 0.92
        if owner.action_command is PlayerCommand.GOAL_KICK:
            ball_speed *= 0.86
        self.ball.vel = direction * ball_speed
        self.ball.z = 6.0
        loft_chance = 0.08 + long_factor * (0.48 + passing * 0.34)
        if obstacle_ahead:
            loft_chance += 0.26 + passing * 0.48
        if owner.action_command in (PlayerCommand.CROSS, PlayerCommand.CORNER_KICK, PlayerCommand.GOAL_KICK):
            loft_chance += 0.24
        loft_chance = clamp(loft_chance, 0.05, 0.97)
        curve_chance = (1.0 - loft_chance) * passing * congestion * 0.30
        style_roll = self.rng.random()
        if style_roll < loft_chance:
            pass_type = "高いパス"
        elif style_roll < loft_chance + curve_chance:
            pass_type = "カーブパス"
        else:
            pass_type = "グラウンダーパス"
        if active_skill is PlayerCommand.SKILL_BLIND_FEED:
            pass_type = "ブラインドフィード"
        elif active_skill is PlayerCommand.SKILL_SIGNAL_LINK:
            pass_type = "サイン連携パス"
        owner.last_pass_type = pass_type
        self.ball.flight_type = pass_type
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.shot_deception = 0.0
        if pass_type == "高いパス":
            loft_time = distance / max(230.0, ball_speed)
            if owner.action_command is PlayerCommand.GOAL_KICK:
                loft_time *= 1.08
            landing_arc = GRAVITY * loft_time * 0.50
            distance_lift = 18 + long_factor * (34 + passing * 32)
            ideal_loft = landing_arc + distance_lift
            if obstacle_ahead:
                obstacle_time = max(0.10, loft_time * lane_progress)
                clearance_height = 60 + passing * 28
                clearance_speed = (
                    clearance_height - self.ball.z + 0.5 * GRAVITY * obstacle_time * obstacle_time
                ) / obstacle_time
                ideal_loft = max(ideal_loft, clearance_speed)
            ideal_loft = clamp(ideal_loft, 92, 264)
            loft_error = (1.0 - pass_accuracy) * 38 * owner.mistake_error_factor
            self.ball.vertical_speed = clamp(ideal_loft + self.rng.gauss(0, loft_error), 54, 248)
        else:
            self.ball.vertical_speed = clamp(
                6 + self.rng.gauss(0, (1.0 - pass_accuracy) * 12 * owner.mistake_error_factor),
                0,
                30,
            )
        if pass_outcome == PASS_OVERHIT:
            self.ball.vertical_speed *= 1.12
        elif pass_outcome == PASS_UNDERHIT:
            self.ball.vertical_speed *= 0.72
        if pass_type == "カーブパス":
            lane_midpoint = owner.pos.lerp(destination, 0.5)
            curve_side = (
                -1.0 if closest_lane_opponent is not None and closest_lane_opponent.pos.y > lane_midpoint.y else 1.0
            )
            curve_error = self.rng.gauss(0, (1.0 - pass_accuracy) * 18 * owner.mistake_error_factor)
            self.ball.curve_acceleration = curve_side * clamp(18 + passing * 44 + curve_error, 8, 72)
        self.decision_timer = self.rng.uniform(0.35, 0.7)

    def choose_corner_counter_target(self, owner: Player) -> Player | None:
        """Occasionally turn a defensive corner clearance into a directed counter."""
        if self.corner_phase_timer <= 0.0 or owner.team is not self.corner_defending_team:
            return None
        candidates = [
            player for player in self.corner_counter_players
            if not player.sent_off and player is not owner
        ]
        if not candidates:
            return None
        intelligence = owner.effective_intelligence
        passing = owner.effective_stat(owner.passing_technique)
        tactic_bonus = 0.10 if owner.team.tactic in ("ATTACK", "ULTRA_ATTACK") else 0.0
        if self.rng.random() >= clamp(0.24 + intelligence * 0.34 + passing * 0.18 + tactic_bonus, 0.24, 0.82):
            return None

        opponents = [
            player for team in self.teams if team is not owner.team
            for player in team.players if not player.sent_off
        ]
        best: Player | None = None
        best_score = -9999.0
        for candidate in candidates:
            openness = min((opponent.pos.distance_to(candidate.pos) for opponent in opponents), default=180.0)
            progress = (candidate.pos.x - owner.pos.x) * owner.team.direction
            distance = owner.pos.distance_to(candidate.pos)
            score = openness * 0.64 + progress * 0.22 - distance * 0.035
            score += candidate.effective_stat(candidate.dash_speed) * 58
            score += candidate.run_into_space * 34
            score = perceived_utility(score, intelligence, self.rng, noise_span=34.0)
            if score > best_score:
                best_score, best = score, candidate
        return best

    def clear_destination(self, owner: Player, target: Player | None) -> Vec2:
        if target is not None:
            lead = 42 + target.effective_stat(target.dash_speed) * 46
            return Vec2(
                clamp(target.pos.x + owner.team.direction * lead, FIELD.left + 45, FIELD.right - 45),
                clamp(target.pos.y, FIELD.top + 45, FIELD.bottom - 45),
            )
        return Vec2(
            owner.pos.x + owner.team.direction * (
                245 + kick_power_output(owner.effective_stat(owner.pass_power)) * 180
            ),
            clamp(FIELD.centery + self.rng.uniform(-250, 250), FIELD.top + 40, FIELD.bottom - 40),
        )

    def clear_ball(self, owner: Player) -> bool:
        target = self.choose_corner_counter_target(owner)
        return self.begin_kick(
            owner,
            PlayerCommand.CLEAR,
            target_player=target,
            target_point=self.clear_destination(owner, target),
        )

    def _release_clear(self, owner: Player, target: Player | None = None) -> None:
        pass_power = owner.effective_stat(owner.pass_power)
        kick_output = kick_power_output(pass_power)
        if target is not None and (target.sent_off or target.team is not owner.team):
            target = None
        destination = self.clear_destination(owner, target)
        direction = safe_normalize(destination - owner.pos)
        distance = owner.pos.distance_to(destination)
        self.ball.owner = None
        self.ball.flight_serial += 1
        self.ball.last_touch = owner
        self.ball.intended = target
        self.ball.catch_forbidden = False
        self.ball.last_keeper_response = ""
        self.ball.pickup_lock = 0.24
        self.ball.pos.update(owner.pos + direction * 12)
        if target is not None:
            clearance_speed = clamp(315 + kick_output * 160 + distance * 0.055, 335, 555)
            self.ball.vel = direction * clearance_speed
        else:
            self.ball.vel = direction * (270 + kick_output * 120)
        self.ball.z = 7.0
        self.ball.vertical_speed = (
            clamp(108 + kick_output * 55 + distance * 0.035, 118, 205)
            if target is not None else 96 + kick_output * 40
        )
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.flight_type = "カウンタークリア" if target is not None else "クリア"
        self.ball.shot_deception = 0.0
        self.ball.eye_contact_bonus = 0.0
        if target is not None:
            target.issue_action(PlayerCommand.RECEIVE_PASS, destination, duration=1.45, force=True)
            self.counterattack_timer[owner.team] = max(self.counterattack_timer[owner.team], 3.8)
            self.add_event(f"{owner.name}が中央へカウンタークリア")
        self.decision_timer = 0.6

    def choose_shot_skill(self, owner: Player) -> None:
        if owner.skill_command is not PlayerCommand.IDLE:
            return
        goal_x = FIELD.right if owner.team.direction == 1 else FIELD.left
        distance = abs(goal_x - owner.pos.x)
        intelligence = owner.effective_intelligence
        shooting = owner.effective_stat(owner.shooting_technique)
        accuracy = owner.effective_stat(owner.shot_accuracy)
        options: dict[PlayerCommand, float] = {PlayerCommand.SHOOT: 0.48}
        if owner.has_skill(ARC_CURVE):
            angle = clamp(abs(owner.pos.y - FIELD.centery) / 250.0, 0.0, 1.0)
            options[PlayerCommand.SKILL_ARC_CURVE] = 0.36 + angle * 0.30 + shooting * 0.18
        if owner.has_skill(WOBBLE_BALL):
            long_range = clamp((distance - 150) / 260.0, 0.0, 1.0)
            options[PlayerCommand.SKILL_WOBBLE_BALL] = 0.34 + long_range * 0.34 + shooting * 0.16
        if owner.has_skill(CHANCE_SENSOR):
            good_range = clamp(1.0 - distance / 360.0, 0.0, 1.0)
            options[PlayerCommand.SKILL_CHANCE_SENSOR] = 0.38 + good_range * 0.30 + intelligence * 0.15
        selected = choose_utility_action(options, intelligence, self.rng)
        skill_by_command = {
            PlayerCommand.SKILL_ARC_CURVE: ARC_CURVE,
            PlayerCommand.SKILL_WOBBLE_BALL: WOBBLE_BALL,
            PlayerCommand.SKILL_CHANCE_SENSOR: CHANCE_SENSOR,
        }
        skill = skill_by_command.get(selected)
        if skill is not None:
            self.try_activate_player_skill(
                owner,
                skill,
                options[selected],
                (shooting + accuracy) * 0.5,
                duration=owner.kick_contact_time + 0.42,
            )

    def shoot(self, owner: Player) -> bool:
        self.choose_shot_skill(owner)
        goal_x = FIELD.right + 8 if owner.team.direction == 1 else FIELD.left - 8
        return self.begin_kick(owner, PlayerCommand.SHOOT, target_point=(goal_x, FIELD.centery))

    def choose_shot_outcome(
        self,
        owner: Player,
        shot_accuracy: float,
        shooting: float,
        distance_to_goal: float,
    ) -> str:
        """Choose a readable shot result while keeping player stats decisive."""
        execution = clamp(
            shot_accuracy * 0.72 + shooting * 0.18 + owner.effective_intelligence * 0.10,
            0.0,
            1.0,
        )
        distance_pressure = clamp((distance_to_goal - 120.0) / 680.0, 0.0, 1.0)
        post_chance = clamp(0.022 + (1.0 - execution) * 0.055 + shooting * 0.012, 0.025, 0.095)
        miss_chance = clamp(
            0.028
            + (1.0 - execution) * (0.34 + distance_pressure * 0.24) * owner.mistake_error_factor,
            0.025,
            0.68,
        )
        roll = self.rng.random()
        if roll < post_chance:
            return SHOT_POST
        if roll >= post_chance + miss_chance:
            return SHOT_ON_TARGET

        miss_roll = self.rng.random()
        if miss_roll < 0.33:
            return SHOT_WIDE
        if miss_roll < 0.70:
            return SHOT_KEEPER_FRIENDLY
        return SHOT_OVER

    def _release_shot(self, owner: Player, set_piece_skill: float = 0.0) -> None:
        goal_x = FIELD.right + 8 if owner.team.direction == 1 else FIELD.left - 8
        distance_to_goal = abs(goal_x - owner.pos.x)
        shot_accuracy = owner.effective_stat(owner.shot_accuracy)
        shot_power = owner.effective_stat(owner.shot_power)
        kick_output = kick_power_output(shot_power)
        shooting = max(owner.effective_stat(owner.shooting_technique), set_piece_skill)
        intelligence = owner.effective_intelligence
        active_skill = owner.skill_command
        defending = self.away if owner.team is self.home else self.home
        keeper = defending.keeper
        open_side = -1.0 if keeper.pos.y >= FIELD.centery else 1.0
        read_skill = blended_judgment(shooting, intelligence, 0.68)
        correct_read_chance = 0.50 + shooting * 0.45
        if active_skill is PlayerCommand.SKILL_CHANCE_SENSOR:
            correct_read_chance = 0.68 + read_skill * 0.29
        if self.rng.random() > correct_read_chance:
            open_side *= -1.0
        corner_offset = GOAL_HALF_HEIGHT * (0.30 + read_skill * 0.40)
        planned_y = FIELD.centery + open_side * corner_offset
        accuracy_factor = 1.18 - shot_accuracy * 0.92
        accuracy = (42 + distance_to_goal * 0.17) * accuracy_factor * owner.mistake_error_factor
        shot_outcome = self.choose_shot_outcome(owner, shot_accuracy, shooting, distance_to_goal)
        if shot_outcome == SHOT_WIDE:
            miss_side = open_side if self.rng.random() < 0.64 else -open_side
            wide_distance = self.rng.uniform(14.0, 34.0 + accuracy * 0.28)
            target_y = FIELD.centery + miss_side * (GOAL_HALF_HEIGHT + wide_distance)
        elif shot_outcome == SHOT_POST:
            post_side = open_side if self.rng.random() < 0.72 else -open_side
            target_y = FIELD.centery + post_side * GOAL_HALF_HEIGHT
        elif shot_outcome == SHOT_KEEPER_FRIENDLY:
            target_y = clamp(
                keeper.pos.y + self.rng.gauss(0.0, 5.0 + accuracy * 0.06),
                FIELD.centery - GOAL_HALF_HEIGHT + 13,
                FIELD.centery + GOAL_HALF_HEIGHT - 13,
            )
        else:
            spread_scale = 0.18 if shot_outcome == SHOT_OVER else 0.28
            target_y = clamp(
                planned_y + self.rng.gauss(0, accuracy * spread_scale),
                FIELD.centery - GOAL_HALF_HEIGHT + 10,
                FIELD.centery + GOAL_HALF_HEIGHT - 10,
            )
        direct_corner = active_skill is PlayerCommand.SKILL_ARC_CURVE and owner.action_command is PlayerCommand.CORNER_KICK
        aim_x = goal_x - owner.team.direction * 120 if direct_corner else goal_x
        direction = safe_normalize(Vec2(aim_x, target_y) - owner.pos)
        self.ball.owner = None
        self.ball.flight_serial += 1
        self.ball.last_touch = owner
        self.ball.intended = None
        self.ball.eye_contact_bonus = 0.0
        self.ball.shot_outcome = shot_outcome
        self.ball.shot_miss_announced = False
        self.ball.pickup_lock = 0.22
        self.ball.pos.update(owner.pos + direction * 13)
        ideal_power = clamp(0.54 + distance_to_goal / 520.0, 0.54, 1.0)
        judged_power = ideal_power * shooting + self.rng.uniform(0.48, 1.0) * (1.0 - shooting)
        shot_speed = clamp(300 + kick_output * (135 + judged_power * 82) + self.rng.uniform(-10, 10), 310, 545)
        if active_skill is PlayerCommand.SKILL_HALFWAY_CANNON:
            shot_speed = clamp(shot_speed * (1.10 + kick_output * 0.09), 365, 620)
        elif active_skill is PlayerCommand.SKILL_CANNON_MIDDLE:
            shot_speed = clamp(shot_speed * (1.14 + kick_output * 0.11), 385, 645)
        elif active_skill is PlayerCommand.SKILL_LAST_CHANCE_CANNON:
            shot_speed = clamp(shot_speed * (1.07 + kick_output * 0.07), 350, 600)
        self.ball.vel = direction * shot_speed * 0.93
        self.ball.z = 6.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.knuckle_phase = 0.0
        choice = self.rng.random()
        lob_chance = shooting * (0.18 if distance_to_goal < 235 else 0.08)
        curve_chance = shooting * 0.36
        if active_skill is PlayerCommand.SKILL_ARC_CURVE:
            shot_type = "アークカーブ"
            target_height = GOAL_HEIGHT * (0.43 + shooting * 0.18)
            arc_bonus = 18 + shooting * 20
        elif active_skill is PlayerCommand.SKILL_WOBBLE_BALL:
            shot_type = "揺らぎ弾"
            target_height = GOAL_HEIGHT * (0.40 + shooting * 0.18)
            arc_bonus = 9 + shooting * 14
        elif active_skill is PlayerCommand.SKILL_MAGIC_PLACE_KICK:
            shot_type = "魔術師のプレースキック"
            target_height = GOAL_HEIGHT * (0.46 + shooting * 0.18)
            arc_bonus = 20 + shooting * 24
        elif active_skill is PlayerCommand.SKILL_SLIDE_FINISH:
            shot_type = "スライドフィニッシュ"
            target_height = GOAL_HEIGHT * (0.30 + shooting * 0.18)
            arc_bonus = shooting * 7
        elif active_skill is PlayerCommand.SKILL_CHANCE_SENSOR:
            shot_type = "嗅覚シュート"
            target_height = GOAL_HEIGHT * (0.34 + shooting * 0.19)
            arc_bonus = shooting * 9
        elif active_skill is PlayerCommand.SKILL_CARRY_SHOT:
            shot_type = "キャリーショット"
            target_height = GOAL_HEIGHT * (0.31 + shooting * 0.18)
            arc_bonus = 5 + shooting * 8
        elif active_skill is PlayerCommand.SKILL_HALFWAY_CANNON:
            shot_type = "ハーフウェイ砲"
            target_height = GOAL_HEIGHT * (0.52 + shooting * 0.15)
            arc_bonus = 24 + shooting * 28
        elif active_skill is PlayerCommand.SKILL_CANNON_MIDDLE:
            shot_type = "キャノンミドル"
            target_height = GOAL_HEIGHT * (0.40 + shooting * 0.16)
            arc_bonus = 12 + shooting * 16
        elif active_skill is PlayerCommand.SKILL_LAST_CHANCE_CANNON:
            shot_type = "ラストチャンス砲"
            target_height = GOAL_HEIGHT * (0.48 + shooting * 0.16)
            arc_bonus = 20 + shooting * 24
        elif active_skill is PlayerCommand.SKILL_DIRECT_VOLLEY:
            shot_type = "ダイレクトボレー"
            target_height = GOAL_HEIGHT * (0.42 + shooting * 0.17)
            arc_bonus = 16 + shooting * 20
        elif active_skill is PlayerCommand.SKILL_SET_AND_SHOOT:
            shot_type = "セット＆シュート"
            target_height = GOAL_HEIGHT * (0.38 + shooting * 0.17)
            arc_bonus = 9 + shooting * 14
        elif owner.shadow_striker_timer > 0.0:
            shot_type = "背後の狩人シュート"
            target_height = GOAL_HEIGHT * (0.33 + shooting * 0.18)
            arc_bonus = 6 + shooting * 9
        elif choice < lob_chance:
            shot_type = "シュート・ループ"
            target_height = GOAL_HEIGHT * 0.72
            arc_bonus = 82 + shooting * 54
        elif choice < lob_chance + curve_chance:
            shot_type = "シュート・カーブ"
            target_height = GOAL_HEIGHT * (0.42 + shooting * 0.18)
            arc_bonus = 13 + shooting * 16
        elif shooting > 0.58 and shot_power > 0.58 and distance_to_goal > 205:
            shot_type = "シュート・ロング"
            target_height = GOAL_HEIGHT * (0.48 + shooting * 0.16)
            arc_bonus = 8 + shooting * 13
        else:
            shot_type = "シュート・通常"
            target_height = GOAL_HEIGHT * (0.34 + shooting * 0.19)
            arc_bonus = shooting * 9

        if shot_outcome == SHOT_OVER:
            target_height = GOAL_HEIGHT + self.rng.uniform(14.0, 40.0 + (1.0 - shot_accuracy) * 24.0)
        elif shot_outcome == SHOT_POST:
            target_height = GOAL_HEIGHT * self.rng.uniform(0.24, 0.68)
        elif shot_outcome == SHOT_KEEPER_FRIENDLY:
            target_height = GOAL_HEIGHT * self.rng.uniform(0.25, 0.43)
        elif shot_outcome == SHOT_WIDE:
            target_height = GOAL_HEIGHT * self.rng.uniform(0.28, 0.62)

        shot_flight_time = max(0.16, distance_to_goal / max(80.0, abs(self.ball.vel.x)))
        desired_goal_height = target_height + arc_bonus * 0.08
        ideal_height = (
            desired_goal_height - self.ball.z + 0.5 * GRAVITY * shot_flight_time * shot_flight_time
        ) / shot_flight_time
        height_error = (1.0 - shot_accuracy) * 12 * owner.mistake_error_factor
        if shot_outcome in (SHOT_POST, SHOT_OVER):
            height_error *= 0.22
        self.ball.vertical_speed = clamp(ideal_height + self.rng.gauss(0, height_error), 22, 320)
        self.ball.curve_acceleration = 0.0
        if shot_type == "シュート・カーブ":
            curve_error = self.rng.gauss(0, (1.0 - shot_accuracy) * 22 * owner.mistake_error_factor)
            self.ball.curve_acceleration = open_side * clamp(24 + shooting * 58 + curve_error, 10, 90)
        elif shot_type in ("アークカーブ", "魔術師のプレースキック"):
            curve_error = self.rng.gauss(0, (1.0 - shot_accuracy) * 28 * owner.mistake_error_factor)
            perpendicular = Vec2(-direction.y, direction.x)
            curve_strength = clamp(48 + shooting * 88 + curve_error, 28, 145)
            self.ball.curve_vector = perpendicular * open_side * curve_strength
            if direct_corner:
                self.ball.curve_vector.x += owner.team.direction * (390 + shooting * 170)
        elif shot_type == "揺らぎ弾":
            self.ball.knuckle_amplitude = 42 + shooting * 68
        owner.last_shot_type = shot_type
        self.ball.flight_type = shot_type
        deception_bonus = 0.16 if active_skill in (
            PlayerCommand.SKILL_CHANCE_SENSOR,
            PlayerCommand.SKILL_WOBBLE_BALL,
            PlayerCommand.SKILL_ARC_CURVE,
            PlayerCommand.SKILL_MAGIC_PLACE_KICK,
            PlayerCommand.SKILL_CARRY_SHOT,
            PlayerCommand.SKILL_HALFWAY_CANNON,
            PlayerCommand.SKILL_CANNON_MIDDLE,
            PlayerCommand.SKILL_LAST_CHANCE_CANNON,
            PlayerCommand.SKILL_DIRECT_VOLLEY,
            PlayerCommand.SKILL_SET_AND_SHOOT,
        ) else 0.0
        if owner.shadow_striker_timer > 0.0:
            deception_bonus += 0.12
            owner.shadow_striker_timer = 0.0
        self.ball.shot_deception = clamp(shooting * owner.technique_success_factor + deception_bonus * read_skill, 0.0, 1.0)
        if shot_outcome == SHOT_KEEPER_FRIENDLY:
            self.ball.shot_deception *= 0.32
        self.ball.catch_forbidden = active_skill is PlayerCommand.SKILL_CANNON_MIDDLE
        self.ball.last_keeper_response = ""
        self.ball.shot_serial += 1
        self.shot_outcome_counts[shot_outcome] += 1
        owner.team.shots += 1
        owner.adjust_confidence(0.008)
        self.add_event(f"{owner.name}の{shot_type}！")

    def update_owner_decision(self, dt: float) -> None:
        owner = self.ball.owner
        if owner is None:
            return
        decision_dt = dt / self.ai_rethink_multiplier
        normal_offset = Vec2(owner.team.direction * 10, 0)
        if owner.cruyff_timer > 0.0:
            phase = clamp(1.0 - owner.cruyff_timer / 0.72, 0.0, 1.0)
            turn_offset = normal_offset.rotate((180.0 if owner.cruyff_direction.y >= 0 else -180.0) * phase)
            self.ball.control_offset += (turn_offset - self.ball.control_offset) * min(1.0, dt * 14.0)
        elif owner.razor_dribble_timer > 0.0:
            tight_offset = Vec2(owner.team.direction * 4.2, 0)
            self.ball.control_offset += (tight_offset - self.ball.control_offset) * min(1.0, dt * 15.0)
        elif owner.roulette_timer > 0.0:
            phase = clamp(1.0 - owner.roulette_timer / 0.68, 0.0, 1.0)
            rotation_sign = 1.0 if owner.roulette_direction.y >= 0.0 else -1.0
            roulette_offset = normal_offset.rotate(rotation_sign * 360.0 * phase)
            self.ball.control_offset += (roulette_offset - self.ball.control_offset) * min(1.0, dt * 13.0)
        else:
            self.ball.control_offset += (normal_offset - self.ball.control_offset) * min(1.0, dt * 6.5)
        self.ball.pos.update(owner.pos + self.ball.control_offset)
        self.ball.z = 5.0
        if owner.is_keeper and self.ball.last_keeper_response == "CATCH":
            held_offset = Vec2(owner.team.direction * 2.5, 0)
            self.ball.pos.update(owner.pos + held_offset)
            self.ball.z = 30.0 * PLAYER_VISUAL_SCALE
        self.ball.vertical_speed = 0.0
        if self.pending_kick is not None:
            return
        if owner.one_trap_shot_timer > 0.0 and not owner.is_keeper:
            if self.begin_kick(
                owner,
                PlayerCommand.SHOOT,
                target_point=(FIELD.right if owner.team.direction == 1 else FIELD.left, FIELD.centery),
                display_command=PlayerCommand.SKILL_SET_AND_SHOOT,
            ):
                owner.kick_motion_duration *= 0.72
                owner.one_trap_shot_timer = 0.0
            return
        if owner.is_keeper:
            self.decision_timer -= decision_dt
            if self.decision_timer <= 0:
                self.distribute_keeper_ball(owner)
            return

        opponents = [
            player for player in (self.away.players if owner.team is self.home else self.home.players)
            if not player.sent_off
        ]
        nearest_pressure = min(opponent.pos.distance_to(owner.pos) for opponent in opponents)
        if self.corner_phase_timer > 0.0 and owner.team is self.corner_defending_team:
            # A defender winning the corner is allowed to clear early instead of
            # trying to dribble out of a crowded box.  clear_ball may then select
            # one of the deliberately retained midfield outlets.
            urgent_corner_clear = nearest_pressure < 92 or self.rng.random() < 0.22
            if urgent_corner_clear and self.clear_ball(owner):
                return
        distance_to_goal = FIELD.right - owner.pos.x if owner.team.direction == 1 else owner.pos.x - FIELD.left
        self.decision_timer -= decision_dt
        if nearest_pressure < 110:
            # A threatened holder reassesses immediately. Intelligence makes
            # the reaction faster but never makes a low-intelligence player
            # stand still until the ball is taken.
            pressure_wait = 0.025 + (1.0 - owner.effective_intelligence) * 0.075
            pressure_wait += clamp(nearest_pressure / 110.0, 0.0, 1.0) * 0.055
            self.decision_timer = min(self.decision_timer, pressure_wait)
        if distance_to_goal < 85:
            self.decision_timer = min(self.decision_timer, 0.035)
        stale_possession = clamp((self.possession_stagnation - 1.0) / 5.0, 0.0, 1.0)
        if stale_possession > 0.0:
            # Reconsider sooner when possession has stopped progressing. This is
            # still intelligence-weighted utility selection, not a forced pass.
            self.decision_timer = min(
                self.decision_timer,
                0.08 + (1.0 - owner.effective_intelligence) * 0.12,
            )
        if self.decision_timer > 0:
            return
        centrality = abs(owner.pos.y - FIELD.centery)
        settings = owner.team.tactical_settings(owner)
        shooting = owner.effective_stat(owner.shooting_technique)
        shot_power = owner.effective_stat(owner.shot_power)
        intelligence = owner.effective_intelligence
        shooting_decision = blended_judgment(shooting, intelligence, 0.72)
        shoot_distance = (
            settings["shoot_distance"] + shooting_decision * 70
            + kick_power_output(shot_power) * shooting_decision * 46
        )
        remaining_match_time = MATCH_SECONDS - self.game_time
        if owner.skill_command is PlayerCommand.IDLE and remaining_match_time <= 55.0:
            buzzer_situation = clamp(0.54 + (55.0 - remaining_match_time) / 62.0, 0.54, 1.0)
            buzzer_execution = (shooting + owner.effective_stat(owner.shot_accuracy) + shot_power) / 3.0
            if self.try_activate_player_skill(
                owner,
                LAST_CHANCE_CANNON,
                buzzer_situation,
                buzzer_execution,
                duration=owner.kick_contact_time + 0.82,
            ):
                if self.begin_kick(
                    owner,
                    PlayerCommand.SHOOT,
                    target_point=(FIELD.right if owner.team.direction == 1 else FIELD.left, FIELD.centery),
                    display_command=PlayerCommand.SKILL_LAST_CHANCE_CANNON,
                ):
                    return
        if owner.skill_command is PlayerCommand.IDLE:
            simulation_execution = clamp(intelligence * 0.82 + owner.confidence * 0.18, 0.0, 1.0)
            if self.try_activate_player_skill(
                owner,
                FUTURE_READ,
                0.62 + owner.confidence * 0.10,
                simulation_execution,
                duration=0.92,
            ):
                owner.simulation_timer = 0.92
        if owner.skill_command is PlayerCommand.IDLE:
            special_shots: dict[str, float] = {}
            if owner.has_skill(CARRY_SHOT) and distance_to_goal < shoot_distance + 58:
                special_shots[CARRY_SHOT] = 0.34 + shooting_decision * 0.40 + clamp((shoot_distance + 58 - distance_to_goal) / 240.0, 0.0, 0.22)
            if owner.has_skill(HALFWAY_CANNON) and shoot_distance + 70 < distance_to_goal < FIELD.width * 0.62 and centrality < 185:
                long_setup = clamp(1.0 - abs(distance_to_goal - FIELD.width * 0.47) / 360.0, 0.0, 1.0)
                special_shots[HALFWAY_CANNON] = 0.28 + long_setup * 0.38 + shooting_decision * 0.24
            if owner.has_skill(CANNON_MIDDLE) and 235 < distance_to_goal < 470 and centrality < 205:
                middle_setup = clamp(1.0 - abs(distance_to_goal - 335) / 210.0, 0.0, 1.0)
                special_shots[CANNON_MIDDLE] = 0.32 + middle_setup * 0.40 + shooting_decision * 0.22
            if special_shots:
                selected_shot = choose_utility_action(special_shots, intelligence, self.rng)
                if self.try_activate_player_skill(
                    owner,
                    selected_shot,
                    special_shots[selected_shot],
                    (shooting + owner.effective_stat(owner.shot_accuracy) + shot_power) / 3.0,
                    duration=owner.kick_contact_time + 0.62,
                ):
                    goal_x = FIELD.right + 8 if owner.team.direction == 1 else FIELD.left - 8
                    if self.begin_kick(owner, PlayerCommand.SHOOT, target_point=(goal_x, FIELD.centery)):
                        if selected_shot == CARRY_SHOT:
                            owner.kick_motion_duration *= 0.48
                        return
        shot_available = distance_to_goal < shoot_distance and centrality < 210
        if shot_available:
            range_quality = clamp(1.0 - distance_to_goal / max(1.0, shoot_distance), 0.0, 1.0)
            angle_quality = clamp(1.0 - centrality / 235.0, 0.0, 1.0)
            shot_utility = (
                0.25
                + range_quality * 0.55
                + angle_quality * 0.15
                + shooting_decision * 0.13
            ) * settings["shot_bias"]
            if owner.shadow_striker_timer > 0.0:
                shot_utility += 0.28
            lane_quality = self.shot_lane_quality(owner, opponents)
            shot_utility += lane_quality * (0.10 + intelligence * 0.20)
            shot_utility -= (1.0 - lane_quality) * (0.12 + intelligence * 0.26)
            goalkeeper = next((opponent for opponent in opponents if opponent.is_keeper), None)
            if goalkeeper is not None:
                keeper_position_error = clamp(abs(goalkeeper.pos.y - FIELD.centery) / 125.0, 0.0, 1.0)
                keeper_quality = goalkeeper.effective_stat(goalkeeper.goal_stopping)
                shot_utility += keeper_position_error * shooting_decision * 0.14
                shot_utility -= keeper_quality * (1.0 - range_quality) * intelligence * 0.10
        else:
            shot_utility = -0.35

        target = self.choose_pass_target(owner)
        route: PassRoute | None = None
        if target is not None:
            if self._selected_pass_owner is owner and self._selected_pass_target is target:
                route = self._selected_pass_route
            if route is None:
                route = self.evaluate_pass_route(owner, target)
            opponents = [
                player for player in (self.away.players if owner.team is self.home else self.home.players)
                if not player.sent_off
            ]
            openness = min(opponent.pos.distance_to(target.pos) for opponent in opponents)
            progress = (target.pos.x - owner.pos.x) * owner.team.direction
            pass_utility = 0.34 + clamp(openness / 145.0, 0.0, 1.0) * 0.25
            pass_utility += clamp(progress / 260.0, -0.18, 0.22)
            pass_utility -= route.interception_risk * (0.20 + intelligence * 0.52)
            pass_utility += clamp(route.receiver_margin + 0.12, -0.20, 0.42) * (0.12 + intelligence * 0.24)
            if route.touchline_margin < 54:
                pass_utility -= (54 - route.touchline_margin) / 150.0 * (0.12 + intelligence * 0.26)
        else:
            pass_utility = -0.30
        conservation = owner.stamina_conservation
        if target is not None and conservation > 0.0:
            pass_utility += conservation * (0.38 + owner.stamina_management * 0.34)

        if owner.skill_command is PlayerCommand.IDLE and nearest_pressure < 105:
            no_look_target = self.choose_no_look_target(owner)
            if no_look_target is not None:
                no_look_execution = blended_judgment(
                    owner.effective_stat(owner.passing_technique),
                    intelligence,
                    0.72,
                )
                if self.try_activate_player_skill(
                    owner,
                    BLIND_FEED,
                    0.38 + clamp((105 - nearest_pressure) / 145.0, 0.0, 0.42),
                    no_look_execution,
                    duration=owner.kick_contact_time + 0.56,
                ) and self.pass_ball(owner, no_look_target):
                    return
        dribble_quality = blended_judgment(
            owner.effective_stat(owner.dribble_technique),
            intelligence,
            0.72,
        )
        dribble_utility = 0.24 + settings["dribble"] * 0.72 + dribble_quality * 0.16
        dribble_utility += clamp((distance_to_goal - 260) / 500.0, 0.0, 0.16)
        dribble_utility -= clamp((72 - nearest_pressure) / 110.0, 0.0, 0.28)
        if conservation > 0.0:
            dribble_utility -= conservation * (0.42 + owner.stamina_management * 0.28)

        pressure_urgency = clamp((110 - nearest_pressure) / 86.0, 0.0, 1.0)
        pass_risk_penalty, dribble_risk_penalty = strategic_possession_risk(
            intelligence,
            self.team_progress(owner.team, owner.pos.x),
            pressure_urgency,
            dribble_quality,
            route.interception_risk if route is not None else 0.0,
        )
        pass_utility -= pass_risk_penalty
        dribble_utility -= dribble_risk_penalty
        if pressure_urgency > 0.0:
            # Under a tackle threat all useful exits become more urgent. Good
            # dribblers may take the opponent on; others release the ball.
            pass_utility += pressure_urgency * (0.25 + intelligence * 0.12)
            dribble_utility += pressure_urgency * (dribble_quality * 0.30 - 0.10)
            if distance_to_goal < shoot_distance * 1.22 and centrality < 230:
                shot_utility += pressure_urgency * (0.18 + shooting_decision * 0.16)

        if distance_to_goal < 85:
            if centrality <= GOAL_HALF_HEIGHT * 1.35:
                shot_utility += 0.42
            else:
                # From beside the goal, prefer a cut-back pass or a turn toward
                # the middle over running along the end line toward the corner.
                pass_utility += 0.34
                dribble_utility += 0.18 + dribble_quality * 0.12
                shot_utility -= 0.22
        if owner.post_play_timer > 0.0 and target is not None:
            pass_utility += 0.34
            dribble_utility -= 0.20

        if stale_possession > 0.0:
            if target is not None:
                pass_utility += stale_possession * (0.22 + intelligence * 0.30)
            dribble_utility += stale_possession * (0.10 + dribble_quality * 0.18)
            if shot_available:
                shot_utility += stale_possession * shooting_decision * 0.16

        confidence_drive = owner.confidence - 0.50
        shot_utility += confidence_drive * 0.30
        dribble_utility += confidence_drive * 0.20
        pass_utility -= confidence_drive * 0.06
        decision_intelligence = intelligence
        if owner.simulation_timer > 0.0:
            # A shallow rollout: estimate the next dribble location and the
            # receiver's immediate pressure without running a full search tree.
            projected = self.open_space_target(owner, owner.pos, 86)
            future_pressure = min(opponent.pos.distance_to(projected) for opponent in opponents)
            dribble_utility += clamp((future_pressure - nearest_pressure) / 230.0, -0.16, 0.22)
            if target is not None:
                receiver_pressure = min(opponent.pos.distance_to(target.pos) for opponent in opponents)
                pass_utility += clamp((receiver_pressure - 54) / 360.0, -0.08, 0.18)
            future_goal_distance = abs((FIELD.right if owner.team.direction == 1 else FIELD.left) - projected.x)
            shot_utility += clamp((distance_to_goal - future_goal_distance) / 420.0, -0.06, 0.14)
            decision_intelligence = clamp(intelligence + 0.24, 0.0, 1.0)

        action = choose_utility_action(
            {
                PlayerCommand.SHOOT: shot_utility,
                PlayerCommand.PASS: pass_utility,
                PlayerCommand.DRIBBLE: dribble_utility,
            },
            decision_intelligence,
            self.rng,
        )
        if action is PlayerCommand.SHOOT and self.shoot(owner):
            return
        if action is PlayerCommand.PASS and target is not None and self.pass_ball(owner, target, route):
            return
        if pressure_urgency > 0.0 or distance_to_goal < 85:
            self.decision_timer = self.rng.uniform(0.12, 0.28)
        else:
            self.decision_timer = self.rng.uniform(0.38, 0.72) * (1.0 - conservation * 0.56)

    def resolve_keeper_contact(self, keeper: Player, incoming_speed: float, guardian: bool = False) -> bool:
        if not self.keeper_can_use_hands(keeper):
            return False
        stopping = keeper.effective_stat(keeper.goal_stopping)
        trapping = keeper.effective_stat(keeper.trap_technique)
        intelligence = keeper.effective_intelligence
        catch_allowed = not self.ball.catch_forbidden
        response_utilities = {
            PlayerCommand.CATCH: 0.46 + stopping * 0.43 + keeper.confidence * 0.13 - incoming_speed / 1500.0,
            PlayerCommand.PUNCH: 0.12 + stopping * 0.28 + incoming_speed / 1250.0 + self.ball.shot_deception * 0.18,
            PlayerCommand.TRAP: 0.20 + trapping * 0.45 - incoming_speed / 1180.0,
        }
        if not catch_allowed:
            response_utilities[PlayerCommand.CATCH] = -2.0
            response_utilities[PlayerCommand.TRAP] = -1.0
            response_utilities[PlayerCommand.PUNCH] += 0.46
        if self.ball.z > 28:
            response_utilities[PlayerCommand.PUNCH] += 0.16
            response_utilities[PlayerCommand.TRAP] -= 0.30
        else:
            response_utilities[PlayerCommand.CATCH] += 0.12
            response_utilities[PlayerCommand.PUNCH] -= 0.10
        if self.ball.z < 10 and incoming_speed < 180 and catch_allowed:
            response_utilities[PlayerCommand.TRAP] += 0.42
            response_utilities[PlayerCommand.CATCH] -= 0.10
        response = choose_utility_action(response_utilities, intelligence, self.rng)
        contact_point = Vec2(self.ball.pos)
        if response is PlayerCommand.PUNCH:
            counter_target = self.choose_corner_counter_target(keeper)
            if counter_target is not None:
                destination = self.clear_destination(keeper, counter_target)
                outward = safe_normalize(destination - keeper.pos)
            else:
                goal_y_delta = self.ball.pos.y - FIELD.centery
                outward = Vec2(keeper.team.direction, clamp(goal_y_delta / 95.0, -0.78, 0.78))
                outward = safe_normalize(outward)
            self.ball.owner = None
            self.ball.last_touch = keeper
            self.ball.intended = counter_target
            self.ball.pickup_lock = 0.24
            self.ball.pos.update(keeper.pos + outward * 16)
            punch_speed = 235 + stopping * 150 + incoming_speed * 0.16
            if counter_target is not None:
                punch_speed = max(punch_speed, 390 + stopping * 110)
            self.ball.vel = outward * punch_speed
            self.ball.z = max(10.0, min(self.ball.z, 48.0))
            self.ball.vertical_speed = 58 + stopping * 54
            self.ball.curve_acceleration = 0.0
            self.ball.curve_vector.update(0, 0)
            self.ball.knuckle_amplitude = 0.0
            self.ball.flight_type = "GKカウンターパンチ" if counter_target is not None else "GKパンチング"
            self.ball.shot_outcome = ""
            self.ball.shot_miss_announced = False
            self.ball.catch_forbidden = False
            self.ball.last_keeper_response = "PUNCH"
            self.keeper_response_counts["PUNCH"] += 1
            keeper.spend_stamina(PlayerCommand.PUNCH)
            if counter_target is not None:
                counter_target.issue_action(PlayerCommand.RECEIVE_PASS, counter_target.pos, duration=1.25, force=True)
                self.counterattack_timer[keeper.team] = max(self.counterattack_timer[keeper.team], 3.4)
            keeper.issue_action(
                PlayerCommand.SKILL_SAVING_AURA if guardian else PlayerCommand.PUNCH,
                contact_point,
                force=True,
            )
            keeper.use_technique(PlayerCommand.PUNCH)
            keeper.adjust_confidence(0.035)
            self.add_event(f"{keeper.name}がパンチング！")
            return True

        control_offset = (keeper.team.direction * 7, 0) if response is PlayerCommand.TRAP else None
        self.change_owner(keeper, control_offset)
        self.ball.last_keeper_response = "TRAP" if response is PlayerCommand.TRAP else "CATCH"
        self.keeper_response_counts[self.ball.last_keeper_response] += 1
        action = PlayerCommand.SKILL_SAVING_AURA if guardian else response
        keeper.spend_stamina(PlayerCommand.TRAP if response is PlayerCommand.TRAP else PlayerCommand.CATCH)
        keeper.issue_action(action, contact_point, force=True)
        keeper.use_technique(PlayerCommand.TRAP if response is PlayerCommand.TRAP else PlayerCommand.SAVE)
        keeper.adjust_confidence(0.045 if response is PlayerCommand.CATCH else 0.025)
        label = "キャッチ" if response is PlayerCommand.CATCH else "足元へトラップ"
        self.add_event(f"{keeper.name}が{label}！")
        return True

    def keeper_save(self) -> bool:
        if self.ball.owner is not None or self.ball.vel.length() < 170:
            return False
        defending = self.home if self.ball.vel.x < 0 else self.away
        keeper = defending.keeper
        if not self.keeper_can_use_hands(keeper):
            return False
        distance = keeper.pos.distance_to(self.ball.pos)
        guardian = False
        guardian_consider_range = 50 * PLAYER_VISUAL_SCALE
        if distance < guardian_consider_range and keeper.skill_command is PlayerCommand.IDLE:
            guardian_execution = blended_judgment(
                keeper.effective_stat(keeper.goal_stopping) * 0.72
                + keeper.effective_stat(keeper.jump_accuracy) * 0.28,
                keeper.effective_intelligence,
                0.76,
            )
            guardian = self.try_activate_player_skill(
                keeper,
                SAVING_AURA,
                0.40 + clamp((guardian_consider_range - distance) / max(1.0, guardian_consider_range), 0.0, 0.42),
                guardian_execution,
                duration=0.72,
            )
        contact_radius = (48 if guardian else 32) * PLAYER_VISUAL_SCALE
        keeper_reach = keeper.z + (88 if guardian else 70 if keeper.airborne else 54) * PLAYER_VISUAL_SCALE
        if distance >= contact_radius or self.ball.z > keeper_reach:
            return False
        stopping = keeper.effective_stat(keeper.goal_stopping)
        read_error = abs(keeper.keeper_read_y - self.ball.pos.y)
        read_alignment = 1.0 - clamp(read_error / 145.0, 0.0, 0.82)
        save_chance = 0.28 + stopping * 0.48 + read_alignment * 0.18 + keeper.skill * 0.07
        save_chance -= self.ball.vel.length() / 2150
        save_chance -= self.ball.shot_deception * 0.08
        if self.ball_is_shot() and self.ball.shot_outcome == SHOT_KEEPER_FRIENDLY:
            save_chance += 0.20
        save_chance += 0.19 if guardian else 0.0
        save_chance += 0.13 if keeper.super_save_timer > 0.0 else 0.0
        save_chance *= keeper.technique_success_factor
        save_chance = clamp(save_chance, 0.10, 0.98 if guardian else 0.94)
        if self.rng.random() < save_chance:
            return self.resolve_keeper_contact(keeper, self.ball.vel.length(), guardian)
        keeper.adjust_confidence(-0.018)
        return False

    def handle_goal(self, scoring_team: Team) -> None:
        scoring_team.score += 1
        scorer = self.ball.last_touch
        scorer_name = scorer.name if scorer and scorer.team is scoring_team else scoring_team.short_name
        if scorer and scorer.team is scoring_team:
            scorer.adjust_confidence(0.12)
        conceding = self.away if scoring_team is self.home else self.home
        for teammate in scoring_team.players:
            teammate.adjust_confidence(0.025)
        for defender in conceding.players:
            defender.adjust_confidence(-0.032 if defender.is_keeper else -0.018)
        self.add_event(f"GOAL! {scorer_name}")
        self.goal_scorers.append((int(self.game_time // 60), scorer_name))
        self.goal_scorers = self.goal_scorers[-8:]
        self.show_banner(f"GOAL  {scoring_team.short_name}", 2.2)
        kickoff = self.away if scoring_team is self.home else self.home
        self.apply_pending_manager_changes("得点")
        self.reset_positions(kickoff)

    def choose_open_set_piece_target(self, taker: Player, skill: float, maximum_distance: float) -> Player | None:
        opponents = [player for team in self.teams if team is not taker.team for player in team.players if not player.sent_off]
        intelligence = taker.effective_intelligence
        decision = blended_judgment(skill, intelligence, 0.76)
        candidates = [
            player for player in taker.team.players
            if player is not taker and not player.sent_off and taker.pos.distance_to(player.pos) <= maximum_distance
        ]
        best: Player | None = None
        best_score = -9999.0
        for candidate in candidates:
            distance = taker.pos.distance_to(candidate.pos)
            openness = min((opponent.pos.distance_to(candidate.pos) for opponent in opponents), default=150.0)
            progress = (candidate.pos.x - taker.pos.x) * taker.team.direction
            score = openness * (0.46 + decision * 0.72) + progress * (0.20 + decision * 0.34) - distance * 0.10
            score = perceived_utility(score, intelligence, self.rng, noise_span=52.0)
            if score > best_score:
                best_score, best = score, candidate
        return best

    def configure_set_piece_positions(
        self,
        restart_type: str,
        attacking: Team,
        spot: Vec2,
        taker: Player,
    ) -> None:
        """Assign destinations; players reach them through normal movement."""
        defending = self.away if attacking is self.home else self.home
        self.set_piece_targets.clear()
        for team in self.teams:
            for player in team.players:
                if player.sent_off:
                    continue
                target = self.shape_position(player, team is attacking)
                self.set_piece_targets[player] = Vec2(target)

        approach_distance = {
            "FREE_KICK": 28.0,
            "PENALTY_KICK": 38.0,
            "GOAL_KICK": 20.0,
            "CORNER_KICK": 18.0,
        }.get(restart_type, 24.0)
        approach = Vec2(-attacking.direction * approach_distance, 0)
        if restart_type == "CORNER_KICK":
            approach.y = 12 if spot.y <= FIELD.top else -12
        self.restart_approach.update(spot + approach)
        self.set_piece_targets[taker] = Vec2(self.restart_approach)

        if restart_type == "FREE_KICK":
            wall_candidates = [
                player for player in defending.players
                if not player.is_keeper and not player.sent_off
            ]
            wall_candidates.sort(key=lambda player: player.pos.distance_squared_to(spot))
            wall_size = min(4, len(wall_candidates))
            offsets = self.centered_offsets(wall_size, 27.0)
            wall_x = spot.x + attacking.direction * 92
            for index, player in enumerate(wall_candidates[:wall_size]):
                self.set_piece_targets[player] = Vec2(
                    clamp(wall_x, FIELD.left + 18, FIELD.right - 18),
                    clamp(spot.y + offsets[index], FIELD.top + 20, FIELD.bottom - 20),
                )
        elif restart_type == "PENALTY_KICK":
            goal_x = FIELD.right if attacking.direction == 1 else FIELD.left
            self.set_piece_targets[defending.keeper] = Vec2(
                goal_x - attacking.direction * 18,
                FIELD.centery,
            )
            waiting = [
                player for team in self.teams for player in team.players
                if player is not taker and player is not defending.keeper and not player.sent_off
            ]
            offsets = self.centered_offsets(len(waiting), 38.0)
            wait_x = spot.x - attacking.direction * 184
            for index, player in enumerate(waiting):
                self.set_piece_targets[player] = Vec2(
                    clamp(wait_x - attacking.direction * (index % 2) * 28, FIELD.left + 24, FIELD.right - 24),
                    clamp(FIELD.centery + offsets[index], FIELD.top + 30, FIELD.bottom - 30),
                )

    def move_set_piece_players(self, dt: float) -> float:
        if not self.set_piece_targets:
            return 1.0
        ready = 0
        active = 0
        for player, target in self.set_piece_targets.items():
            if player.sent_off:
                continue
            active += 1
            previous = Vec2(player.pos)
            movement = target - player.pos
            distance = movement.length()
            is_taker = player is self.restart_taker or player is self.thrower
            if distance <= (10.0 if is_taker else 24.0):
                ready += 1
                player.set_movement(PlayerCommand.IDLE)
                action = PlayerCommand.HOLD_POSITION
            else:
                action = PlayerCommand.RETURN_POSITION
                locomotion = PlayerCommand.DASH if distance > 70 and player.can_dash(action) else PlayerCommand.WALK
                player.set_movement(locomotion)
                ability = player.dash_speed if locomotion is PlayerCommand.DASH else player.walk_speed
                speed = movement_speed(locomotion, player.effective_stat(ability))
                speed *= player.team.tactical_settings(player)["speed"] * player.skill
                player.pos += safe_normalize(movement) * min(distance, speed * dt)
            if is_taker:
                action = {
                    "FREE_KICK": PlayerCommand.FREE_KICK,
                    "PENALTY_KICK": PlayerCommand.PENALTY_KICK,
                    "GOAL_KICK": PlayerCommand.GOAL_KICK,
                    "CORNER_KICK": PlayerCommand.CORNER_KICK,
                }.get(self.restart_type, PlayerCommand.THROW_IN)
            player.target.update(target)
            player.issue_action(action, target, duration=0.18, force=True)
            player.pos.x = clamp(player.pos.x, FIELD.left + 6, FIELD.right - 6)
            player.pos.y = clamp(player.pos.y, FIELD.top + 6, FIELD.bottom - 6)
            player.motion_velocity = (player.pos - previous) / max(0.001, dt)
            player.update_stamina(dt)
        return ready / max(1, active)

    def clear_corner_context(self) -> None:
        self.corner_attacking_team = None
        self.corner_defending_team = None
        self.corner_attackers = []
        self.corner_defenders = []
        self.corner_counter_players = []
        self.corner_phase_timer = 0.0

    @staticmethod
    def centered_offsets(amount: int, spacing: float) -> list[float]:
        return [(index - (amount - 1) / 2.0) * spacing for index in range(amount)]

    def arrange_corner_players(self, attacking: Team) -> None:
        """Build a crowded box while preserving players for the next counter."""
        defending = self.away if attacking is self.home else self.home
        attack_numbers = {"ULTRA_ATTACK": 6, "ATTACK": 5, "BALANCE": 4, "DEFEND": 3, "ULTRA_DEFEND": 2}
        defend_numbers = {"ULTRA_ATTACK": 5, "ATTACK": 6, "BALANCE": 7, "DEFEND": 8, "ULTRA_DEFEND": 9}
        attack_amount = self.rng.randint(2, 6) if attacking.tactic == "RANDOM" else attack_numbers.get(attacking.tactic, 4)
        defend_amount = self.rng.randint(5, 9) if defending.tactic == "RANDOM" else defend_numbers.get(defending.tactic, 7)

        attack_candidates = [
            player for player in attacking.players
            if player is not self.restart_taker and not player.is_keeper and not player.sent_off
        ]
        attack_candidates.sort(key=lambda player: (
            {"FW": 0, "MF": 1, "DF": 2}.get(player.role, 3),
            -(player.effective_stat(player.heading_judgment) + player.effective_stat(player.jump_height)),
            -player.goal_poaching,
        ))
        attack_amount = min(attack_amount, len(attack_candidates))
        self.corner_attackers = attack_candidates[:attack_amount]

        defend_candidates = [
            player for player in defending.players if not player.is_keeper and not player.sent_off
        ]
        defend_candidates.sort(key=lambda player: (
            {"DF": 0, "MF": 1, "FW": 2}.get(player.role, 3),
            -(player.shot_blocking + player.effective_stat(player.heading_judgment)),
            -player.interception,
        ))
        # With at least two available outfield players, one is always left outside
        # the box as a counter outlet instead of forcing all ten players back.
        maximum_box_defenders = max(0, len(defend_candidates) - (1 if len(defend_candidates) > 1 else 0))
        defend_amount = min(defend_amount, maximum_box_defenders)
        self.corner_defenders = defend_candidates[:defend_amount]
        self.corner_counter_players = defend_candidates[defend_amount:]
        self.corner_attacking_team = attacking
        self.corner_defending_team = defending
        self.corner_phase_timer = 0.0

        goal_x = FIELD.right if attacking.direction == 1 else FIELD.left
        attack_offsets = self.centered_offsets(len(self.corner_attackers), 43.0)
        for index, player in enumerate(self.corner_attackers):
            self.set_piece_targets[player] = Vec2(
                goal_x - attacking.direction * (58 + (index % 3) * 38),
                clamp(FIELD.centery + attack_offsets[index], FIELD.top + 36, FIELD.bottom - 36),
            )

        defend_offsets = self.centered_offsets(len(self.corner_defenders), 34.0)
        for index, player in enumerate(self.corner_defenders):
            self.set_piece_targets[player] = Vec2(
                goal_x - attacking.direction * (34 + (index % 3) * 42),
                clamp(FIELD.centery + defend_offsets[index], FIELD.top + 34, FIELD.bottom - 34),
            )

        if not defending.keeper.sent_off:
            self.set_piece_targets[defending.keeper] = Vec2(
                goal_x - attacking.direction * 18, FIELD.centery
            )

        # Fast forwards and pass outlets stay around halfway, spread laterally so
        # a clearance can become a real counter rather than a blind hoof.
        counter_offsets = self.centered_offsets(len(self.corner_counter_players), 126.0)
        for index, player in enumerate(self.corner_counter_players):
            self.set_piece_targets[player] = Vec2(
                FIELD.centerx + defending.direction * (72 + (index % 2) * 54),
                clamp(FIELD.centery + counter_offsets[index], FIELD.top + 100, FIELD.bottom - 100),
            )

        # The attacking side also leaves its non-selected players near halfway as
        # rest defence; a corner therefore never means eleven players in the box.
        attacking_safety = [
            player for player in attack_candidates if player not in self.corner_attackers
        ]
        safety_offsets = self.centered_offsets(len(attacking_safety), 112.0)
        for index, player in enumerate(attacking_safety):
            self.set_piece_targets[player] = Vec2(
                FIELD.centerx - attacking.direction * (82 + (index % 2) * 48),
                clamp(FIELD.centery + safety_offsets[index], FIELD.top + 90, FIELD.bottom - 90),
            )

    def start_set_piece(self, restart_type: str, team: Team, spot: Vec2) -> None:
        self.apply_pending_manager_changes("セットプレー")
        self.cancel_pending_kick()
        if restart_type != "CORNER_KICK":
            self.clear_corner_context()
        self.throw_in_team = None
        self.thrower = None
        self.restart_type = restart_type
        self.restart_team = team
        self.restart_spot.update(spot)
        active = [player for player in team.players if not player.sent_off]
        if restart_type == "GOAL_KICK":
            taker = team.keeper
        elif restart_type == "CORNER_KICK":
            taker = min((player for player in active if not player.is_keeper), key=lambda player: player.pos.distance_squared_to(spot))
        elif restart_type == "PENALTY_KICK":
            taker = max(active, key=lambda player: player.penalty_kick_skill)
        else:
            taker = max(active, key=lambda player: player.free_kick_skill - player.pos.distance_to(spot) / 4000)
        self.restart_taker = taker
        self.restart_elapsed = 0.0
        self.configure_set_piece_positions(restart_type, team, spot, taker)
        if restart_type == "CORNER_KICK":
            self.arrange_corner_players(team)
        self.ball.owner = None
        self.ball.intended = None
        self.ball.catch_forbidden = False
        self.ball.last_keeper_response = ""
        self.ball.vel.update(0, 0)
        self.ball.pos.update(spot)
        self.ball.z = 0.0
        self.ball.vertical_speed = 0.0
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.flight_type = f"{restart_type}準備"
        self.stoppage_timer = {
            "FREE_KICK": 1.35,
            "PENALTY_KICK": 1.45,
            "CORNER_KICK": 1.55,
            "GOAL_KICK": 1.00,
        }.get(restart_type, 1.20)
        self.restart_counts[restart_type] += 1

    def start_goal_line_restart(self) -> None:
        left_exit = self.ball.pos.x < FIELD.left
        defending = self.home if left_exit else self.away
        attacking = self.away if left_exit else self.home
        last_team = self.ball.last_touch.team if self.ball.last_touch else None
        if last_team is defending:
            spot = Vec2(
                FIELD.left if left_exit else FIELD.right,
                FIELD.top if self.ball.pos.y < FIELD.centery else FIELD.bottom,
            )
            self.start_set_piece("CORNER_KICK", attacking, spot)
            self.add_event(f"{attacking.short_name}のコーナーキック")
            self.show_banner("CORNER KICK", 0.72)
        else:
            spot = Vec2(
                FIELD.left + 52 if left_exit else FIELD.right - 52,
                FIELD.centery,
            )
            self.start_set_piece("GOAL_KICK", defending, spot)
            self.add_event(f"{defending.short_name}のゴールキック")
            self.show_banner("GOAL KICK", 0.72)

    def update_set_piece(self, dt: float) -> None:
        if not self.restart_type or self.restart_team is None or self.restart_taker is None:
            return
        self.ball.pos.update(self.restart_spot)
        self.ball.z = 0.0
        self.restart_elapsed += dt
        readiness = self.move_set_piece_players(dt)
        referee_busy = self.update_referee(dt)
        self.stoppage_timer = max(0.0, self.stoppage_timer - dt)
        taker_ready = self.restart_taker.pos.distance_to(self.restart_approach) <= 11.0
        if referee_busy or self.stoppage_timer > 0.0 or not taker_ready:
            return
        if readiness < 0.62 and self.restart_elapsed < 4.2:
            return
        kind = self.restart_type
        team = self.restart_team
        taker = self.restart_taker
        skill = 0.0
        target: Player | None = None
        kick_command = PlayerCommand.PASS
        display_command = PlayerCommand.FREE_KICK
        if kind == "PENALTY_KICK":
            skill = taker.effective_stat(taker.penalty_kick_skill)
            kick_command = PlayerCommand.SHOOT
            display_command = PlayerCommand.PENALTY_KICK
        elif kind == "FREE_KICK":
            skill = taker.effective_stat(taker.free_kick_skill)
            distance_to_goal = abs((FIELD.right if team.direction == 1 else FIELD.left) - taker.pos.x)
            direct_quality = clamp(1.0 - distance_to_goal / (300 + skill * 155), 0.0, 1.0)
            shot_execution = (
                taker.effective_stat(taker.shot_accuracy)
                + taker.effective_stat(taker.shooting_technique)
                + skill
            ) / 3.0
            if (
                distance_to_goal <= 300 + skill * 155
                and self.try_activate_player_skill(
                    taker,
                    MAGIC_PLACE_KICK,
                    0.32 + direct_quality * 0.66,
                    shot_execution,
                    duration=taker.kick_contact_time + 0.68,
                    force_decision=True,
                )
            ):
                kick_command = PlayerCommand.SHOOT
            else:
                target = self.choose_open_set_piece_target(taker, skill, 260 + skill * 180)
            display_command = PlayerCommand.FREE_KICK
        elif kind == "GOAL_KICK":
            skill = taker.effective_stat(taker.goal_kick_skill)
            target = self.choose_open_set_piece_target(taker, skill, 280 + skill * 180)
            display_command = PlayerCommand.GOAL_KICK
        elif kind == "CORNER_KICK":
            skill = taker.effective_stat(taker.corner_kick_skill)
            corner_shooting = (
                taker.effective_stat(taker.shot_accuracy)
                + taker.effective_stat(taker.shooting_technique)
                + skill
            ) / 3.0
            if self.try_activate_player_skill(
                taker,
                ARC_CURVE,
                0.22 + corner_shooting * 0.48,
                corner_shooting,
                duration=taker.kick_contact_time + 0.68,
                force_decision=True,
            ):
                kick_command = PlayerCommand.SHOOT
            else:
                target = self.choose_open_set_piece_target(taker, skill, 690 + skill * 150)
            display_command = PlayerCommand.CORNER_KICK
        if target is None and kick_command is not PlayerCommand.SHOOT:
            target = self.choose_pass_target(taker)
        if target is None and kick_command is not PlayerCommand.SHOOT:
            fallbacks = [player for player in team.players if player is not taker and not player.sent_off]
            target = min(fallbacks, key=lambda player: player.pos.distance_squared_to(taker.pos), default=None)
        self.change_owner(taker)
        started = False
        if kick_command is PlayerCommand.SHOOT:
            goal_x = FIELD.right + 8 if team.direction == 1 else FIELD.left - 8
            started = self.begin_kick(
                taker, PlayerCommand.SHOOT, target_point=(goal_x, FIELD.centery),
                set_piece_skill=skill, display_command=display_command,
            )
        elif target is not None:
            pass_command = PlayerCommand.CROSS if kind == "CORNER_KICK" else PlayerCommand.PASS
            started = self.begin_kick(
                taker, pass_command, target, target.pos,
                set_piece_skill=skill, display_command=display_command,
            )
            target.issue_action(PlayerCommand.RECEIVE_PASS, target.pos, duration=taker.kick_contact_time + 0.55, force=True)
        if started:
            label = {
                "FREE_KICK": "フリーキック",
                "PENALTY_KICK": "ペナルティキック",
                "GOAL_KICK": "ゴールキック",
                "CORNER_KICK": "コーナーキック",
            }[kind]
            self.add_event(f"{taker.name}の{label}")
            if kind == "CORNER_KICK":
                # Preserve the corner layout briefly so a successful defensive
                # touch can find one of the deliberately retained counter outlets.
                self.corner_phase_timer = 9.0
            self.restart_type = ""
            self.restart_team = None
            self.restart_taker = None
            self.set_piece_targets.clear()
            self.restart_elapsed = 0.0

    def start_throw_in(self) -> None:
        self.apply_pending_manager_changes("スローイン")
        self.clear_corner_context()
        last_touch = self.ball.last_touch
        if last_touch is not None:
            receiving_team = self.away if last_touch.team is self.home else self.home
        else:
            receiving_team = self.home
        spot_x = clamp(self.ball.pos.x, FIELD.left + 16, FIELD.right - 16)
        spot_y = FIELD.top if self.ball.pos.y < FIELD.top else FIELD.bottom
        self.cancel_pending_kick()
        self.throw_in_team = receiving_team
        self.throw_in_spot.update(spot_x, spot_y)
        candidates = [player for player in receiving_team.players if not player.is_keeper and not player.sent_off]
        self.thrower = min(candidates, key=lambda player: player.pos.distance_squared_to(self.throw_in_spot))
        inside = Vec2(self.throw_in_spot)
        if spot_y == FIELD.top:
            inside.y += 13
        elif spot_y == FIELD.bottom:
            inside.y -= 13
        elif spot_x == FIELD.left:
            inside.x += 13
        else:
            inside.x -= 13
        self.restart_approach.update(inside)
        self.restart_elapsed = 0.0
        self.set_piece_targets.clear()
        for team in self.teams:
            for player in team.players:
                if not player.sent_off:
                    self.set_piece_targets[player] = Vec2(
                        self.shape_position(player, team is receiving_team)
                    )
        self.set_piece_targets[self.thrower] = Vec2(inside)
        receivers = [
            player for player in receiving_team.players
            if player is not self.thrower and not player.sent_off
        ]
        receivers.sort(key=lambda player: player.pos.distance_squared_to(self.throw_in_spot))
        inward_y = 1 if spot_y == FIELD.top else -1
        for index, player in enumerate(receivers[:3]):
            self.set_piece_targets[player] = Vec2(
                clamp(spot_x + receiving_team.direction * (72 + index * 52), FIELD.left + 24, FIELD.right - 24),
                clamp(spot_y + inward_y * (70 + (index % 2) * 66), FIELD.top + 28, FIELD.bottom - 28),
            )
        self.ball.owner = None
        self.ball.intended = None
        self.ball.catch_forbidden = False
        self.ball.last_keeper_response = ""
        self.ball.vel.update(0, 0)
        self.ball.pos.update(self.throw_in_spot)
        self.ball.z = 52.0
        self.ball.vertical_speed = 0.0
        self.ball.curve_acceleration = 0.0
        self.ball.curve_vector.update(0, 0)
        self.ball.knuckle_amplitude = 0.0
        self.ball.flight_type = "スローイン準備"
        self.stoppage_timer = 1.20
        self.restart_counts["THROW_IN"] += 1
        self.add_event(f"{receiving_team.short_name}のスローイン")

    def update_throw_in(self, dt: float) -> None:
        if self.throw_in_team is None or self.thrower is None:
            return
        self.restart_elapsed += dt
        readiness = self.move_set_piece_players(dt)
        self.stoppage_timer = max(0.0, self.stoppage_timer - dt)
        self.ball.pos.update(self.throw_in_spot)
        self.ball.z = 52.0
        thrower_ready = self.thrower.pos.distance_to(self.restart_approach) <= 11.0
        if self.stoppage_timer > 0.0 or not thrower_ready:
            return
        if readiness < 0.58 and self.restart_elapsed < 3.8:
            return
        thrower = self.thrower
        throw_skill = thrower.effective_stat(thrower.throw_in_skill)
        long_throw = throw_skill >= 0.70
        maximum_distance = 175 + throw_skill * (315 if long_throw else 185)
        target = self.choose_open_set_piece_target(thrower, throw_skill, maximum_distance)
        if target is None:
            teammates = [player for player in self.throw_in_team.players if player is not thrower and not player.sent_off]
            target = min(teammates, key=lambda player: player.pos.distance_squared_to(thrower.pos))
        destination = target.pos + Vec2(thrower.team.direction * 12, 0)
        direction = safe_normalize(destination - self.throw_in_spot)
        distance = self.throw_in_spot.distance_to(destination)
        pass_power = thrower.effective_stat(thrower.pass_power)
        speed = clamp(165 + distance * 0.31 + throw_skill * 108 + pass_power * 28, 180, 430 if long_throw else 345)
        self.ball.pos.update(self.throw_in_spot + direction * 8)
        self.ball.vel = direction * speed
        flight_time = max(0.25, distance / speed)
        self.ball.vertical_speed = clamp(
            (9.0 - self.ball.z + 0.5 * GRAVITY * flight_time * flight_time) / flight_time,
            -35,
            126,
        )
        self.ball.flight_serial += 1
        self.ball.last_touch = thrower
        self.ball.intended = target
        self.ball.pickup_lock = 0.16
        self.ball.flight_type = "ロングスロー" if long_throw and distance > 235 else "スローイン"
        target.issue_action(PlayerCommand.RECEIVE_PASS, destination, duration=0.62, force=True)
        self.throw_in_team = None
        self.thrower = None
        self.set_piece_targets.clear()
        self.restart_elapsed = 0.0
        self.decision_timer = 0.45

    def update_loose_ball(self, dt: float) -> None:
        if self.ball.owner is not None:
            return
        self.ball.pickup_lock = max(0.0, self.ball.pickup_lock - dt)
        self.ball.recovery_timer = max(0.0, self.ball.recovery_timer - dt)
        if self.ball.recovery_timer <= 0.0:
            self.ball.recovery_team = None
        self.ball.vel.y += self.ball.curve_acceleration * dt
        self.ball.vel += self.ball.curve_vector * dt
        self.ball.curve_vector *= math.pow(0.68, dt)
        if self.ball.knuckle_amplitude > 0.1 and self.ball.vel.length_squared() > 0.01:
            self.ball.knuckle_phase += dt * (17.0 + self.ball.vel.length() / 72.0)
            travel = safe_normalize(self.ball.vel)
            sideways = Vec2(-travel.y, travel.x)
            self.ball.vel += sideways * math.sin(self.ball.knuckle_phase) * self.ball.knuckle_amplitude * dt
            self.ball.knuckle_amplitude *= math.pow(0.72, dt)
        self.ball.curve_acceleration *= math.pow(0.70, dt)
        self.ball.pos += self.ball.vel * dt
        self.ball.z += self.ball.vertical_speed * dt
        self.ball.vertical_speed -= GRAVITY * dt
        if self.ball.z <= 0.0:
            self.ball.z = 0.0
            if self.ball.vertical_speed < -48:
                self.ball.vertical_speed = -self.ball.vertical_speed * 0.38
                self.ball.vel *= 0.90
            else:
                self.ball.vertical_speed = 0.0
        # A free ball keeps rolling naturally, but once it is grounded it
        # should lose horizontal speed more decisively so it settles sooner.
        if self.ball.z <= 0.5:
            brake = clamp(self.ball.pass_brake, 0.0, 1.0)
            roll_drag = (0.72 if self.ball.vel.length() > 120 else 0.80) - brake * 0.14
            self.ball.vel *= math.pow(roll_drag, dt)
            if self.ball.vel.length() < 7.0:
                self.ball.vel.update(0, 0)
        else:
            brake = clamp(self.ball.pass_brake, 0.0, 1.0)
            drag = (0.958 if self.ball.vel.length() > 90 else 0.972) - brake * 0.014
            self.ball.vel *= math.pow(drag, dt)

        if self.keeper_save():
            return

        in_goal_y = abs(self.ball.pos.y - FIELD.centery) <= GOAL_HALF_HEIGHT
        below_bar = self.ball.z <= GOAL_HEIGHT
        crossed_right = self.ball.pos.x > FIELD.right
        crossed_left = self.ball.pos.x < FIELD.left
        if (
            self.ball.shot_outcome == SHOT_POST
            and self.ball_is_shot()
            and (crossed_right or crossed_left)
        ):
            goal_line = FIELD.right if crossed_right else FIELD.left
            inward = -1.0 if crossed_right else 1.0
            post_side = 1.0 if self.ball.pos.y >= FIELD.centery else -1.0
            post_y = FIELD.centery + post_side * GOAL_HALF_HEIGHT
            self.ball.pos.update(goal_line + inward * 3.0, post_y)
            self.ball.vel.x = -self.ball.vel.x * 0.48
            self.ball.vel.y = (FIELD.centery - post_y) * 1.35 - self.ball.vel.y * 0.28
            self.ball.vertical_speed = max(24.0, abs(self.ball.vertical_speed) * 0.42)
            self.ball.curve_acceleration = 0.0
            self.ball.curve_vector.update(0, 0)
            self.ball.knuckle_amplitude = 0.0
            self.ball.flight_type = "ポスト跳ね返り"
            self.ball.shot_outcome = ""
            self.ball.catch_forbidden = False
            shooter = self.ball.last_touch
            self.add_event(f"{shooter.name if shooter else 'シュート'}はポスト！")
            return
        if self.ball.pos.x > FIELD.right and in_goal_y and below_bar:
            self.handle_goal(self.home)
            return
        if self.ball.pos.x < FIELD.left and in_goal_y and below_bar:
            self.handle_goal(self.away)
            return

        if self.ball.pos.y < FIELD.top or self.ball.pos.y > FIELD.bottom:
            self.ball.shot_outcome = ""
            self.start_throw_in()
            return
        if self.ball.pos.x < FIELD.left or self.ball.pos.x > FIELD.right:
            if not self.ball.shot_miss_announced:
                shooter = self.ball.last_touch
                shooter_name = shooter.name if shooter else "シュート"
                if self.ball.shot_outcome == SHOT_WIDE:
                    self.add_event(f"{shooter_name}のシュートはゴールの外")
                    self.ball.shot_miss_announced = True
                elif self.ball.shot_outcome == SHOT_OVER:
                    self.add_event(f"{shooter_name}のシュートはバーの上")
                    self.ball.shot_miss_announced = True
            self.ball.shot_outcome = ""
            self.start_goal_line_restart()
            return

        recovery_team = self.ball.recovery_team if self.ball.recovery_timer > 0.0 else None
        nearby = sorted(
            (player for team in self.teams for player in team.players if not player.sent_off),
            key=lambda player: (
                0 if recovery_team is not None and player.team is recovery_team else 1,
                player.pos.distance_squared_to(self.ball.pos),
            ),
        )
        for player in nearby:
            keeper_hands_legal = player.is_keeper and self.keeper_can_use_hands(player)
            if keeper_hands_legal:
                radius = KEEPER_BALL_REACH
            elif player.airborne:
                radius = (11 + player.effective_stat(player.jump_accuracy) * 9) * PLAYER_VISUAL_SCALE
            else:
                radius = OUTFIELD_BALL_REACH
            if recovery_team is not None and player.team is recovery_team:
                radius += 5 * PLAYER_VISUAL_SCALE
            if player.pos.distance_to(self.ball.pos) <= radius:
                if self.ball.pickup_lock > 0 and player is self.ball.last_touch:
                    continue
                if keeper_hands_legal:
                    vertical_reach = player.z + (72 if player.airborne else 55) * PLAYER_VISUAL_SCALE
                elif player.airborne:
                    vertical_reach = player.z + 54 * PLAYER_VISUAL_SCALE
                else:
                    vertical_reach = 24 * PLAYER_VISUAL_SCALE
                if self.ball.z > vertical_reach:
                    continue
                if (
                    not player.is_keeper
                    and player.airborne
                    and player.technique_command is PlayerCommand.HEADER
                    and player.heading_purpose in (
                        PlayerCommand.SKILL_AERIAL_HEADER,
                        PlayerCommand.SKILL_OVERHEAD_VOLLEY,
                        PlayerCommand.INTERCEPT_PASS,
                        PlayerCommand.BLOCK_SHOT,
                    )
                ):
                    head_height = player.z + 45.0 * PLAYER_VISUAL_SCALE
                    contact_tolerance = (13 + player.effective_stat(player.jump_accuracy) * 17) * PLAYER_VISUAL_SCALE
                    if abs(self.ball.z - head_height) <= contact_tolerance:
                        self.header_ball(player)
                        return
                intended = self.ball.intended
                incoming_speed = self.ball.vel.length()
                last_touch = self.ball.last_touch
                if keeper_hands_legal and self.ball_is_shot() and incoming_speed >= 170:
                    # keeper_save already resolved this exact contact once.
                    continue
                trap_ability = player.effective_stat(player.trap_technique)
                mistake_ability = player.effective_stat(player.mistake_avoidance)
                if intended is player and not player.is_keeper and player.skill_command is PlayerCommand.IDLE:
                    goal_x = FIELD.right if player.team.direction == 1 else FIELD.left
                    goal_distance = abs(goal_x - player.pos.x)
                    attacking_progress = self.team_progress(player.team, player.pos.x)
                    shooting = player.effective_stat(player.shooting_technique)
                    receiving_shot_quality = blended_judgment(
                        shooting * 0.58 + trap_ability * 0.42,
                        player.effective_intelligence,
                        0.72,
                    )
                    receiving_options: dict[str, float] = {}
                    if player.has_skill(DIRECT_VOLLEY) and 6 <= self.ball.z <= 72 and incoming_speed > 72 and goal_distance < 390 and attacking_progress > 0.58:
                        receiving_options[DIRECT_VOLLEY] = (
                            0.30 + clamp((390 - goal_distance) / 430.0, 0.0, 0.36)
                            + clamp(incoming_speed / 1000.0, 0.0, 0.18)
                        )
                    if player.has_skill(SET_AND_SHOOT) and self.ball.z <= 34 and incoming_speed > 42 and goal_distance < 355 and attacking_progress > 0.60:
                        receiving_options[SET_AND_SHOOT] = 0.36 + clamp((355 - goal_distance) / 420.0, 0.0, 0.40)
                    if receiving_options:
                        receiving_skill = choose_utility_action(
                            receiving_options,
                            player.effective_intelligence,
                            self.rng,
                        )
                        if self.try_activate_player_skill(
                            player,
                            receiving_skill,
                            receiving_options[receiving_skill],
                            receiving_shot_quality,
                            duration=0.82,
                        ):
                            incoming_height = self.ball.z
                            self.change_owner(player)
                            if receiving_skill == DIRECT_VOLLEY:
                                player.issue_action(PlayerCommand.SKILL_DIRECT_VOLLEY, (goal_x, FIELD.centery), force=True)
                                self._release_shot(player)
                                self.ball.z = max(8.0, incoming_height)
                            else:
                                player.one_trap_shot_timer = 0.44
                                player.issue_action(PlayerCommand.SKILL_SET_AND_SHOOT, self.ball.pos, duration=0.44, force=True)
                                player.use_technique(PlayerCommand.TRAP, duration=0.30)
                                self.decision_timer = 0.08
                            return
                if intended is player and not player.is_keeper and self.ball.z <= 30:
                    direct_target = self.choose_pass_target(player)
                    if direct_target is not None and direct_target is not last_touch:
                        direct_execution = blended_judgment(
                            player.effective_stat(player.passing_technique) * 0.58 + trap_ability * 0.42,
                            player.effective_intelligence,
                            0.70,
                        )
                        direct_situation = clamp(0.66 - incoming_speed / 1300.0 + self.ball.eye_contact_bonus * 0.34, 0.24, 0.78)
                        if self.try_activate_player_skill(
                            player,
                            ONE_TOUCH_RELAY,
                            direct_situation,
                            direct_execution,
                            duration=0.48,
                        ):
                            self.change_owner(player)
                            player.issue_action(PlayerCommand.SKILL_ONE_TOUCH_RELAY, direct_target.pos, duration=0.42, force=True)
                            player.spend_stamina(PlayerCommand.PASS)
                            self._release_pass(player, direct_target)
                            self.ball.flight_type = "ワンタッチリレー"
                            return
                if keeper_hands_legal:
                    command = PlayerCommand.SAVE
                    stopping = player.effective_stat(player.goal_stopping)
                    control = clamp(0.50 + stopping * 0.43 - incoming_speed / 1650, 0.12, 0.96)
                    control *= player.technique_success_factor
                elif player.is_keeper:
                    # Outside the area, and after a deliberate team back-pass,
                    # the keeper must control the ball with the feet.
                    command = PlayerCommand.TRAP
                    control = trap_success_chance(
                        trap_ability,
                        mistake_ability,
                        player.fatigue_factor,
                        incoming_speed,
                        self.ball.z,
                    )
                elif intended is player:
                    command = PlayerCommand.TRAP
                    control = trap_success_chance(
                        trap_ability,
                        mistake_ability,
                        player.fatigue_factor,
                        incoming_speed,
                        self.ball.z,
                    )
                    control = clamp(control + self.ball.eye_contact_bonus, 0.0, 0.98)
                elif intended and player.team is not intended.team:
                    command = PlayerCommand.INTERCEPT_PASS
                    control = trap_success_chance(
                        trap_ability,
                        mistake_ability,
                        player.fatigue_factor,
                        incoming_speed,
                        self.ball.z,
                        player.effective_stat(player.pass_interception),
                    )
                elif intended is None and last_touch and last_touch.team is not player.team and incoming_speed > 250:
                    command = PlayerCommand.BLOCK_SHOT
                    control = trap_success_chance(
                        trap_ability,
                        mistake_ability,
                        player.fatigue_factor,
                        incoming_speed,
                        self.ball.z,
                        player.effective_stat(player.pass_interception) * 0.60,
                    )
                else:
                    command = PlayerCommand.RECOVER_LOOSE_BALL
                    control = clamp(0.62 + trap_ability * 0.27 - incoming_speed / 1900, 0.22, 0.96)
                    control *= player.technique_success_factor
                    if recovery_team is not None and player.team is recovery_team:
                        control = clamp(control + 0.20, 0.0, 0.99)
                if self.ball.z > 22:
                    control *= 0.90 if player.airborne else 0.35

                trap_command = command in (PlayerCommand.TRAP, PlayerCommand.INTERCEPT_PASS)
                style = choose_trap_style(self.ball.z, self.ball.vel.y, self.rng) if trap_command else None
                if self.rng.random() < control:
                    if keeper_hands_legal:
                        self.resolve_keeper_contact(player, incoming_speed)
                        return
                    if style is not None:
                        touch_offset = trap_touch_offset(style, player.team.direction, self.ball.vel.y)
                        player.last_trap_style = style.value
                        self.change_owner(player, touch_offset)
                    else:
                        self.change_owner(player)
                    player.spend_stamina(command)
                    player.issue_action(command, self.ball.pos, force=True)
                    player.use_technique(PlayerCommand.TRAP if command is not PlayerCommand.SAVE else PlayerCommand.SAVE)
                    if command is PlayerCommand.INTERCEPT_PASS and self.rng.random() < 0.55:
                        self.add_event(f"{player.name}がパスカット")
                    return

                if style is not None:
                    # A failed first touch still contacts the ball. The five trap
                    # surfaces produce distinct small deflections.
                    touch_offset = Vec2(trap_touch_offset(style, player.team.direction, self.ball.vel.y))
                    player.last_trap_style = style.value
                    touch_direction = safe_normalize(touch_offset)
                    self.ball.vel = self.ball.vel * 0.30 + touch_direction * (38 + incoming_speed * 0.10)
                    self.ball.vertical_speed *= 0.32
                    self.ball.curve_acceleration *= 0.35
                    self.ball.last_touch = player
                    self.ball.intended = None
                    self.ball.pickup_lock = 0.14
                    player.spend_stamina(PlayerCommand.TRAP)
                    player.issue_action(command, self.ball.pos, force=True)
                    player.use_technique(PlayerCommand.TRAP)
                    return

    def update(self, dt: float) -> None:
        if self.state != "PLAYING":
            return
        remaining = dt * self.speed_multiplier
        # High speeds still use small physics steps so aerial balls, tackles,
        # goals and jumps cannot skip past one another.
        while remaining > 0.0001 and self.state == "PLAYING":
            step = min(0.05, remaining)
            self.update_step(step)
            remaining -= step

    def update_step(self, dt: float) -> None:
        self.simulation_elapsed += dt
        if self.corner_phase_timer > 0.0:
            self.corner_phase_timer = max(0.0, self.corner_phase_timer - dt)
            if self.corner_phase_timer <= 0.0:
                self.clear_corner_context()
        for team in self.teams:
            self.header_intercept_cooldown[team] = max(0.0, self.header_intercept_cooldown[team] - dt)
            self.catenaccio_timer[team] = max(0.0, self.catenaccio_timer[team] - dt)
            self.catenaccio_cooldown[team] = max(0.0, self.catenaccio_cooldown[team] - dt)
            self.counterattack_timer[team] = max(0.0, self.counterattack_timer[team] - dt)
        for pair in list(self.knockback_pair_cooldowns):
            remaining = self.knockback_pair_cooldowns[pair] - dt
            if remaining <= 0.0:
                del self.knockback_pair_cooldowns[pair]
            else:
                self.knockback_pair_cooldowns[pair] = remaining
        banner_active = self.banner_timer > 0
        if banner_active:
            self.banner_timer = max(0.0, self.banner_timer - dt)
            if self.ball.owner:
                self.ball.pos.update(self.ball.owner.pos + self.ball.control_offset)

        # Set-piece preparation uses real simulation time for players and the
        # referee to reach their positions, but it is not playing time.  Pause
        # the match clock until the throw or kick has actually been started.
        restart_waiting = self.throw_in_team is not None or bool(self.restart_type)
        kickoff_preview = banner_active and self.banner == "KICK OFF" and self.game_time <= 0.0001
        if not restart_waiting and not kickoff_preview:
            self.game_time += dt * GAME_CLOCK_RATE

            if not self.halftime_done and self.game_time >= MATCH_SECONDS / 2 - 0.000001:
                self.halftime_done = True
                self.game_time = MATCH_SECONDS / 2
                self.add_event("ハーフタイム")
                self.show_banner("HALF TIME", 2.4)
                self.reset_positions(self.away)
                return

            if self.game_time >= MATCH_SECONDS - 0.000001:
                self.game_time = MATCH_SECONDS
                self.cancel_pending_kick()
                self.throw_in_team = None
                self.thrower = None
                self.restart_type = ""
                self.restart_team = None
                self.restart_taker = None
                self.clear_corner_context()
                self.referee_active = False
                self.state = "FULLTIME"
                self.add_event("試合終了")
                return

        if self.throw_in_team is not None:
            self.update_throw_in(dt)
            return

        if self.restart_type:
            self.update_set_piece(dt)
            return

        if banner_active:
            return

        self.update_manager_ai()
        if self.ball.owner:
            self.ball.owner.team.possession += dt

        self.update_possession_stagnation(dt)
        self.update_dynamic_player_states(dt)
        self.update_vertical_motion(dt)
        self.update_player_movement(dt)
        self.try_tackles(dt)
        self.resolve_player_collisions()
        self.enforce_goal_line_cutback()
        if self.restart_type:
            return
        self.update_owner_decision(dt)
        self.update_pending_kick(dt)
        self.update_loose_ball(dt)
        self.consider_aerial_jumps()
