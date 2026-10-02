from __future__ import annotations

import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.tools import godot_runner as runner


class GodotRunnerTests(unittest.TestCase):
    def test_explicit_engine_and_environment_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Path(directory) / "Godot with spaces.exe"
            engine.touch()
            with patch.dict("os.environ", {"GODOT_BIN": str(engine)}), patch.object(runner.shutil, "which", return_value=None):
                self.assertEqual(runner.resolve_engine(), engine.resolve())
                self.assertEqual(runner.resolve_engine(str(engine)), engine.resolve())
                with self.assertRaisesRegex(ValueError, "not found"):
                    runner.resolve_engine(str(engine) + ".missing")

    def test_engine_path_lookup_and_missing_engine(self):
        with patch.dict("os.environ", {"GODOT_BIN": ""}), patch.object(runner.shutil, "which", side_effect=[None, "/bin/godot"]):
            self.assertEqual(runner.resolve_engine(), Path("/bin/godot").resolve())
        with patch.dict("os.environ", {"GODOT_BIN": ""}), patch.object(runner.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "Set GODOT_BIN"):
                runner.resolve_engine()

    def test_pinned_version_rejects_preview_wrong_version_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "engine_version.txt").write_text("4.7.2\n", encoding="utf-8")
            for version, code, valid in (
                ("4.7.2.stable.official.hash\n", 0, True),
                ("4.7.2.rc1.official.hash", 0, False),
                ("4.7.20.stable.official.hash", 0, False),
                ("4.6.stable.official.hash", 0, False),
                ("", 1, False),
            ):
                with self.subTest(version=version), patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], code, version, "")):
                    if valid:
                        self.assertEqual(runner.validate_engine(Path("engine"), project), version.strip())
                    else:
                        with self.assertRaisesRegex(ValueError, "Expected Godot"):
                            runner.validate_engine(Path("engine"), project)

    def test_command_keeps_space_paths_separate(self):
        self.assertEqual(runner.engine_command(Path("some engine"), Path("some project"), "--headless"), ["some engine", "--path", "some project", "--headless"])

    def test_checked_execution_fails_on_logged_errors_or_missing_marker(self):
        for code, stdout, stderr, markers, expected in (
            (0, "READY", "", ("READY",), 0),
            (0, "", "", (), 0),
            (3, "", "", (), 3),
            (0, "SCRIPT ERROR: type failure", "", (), 1),
            (0, "", "ERROR: failed import", (), 1),
            (0, "", "", ("READY",), 1),
        ):
            with self.subTest(code=code, stdout=stdout, stderr=stderr), patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], code, stdout, stderr)):
                self.assertEqual(runner.run_checked(["engine"], 5, markers), expected)

    def test_checks_every_script_but_not_generated_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "a.gd").touch()
            (project / "b.gd").touch()
            (project / ".godot").mkdir()
            (project / ".godot" / "generated.gd").touch()
            with patch.object(runner, "run_checked", return_value=0) as checked:
                self.assertEqual(runner.check_scripts(Path("engine"), project, 5), 0)
                self.assertEqual(checked.call_count, 3)
                self.assertIn("--import", checked.call_args_list[0].args[0])
            with patch.object(runner, "run_checked", side_effect=[2]) as checked:
                self.assertEqual(runner.check_scripts(Path("engine"), project, 5), 2)
                self.assertEqual(checked.call_count, 1)
            with patch.object(runner, "run_checked", side_effect=[0, 1]) as checked:
                self.assertEqual(runner.check_scripts(Path("engine"), project, 5), 1)
                self.assertEqual(checked.call_count, 2)

    def test_negative_fixtures_require_parse_error_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runner, "USER_LOG_DIR", Path(directory)), patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "SCRIPT ERROR: Parse Error")) as run:
                self.assertEqual(runner.check_error_detection(Path("engine"), runner.GODOT_PROJECT, 5), 0)
                self.assertEqual(run.call_count, 2)
            for code, error in ((0, "Parse Error"), (1, "crash")):
                with self.subTest(code=code), patch.object(runner, "USER_LOG_DIR", Path(directory)), patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], code, "", error)):
                    self.assertEqual(runner.check_error_detection(Path("engine"), runner.GODOT_PROJECT, 5), 1)

    def test_smoke_checks_both_lifecycle_markers(self):
        for headless in (False, True):
            with self.subTest(headless=headless), patch.object(runner, "run_checked", return_value=0) as checked:
                self.assertEqual(runner.run_smoke(Path("engine"), Path("project"), 5, headless), 0)
                command, _, markers = checked.call_args.args
                self.assertIn("--headless" if headless else "--windowed", command)
                self.assertEqual(command[command.index("--audio-driver") + 1], "Dummy")
                self.assertEqual(command[-2:], ["--", "--smoke-exit"])
                self.assertEqual(len(markers), 2)

    def test_execute_run_preserves_interactive_exit_status(self):
        for headless in (False, True):
            with self.subTest(headless=headless), patch.object(runner.subprocess, "call", return_value=7) as call:
                self.assertEqual(runner.execute("run", Path("engine"), Path("project"), 5, headless), 7)
                self.assertEqual("--headless" in call.call_args.args[0], headless)

    def test_execute_dispatch_and_stops_on_failures(self):
        for mode, check_status in (("check", 0), ("test", 1), ("smoke", 1)):
            with self.subTest(mode=mode), patch.object(runner, "check_scripts", return_value=check_status), patch.object(runner, "run_checked") as checked:
                self.assertEqual(runner.execute(mode, Path("engine"), Path("project"), 5, True), check_status)
                checked.assert_not_called()
        with patch.object(runner, "check_scripts", return_value=0), patch.object(runner, "run_smoke", return_value=8) as smoke:
            self.assertEqual(runner.execute("smoke", Path("engine"), Path("project"), 5, False), 8)
            smoke.assert_called_once()
        for test_status, negative_status in ((1, 0), (0, 1), (0, 0)):
            with self.subTest(test_status=test_status, negative_status=negative_status), patch.object(runner, "check_scripts", return_value=0), patch.object(runner, "run_checked", return_value=test_status), patch.object(runner, "check_error_detection", return_value=negative_status) as negative, patch.object(runner, "run_smoke", return_value=0) as smoke:
                self.assertEqual(runner.execute("test", Path("engine"), Path("project"), 5, False), test_status or negative_status)
                self.assertEqual(negative.called, not test_status)
                self.assertEqual(smoke.called, not (test_status or negative_status))

    def test_timeout_bounds(self):
        self.assertEqual(runner.positive_timeout("0.5"), 0.5)
        for value in ("0", "-1", "301", "inf", "nan"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                runner.positive_timeout(value)

    def test_cli_success_and_operational_failures(self):
        with patch.object(runner, "resolve_engine", return_value=Path("engine")), patch.object(runner, "validate_engine", return_value="version"), patch.object(runner, "execute", return_value=0) as execute:
            self.assertEqual(runner.main(["test", "--timeout", "5"]), 0)
            execute.assert_called_once_with("test", Path("engine"), runner.GODOT_PROJECT, 5, False)
        for error in (ValueError("missing"), OSError("denied"), subprocess.TimeoutExpired("engine", 5)):
            with self.subTest(error=error), patch.object(runner, "resolve_engine", side_effect=error):
                self.assertEqual(runner.main([]), 2)


if __name__ == "__main__":
    unittest.main()
