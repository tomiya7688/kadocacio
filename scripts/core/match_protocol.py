"""Portable observation/operation contract, not a second football engine."""

import math

from scripts.core.settings import SPEED_OPTIONS
from scripts.core.simulation_runtime import FIXED_PHYSICS_DT

INPUT_FORMAT = "kadocalcio.match-contract-input"
TRACE_FORMAT = "kadocalcio.match-contract-trace"
REPORT_FORMAT = "kadocalcio.match-contract-diff"
VERSION = 1
OPERATION_KINDS = ("START", "STEP", "SET_SPEED", "PAUSE", "RESUME")
EXACT_NUMBERS = ("step", "operation_index", "sequence", "number", "direction",
                 "score", "shots", "home_score", "away_score", "home_shots", "away_shots",
                 "speed_multiplier", "foul_count", "card_count")
EXACT_NUMBERS += ("rng_word_count", "rng_words", "rng_index", "word_before", "word_after", "bit_value")
TOLERANCES = {"position": 1e-3, "velocity": 1e-3, "target": 1e-3, "spot": 1e-3,
              "target_point": 1e-3, "stamina": 1e-6, "default": 1e-8, "relative": 1e-9}


def is_json_integer(value: object) -> bool:
    return type(value) in (int, float) and abs(value) < 9e15 and math.isfinite(value) and int(value) == value


def protocol_definition() -> dict:
    return {"input_format": INPUT_FORMAT, "trace_format": TRACE_FORMAT,
            "report_format": REPORT_FORMAT, "version": VERSION,
            "operations": list(OPERATION_KINDS), "max_dt": FIXED_PHYSICS_DT,
            "speeds": list(SPEED_OPTIONS), "exact_numbers": list(EXACT_NUMBERS),
            "tolerances": dict(TOLERANCES)}
