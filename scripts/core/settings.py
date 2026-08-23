# Shared constants and small coordinate helpers.

from scripts.core.paths import TEAMS_DIR
from scripts.core.simulation_geometry import Rect, Vec2
from scripts.core.stat_scale import (
    PLAYER_STAT_DEFAULT,
    PLAYER_STAT_MAX,
    PLAYER_STAT_MIN,
    normalize_player_stat,
)


WIDTH, HEIGHT = 1280, 720
PROJECT_NAME = "カドカルチョ"
WINDOW_SIZE_OPTIONS = ((960, 540), (1280, 720), (1600, 900), (1920, 1080))
FPS = 60
# The supplied frame shows one half from the halfway line to the goal.  Its
# player-to-half-pitch ratio gives roughly 2200x1420 for the complete pitch.
FIELD_SCALE = 2.4
FIELD = Rect(34, 72, 2200, 1420)
PANEL = Rect(954, 20, 306, 680)
GOAL_HALF_HEIGHT = 76
# The chibi players are about 37 world units tall after visual scaling.  A taller
# frame keeps the goal close to the roughly two-player-height look of Calciobit.
GOAL_HEIGHT = 82
GOAL_DEPTH = 32
CENTER_CIRCLE_RADIUS = 165
PENALTY_AREA_DEPTH = 400
PENALTY_AREA_WIDTH = 760
GOAL_AREA_DEPTH = 135
GOAL_AREA_WIDTH = 350
PENALTY_SPOT_DISTANCE = 240
MATCH_SECONDS = 90 * 60
GAME_CLOCK_RATE = 10.0  # One real second advances the match clock by ten seconds.
GRAVITY = 320.0
SPEED_OPTIONS = (1, 2, 3, 5, 10, 100)
CAMERA_FOCAL_LENGTHS = {1: 520.0, 2: 500.0, 3: 480.0, 5: 445.0, 10: 395.0, 100: 305.0}
# Manual broadcast-camera zoom.  It multiplies the speed-dependent focal length,
# so fast-forward remains comfortable while the player can still inspect play.
CAMERA_ZOOM_LEVELS = (0.70, 0.84, 1.00, 1.18, 1.40, 1.65)
# Low, distant broadcast angle from the supplied Calciobit frame.  This makes
# the centre circle about 2.2 times wider than it appears deep while retaining
# readable player sprites and reducing vertical camera motion on screen.
CAMERA_BACK = 800.0
CAMERA_HEIGHT = 390.0
CAMERA_MAX_SPEED = 300.0
PLAYER_VISUAL_SCALE = 0.72
PLAYER_CONTACT_DISTANCE = 18.0 * PLAYER_VISUAL_SCALE
STANDING_TACKLE_REACH = 17.0 * PLAYER_VISUAL_SCALE
SLIDE_TACKLE_REACH = 23.0 * PLAYER_VISUAL_SCALE
SLIDE_START_MIN_DISTANCE = 28.0 * PLAYER_VISUAL_SCALE
SLIDE_START_MAX_DISTANCE = 72.0 * PLAYER_VISUAL_SCALE
OUTFIELD_BALL_REACH = 14.0 * PLAYER_VISUAL_SCALE
KEEPER_BALL_REACH = 18.0 * PLAYER_VISUAL_SCALE

INK = (28, 33, 43)
PAPER = (245, 241, 226)
CREAM = (255, 250, 232)
MUTED = (127, 132, 132)
GOLD = (246, 190, 49)
HOME_RED = (222, 68, 66)
HOME_DARK = (101, 25, 39)
AWAY_BLUE = (66, 132, 213)
AWAY_DARK = (27, 61, 115)
PITCH_1 = (74, 154, 92)
PITCH_2 = (67, 145, 84)
LINE = (232, 239, 218)


TACTICS = {
    "ULTRA_ATTACK": {
        "label": "超攻撃的", "speed": 1.08, "press": 1.38, "width": 1.10,
        "retreat": 0.70, "push": 1.00, "press_trigger": 1.00,
        "shoot_distance": 245, "shot_bias": 1.30, "pass_forward": 0.88, "dribble": 0.38, "bias": 0.035,
        "freedom": 1.35, "pressers": 3, "lateral": 0.62,
    },
    "ATTACK": {
        "label": "攻撃的", "speed": 1.04, "press": 1.20, "width": 1.05,
        "retreat": 0.80, "push": 0.90, "press_trigger": 0.86,
        "shoot_distance": 225, "shot_bias": 1.15, "pass_forward": 0.74, "dribble": 0.31, "bias": 0.018,
        "freedom": 1.18, "pressers": 2, "lateral": 0.56,
    },
    "BALANCE": {
        "label": "バランス", "speed": 1.00, "press": 1.00, "width": 1.00,
        "retreat": 0.90, "push": 0.78, "press_trigger": 0.68,
        "shoot_distance": 205, "shot_bias": 1.00, "pass_forward": 0.62, "dribble": 0.25, "bias": 0.0,
        "freedom": 1.00, "pressers": 2, "lateral": 0.50,
    },
    "DEFEND": {
        "label": "防御的", "speed": 0.97, "press": 0.86, "width": 0.95,
        "retreat": 1.00, "push": 0.65, "press_trigger": 0.50,
        "shoot_distance": 188, "shot_bias": 0.86, "pass_forward": 0.52, "dribble": 0.18, "bias": -0.018,
        "freedom": 0.84, "pressers": 1, "lateral": 0.46,
    },
    "ULTRA_DEFEND": {
        "label": "超防御的", "speed": 0.94, "press": 0.72, "width": 0.90,
        "retreat": 1.08, "push": 0.52, "press_trigger": 0.36,
        "shoot_distance": 170, "shot_bias": 0.72, "pass_forward": 0.42, "dribble": 0.12, "bias": -0.035,
        "freedom": 0.70, "pressers": 1, "lateral": 0.42,
    },
}

BASE_TACTIC_KEYS = ("ULTRA_ATTACK", "ATTACK", "BALANCE", "DEFEND", "ULTRA_DEFEND")

# These two modes choose the five ordinary plans at player level.  Their own
# values are used only by team-level previews and as a safe fallback.
TACTICS["NO_INSTRUCTION"] = {
    **TACTICS["BALANCE"],
    "label": "指示なし",
    "freedom": 1.16,
}
TACTICS["RANDOM"] = {
    **TACTICS["BALANCE"],
    "label": "ランダム",
    "freedom": 1.38,
    "width": 1.10,
}

TACTIC_NAMES = {
    "超攻撃的": "ULTRA_ATTACK",
    "攻撃的": "ATTACK",
    "バランス": "BALANCE",
    "防御的": "DEFEND",
    "守備的": "DEFEND",
    "超防御的": "ULTRA_DEFEND",
    "超守備的": "ULTRA_DEFEND",
    "指示なし": "NO_INSTRUCTION",
    "ランダム": "RANDOM",
}

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def player_stat(raw: dict, key: str, default: float = PLAYER_STAT_DEFAULT, legacy_key: str = "Kick") -> float:
    """Read a configurable player stat and return its normalized 0..1 value."""
    value = raw.get(key, raw.get(legacy_key, default))
    return normalize_player_stat(value, default)


def percentage_stat(raw: dict, key: str, default: float = 50.0) -> float:
    """Read a 0..100 match-behavior parameter and normalize it to 0..1."""
    try:
        return clamp(float(raw.get(key, default)), 0.0, 100.0) / 100.0
    except (TypeError, ValueError):
        return clamp(default, 0.0, 100.0) / 100.0


def safe_normalize(vector: Vec2) -> Vec2:
    if vector.length_squared() < 0.0001:
        return Vec2()
    return vector.normalize()


def grid_role(position_y: int) -> str:
    if 1 <= position_y <= 3:
        return "FW"
    if 4 <= position_y <= 7:
        return "MF"
    if 8 <= position_y <= 10:
        return "DF"
    if position_y == 11:
        return "GK"
    return "SUB"


def grid_slot(position_x: int, position_y: int) -> tuple[str, float, float]:
    """Convert the 15x10 formation grid into normalized home-side coordinates."""
    role = grid_role(position_y)
    if role == "GK":
        return role, 0.055, 0.5
    if role == "SUB":
        raise ValueError("Bench players do not have a field slot")
    if not 1 <= position_x <= 15:
        raise ValueError(f"PositionX must be between 1 and 15: {position_x}")
    # X uses cell centers across the full pitch width.
    lateral = (position_x - 0.5) / 15.0
    # Y=1 is the front row near halfway. Y=10 is the deepest outfield row.
    # The interval 0.10..0.50 excludes the fixed goalkeeper zone.
    longitudinal = 0.10 + (10 - position_y + 0.5) / 10.0 * 0.40
    return role, longitudinal, lateral


def parse_hex_color(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    try:
        value = value.strip().lstrip("#")
        if len(value) != 6:
            return fallback
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
    except (AttributeError, ValueError):
        return fallback


def darken_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(max(18, round(channel * 0.45)) for channel in color)
