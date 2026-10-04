"""Actual Python ball-rule oracle with explicitly intercepted contact/restart seams."""

import argparse
from copy import deepcopy
import json
from pathlib import Path

from scripts.core.paths import USER_LOG_DIR
from scripts.core.settings import FIELD, GOAL_HALF_HEIGHT, GOAL_HEIGHT
from scripts.core.simulation_geometry import Vec2
from scripts.core.match_protocol import TRACE_FORMAT, VERSION
from scripts.match.match_engine import Match
from scripts.match.player_command import PlayerCommand
from scripts.tools.godot_match_fixture import write_fixture
from scripts.tools.godot_team_oracle import assert_sources_unchanged
from scripts.tools.match_contract_input import restore_contract_input

DEFAULT_OUTPUT = USER_LOG_DIR / "godot/ball_physics"
SCALARS = ("pickup_lock", "curve_acceleration", "knuckle_amplitude", "knuckle_phase", "flight_type",
           "flight_serial", "shot_serial", "shot_deception", "shot_outcome", "shot_miss_announced",
           "pass_outcome", "pass_brake", "eye_contact_bonus", "catch_forbidden", "last_keeper_response", "recovery_timer")
VECTORS = ("control_offset", "curve_vector", "intended_destination")


def identity(match, player):
    if player is None:
        return None
    team = match.home if player.team is match.home else match.away
    return ("HOME" if team is match.home else "AWAY") + ":" + str(team.players.index(player))


def ball_values(match: Match) -> dict:
    ball = match.ball
    return {"position": [ball.pos.x, ball.pos.y, ball.z], "velocity": [ball.vel.x, ball.vel.y, ball.vertical_speed],
            **{key: getattr(ball, key) for key in SCALARS}, **{key: list(getattr(ball, key)) for key in VECTORS},
            **{key: identity(match, getattr(ball, key)) for key in ("owner", "last_touch", "intended")},
            "recovery_team": None if ball.recovery_team is None else "HOME" if ball.recovery_team is match.home else "AWAY"}


def case_definitions() -> list[dict]:
    x, y = FIELD.center
    right, left, top, bottom = FIELD.right, FIELD.left, FIELD.top, FIELD.bottom
    cases = [
        {"name": "slow_roll", "steps": 260, "ball": {"position": [x, y, 0], "velocity": [32, 11, 0]}},
        {"name": "fast_roll", "steps": 80, "ball": {"velocity": [370, -26, 0]}},
        {"name": "settling", "steps": 4, "ball": {"velocity": [6, 0, 0], "pass_brake": 2}},
        {"name": "negative_brake", "steps": 4, "ball": {"velocity": [120, 0, 0], "pass_brake": -1}},
        {"name": "lofted", "steps": 85, "ball": {"velocity": [180, 45, 235], "pass_brake": 0.65}},
        {"name": "soft_bounce", "steps": 4, "ball": {"position": [x, y, 0.1], "velocity": [95, 0, -20]}},
        {"name": "hard_bounce", "steps": 8, "ball": {"position": [x, y, 1], "velocity": [90, 0, -160]}},
        {"name": "curve", "steps": 80, "ball": {"velocity": [200, 30, 170], "curve_acceleration": 55, "curve_vector": [25, -44]}},
        {"name": "knuckle", "steps": 85, "ball": {"velocity": [190, 20, 150], "knuckle_amplitude": 36, "knuckle_phase": 0.4}},
        {"name": "knuckle_still", "steps": 3, "ball": {"knuckle_amplitude": 0.2}},
        {"name": "held", "steps": 3, "ball": {"owner": "HOME:1", "last_touch": "HOME:1", "intended": "AWAY:1", "velocity": [210, 20, 155], "pickup_lock": 0.3}},
        {"name": "spill_tackle", "steps": 4, "operation": "spill", "recovery": "AWAY", "ball": {"owner": "HOME:1", "intended": "HOME:2", "pass_outcome": "OVERHIT", "pass_brake": 0.4}},
        {"name": "spill_plain", "steps": 4, "operation": "spill", "ball": {"owner": "HOME:1", "catch_forbidden": True}},
        {"name": "spill_non_owner", "steps": 2, "operation": "spill", "ball": {"owner": "AWAY:1"}},
        {"name": "claim", "steps": 2, "operation": "claim", "ball": {"intended": "AWAY:1", "pickup_lock": 0.3, "curve_acceleration": 20, "pass_brake": 0.6}},
        {"name": "claim_default", "steps": 2, "operation": "claim_default", "ball": {}},
        {"name": "metadata_expiry", "steps": 4, "ball": {"last_touch": "AWAY:1", "intended": "HOME:1", "recovery_team": "HOME", "recovery_timer": 0.07, "pickup_lock": 0.07, "flight_serial": 7, "shot_serial": 11, "eye_contact_bonus": 0.2}},
    ]
    for side, goal_x, direction in (("right", right, 1), ("left", left, -1)):
        for label, height, lateral, outcome in (("goal", 20, 0, ""), ("bar_exact", GOAL_HEIGHT, 0, ""),
                                                  ("bar_over", GOAL_HEIGHT + 0.01, 0, "OVER"),
                                                  ("side_exact", 0, GOAL_HALF_HEIGHT, ""),
                                                  ("wide", 0, GOAL_HALF_HEIGHT + 0.01, "WIDE"),
                                                  ("post", 18, GOAL_HALF_HEIGHT, "POST"),
                                                  ("post_not_shot", 18, GOAL_HALF_HEIGHT, "POST")):
            cases.append({"name": side + "_" + label, "steps": 2, "ball": {
                "position": [goal_x - direction, y + lateral, height], "velocity": [direction * 80, 0, 0],
                "shot_outcome": outcome, "flight_type": "パス" if label == "post_not_shot" else "シュート",
                "catch_forbidden": True}})
        for last in (None, "HOME:1", "AWAY:1"):
            cases.append({"name": side + "_endline_" + str(last), "steps": 1, "ball": {
                "position": [goal_x - direction, y + 110, 0], "velocity": [direction * 80, 0, 0], "last_touch": last}})
    for touch_y in (top - 1, bottom + 1):
        for last in (None, "HOME:1", "AWAY:1"):
            cases.append({"name": "throw_" + str(touch_y) + "_" + str(last), "steps": 1,
                          "ball": {"position": [x, touch_y, 0], "last_touch": last}})
    cases += [
        {"name": "line_exact", "steps": 1, "ball": {"position": [right, y, 0]}},
        {"name": "corner_priority", "steps": 1, "ball": {"position": [right + 1, top - 1, 0]}},
        {"name": "post_above", "steps": 1, "ball": {"position": [right + 1, top - 1, 110], "flight_type": "シュート", "shot_outcome": "POST"}},
        {"name": "keeper_hands", "steps": 1, "ball": {"position": [left + 70, y, 30]}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_opponent_touch", "steps": 1, "ball": {"position": [left + 70, y, 0], "last_touch": "AWAY:1"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_self_touch", "steps": 1, "ball": {"position": [left + 70, y, 0], "last_touch": "HOME_GK"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_backpass_feet", "steps": 1, "ball": {"position": [left + 70, y, 0], "last_touch": "HOME:1", "intended": "HOME_GK"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_backpass_high", "steps": 1, "ball": {"position": [left + 70, y, 30], "last_touch": "HOME:1", "flight_type": "パス"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_outside_feet", "steps": 1, "ball": {"position": [left + 500, y, 0]}, "players": [{"id": "HOME_GK", "position": [left + 500, y, 0]}]},
        {"name": "keeper_box_edge", "steps": 1, "ball": {"position": [left + 400, y + 380, 0]}, "players": [{"id": "HOME_GK", "position": [left + 400, y + 380, 0]}]},
        {"name": "keeper_air_reach", "steps": 1, "ball": {"position": [left + 70, y, 71]}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 20]}]},
        {"name": "keeper_air_too_high", "steps": 1, "ball": {"position": [left + 70, y, 72]}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 20]}]},
        {"name": "keeper_fast_shot_skip", "steps": 1, "ball": {"position": [left + 70, y, 0], "velocity": [-220, 0, 0], "flight_type": "シュート"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "contact_order", "steps": 1, "ball": {}, "players": [{"id": "HOME:1", "position": [x, y, 0]}, {"id": "AWAY:1", "position": [x, y, 0]}]},
        {"name": "contact_recovery", "steps": 1, "ball": {"recovery_team": "AWAY", "recovery_timer": 1.25}, "players": [{"id": "HOME:1", "position": [x, y, 0]}, {"id": "AWAY:1", "position": [x + 12, y, 0]}]},
        {"name": "contact_lock", "steps": 1, "ball": {"last_touch": "HOME:1", "pickup_lock": 0.2}, "players": [{"id": "HOME:1", "position": [x, y, 0]}, {"id": "AWAY:1", "position": [x + 4, y, 0]}]},
        {"name": "contact_sent_off", "steps": 1, "ball": {}, "players": [{"id": "HOME:1", "position": [x, y, 0], "sent_off": True}]},
        {"name": "contact_too_high", "steps": 1, "ball": {"position": [x, y, 30]}, "players": [{"id": "HOME:1", "position": [x, y, 0]}]},
        {"name": "contact_air_low", "steps": 1, "ball": {"position": [x, y, 35]}, "players": [{"id": "HOME:1", "position": [x + 10, y, 2], "jump_accuracy": 0.0}]},
        {"name": "contact_air_high", "steps": 1, "ball": {"position": [x, y, 35]}, "players": [{"id": "HOME:1", "position": [x + 10, y, 2], "jump_accuracy": 1.0}]},
        {"name": "contact_intended", "steps": 1, "ball": {"intended": "HOME:1", "velocity": [30, 0, 0]}, "players": [{"id": "HOME:1", "position": [x + 2, y, 0]}]},
    ]
    return cases


def configure(match: Match, case: dict) -> dict:
    players = {side + ":" + str(index): player for side, team in (("HOME", match.home), ("AWAY", match.away)) for index, player in enumerate(team.players)}
    for player in players.values():
        player.pos.update(FIELD.centerx, FIELD.top + 20)
        player.z = 0.0
        player.motion_velocity.update(8, -4)
        player.skills = frozenset()
        player.technique_command = PlayerCommand.IDLE
    references = {**players, "HOME_GK": match.home.keeper, "AWAY_GK": match.away.keeper}
    ball = match.ball
    ball.owner = ball.last_touch = ball.intended = None
    ball.pos.update(FIELD.center)
    ball.z = 0.0
    ball.vel.update(0, 0)
    for key, value in case["ball"].items():
        if key in ("position", "velocity"):
            horizontal, vertical = ("pos", "z") if key == "position" else ("vel", "vertical_speed")
            getattr(ball, horizontal).update(value[:2])
            setattr(ball, vertical, value[2])
        elif key in VECTORS:
            getattr(ball, key).update(value)
        elif key in ("owner", "last_touch", "intended"):
            setattr(ball, key, references.get(value))
        elif key == "recovery_team":
            ball.recovery_team = match.home if value == "HOME" else match.away
        else:
            setattr(ball, key, value)
    for record in case.get("players", []):
        player = references[record["id"]]
        player.pos.update(record["position"][:2])
        player.z = record["position"][2]
        player.sent_off = record.get("sent_off", False)
        player.jump_accuracy = record.get("jump_accuracy", player.jump_accuracy)
    return players


def capture_case(home: dict, away: dict, case: dict) -> tuple[dict, list[dict]]:
    match = Match(home, away, "NEUTRAL", seed=41)
    match.start_new()
    players = configure(match, case)
    initial = {"ball": ball_values(match), "players": [{"id": key, "position": [player.pos.x, player.pos.y, player.z],
               "velocity": [player.motion_velocity.x, player.motion_velocity.y, 0], "sent_off": player.sent_off,
               "contact_jump_accuracy": player.effective_stat(player.jump_accuracy)} for key, player in players.items()]}
    operation = case.get("operation", "flight")
    if operation == "spill":
        match.release_ball_from_knockback(players["HOME:1"], Vec2(0.6, 0.8), match.away if case.get("recovery") else None)
    elif operation.startswith("claim"):
        match.change_owner(players["HOME:1"], (8, -3) if operation == "claim" else None)
    # Only flight, spatial eligibility and boundary detection are under test.
    # Keeper/skill/control/manager and restart progress are separately owned units.
    match.keeper_save = lambda: False
    match.rng.random = lambda: 0.0
    match.choose_pass_target = lambda player: None
    match.apply_pending_manager_changes = lambda reason: None
    pending = {"boundary": None, "contact": None, "ball": None}

    def goal(team):
        pending["boundary"] = {"kind": "GOAL", "side": "HOME" if team is match.home else "AWAY", "spot": list(match.ball.pos)}

    def set_piece(kind, team, spot):
        pending["boundary"] = {"kind": kind, "side": "HOME" if team is match.home else "AWAY", "spot": list(spot)}

    original_throw = match.start_throw_in

    def throw():
        pending["ball"] = ball_values(match)
        original_throw()
        pending["boundary"] = {"kind": "THROW_IN", "side": "HOME" if match.throw_in_team is match.home else "AWAY", "spot": list(match.throw_in_spot)}

    def touch(player, *args):
        pending["contact"] = {"kind": "TOUCH", "player": identity(match, player), "hands_legal": player.is_keeper and match.keeper_can_use_hands(player)}
        raise StopIteration

    match.handle_goal, match.start_set_piece, match.start_throw_in = goal, set_piece, throw
    match.change_owner = match.resolve_keeper_contact = touch
    frames = []
    for step in range(case["steps"]):
        try:
            match.update_loose_ball(0.05)
        except StopIteration:
            pass
        frames.append({"step": step + 1, "case_name": case["name"], "ball": pending["ball"] or ball_values(match),
                       "boundary": pending["boundary"], "contact": pending["contact"]})
        if pending["boundary"] is not None or pending["contact"] is not None:
            break
    return initial, frames


def observation(frame: dict, index: int) -> dict:
    return {"operation_index": index, "snapshot": {**frame, "paused": False, "simulation_elapsed": 0.0,
            "status": {"state": "PLAYING", "game_time": 0.0, "home_score": 0, "away_score": 0},
            "home": {"players": []}, "away": {"players": []}, "restart": None}, "events": [], "result": None}


def write_ball_fixture(output: Path = DEFAULT_OUTPUT) -> tuple[Path, dict[str, str]]:
    path, hashes = write_fixture(output, 1)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        home, away, _, _ = restore_contract_input(document["input"])
        cases, entries = [], []
        for case in case_definitions():
            initial, frames = capture_case(home, away, case)
            cases.append({**deepcopy(case), "initial": initial, "frames": frames})
            first_index = len(entries)
            entries.extend(observation(frame, first_index + index) for index, frame in enumerate(frames))
        document["cases"] = cases
        document["reference"] = {"format": TRACE_FORMAT, "version": VERSION, "source": {
            "implementation": "python-ball-rules/Match.update_loose_ball", "execution": "simulation",
            "rng": "contact success intercepted; flight deterministic", "seed_text": "41"}, "entries": entries}
        path.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return path, hashes
    finally:
        assert_sources_unchanged(hashes)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    path, _ = write_ball_fixture(args.output)
    print(f"GODOT BALL FIXTURE: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
