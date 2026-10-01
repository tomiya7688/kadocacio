"""Versioned, lossless input records for the developer match parity checker."""

from __future__ import annotations

import json
import math

from scripts.core.simulation_runtime import FIXED_PHYSICS_DT


INPUT_FORMAT = "kadocalcio.match-repro-input"
INPUT_VERSION = 1


def create_input_record(home: dict, away: dict, **settings) -> dict:
    """Detach normalized inputs without rounding player or manager values."""
    record = json.loads(json.dumps({
        "format": INPUT_FORMAT,
        "version": INPUT_VERSION,
        "settings": {"fixed_physics_dt": FIXED_PHYSICS_DT, **settings},
        "teams": {"home": home, "away": away},
        "commands": [],
    }, ensure_ascii=False, allow_nan=False))
    restore_input_record(record)
    return record


def _validate_settings(settings: object) -> None:
    if not isinstance(settings, dict):
        raise ValueError("input settings must be an object")
    for key in ("seed", "max_steps"):
        if type(settings.get(key)) is not int:
            raise ValueError(f"input {key} must be an integer")
    if settings["max_steps"] < 1:
        raise ValueError("input max_steps must be positive")
    if settings.get("fixed_physics_dt") != FIXED_PHYSICS_DT:
        raise ValueError("input fixed_physics_dt is incompatible with this engine")
    if settings.get("venue_mode") not in ("HOME", "AWAY", "NEUTRAL"):
        raise ValueError("input venue_mode must be HOME, AWAY or NEUTRAL")
    multiplier = settings.get("ai_rethink_multiplier")
    if type(multiplier) not in (int, float) or not math.isfinite(multiplier) or not 0.5 <= multiplier <= 3.0:
        raise ValueError("input ai_rethink_multiplier must be finite and in 0.5..3.0")


def _restore_team(team: object, side: str) -> dict:
    if not isinstance(team, dict):
        raise ValueError(f"input {side} team must be an object")
    for key in ("id", "name", "short"):
        if not isinstance(team.get(key), str) or not team[key]:
            raise ValueError(f"input {side} team requires {key}")
    if not isinstance(team.get("starters"), list) or not team["starters"]:
        raise ValueError(f"input {side} team requires starters")
    for key in ("primary", "secondary"):
        if key == "secondary" and key not in team:
            continue
        color = team.get(key)
        if not isinstance(color, list) or len(color) != 3:
            raise ValueError(f"input {side} team requires an RGB {key}")
        if any(type(channel) is not int or not 0 <= channel <= 255 for channel in color):
            raise ValueError(f"input {side} team has invalid RGB {key}")
        # Match compares kit colours with tuple constants when resolving clashes.
        team[key] = tuple(color)
    return team


def restore_input_record(record: object) -> tuple[dict, dict, dict]:
    """Validate a record and return independent Match inputs without discovery."""
    if not isinstance(record, dict) or record.get("format") != INPUT_FORMAT:
        raise ValueError("not a match reproduction input record")
    if type(record.get("version")) is not int or record["version"] != INPUT_VERSION:
        raise ValueError("unsupported match reproduction input version")
    # Never silently replay a future record while discarding its commands.
    if record.get("commands") != []:
        raise ValueError("this input version supports autonomous matches with no external commands only")
    _validate_settings(record.get("settings"))
    copy = json.loads(json.dumps(record, ensure_ascii=False, allow_nan=False))
    teams = copy.get("teams")
    if not isinstance(teams, dict):
        raise ValueError("input teams must be an object")
    home = _restore_team(teams.get("home"), "home")
    away = _restore_team(teams.get("away"), "away")
    settings = copy["settings"]
    return home, away, {key: settings[key] for key in (
        "seed", "max_steps", "venue_mode", "ai_rethink_multiplier",
    )}
