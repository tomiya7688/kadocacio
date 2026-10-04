"""Actual-reference ball fixtures and native runner safety gates, not UI parity."""

from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from scripts.core.match_trace_comparison import compare_traces
from scripts.core.settings import GOAL_HEIGHT
from scripts.tools import godot_ball_fixture as fixture, godot_runner as runner
from scripts.tools.match_contract_input import restore_contract_input


class GodotBallPhysicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            path, cls.hashes = fixture.write_ball_fixture(Path(directory))
            cls.document = json.loads(path.read_text(encoding="utf-8"))
        cls.cases = {case["name"]: case for case in cls.document["cases"]}

    def test_real_rule_oracle_has_trajectories_bounds_and_contact_gates(self):
        trace = self.document["reference"]
        self.assertTrue(compare_traces(trace, trace)["same_observations"])
        self.assertEqual(len(self.hashes), 2)
        self.assertGreaterEqual(len(self.cases), 50)
        self.assertEqual(self.cases["slow_roll"]["frames"][-1]["ball"]["velocity"], [0.0, 0.0, 0.0])
        self.assertGreater(max(frame["ball"]["position"][2] for frame in self.cases["lofted"]["frames"]), 80)
        self.assertGreater(self.cases["hard_bounce"]["frames"][0]["ball"]["velocity"][2], 0)
        self.assertEqual(self.cases["soft_bounce"]["frames"][0]["ball"]["velocity"][2], 0)
        for side in ("left", "right"):
            self.assertEqual(self.cases[side + "_bar_exact"]["frames"][0]["boundary"]["kind"], "GOAL")
            self.assertEqual(self.cases[side + "_bar_over"]["frames"][0]["boundary"]["kind"], "GOAL_KICK")
            self.assertEqual(self.cases[side + "_post"]["frames"][0]["ball"]["flight_type"], "ポスト跳ね返り")
            self.assertGreater(self.cases[side + "_bar_over"]["frames"][0]["ball"]["position"][2], GOAL_HEIGHT)
        self.assertIsNone(self.cases["line_exact"]["frames"][0]["boundary"])
        self.assertEqual(self.cases["corner_priority"]["frames"][0]["boundary"]["kind"], "THROW_IN")
        for name, expected in (("contact_order", "HOME:1"), ("contact_recovery", "AWAY:1"), ("contact_lock", "AWAY:1"), ("contact_air_high", "HOME:1")):
            self.assertEqual(self.cases[name]["frames"][0]["contact"]["player"], expected)
        for name in ("contact_sent_off", "contact_too_high", "contact_air_low"):
            self.assertIsNone(self.cases[name]["frames"][0]["contact"])
        for name in ("keeper_hands", "keeper_opponent_touch", "keeper_self_touch", "keeper_box_edge", "keeper_air_reach"):
            self.assertTrue(self.cases[name]["frames"][0]["contact"]["hands_legal"])
        for name in ("keeper_backpass_feet", "keeper_outside_feet"):
            self.assertFalse(self.cases[name]["frames"][0]["contact"]["hands_legal"])
        for name in ("keeper_backpass_high", "keeper_air_too_high", "keeper_fast_shot_skip"):
            self.assertIsNone(self.cases[name]["frames"][0]["contact"])

    def test_possession_metadata_and_reproducible_isolated_capture(self):
        for name in ("held", "claim", "claim_default", "spill_tackle", "spill_plain", "spill_non_owner", "metadata_expiry"):
            with self.subTest(name=name):
                case = self.cases[name]
                home, away, _, _ = restore_contract_input(self.document["input"])
                before = random.getstate()
                initial, frames = fixture.capture_case(home, away, case)
                self.assertEqual((initial, frames), (case["initial"], case["frames"]))
                self.assertEqual(random.getstate(), before)
        held = self.cases["held"]
        self.assertTrue(all(frame["ball"] == held["initial"]["ball"] for frame in held["frames"]))
        self.assertIsNone(self.cases["spill_tackle"]["frames"][0]["ball"]["owner"])
        self.assertEqual(self.cases["spill_tackle"]["frames"][0]["ball"]["recovery_team"], "AWAY")
        self.assertEqual(self.cases["spill_non_owner"]["frames"][0]["ball"]["owner"], "AWAY:1")
        self.assertIsNone(self.cases["metadata_expiry"]["frames"][-1]["ball"]["recovery_team"])
        self.assertEqual(self.cases["claim"]["frames"][0]["ball"]["control_offset"], [8.0, -3.0])
        copied = deepcopy(self.document["reference"])
        copied["entries"][0]["snapshot"]["ball"]["velocity"][0] += 0.1
        self.assertFalse(compare_traces(self.document["reference"], copied)["same_observations"])

    def test_cli_and_original_hash_guard_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            with patch.object(fixture, "write_ball_fixture", return_value=(path, self.hashes)):
                self.assertEqual(fixture.main(["--output", directory]), 0)
            with patch.object(fixture, "capture_case", side_effect=RuntimeError("fixture failure")), patch.object(fixture, "assert_sources_unchanged") as guard:
                with self.assertRaises(RuntimeError):
                    fixture.write_ball_fixture(Path(directory))
                guard.assert_called_once()

    def test_runner_actual_ball_stage_and_fail_closed(self):
        with patch.object(fixture, "write_ball_fixture", return_value=(Path("fixture.json"), {})), patch.object(runner, "run_native_trace_check", return_value=0) as checked:
            self.assertEqual(runner.run_ball_checks(Path("engine"), Path("project"), 60), 0)
            self.assertEqual(checked.call_args.args[-2:], ("ball_physics_tests.gd", "KADOCALCIO_BALL_TESTS:"))
        with patch.object(runner, "check_scripts", return_value=0), patch.object(runner, "run_ui_checks", return_value=0), patch.object(runner, "run_team_checks", return_value=0), patch.object(runner, "run_match_checks", return_value=0), patch.object(runner, "run_kernel_checks", return_value=0), patch.object(runner, "run_ball_checks", return_value=1), patch.object(runner, "check_error_detection") as checked:
            self.assertEqual(runner.execute("test", Path("engine"), Path("project"), 60, True), 1)
            checked.assert_not_called()
