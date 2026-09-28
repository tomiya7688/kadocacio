"""Rendering should not change a seeded match's simulation state."""

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("KADOKA_DISABLE_GPU", "1")

from scripts.team.team_data import discover_team_choices
from scripts.tools.match_repro_check import compare_matches


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


if __name__ == "__main__":
    unittest.main()
