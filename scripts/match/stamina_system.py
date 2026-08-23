from __future__ import annotations

from scripts.match.player_commands import PlayerCommand


FATIGUE_POINTS = (
    (0.0, 0.32),
    (1 / 6, 0.68),
    (1 / 4, 0.82),
    (1 / 3, 0.92),
    (1 / 2, 1.00),
    (1.0, 1.00),
)

MOVEMENT_DRAIN_PER_SECOND = {
    PlayerCommand.DASH: 0.62,
}

ACTION_DRAIN_PER_SECOND = {
    PlayerCommand.DRIBBLE: 0.32,
    PlayerCommand.KEEP_BALL: 0.16,
    PlayerCommand.FOLLOW_BALL: 0.18,
    PlayerCommand.RECOVER_LOOSE_BALL: 0.14,
    PlayerCommand.RECEIVE_PASS: 0.14,
    PlayerCommand.PRESS: 0.30,
    PlayerCommand.INTERCEPT_PASS: 0.16,
    PlayerCommand.CREATE_PASS_LANE: 0.07,
    PlayerCommand.OVERLAP: 0.22,
    PlayerCommand.TRIANGLE_SUPPORT: 0.08,
    PlayerCommand.LOSE_MARK: 0.18,
    PlayerCommand.DIAGONAL_RUN: 0.24,
    PlayerCommand.RUN_INTO_SPACE: 0.22,
    PlayerCommand.SKILL_SPRINT_CARRY: 0.62,
    PlayerCommand.SKILL_TIGHT_TOUCH: 0.36,
    PlayerCommand.SKILL_RECOVERY_CHASE: 0.46,
    PlayerCommand.SKILL_ENERGY_KEEP: 0.32,
    PlayerCommand.SKILL_ILLUSION_STEP: 0.34,
    PlayerCommand.SKILL_RELENTLESS_PRESS: 0.58,
    PlayerCommand.SKILL_SWEEPER_KEEPER: 0.24,
}

ACTION_STAMINA_COSTS = {
    PlayerCommand.PASS: 1.20,
    PlayerCommand.THROUGH_PASS: 1.50,
    PlayerCommand.CROSS: 1.60,
    PlayerCommand.SHOOT: 2.20,
    PlayerCommand.CLEAR: 1.80,
    PlayerCommand.SLIDE_TACKLE: 5.50,
    PlayerCommand.TACKLE: 1.40,
    PlayerCommand.HEADER: 3.40,
    PlayerCommand.TRAP: 0.50,
    PlayerCommand.BLOCK_SHOT: 1.20,
    PlayerCommand.SAVE: 2.00,
    PlayerCommand.CATCH: 1.80,
    PlayerCommand.PUNCH: 2.40,
    PlayerCommand.KEEPER_THROW: 0.80,
    PlayerCommand.KEEPER_PUNT: 1.60,
    PlayerCommand.SKILL_FORTRESS_BLOCK: 0.40,
    PlayerCommand.SKILL_SPIN_TURN: 1.40,
    PlayerCommand.SKILL_CLOSE_LOCK: 0.80,
    PlayerCommand.SKILL_VACANT_COVER: 1.10,
    PlayerCommand.SKILL_BACKLINE_HUNTER: 2.40,
    PlayerCommand.SKILL_PIVOT_KEEP: 1.20,
    PlayerCommand.SKILL_ONE_TOUCH_RELAY: 1.50,
    PlayerCommand.SKILL_CARRY_SHOT: 3.20,
    PlayerCommand.SKILL_UNBREAKABLE_HEART: 1.60,
    PlayerCommand.SKILL_OVERLOAD: 1.40,
    PlayerCommand.SKILL_RECOVERY_CHASE: 2.60,
    PlayerCommand.SKILL_TURNOVER_COUNTER: 3.80,
    PlayerCommand.SKILL_HEEL_REVERSE_TURN: 1.80,
    PlayerCommand.SKILL_STABLE_CORE: 2.80,
    PlayerCommand.SKILL_OVERHEAD_VOLLEY: 5.20,
    PlayerCommand.SKILL_HALFWAY_CANNON: 4.80,
    PlayerCommand.SKILL_TIGHT_TOUCH: 1.90,
    PlayerCommand.SKILL_SPRINT_CARRY: 3.10,
    PlayerCommand.SKILL_ENERGY_KEEP: 1.50,
    PlayerCommand.SKILL_COOLDOWN_REST: 0.20,
    PlayerCommand.SKILL_POWER_SLIDE: 5.80,
    PlayerCommand.SKILL_ONE_WAY_BLOCK: 1.50,
    PlayerCommand.SKILL_BLIND_FEED: 1.40,
    PlayerCommand.SKILL_SIGNAL_LINK: 0.80,
    PlayerCommand.SKILL_LAST_CHANCE_CANNON: 5.20,
    PlayerCommand.SKILL_SAVING_AURA: 3.20,
    PlayerCommand.SKILL_EARLY_READ_SAVE: 4.20,
    PlayerCommand.SKILL_CANNON_MIDDLE: 4.00,
    PlayerCommand.SKILL_DIRECT_VOLLEY: 3.60,
    PlayerCommand.SKILL_SET_AND_SHOOT: 3.20,
    PlayerCommand.SKILL_ILLUSION_STEP: 2.00,
    PlayerCommand.SKILL_RELENTLESS_PRESS: 3.20,
    PlayerCommand.SKILL_FUTURE_READ: 2.80,
    PlayerCommand.SKILL_SWEEPER_KEEPER: 2.40,
}

RECOVERY_ACTIONS = {
    PlayerCommand.IDLE,
    PlayerCommand.HOLD_POSITION,
    PlayerCommand.RETURN_POSITION,
    PlayerCommand.MARK,
    PlayerCommand.COVER,
    PlayerCommand.SUPPORT,
    PlayerCommand.TRIANGLE_SUPPORT,
    PlayerCommand.WAIT_IN_FRONT_OF_GOAL,
    PlayerCommand.GUARD_GOAL,
    PlayerCommand.SKILL_COOLDOWN_REST,
}


def stamina_capacity(ability: float) -> float:
    return 70.0 + max(0.0, min(1.0, ability)) * 130.0


def stamina_recovery_rate(ability: float) -> float:
    return 0.06 + max(0.0, min(1.0, ability)) * 0.18


def command_stamina_drain(action: PlayerCommand, movement: PlayerCommand) -> float:
    return MOVEMENT_DRAIN_PER_SECOND.get(movement, 0.0) + ACTION_DRAIN_PER_SECOND.get(action, 0.0)


def command_stamina_cost(command: PlayerCommand) -> float:
    return ACTION_STAMINA_COSTS.get(command, 0.0)


def base_fatigue_multiplier(stamina_ratio: float) -> float:
    ratio = max(0.0, min(1.0, stamina_ratio))
    for index in range(1, len(FATIGUE_POINTS)):
        low_ratio, low_value = FATIGUE_POINTS[index - 1]
        high_ratio, high_value = FATIGUE_POINTS[index]
        if ratio <= high_ratio:
            span = max(0.0001, high_ratio - low_ratio)
            blend = (ratio - low_ratio) / span
            return low_value + (high_value - low_value) * blend
    return 1.0


def fatigue_multiplier(stamina_ratio: float, resistance: float) -> float:
    base = base_fatigue_multiplier(stamina_ratio)
    resistance = max(0.0, min(1.0, resistance))
    return 1.0 - (1.0 - base) * (1.0 - resistance * 0.65)


def fatigue_error_multiplier(stamina_ratio: float, resistance: float) -> float:
    performance = fatigue_multiplier(stamina_ratio, resistance)
    return 1.0 + (1.0 - performance) * 1.8
