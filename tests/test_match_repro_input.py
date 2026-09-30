"""Saved reproduction inputs must survive later changes to team source files."""

import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("KADOKA_DISABLE_GPU", "1")

from scripts.core.settings import AWAY_BLUE
from scripts.team.team_data import discover_team_choices
from scripts.tools.match_repro_check import main, run_headless
from scripts.tools.match_repro_input import create_input_record, restore_input_record


class MatchReproInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home, cls.away = discover_team_choices()[:2]

    def record(self):
        return create_input_record(
            self.home, self.away, seed=29, max_steps=45,
            venue_mode="AWAY", ai_rethink_multiplier=0.75,
        )

    def test_roundtrip_preserves_exact_team_values_and_match_state(self):
        home, away = deepcopy(self.home), deepcopy(self.away)
        home["manager_intelligence"] = 0.123456789123
        home["starters"][0]["raw"]["ShotPower"] = 3210.123456789
        home["primary"] = away["primary"] = AWAY_BLUE
        home["secondary"] = (80, 95, 110)
        settings = {"seed": 3, "max_steps": 80, "venue_mode": "NEUTRAL", "ai_rethink_multiplier": 2.5}
        original = run_headless(home, away, **settings)
        record = create_input_record(home, away, **settings)
        saved = json.dumps(record, ensure_ascii=False)
        home["starters"][0]["raw"]["ShotPower"] = 0
        restored_home, restored_away, restored_settings = restore_input_record(json.loads(saved))
        self.assertEqual(restored_home["manager_intelligence"], 0.123456789123)
        self.assertEqual(restored_home["primary"], AWAY_BLUE)
        self.assertEqual(run_headless(restored_home, restored_away, **restored_settings), original)
        restored_home["starters"][0]["raw"]["ShotPower"] = 1
        self.assertEqual(json.dumps(record, ensure_ascii=False), saved)

    def test_cli_saves_and_reloads_without_discovering_teams(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "試合条件.json"
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main([
                    "--save-input", str(path), "--max-steps", "25", "--seed", "0",
                    "--venue", "AWAY", "--ai-rethink-multiplier", "0.75", "--allow-partial",
                ]), 0)
            first_report = json.loads(output.getvalue())
            output = StringIO()
            with patch("scripts.tools.match_repro_check.discover_team_choices", side_effect=AssertionError("discovery")):
                with patch("scripts.app.game_app.discover_team_choices", side_effect=AssertionError("discovery")):
                    with redirect_stdout(output):
                        self.assertEqual(main(["--load-input", str(path), "--allow-partial"]), 0)
            self.assertEqual(json.loads(output.getvalue()), first_report)
            self.assertEqual(first_report["seed"], 0)
            previous = path.read_bytes()
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(["--load-input", str(path), "--save-input", str(path)])
            self.assertEqual(path.read_bytes(), previous)

    def test_cli_rejects_overrides_missing_files_and_malformed_json(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            for args in (["--load-input", str(path), "--seed", "1"], ["--load-input", str(path)]):
                with self.subTest(args=args), redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                    main(args)
            path.write_text("{", encoding="utf-8")
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(["--load-input", str(path)])

    def test_rejects_incompatible_envelope(self):
        for record in (None, {}, {**self.record(), "version": 2}, {**self.record(), "version": True},
                       {**self.record(), "commands": [{"step": 0, "command": "unknown"}]},
                       {**self.record(), "teams": []}, {**self.record(), "settings": []}):
            with self.subTest(record=record), self.assertRaises(ValueError):
                restore_input_record(record)

    def test_rejects_invalid_settings(self):
        invalid = (
            ("seed", True), ("seed", "1"), ("max_steps", 0), ("max_steps", 1.5),
            ("fixed_physics_dt", 0.1), ("venue_mode", "unknown"),
            ("ai_rethink_multiplier", None), ("ai_rethink_multiplier", True),
            ("ai_rethink_multiplier", float("nan")), ("ai_rethink_multiplier", 0.4),
            ("ai_rethink_multiplier", 3.1),
        )
        for key, value in invalid:
            record = self.record()
            record["settings"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                restore_input_record(record)

    def test_rejects_malformed_team_snapshots(self):
        for side in ("home", "away"):
            record = self.record()
            record["teams"][side] = None
            with self.subTest(side=side), self.assertRaises(ValueError):
                restore_input_record(record)
        for key, value in (("id", ""), ("name", 1), ("short", None), ("starters", []),
                           ("primary", [1, 2]), ("secondary", "blue"), ("primary", [0, -1, 256])):
            record = self.record()
            record["teams"]["home"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                restore_input_record(record)


if __name__ == "__main__":
    unittest.main()
