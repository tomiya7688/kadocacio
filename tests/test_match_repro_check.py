"""Rendering should not change a seeded match's simulation state."""

import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("KADOKA_DISABLE_GPU", "1")

from scripts.team.team_data import discover_team_choices
from scripts.tools.match_repro_check import compare_matches, main


class MatchReproCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home, cls.away = discover_team_choices()[:2]

    def test_real_pygame_draw_matches_headless_fixed_steps(self):
        report = compare_matches(self.home, self.away, seed=917, max_steps=40, render_every=10)
        self.assertTrue(report["same_state"], report)
        self.assertEqual(report["different_fields"], [])
        self.assertEqual((report["headless_steps"], report["rendered_steps"]), (40, 40))
        self.assertGreaterEqual(report["rendered_frames"], 5)
        self.assertFalse(report["fulltime"])

    def test_invalid_step_limits_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            compare_matches(self.home, self.away, seed=1, max_steps=0, render_every=10)

    def test_rendered_partial_frame_matches_headless(self):
        report = compare_matches(self.home, self.away, seed=918, max_steps=41, render_every=12)
        self.assertTrue(report["same_state"], report)
        self.assertEqual(report["rendered_frames"], 5)

    def test_step_mismatch_is_reported(self):
        state = {"state": "PLAYING", "game_time": 1.0}
        with patch("scripts.tools.match_repro_check.run_headless", return_value=(state, 2)):
            with patch("scripts.tools.match_repro_check.run_rendered", return_value=(state, 3, 1)):
                report = compare_matches(self.home, self.away, seed=1, max_steps=3, render_every=1)
        self.assertFalse(report["same_state"])
        self.assertEqual(report["different_fields"], ["steps"])

    def test_cli_accepts_explicit_teams_and_partial_result(self):
        report = {"same_state": True, "fulltime": False}
        with patch("scripts.tools.match_repro_check.discover_team_choices", return_value=[self.home, self.away]):
            with patch("scripts.tools.match_repro_check.compare_matches", return_value=report) as compare:
                with redirect_stdout(StringIO()):
                    result = main([
                        "--home", str(self.home["id"]), "--away", self.away["name"],
                        "--allow-partial", "--max-steps", "3",
                    ])
        self.assertEqual(result, 0)
        self.assertEqual(compare.call_args.kwargs["max_steps"], 3)

    def test_cli_rejects_incomplete_and_mismatching_results(self):
        with patch("scripts.tools.match_repro_check.discover_team_choices", return_value=[self.home, self.away]):
            with patch("scripts.tools.match_repro_check.compare_matches") as compare:
                with redirect_stdout(StringIO()):
                    compare.return_value = {"same_state": True, "fulltime": False}
                    self.assertEqual(main([]), 1)
                    compare.return_value = {"same_state": False, "fulltime": True}
                    self.assertEqual(main(["--allow-partial"]), 1)

    def test_cli_rejects_unknown_or_insufficient_teams(self):
        with patch("scripts.tools.match_repro_check.discover_team_choices", return_value=[self.home]):
            with self.assertRaises(SystemExit):
                main([])
        with patch("scripts.tools.match_repro_check.discover_team_choices", return_value=[self.home, self.away]):
            with self.assertRaises(SystemExit):
                main(["--home", "missing-team"])


if __name__ == "__main__":
    unittest.main()
