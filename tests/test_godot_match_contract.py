"""Real Match adapter, shared input, exact/tolerant reports, safe fixture tooling."""

import json
import math
import tempfile
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from scripts.core.match_operation import MatchOperation
from scripts.core.match_protocol import is_json_integer
from scripts.core.match_trace_comparison import compare_traces, first_difference, validate_trace
from scripts.core.settings import FIELD, MATCH_SECONDS
from scripts.core.simulation_geometry import Vec2
from scripts.match.match_session import MatchSession
from scripts.match.pending_kick import PendingKick
from scripts.match.player_command import PlayerCommand
from scripts.tools import godot_match_contract as contract, godot_match_fixture as fixture
from scripts.tools.godot_team_oracle import public_team_paths, reference_case
from scripts.tools.match_contract_cases import comparison_cases, input_cases, trace_cases
from scripts.tools.match_contract_input import create_contract_input, restore_contract_input
from scripts.tools.match_contract_trace import capture_trace


class GodotMatchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.choices = [reference_case(json.loads(path.read_text(encoding="utf-8-sig")), path.relative_to(fixture.PROJECT_ROOT / "teams").as_posix())["choice"] for path in public_team_paths()[:2]]
        cls.operations = [{"kind": "START"}, {"kind": "STEP", "dt": 0.05}, {"kind": "SET_SPEED", "value": 100}, {"kind": "PAUSE"}, {"kind": "STEP", "dt": 0.05}, {"kind": "RESUME"}, {"kind": "STEP", "dt": 0.025}]
        cls.input = create_contract_input(*cls.choices, cls.operations, seed=2**63 + 12345, max_steps=20, venue_mode="NEUTRAL", ai_rethink_multiplier=1.0)
        cls.trace = capture_trace(cls.input)

    def session(self):
        home, away, settings, _ = restore_contract_input(self.input)
        return MatchSession(home, away, **settings)

    def test_operation_and_input_detach_validation_and_whole_json_numbers(self):
        for value, valid in ((0, True), (1.0, True), (1.5, False), (True, False), (None, False), (float("nan"), False), (10**500, False)):
            self.assertEqual(is_json_integer(value), valid)
        for payload in self.operations:
            operation = MatchOperation.from_payload(payload)
            self.assertEqual(operation.to_payload(), payload)
            with self.assertRaises(FrozenInstanceError):
                operation.kind = "other"
        for payload in (None, {}, {"kind": "unknown"}, {"kind": "START", "extra": 1}, {"kind": "STEP"}, {"kind": "STEP", "dt": True}, {"kind": "STEP", "dt": math.nan}, {"kind": "STEP", "dt": -1}, {"kind": "STEP", "dt": 0.1}, {"kind": "SET_SPEED", "value": True}, {"kind": "SET_SPEED", "value": 4}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                MatchOperation.from_payload(payload)
        self.assertEqual(MatchOperation.from_payload({"kind": "SET_SPEED", "value": 10.0}).value, 10)
        for row in input_cases(self.input):
            self.assertFalse(row["valid"], row["name"])
        for seed in ("", " 0", "bad", "01", "-0", "0" * 4097):
            actual = deepcopy(self.input)
            actual["repro_input"]["settings"]["seed"] = seed
            with self.subTest(seed=seed[:15]), self.assertRaises(ValueError):
                restore_contract_input(actual)
        for actual in (None, {"format": "bad"}, {**self.input, "version": 99}, {**self.input, "operations": {}}, {**self.input, "operations": [{"kind": "START"}] + [{"kind": "STEP", "dt": 0.05}] * 21}):
            with self.assertRaises(ValueError):
                restore_contract_input(actual)
        actual = deepcopy(self.input)
        actual["version"] = 1.0
        actual["repro_input"]["settings"]["max_steps"] = 20.0
        actual["repro_input"]["teams"]["home"]["primary"] = [1.0, 2.0, 3.0]
        home, _, settings, operations = restore_contract_input(actual)
        self.assertEqual(home["primary"], (1, 2, 3))
        self.assertEqual(settings["seed"], 2**63 + 12345)
        operations.clear()
        self.assertTrue(actual["operations"])
        for team in (None, {"name": "no id", "primary": {}}):
            actual = deepcopy(self.input)
            actual["repro_input"]["teams"]["home"] = team
            with self.assertRaises(ValueError):
                restore_contract_input(actual)

    def test_real_adapter_replay_fixed_step_pause_and_immutable_observation(self):
        self.assertEqual(self.trace, capture_trace(self.input))
        entries = self.trace["entries"]
        self.assertEqual(entries[4]["snapshot"]["simulation_elapsed"], 0.05)
        self.assertEqual(entries[-1]["snapshot"]["simulation_elapsed"], 0.07500000000000001)
        self.assertEqual(entries[-1]["snapshot"]["step"], 2)
        self.assertEqual(entries[-1]["snapshot"]["status"]["speed_multiplier"], 100)
        session = self.session()
        with self.assertRaises(ValueError):
            session.observe()
        with self.assertRaises(ValueError):
            session.apply({"kind": "PAUSE"})
        session.apply({"kind": "START"})
        with self.assertRaises(ValueError):
            session.apply({"kind": "START"})
        for cursor in (-1, False):
            with self.assertRaises(ValueError):
                session.observe(cursor)
        observation = session.observe()
        payload = observation.to_payload()
        payload["snapshot"]["ball"]["position"][0] = -100
        self.assertNotEqual(payload, observation.to_payload())
        with self.assertRaises(FrozenInstanceError):
            observation._json = "{}"
        self.assertEqual(len(session.observe().to_payload()["events"]), 1)
        self.assertEqual(session.observe(1).to_payload()["events"], [])
        session._max_steps = 0
        with self.assertRaises(ValueError):
            session.apply({"kind": "STEP", "dt": 0.05})

    def test_restart_pending_kick_owner_and_fulltime_use_existing_rules(self):
        session = self.session()
        session.apply({"kind": "START"})
        match = session._match  # Test setup only; not an API exposed to UI.
        match.start_set_piece("FREE_KICK", match.away, Vec2(FIELD.center))
        snapshot = session.observe().to_payload()["snapshot"]
        self.assertEqual(snapshot["restart"]["side"], "AWAY")
        session.apply({"kind": "STEP", "dt": 0.05})
        self.assertEqual(session.observe().to_payload()["snapshot"]["status"]["game_time"], 0)
        match.restart_type = ""
        match.throw_in_team = match.home
        match.thrower = match.home.players[0]
        match.pending_kick = PendingKick(match.home.players[0], PlayerCommand.PASS, target_player=match.home.players[1], target_point=Vec2(FIELD.center))
        snapshot = session.observe().to_payload()["snapshot"]
        self.assertEqual(snapshot["throw_in"]["taker"], "HOME:0")
        self.assertEqual(snapshot["pending_kick"]["command"], "PASS")
        match.pending_kick.target_point = None
        self.assertIsNone(session.observe().to_payload()["snapshot"]["pending_kick"]["target_point"])
        match.throw_in_team = None
        match.pending_kick = None
        match.ball.owner = None
        match.banner_timer = 0
        match.halftime_done = True
        match.game_time = MATCH_SECONDS - 0.5
        session.apply({"kind": "STEP", "dt": 0.05})
        observation = session.observe().to_payload()
        self.assertEqual(observation["snapshot"]["status"]["state"], "FULLTIME")
        self.assertEqual(observation["result"], json.loads(json.dumps(match.final_result().to_payload())))
        elapsed = observation["snapshot"]["simulation_elapsed"]
        session.apply({"kind": "STEP", "dt": 0.05})
        self.assertEqual(session.observe().to_payload()["snapshot"]["simulation_elapsed"], elapsed)
        trace = {**deepcopy(self.trace), "entries": [{"operation_index": 0, **observation}]}
        actual = deepcopy(trace)
        actual["entries"][0]["result"]["home_score"] += 1
        self.assertIsNotNone(compare_traces(trace, actual)["first_result_difference"])

    def test_reports_first_state_event_result_and_exact_vs_tolerant_values(self):
        for row in comparison_cases(self.trace):
            self.assertEqual(row["report"], compare_traces(row["expected"], row["actual"]))
        actual = deepcopy(self.trace)
        actual["entries"][1]["snapshot"]["status"]["game_time"] += 1
        actual["entries"][0]["events"][0]["text"] += "!"
        report = compare_traces(self.trace, actual)
        self.assertEqual(report["first_difference"]["step"], 0)
        self.assertEqual(report["first_state_difference"]["step"], 1)
        self.assertEqual(report["first_event_difference"]["category"], "event")
        self.assertEqual(report["kernel_parity"], "not_evaluated")
        actual = deepcopy(self.trace)
        actual["source"]["execution"] = "contract_roundtrip"
        self.assertEqual(compare_traces(self.trace, actual)["scope"], "contract_roundtrip")
        actual["source"]["seed_text"] = "1"
        self.assertEqual(compare_traces(self.trace, actual)["first_difference"]["category"], "input")
        shorter = {**self.trace, "entries": self.trace["entries"][:-1]}
        self.assertEqual(compare_traces(self.trace, shorter)["first_difference"]["reason"], "missing_entry")
        self.assertEqual(compare_traces(shorter, self.trace)["first_difference"]["reason"], "missing_entry")
        for left, right in (({}, {"key": None}), ([1], [1, 2]), ([1], [2]), (False, 0), ({"score": 1}, {"score": 1.00000001})):
            self.assertIsNotNone(first_difference(left, right))
        self.assertIsNone(first_difference({"position": [2000.0]}, {"position": [2000.0002]}))
        self.assertIsNone(first_difference(None, None))

    def test_malformed_traces_do_not_pass_as_equal(self):
        for row in trace_cases(self.trace):
            self.assertFalse(row["valid"], row["name"])
            with self.assertRaises(ValueError):
                compare_traces(row["trace"], row["trace"])
        invalids = [None, {}, {**self.trace, "version": True}, {**self.trace, "source": {}}, {**self.trace, "entries": []}]
        for path, value in (("operation_index", -1), ("snapshot", None), ("events", None), ("result", [])):
            actual = deepcopy(self.trace)
            actual["entries"][0][path] = value
            invalids.append(actual)
        for key, value in (("step", False), ("status", {}), ("ball", {}), ("home", {}), ("away", None), ("extra", math.nan), ("object", object())):
            actual = deepcopy(self.trace)
            actual["entries"][0]["snapshot"][key] = value
            invalids.append(actual)
        for event in ({}, {"sequence": True}, {"sequence": 0}, None):
            actual = deepcopy(self.trace)
            actual["entries"][0]["events"] = [event]
            invalids.append(actual)
        actual = deepcopy(self.trace)
        actual["source"].pop("rng")
        invalids.append(actual)
        actual = deepcopy(self.trace)
        actual["entries"][0]["snapshot"]["home"]["players"] = [None]
        invalids.append(actual)
        actual = deepcopy(self.trace)
        actual["extra"] = {1: "invalid JSON key"}
        invalids.append(actual)
        for actual in invalids:
            with self.assertRaises(ValueError):
                validate_trace(actual)

    def test_contract_export_and_safe_public_fixture_cli(self):
        with self.assertRaises(ValueError):
            MatchSession(*self.choices, seed=None, venue_mode="NEUTRAL", ai_rethink_multiplier=1.0, max_steps=1)
        self.assertTrue(contract.check_contract())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertFalse(contract.check_contract(output / "missing.json"))
            path = output / "contract.json"
            with patch.object(contract, "CONTRACT_PATH", path):
                self.assertEqual(contract.main(["--write"]), 0)
            self.assertTrue(contract.check_contract(path))
            path.write_text("{}", encoding="utf-8")
            self.assertFalse(contract.check_contract(path))
            for valid in (False, True):
                with patch.object(contract, "check_contract", return_value=valid):
                    self.assertEqual(contract.main([]), 0 if valid else 1)
            path, fingerprints = fixture.write_fixture(output, 2)
            self.assertTrue(path.is_file())
            self.assertEqual(len(fingerprints), 2)
            for steps in (0, 501, True):
                with self.assertRaises(ValueError):
                    fixture.write_fixture(output, steps)
            with patch.object(fixture, "check_contract", return_value=False), self.assertRaises(ValueError):
                fixture.write_fixture(output)
            with patch.object(fixture, "public_team_paths", return_value=[]), self.assertRaises(ValueError):
                fixture.write_fixture(output)
            with patch.object(fixture, "reference_case", return_value={"valid": False}), self.assertRaises(ValueError):
                fixture.write_fixture(output)
            native = output / "native.json"
            native.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8"))["reference"]), encoding="utf-8")
            self.assertEqual(fixture.main(["--fixture", str(path), "--actual", str(native), "--output", str(output)]), 0)
            actual = json.loads(native.read_text(encoding="utf-8"))
            actual["entries"][0]["snapshot"]["status"]["home_score"] += 1
            native.write_text(json.dumps(actual), encoding="utf-8")
            self.assertEqual(fixture.main(["--fixture", str(path), "--actual", str(native), "--output", str(output)]), 1)
            for args in (["--actual", str(native)], ["--fixture", str(path)], ["--actual", "missing", "--fixture", str(path)]):
                self.assertEqual(fixture.main(args), 2)
            with patch.object(fixture, "write_fixture", return_value=(path, {})):
                self.assertEqual(fixture.main([]), 0)
