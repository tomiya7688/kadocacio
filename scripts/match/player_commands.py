from __future__ import annotations

from scripts.match.command_spec import CommandSpec
from scripts.match.player_command import PlayerCommand


COMMAND_SPECS = {
    PlayerCommand.IDLE: CommandSpec(0, 0.0),
    PlayerCommand.HOLD_POSITION: CommandSpec(5, 0.12),
    PlayerCommand.WALK: CommandSpec(5, 0.0),
    PlayerCommand.DASH: CommandSpec(10, 0.0),
    PlayerCommand.RETURN_POSITION: CommandSpec(15, 0.18),
    PlayerCommand.SUPPORT: CommandSpec(20, 0.18),
    PlayerCommand.TRIANGLE_SUPPORT: CommandSpec(21, 0.22),
    PlayerCommand.LOSE_MARK: CommandSpec(23, 0.24),
    PlayerCommand.CREATE_PASS_LANE: CommandSpec(22, 0.18),
    PlayerCommand.OVERLAP: CommandSpec(24, 0.22),
    PlayerCommand.DIAGONAL_RUN: CommandSpec(25, 0.26),
    PlayerCommand.RUN_INTO_SPACE: CommandSpec(26, 0.24),
    PlayerCommand.WAIT_IN_FRONT_OF_GOAL: CommandSpec(27, 0.28),
    PlayerCommand.GUARD_GOAL: CommandSpec(25, 0.20),
    PlayerCommand.MARK: CommandSpec(30, 0.20),
    PlayerCommand.COVER: CommandSpec(32, 0.20),
    PlayerCommand.DRIBBLE: CommandSpec(35, 0.20),
    PlayerCommand.KEEP_BALL: CommandSpec(38, 0.24),
    PlayerCommand.FOLLOW_BALL: CommandSpec(40, 0.16),
    PlayerCommand.RECOVER_LOOSE_BALL: CommandSpec(42, 0.16),
    PlayerCommand.RECEIVE_PASS: CommandSpec(45, 0.28),
    PlayerCommand.PRESS: CommandSpec(48, 0.22),
    PlayerCommand.INTERCEPT_PASS: CommandSpec(52, 0.30),
    PlayerCommand.BLOCK_SHOT: CommandSpec(58, 0.32),
    PlayerCommand.TACKLE: CommandSpec(60, 0.34),
    PlayerCommand.SLIDE_TACKLE: CommandSpec(65, 0.44),
    PlayerCommand.TRAP: CommandSpec(68, 0.34),
    PlayerCommand.HEADER: CommandSpec(70, 0.42),
    PlayerCommand.PASS: CommandSpec(72, 0.34),
    PlayerCommand.THROUGH_PASS: CommandSpec(74, 0.36),
    PlayerCommand.CROSS: CommandSpec(74, 0.38),
    PlayerCommand.KICK: CommandSpec(75, 0.30),
    PlayerCommand.CLEAR: CommandSpec(78, 0.38),
    PlayerCommand.SHOOT: CommandSpec(82, 0.42),
    PlayerCommand.PUNCH: CommandSpec(86, 0.42),
    PlayerCommand.CATCH: CommandSpec(91, 0.46),
    PlayerCommand.SAVE: CommandSpec(90, 0.46),
    PlayerCommand.KEEPER_THROW: CommandSpec(88, 0.42),
    PlayerCommand.KEEPER_PUNT: CommandSpec(89, 0.52),
    PlayerCommand.THROW_IN: CommandSpec(92, 0.62),
    PlayerCommand.GOAL_KICK: CommandSpec(93, 0.72),
    PlayerCommand.CORNER_KICK: CommandSpec(94, 0.76),
    PlayerCommand.FREE_KICK: CommandSpec(95, 0.72),
    PlayerCommand.PENALTY_KICK: CommandSpec(96, 0.82),
    PlayerCommand.STAGGER: CommandSpec(98, 0.42),
    PlayerCommand.SKILL_AERIAL_HEADER: CommandSpec(83, 0.52),
    PlayerCommand.SKILL_SLIDE_FINISH: CommandSpec(84, 0.48),
    PlayerCommand.SKILL_ARC_CURVE: CommandSpec(85, 0.52),
    PlayerCommand.SKILL_WOBBLE_BALL: CommandSpec(85, 0.52),
    PlayerCommand.SKILL_CHANCE_SENSOR: CommandSpec(84, 0.46),
    PlayerCommand.SKILL_MAGIC_PLACE_KICK: CommandSpec(97, 0.82),
    PlayerCommand.SKILL_FORTRESS_BLOCK: CommandSpec(40, 0.80),
    PlayerCommand.SKILL_SPIN_TURN: CommandSpec(76, 0.68),
    PlayerCommand.SKILL_CLOSE_LOCK: CommandSpec(64, 0.70),
    PlayerCommand.SKILL_VACANT_COVER: CommandSpec(44, 0.62),
    PlayerCommand.SKILL_BACKLINE_HUNTER: CommandSpec(62, 0.82),
    PlayerCommand.SKILL_PIVOT_KEEP: CommandSpec(63, 0.72),
    PlayerCommand.SKILL_ONE_TOUCH_RELAY: CommandSpec(88, 0.38),
    PlayerCommand.SKILL_CARRY_SHOT: CommandSpec(88, 0.48),
    PlayerCommand.SKILL_UNBREAKABLE_HEART: CommandSpec(42, 0.55),
    PlayerCommand.SKILL_OVERLOAD: CommandSpec(46, 0.72),
    PlayerCommand.SKILL_RECOVERY_CHASE: CommandSpec(68, 0.60),
    PlayerCommand.SKILL_TURNOVER_COUNTER: CommandSpec(75, 0.72),
    PlayerCommand.SKILL_HEEL_REVERSE_TURN: CommandSpec(77, 0.68),
    PlayerCommand.SKILL_STABLE_CORE: CommandSpec(99, 0.46),
    PlayerCommand.SKILL_OVERHEAD_VOLLEY: CommandSpec(89, 0.78),
    PlayerCommand.SKILL_HALFWAY_CANNON: CommandSpec(90, 0.68),
    PlayerCommand.SKILL_TIGHT_TOUCH: CommandSpec(67, 0.72),
    PlayerCommand.SKILL_SPRINT_CARRY: CommandSpec(67, 0.72),
    PlayerCommand.SKILL_ENERGY_KEEP: CommandSpec(55, 0.70),
    PlayerCommand.SKILL_COOLDOWN_REST: CommandSpec(43, 2.40),
    PlayerCommand.SKILL_POWER_SLIDE: CommandSpec(91, 0.72),
    PlayerCommand.SKILL_ONE_WAY_BLOCK: CommandSpec(69, 0.68),
    PlayerCommand.SKILL_BLIND_FEED: CommandSpec(86, 0.46),
    PlayerCommand.SKILL_SIGNAL_LINK: CommandSpec(79, 0.44),
    PlayerCommand.SKILL_LAST_CHANCE_CANNON: CommandSpec(96, 0.76),
    PlayerCommand.SKILL_SAVING_AURA: CommandSpec(99, 0.58),
    PlayerCommand.SKILL_EARLY_READ_SAVE: CommandSpec(99, 0.82),
    PlayerCommand.SKILL_CANNON_MIDDLE: CommandSpec(92, 0.68),
    PlayerCommand.SKILL_DIRECT_VOLLEY: CommandSpec(93, 0.58),
    PlayerCommand.SKILL_SET_AND_SHOOT: CommandSpec(91, 0.72),
    PlayerCommand.SKILL_ILLUSION_STEP: CommandSpec(78, 0.68),
    PlayerCommand.SKILL_RELENTLESS_PRESS: CommandSpec(82, 0.72),
    PlayerCommand.SKILL_FUTURE_READ: CommandSpec(97, 0.82),
    PlayerCommand.SKILL_SWEEPER_KEEPER: CommandSpec(72, 1.20),
}


SKILL_COMMANDS = {
    PlayerCommand.SKILL_AERIAL_HEADER,
    PlayerCommand.SKILL_SLIDE_FINISH,
    PlayerCommand.SKILL_ARC_CURVE,
    PlayerCommand.SKILL_WOBBLE_BALL,
    PlayerCommand.SKILL_CHANCE_SENSOR,
    PlayerCommand.SKILL_MAGIC_PLACE_KICK,
    PlayerCommand.SKILL_FORTRESS_BLOCK,
    PlayerCommand.SKILL_SPIN_TURN,
    PlayerCommand.SKILL_CLOSE_LOCK,
    PlayerCommand.SKILL_VACANT_COVER,
    PlayerCommand.SKILL_BACKLINE_HUNTER,
    PlayerCommand.SKILL_PIVOT_KEEP,
    PlayerCommand.SKILL_ONE_TOUCH_RELAY,
    PlayerCommand.SKILL_CARRY_SHOT,
    PlayerCommand.SKILL_UNBREAKABLE_HEART,
    PlayerCommand.SKILL_OVERLOAD,
    PlayerCommand.SKILL_RECOVERY_CHASE,
    PlayerCommand.SKILL_TURNOVER_COUNTER,
    PlayerCommand.SKILL_HEEL_REVERSE_TURN,
    PlayerCommand.SKILL_STABLE_CORE,
    PlayerCommand.SKILL_OVERHEAD_VOLLEY,
    PlayerCommand.SKILL_HALFWAY_CANNON,
    PlayerCommand.SKILL_TIGHT_TOUCH,
    PlayerCommand.SKILL_SPRINT_CARRY,
    PlayerCommand.SKILL_ENERGY_KEEP,
    PlayerCommand.SKILL_COOLDOWN_REST,
    PlayerCommand.SKILL_POWER_SLIDE,
    PlayerCommand.SKILL_ONE_WAY_BLOCK,
    PlayerCommand.SKILL_BLIND_FEED,
    PlayerCommand.SKILL_SIGNAL_LINK,
    PlayerCommand.SKILL_LAST_CHANCE_CANNON,
    PlayerCommand.SKILL_SAVING_AURA,
    PlayerCommand.SKILL_EARLY_READ_SAVE,
    PlayerCommand.SKILL_CANNON_MIDDLE,
    PlayerCommand.SKILL_DIRECT_VOLLEY,
    PlayerCommand.SKILL_SET_AND_SHOOT,
    PlayerCommand.SKILL_ILLUSION_STEP,
    PlayerCommand.SKILL_RELENTLESS_PRESS,
    PlayerCommand.SKILL_FUTURE_READ,
    PlayerCommand.SKILL_SWEEPER_KEEPER,
}


def command_spec(command: PlayerCommand) -> CommandSpec:
    return COMMAND_SPECS[command]


def movement_speed(command: PlayerCommand, ability: float) -> float:
    """Convert a normalized movement ability into world units per second."""
    ability = max(0.0, min(1.0, ability))
    if command is PlayerCommand.DASH:
        return 36.0 + 164.0 * ability ** 1.30
    if command is PlayerCommand.WALK:
        return 24.0 + 86.0 * ability ** 1.20
    return 0.0


def dribble_movement_speed(ability: float) -> float:
    ability = max(0.0, min(1.0, ability))
    return 29.0 + 126.0 * ability ** 1.30
