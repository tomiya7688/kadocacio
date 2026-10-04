"""Portable first-divergence comparison; matching samples are not engine parity."""

import math

from scripts.core.match_protocol import EXACT_NUMBERS, REPORT_FORMAT, TRACE_FORMAT, TOLERANCES, VERSION, is_json_integer


def validate_trace(trace: object) -> None:
    if not isinstance(trace, dict) or trace.get("format") != TRACE_FORMAT or not is_json_integer(trace.get("version")) or trace["version"] != VERSION:
        raise ValueError("unsupported match trace")
    source = trace.get("source")
    if not isinstance(source, dict) or source.get("execution") not in ("simulation", "contract_roundtrip"):
        raise ValueError("trace must declare execution scope")
    if any(not isinstance(source.get(key), str) or not source[key] for key in ("implementation", "rng", "seed_text")):
        raise ValueError("missing source provenance")
    entries = trace.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("trace must contain observations")
    sequence = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not is_json_integer(entry.get("operation_index")) or entry["operation_index"] != index:
            raise ValueError("invalid operation index")
        _validate_snapshot(entry.get("snapshot"))
        events = entry.get("events")
        if not isinstance(events, list) or "result" not in entry or (entry["result"] is not None and not isinstance(entry["result"], dict)):
            raise ValueError("missing events/result boundary")
        for event in events:
            if not isinstance(event, dict) or not is_json_integer(event.get("sequence")) or event["sequence"] <= sequence or not _nonnegative_number(event.get("game_time")) or not _nonnegative_number(event.get("simulation_elapsed")) or not isinstance(event.get("text"), str):
                raise ValueError("invalid chronological event")
            sequence = event["sequence"]
        if entry["result"] is not None:
            result = entry["result"]
            if any(not _nonnegative_integer(result.get(key)) for key in ("home_score", "away_score", "home_shots", "away_shots")) or not _nonnegative_number(result.get("game_time")):
                raise ValueError("invalid result values")
    _validate_json(trace)


def _nonnegative_number(value: object) -> bool:
    return type(value) in (int, float) and 0 <= value < 9e15 and math.isfinite(value)


def _nonnegative_integer(value: object) -> bool:
    return is_json_integer(value) and value >= 0


def _vector(value: object, size: int) -> bool:
    return isinstance(value, list) and len(value) == size and all(type(component) in (int, float) and abs(component) < 9e15 and math.isfinite(component) for component in value)


def _validate_snapshot(snapshot: object) -> None:
    if not isinstance(snapshot, dict) or not _nonnegative_integer(snapshot.get("step")):
        raise ValueError("invalid snapshot step")
    for key in ("status", "ball", "home", "away"):
        if not isinstance(snapshot.get(key), dict):
            raise ValueError("missing observation: " + key)
    status, ball = snapshot["status"], snapshot["ball"]
    if not isinstance(status.get("state"), str) or not status["state"] or not _nonnegative_number(status.get("game_time")) or any(not _nonnegative_integer(status.get(key)) for key in ("home_score", "away_score")):
        raise ValueError("invalid clock/score observation")
    if type(snapshot.get("paused")) is not bool or not _nonnegative_number(snapshot.get("simulation_elapsed")):
        raise ValueError("invalid simulation clock/pause observation")
    if "owner" not in ball or (ball["owner"] is not None and (not isinstance(ball["owner"], str) or not ball["owner"])) or not _vector(ball.get("position"), 3) or not _vector(ball.get("velocity"), 3):
        raise ValueError("invalid ball observation")
    if "restart" not in snapshot or (snapshot["restart"] is not None and not isinstance(snapshot["restart"], dict)):
        raise ValueError("invalid restart observation")
    for side in ("home", "away"):
        players = snapshot[side].get("players")
        if not isinstance(players, list):
            raise ValueError("missing player decisions")
        for player in players:
            if not isinstance(player, dict) or any(not isinstance(player.get(key), str) or not player[key] for key in ("id", "command")) or not _vector(player.get("position"), 3) or not _vector(player.get("target"), 2) or not _nonnegative_number(player.get("stamina")):
                raise ValueError("invalid player decision")


def _validate_json(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON keys must be strings")
            _validate_json(child)
    elif isinstance(value, list):
        for child in value:
            _validate_json(child)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite observation")
    elif value is not None and type(value) not in (str, bool, int, float):
        raise ValueError("observation must contain only JSON values")


def first_difference(expected: object, actual: object, path: str = "$") -> dict | None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(expected.keys() | actual.keys()):
            child_path = f"{path}.{key}"
            if key not in expected or key not in actual:
                return {"path": child_path, "reason": "missing_key", "expected": expected.get(key), "actual": actual.get(key)}
            difference = first_difference(expected[key], actual[key], child_path)
            if difference:
                return difference
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return {"path": path, "reason": "length", "expected": len(expected), "actual": len(actual)}
        for index, (left, right) in enumerate(zip(expected, actual)):
            difference = first_difference(left, right, f"{path}[{index}]")
            if difference:
                return difference
        return None
    if type(expected) in (int, float) and type(actual) in (int, float):
        fields = path.replace("[", ".").replace("]", "").split(".")
        tolerance = 0.0 if any(field in EXACT_NUMBERS for field in fields) else next((TOLERANCES[field] for field in reversed(fields) if field in TOLERANCES), TOLERANCES["default"])
        relative = 0.0 if tolerance == 0 else TOLERANCES["relative"] * max(abs(expected), abs(actual))
        equal = abs(expected - actual) <= tolerance + relative
    else:
        equal = type(expected) is type(actual) and expected == actual
    return None if equal else {"path": path, "reason": "value", "expected": expected, "actual": actual}


def compare_traces(expected: dict, actual: dict) -> dict:
    validate_trace(expected)
    validate_trace(actual)
    report = {"format": REPORT_FORMAT, "version": VERSION, "same_observations": True,
              "kernel_parity": "not_evaluated", "scope": "contract_roundtrip" if actual["source"]["execution"] == "contract_roundtrip" or expected["source"]["execution"] == "contract_roundtrip" else "simulation_observations",
              "sources": {"expected": expected["source"], "actual": actual["source"]},
              "first_difference": None, "first_state_difference": None,
              "first_event_difference": None, "first_result_difference": None}
    left, right = expected["entries"], actual["entries"]
    if expected["source"]["seed_text"] != actual["source"]["seed_text"]:
        report["first_difference"] = {"path": "$.source.seed_text", "reason": "different_input_seed", "expected": expected["source"]["seed_text"], "actual": actual["source"]["seed_text"], "entry_index": None, "operation_index": None, "step": None, "category": "input"}
    for index in range(max(len(left), len(right))):
        if index >= min(len(left), len(right)):
            difference = {"path": f"$.entries[{index}]", "reason": "missing_entry", "expected": index < len(left), "actual": index < len(right), "entry_index": index, "step": None, "operation_index": index, "category": "trace"}
            report["first_difference"] = report["first_difference"] or difference
            break
        for field, category in (("snapshot", "state"), ("events", "event"), ("result", "result")):
            difference = first_difference(left[index][field], right[index][field], f"$.entries[{index}].{field}")
            if difference:
                difference.update(entry_index=index, operation_index=index, step=left[index]["snapshot"]["step"], category=category)
                key = f"first_{category}_difference"
                report[key] = report[key] or difference
                report["first_difference"] = report["first_difference"] or difference
    report["same_observations"] = report["first_difference"] is None
    return report
