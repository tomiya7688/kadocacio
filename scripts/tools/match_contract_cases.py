"""Small negative boundary fixtures, never synthetic football results."""

from copy import deepcopy

from scripts.core.match_trace_comparison import compare_traces, validate_trace
from scripts.tools.match_contract_input import restore_contract_input


def input_cases(payload: dict) -> list[dict]:
    cases = []
    for name, path, value in (
        ("format", ("format",), "future"), ("version", ("version",), True),
        ("no_repro", ("repro_input",), None), ("no_settings", ("repro_input", "settings"), None),
        ("seed_number", ("repro_input", "settings", "seed"), 42),
        ("seed_zeroes", ("repro_input", "settings", "seed"), "01"),
        ("max_steps_bool", ("repro_input", "settings", "max_steps"), True),
        ("dt", ("repro_input", "settings", "fixed_physics_dt"), 0.1),
        ("venue", ("repro_input", "settings", "venue_mode"), "other"),
        ("AI", ("repro_input", "settings", "ai_rethink_multiplier"), 4),
        ("no_teams", ("repro_input", "teams"), None),
        ("RGB", ("repro_input", "teams", "home", "primary"), [True, 2, 3]),
        ("old_commands", ("repro_input", "commands"), [{"future": True}]),
        ("empty_operations", ("operations",), []),
        ("wrong_first", ("operations",), [{"kind": "STEP", "dt": 0.05}]),
        ("double_start", ("operations",), [{"kind": "START"}, {"kind": "START"}]),
        ("unknown_operation", ("operations",), [{"kind": "START"}, {"kind": "SHOT"}]),
        ("oversize_step", ("operations",), [{"kind": "START"}, {"kind": "STEP", "dt": 0.1}]),
        ("extra_field", ("operations",), [{"kind": "START", "ignored": True}]),
    ):
        actual = deepcopy(payload)
        parent = actual
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = value
        try:
            restore_contract_input(actual)
            valid = True
        except ValueError:
            valid = False
        cases.append({"name": name, "input": actual, "valid": valid})
    return cases


def comparison_cases(trace: dict) -> list[dict]:
    expected = deepcopy(trace)
    expected["entries"] = expected["entries"][:7]
    cases = []
    for name, path, value in (
        ("same", (), None),
        ("clock", ("snapshot", "status", "game_time"), 12.0),
        ("score", ("snapshot", "status", "home_score"), 1),
        ("owner", ("snapshot", "ball", "owner"), "AWAY:0"),
        ("restart", ("snapshot", "restart"), {"kind": "FREE_KICK", "side": "AWAY", "spot": [34.0, 72.0], "taker": "AWAY:0", "elapsed": 0.1}),
        ("decision", ("snapshot", "home", "players", 0, "command"), "SHOOT"),
        ("position_inside_tolerance", ("snapshot", "ball", "position", 0), expected["entries"][-1]["snapshot"]["ball"]["position"][0] + 0.0002),
    ):
        actual = deepcopy(expected)
        if path:
            parent = actual["entries"][-1]
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = value
        cases.append({"name": name, "expected": expected, "actual": actual, "report": compare_traces(expected, actual)})
    actual = deepcopy(expected)
    actual["entries"][0]["events"][0]["text"] += "違い"
    cases.append({"name": "event", "expected": expected, "actual": actual, "report": compare_traces(expected, actual)})
    return cases


def trace_cases(trace: dict) -> list[dict]:
    """Malformed observation values must not compare equal in either engine."""
    cases = []
    for name, path, value in (
        ("clock_text", ("snapshot", "status", "game_time"), "0"),
        ("fractional_score", ("snapshot", "status", "home_score"), 0.5),
        ("negative_score", ("snapshot", "status", "away_score"), -1),
        ("empty_state", ("snapshot", "status", "state"), ""),
        ("pause_number", ("snapshot", "paused"), 0),
        ("negative_elapsed", ("snapshot", "simulation_elapsed"), -1),
        ("owner_number", ("snapshot", "ball", "owner"), 0),
        ("position_size", ("snapshot", "ball", "position"), [1, 2]),
        ("velocity_bool", ("snapshot", "ball", "velocity"), [True, 0, 0]),
        ("restart_number", ("snapshot", "restart"), 0),
        ("player_id", ("snapshot", "home", "players", 0, "id"), ""),
        ("command_bool", ("snapshot", "home", "players", 0, "command"), False),
        ("player_position", ("snapshot", "home", "players", 0, "position"), None),
        ("player_target", ("snapshot", "home", "players", 0, "target"), [1, "2"]),
        ("stamina_text", ("snapshot", "home", "players", 0, "stamina"), "10"),
        ("event_clock", ("events", 0, "game_time"), False),
        ("event_elapsed", ("events", 0, "simulation_elapsed"), -1),
        ("event_text", ("events", 0, "text"), 1),
        ("empty_result", ("result",), {}),
    ):
        actual = deepcopy(trace)
        actual["entries"] = actual["entries"][:1]
        parent = actual["entries"][0]
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = value
        try:
            validate_trace(actual)
            valid = True
        except ValueError:
            valid = False
        cases.append({"name": name, "trace": actual, "valid": valid})
    return cases
