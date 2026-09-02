import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.tools.developer_league_evaluator import _new_config, _resume_config, build_parser
from scripts.tools.league_evaluation_runner import LeagueEvaluationRunner
from scripts.tools.league_evaluation_report import build_summary, read_jsonl


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _instant_match(job: dict) -> dict:
    fixture = job["fixture"]
    return {
        "fixture_id": fixture["id"],
        "home_score": 2,
        "away_score": 1,
        "home_shots": 5,
        "away_shots": 3,
        "home_possession": 60.0,
        "away_possession": 40.0,
        "goal_scorers": [],
        "engine_steps": 123,
        "simulation_mode": job["simulation_mode"],
        "fulltime": True,
        "wall_seconds": 0.01,
        "home_remaining_stamina": 0.6,
        "away_remaining_stamina": 0.5,
        "home_telemetry": {"command_counts": {"パス": 3}, "crowded_player_ratio": 0.2},
        "away_telemetry": {"command_counts": {"プレス": 2}, "crowded_player_ratio": 0.3},
    }


class DeveloperLeagueEvaluatorTests(unittest.TestCase):
    def test_windows_launcher_is_utf8_safe_before_python_starts(self) -> None:
        launcher = (PROJECT_ROOT / "run_developer_evaluation.bat").read_bytes().decode("utf-8")

        self.assertTrue(all(ord(character) < 128 for character in launcher))
        self.assertIn("chcp.com 65001", launcher)
        self.assertIn('set "PYTHONIOENCODING=utf-8"', launcher)
        self.assertIn("scripts.tools.developer_league_evaluator %*", launcher)

    def test_default_cli_is_eight_hour_unattended_precise_run(self) -> None:
        args = build_parser().parse_args([])
        with patch("scripts.tools.developer_league_evaluator.load_performance_settings") as settings:
            settings.return_value.cpu_limit_percent = 50
            settings.return_value.league_simulation_mode = "PRECISE"
            config = _new_config(args)

        self.assertEqual(config["hours"], 8.0)
        self.assertEqual(config["seasons"], 0)
        self.assertEqual(config["leagues"], ["all"])
        self.assertEqual(config["quality"], "PRECISE")
        self.assertEqual(config["cpu_limit"], 50)

    def test_one_matchday_writes_checkpoint_and_all_report_types(self) -> None:
        config = {
            "template_id": "default",
            "leagues": ["all"],
            "hours": 0.0,
            "seasons": 0,
            "quality": "PRECISE",
            "cpu_limit": 25,
            "processes": "1",
            "max_processes": 1,
            "sample_every_steps": 18,
            "max_matchdays": 1,
            "stop_on_error": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evaluation"
            with patch("scripts.tools.league_evaluation_runner._run_headless_league_match", _instant_match):
                summary = LeagueEvaluationRunner(config, output).run()

            checkpoint = json.loads((output / "checkpoint.json").read_text(encoding="utf-8"))
            matches = read_jsonl(output / "matches.jsonl")
            events = read_jsonl(output / "events.jsonl")

            self.assertEqual(summary["status"], "matchday_limit")
            self.assertGreater(len(matches), 0)
            self.assertEqual(checkpoint["matchdays_completed"], 1)
            self.assertTrue(any(row["event"] == "matchday_completed" for row in events))
            self.assertTrue((output / "team_summary.csv").exists())
            self.assertTrue((output / "commands.csv").exists())
            self.assertTrue((output / "performance.csv").exists())

            resume_args = build_parser().parse_args(["--hours", "2", "--cpu-limit", "25"])
            resumed_config = _resume_config(checkpoint["config"], resume_args)
            resumed = LeagueEvaluationRunner(resumed_config, output, checkpoint=checkpoint)
            self.assertEqual(resumed.matches_completed, len(matches))
            self.assertEqual(resumed.previous_elapsed_seconds, checkpoint["elapsed_seconds"])
            self.assertEqual(resumed_config["hours"], 2.0)

    def test_summary_reports_runtime_failures_and_team_results(self) -> None:
        rows = [{
            "fixture_id": "one",
            "home_id": "a",
            "away_id": "b",
            "home_name": "A",
            "away_name": "B",
            "home_score": 1,
            "away_score": 0,
            "home_shots": 2,
            "away_shots": 1,
            "home_possession": 55.0,
            "away_possession": 45.0,
            "wall_seconds": 3.0,
            "engine_steps": 10,
            "fulltime": False,
            "evaluation_failed": True,
        }]

        summary = build_summary(rows, [], status="error", elapsed_seconds=3.0)

        self.assertEqual(summary["failed_matches"], 1)
        self.assertEqual(summary["teams"][0]["team_name"], "A")
        self.assertEqual(summary["teams"][0]["won"], 1)

    def test_keyboard_interrupt_stops_run_without_recording_failed_match(self) -> None:
        config = {
            "template_id": "default",
            "leagues": ["all"],
            "hours": 0.0,
            "seasons": 0,
            "quality": "PRECISE",
            "cpu_limit": 25,
            "processes": "1",
            "max_processes": 1,
            "sample_every_steps": 18,
            "max_matchdays": 1,
            "stop_on_error": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evaluation"
            with patch(
                "scripts.tools.league_evaluation_runner._run_headless_league_match",
                side_effect=KeyboardInterrupt,
            ):
                summary = LeagueEvaluationRunner(config, output).run()

            self.assertEqual(summary["status"], "interrupted")
            self.assertEqual(read_jsonl(output / "matches.jsonl"), [])
            self.assertEqual(read_jsonl(output / "errors.jsonl"), [])

    def test_incomplete_match_is_retried_once_then_refused(self) -> None:
        config = {
            "template_id": "default",
            "leagues": ["all"],
            "hours": 0.0,
            "seasons": 0,
            "quality": "PRECISE",
            "cpu_limit": 25,
            "processes": "1",
            "max_processes": 1,
            "sample_every_steps": 18,
            "max_matchdays": 1,
            "stop_on_error": False,
        }
        calls = []

        def never_finishes(job: dict) -> dict:
            calls.append(job)
            fixture = job["fixture"]
            return {
                "fixture_id": fixture["id"],
                "home_score": 0,
                "away_score": 0,
                "engine_steps": int(job.get("max_match_steps", 18000)),
                "fulltime": False,
                "finish_reason": "step_limit",
                "game_time": 300.0,
                "restart_type": "FREE_KICK",
                "restart_elapsed": 20.0,
            }

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evaluation"
            runner = LeagueEvaluationRunner(config, output)
            fixture = next(item for item in runner.manager.fixtures if not item.get("played"))
            with patch("scripts.tools.league_evaluation_runner._run_headless_league_match", never_finishes):
                results = runner._run_batch([fixture], None)

            self.assertEqual(len(calls), 2)
            self.assertGreater(calls[1]["max_match_steps"], calls[0].get("max_match_steps", 0))
            with self.assertRaisesRegex(RuntimeError, "順位表には反映しません"):
                runner._record_batch([fixture], results)
            self.assertFalse(fixture["played"])
            self.assertEqual(read_jsonl(output / "matches.jsonl"), [])
            self.assertEqual(read_jsonl(output / "errors.jsonl")[0]["event"], "match_incomplete_after_retry")


if __name__ == "__main__":
    unittest.main()
