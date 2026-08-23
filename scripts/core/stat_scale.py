from __future__ import annotations

import math


# Edit these two values when the editable ability range changes again. Runtime
# systems consume normalized 0..1 values, so their football balance is isolated
# from the JSON/UI scale.
PLAYER_STAT_MIN = 0.0
PLAYER_STAT_MAX = 5500.0
PLAYER_STAT_SCALE_VERSION = 2

# The previous data scale is retained only for deterministic data migration and
# backwards-compatible loading of custom JSON without scale metadata.
LEGACY_PLAYER_STAT_MIN = 50.0
LEGACY_PLAYER_STAT_MAX = 1250.0

STAT_SCALE_METADATA_KEY = "能力値スケール"


def clamp_player_stat(value: float) -> float:
    return max(PLAYER_STAT_MIN, min(PLAYER_STAT_MAX, float(value)))


def normalize_player_stat(value: object, default: float) -> float:
    try:
        numeric = clamp_player_stat(float(value))
    except (TypeError, ValueError):
        numeric = clamp_player_stat(default)
    span = max(1.0, PLAYER_STAT_MAX - PLAYER_STAT_MIN)
    return (numeric - PLAYER_STAT_MIN) / span


def denormalize_player_stat(value: float) -> float:
    unit = max(0.0, min(1.0, float(value)))
    return PLAYER_STAT_MIN + unit * (PLAYER_STAT_MAX - PLAYER_STAT_MIN)


def remap_player_stat(
    value: object,
    source_min: float,
    source_max: float,
    *,
    default: float | None = None,
) -> float:
    """Map a raw ability between scales without changing its 0..1 strength."""
    fallback = source_min if default is None else default
    try:
        numeric = float(value)
        if not math.isfinite(numeric):
            numeric = float(fallback)
    except (TypeError, ValueError):
        numeric = float(fallback)
    source_span = max(1.0, float(source_max) - float(source_min))
    unit = (max(float(source_min), min(float(source_max), numeric)) - float(source_min)) / source_span
    return denormalize_player_stat(unit)


def legacy_player_stat(value: float) -> float:
    return remap_player_stat(value, LEGACY_PLAYER_STAT_MIN, LEGACY_PLAYER_STAT_MAX)


def legacy_player_stat_delta(value: float) -> float:
    return float(value) * (PLAYER_STAT_MAX - PLAYER_STAT_MIN) / (
        LEGACY_PLAYER_STAT_MAX - LEGACY_PLAYER_STAT_MIN
    )


def current_to_legacy_player_stat(value: object) -> float:
    normalized = normalize_player_stat(value, PLAYER_STAT_MIN)
    return LEGACY_PLAYER_STAT_MIN + normalized * (
        LEGACY_PLAYER_STAT_MAX - LEGACY_PLAYER_STAT_MIN
    )


def payload_stat_bounds(payload: object) -> tuple[float, float]:
    """Read scale metadata; metadata-free custom teams use the legacy scale."""
    if not isinstance(payload, dict):
        return LEGACY_PLAYER_STAT_MIN, LEGACY_PLAYER_STAT_MAX
    metadata = payload.get(STAT_SCALE_METADATA_KEY)
    if not isinstance(metadata, dict):
        return LEGACY_PLAYER_STAT_MIN, LEGACY_PLAYER_STAT_MAX
    try:
        minimum = float(metadata.get("最小", PLAYER_STAT_MIN))
        maximum = float(metadata.get("最大", PLAYER_STAT_MAX))
    except (TypeError, ValueError):
        return LEGACY_PLAYER_STAT_MIN, LEGACY_PLAYER_STAT_MAX
    if not math.isfinite(minimum) or not math.isfinite(maximum) or maximum <= minimum:
        return LEGACY_PLAYER_STAT_MIN, LEGACY_PLAYER_STAT_MAX
    return minimum, maximum


def current_scale_metadata() -> dict[str, int | float]:
    def clean(value: float) -> int | float:
        return int(value) if float(value).is_integer() else value

    return {
        "バージョン": PLAYER_STAT_SCALE_VERSION,
        "最小": clean(PLAYER_STAT_MIN),
        "最大": clean(PLAYER_STAT_MAX),
    }


PLAYER_STAT_DEFAULT = legacy_player_stat(700.0)
PLAYER_STAT_INITIAL = round(legacy_player_stat(100.0))
MANAGER_ACTIVITY_DEFAULT = round(legacy_player_stat(500.0))
MANAGER_INTELLIGENCE_DEFAULT = round(PLAYER_STAT_DEFAULT)
PLAYER_STAT_MEAN_TOLERANCE = legacy_player_stat_delta(10.0)

PLAYER_GRADE_THRESHOLDS = (
    {"rank": "S", "minimum": 5000},
    {"rank": "A+", "minimum": 4500},
    {"rank": "A-", "minimum": 4000},
    {"rank": "B+", "minimum": 3500},
    {"rank": "B-", "minimum": 3000},
    {"rank": "C+", "minimum": 2500},
    {"rank": "C-", "minimum": 2000},
    {"rank": "D+", "minimum": 1500},
    {"rank": "D", "minimum": 1000},
    {"rank": "E+", "minimum": 500},
    {"rank": "E-", "minimum": 0},
)
