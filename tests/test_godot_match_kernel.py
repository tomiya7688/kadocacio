"""Reference-preserving RNG injection and public-only foundation fixture checks."""

from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from scripts.core.match_trace_comparison import compare_traces
from scripts.match.match_session import MatchSession
from scripts.tools import godot_kernel_fixture as fixture, godot_runner as runner
from scripts.tools.godot_match_fixture import write_fixture
from scripts.tools.match_contract_input import restore_contract_input
from scripts.tools.match_random_audit import MatchRandomAudit


class GodotMatchKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = write_fixture(Path(directory), 2)
            cls.input = json.loads(path.read_text(encoding="utf-8"))["input"]
        cls.home, cls.away, cls.settings, _ = restore_contract_input(cls.input)

    def test_audit_records_primitives_without_changing_reference_sequence(self):
        for seed in (0, -1, 2**63 + 12345, 10**4095 + 321):
            actual, expected = MatchRandomAudit(seed), random.Random(seed)
            for _ in range(720):
                self.assertEqual(actual.random(), expected.random())
            for bits in (0, 1, 32, 33, 53):
                self.assertEqual(actual.getrandbits(bits), expected.getrandbits(bits))
            for _ in range(3):
                self.assertEqual(actual.uniform(-2, 7), expected.uniform(-2, 7))
                self.assertEqual(actual.randint(-30, 45), expected.randint(-30, 45))
                self.assertEqual(actual.choice(["a", "b", "c"]), expected.choice(["a", "b", "c"]))
                self.assertEqual(actual.gauss(2.0, 0.7), expected.gauss(2.0, 0.7))
            self.assertEqual(actual.getstate(), expected.getstate())
            snapshot = actual.getstate()
            copied = actual.history()
            copied[0]["value"] = -1
            self.assertNotEqual(actual.history()[0]["value"], -1)
            self.assertEqual(actual.getstate(), snapshot)
            self.assertEqual(actual.state_payload()["words"], list(snapshot[1][:-1]))
            self.assertEqual(actual.history()[-1]["word_after"], actual.word_count)
        with self.assertRaises(ValueError):
            MatchRandomAudit(1).getrandbits(-1)

    def test_injected_audit_keeps_real_match_rules_and_rng_state(self):
        global_state = random.getstate()
        settings = {**self.settings, "max_steps": 100}
        default = MatchSession(self.home, self.away, **settings)
        audited = MatchSession(self.home, self.away, **settings, rng_factory=MatchRandomAudit)
        for session in (default, audited):
            session.apply({"kind": "START"})
        for step in range(80):
            audited._match.rng.purpose, audited._match.rng.step = "test.live", step
            for session in (default, audited):
                session.apply({"kind": "STEP", "dt": 0.05})
        self.assertEqual(default.observe().to_payload(), audited.observe().to_payload())
        self.assertEqual(default._match.rng.getstate(), audited._match.rng.getstate())
        self.assertEqual(random.getstate(), global_state)
        self.assertTrue(audited._match.rng.history())
        capture = fixture.capture_kickoff(self.input)
        self.assertEqual(capture, fixture.capture_kickoff(self.input))
        changed = deepcopy(capture)
        changed["entries"][0]["snapshot"]["rng"]["rng_draws"][0]["purpose"] = "wrong"
        report = compare_traces(capture, changed)
        self.assertEqual(report["first_difference"]["step"], 0)
        self.assertTrue(report["first_difference"]["path"].endswith(".purpose"))
        changed = deepcopy(capture)
        changed["entries"][0]["snapshot"]["rng"]["rng_words"][0] += 1
        self.assertFalse(compare_traces(capture, changed)["same_observations"])

    def test_public_fixture_cli_clocks_and_original_fingerprint_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path, hashes = fixture.write_kernel_fixture(output)
            self.assertEqual(len(hashes), 2)
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(document["rng_cases"]), 8)
            self.assertEqual(len(document["clock_cases"]), 6)
            self.assertEqual(len(document["rng_cases"][-1]["seed_text"]), 4096)
            native = output / "native.json"
            native.write_text(json.dumps(document["reference"]), encoding="utf-8")
            self.assertTrue(fixture.compare_native(path, native)["same_observations"])
            with patch.object(fixture, "write_kernel_fixture", return_value=(path, hashes)):
                self.assertEqual(fixture.main(["--output", str(output)]), 0)
            with patch.object(fixture, "capture_kickoff", side_effect=RuntimeError("test failure")), patch.object(fixture, "assert_sources_unchanged") as checked:
                with self.assertRaises(RuntimeError):
                    fixture.write_kernel_fixture(output)
                checked.assert_called_once()
        with patch("scripts.match.match_engine.Match.update_step"):
            with self.assertRaisesRegex(ValueError, "stale"):
                fixture.clock_cases(self.home, self.away)

    def test_kernel_runner_connects_actual_checks_and_stops_on_failure(self):
        with patch.object(fixture, "write_kernel_fixture", return_value=(Path("fixture.json"), {})), patch.object(runner, "run_native_trace_check", return_value=0) as checked:
            self.assertEqual(runner.run_kernel_checks(Path("engine"), Path("project"), 60), 0)
            self.assertEqual(checked.call_args.args[-2:], ("match_kernel_tests.gd", "KADOCALCIO_MATCH_KERNEL_TESTS:"))
        with patch.object(runner, "check_scripts", return_value=0), patch.object(runner, "run_ui_checks", return_value=0), patch.object(runner, "run_team_checks", return_value=0), patch.object(runner, "run_match_checks", return_value=0), patch.object(runner, "run_kernel_checks", return_value=1), patch.object(runner, "check_error_detection") as checked:
            self.assertEqual(runner.execute("test", Path("engine"), Path("project"), 60, True), 1)
            checked.assert_not_called()
