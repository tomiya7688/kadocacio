"""The live scoreboard reads a detached, immutable match status."""

import json
import unittest
from dataclasses import FrozenInstanceError, asdict
from types import SimpleNamespace

import pygame

from scripts.app.rendering import RendererMixin
from scripts.app.match_hud_view import MatchHudView
from scripts.core.settings import WIDTH, HEIGHT
from scripts.match.match_engine import Match
from scripts.match.match_status_snapshot import MatchStatusSnapshot
from scripts.team.team_data import discover_team_choices


class MatchStatusSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.choices = discover_team_choices()

    def test_snapshot_is_detached_and_serializable_during_play(self):
        match = Match(self.choices[0], self.choices[1], "NEUTRAL")
        match.home.score = 2
        match.game_time = 123.5
        match.show_banner("HALF TIME", 2.0)

        status = match.status_snapshot()
        self.assertIsInstance(status, MatchStatusSnapshot)
        self.assertEqual(status.home_score, 2)
        self.assertEqual(status.game_time, 123.5)
        self.assertEqual(json.loads(json.dumps(asdict(status)))["banner"], "HALF TIME")
        with self.assertRaises(FrozenInstanceError):
            status.home_score = 9

        match.home.score = 3
        match.game_time = 180.0
        match.banner = ""
        self.assertEqual((status.home_score, status.game_time, status.banner), (2, 123.5, "HALF TIME"))
        self.assertEqual(match.status_snapshot().home_score, 3)

    def test_scoreboard_only_requires_snapshot_not_mutable_team_objects(self):
        pygame.font.init()
        status = MatchStatusSnapshot("HOME", "AWAY", 2, 1, 123.5, "PLAYING", "", 0.0, 3)
        labels = []
        probe = SimpleNamespace(
            match=SimpleNamespace(status_snapshot=lambda: status),
            screen=pygame.Surface((WIDTH, HEIGHT)),
            match_hud_view=MatchHudView(),
            font=lambda size, bold=False: pygame.font.Font(None, size),
            text=lambda value, *_args, **_kwargs: labels.append(value),
        )

        RendererMixin.draw_scoreboard(probe)

        self.assertIn("HOME", labels)
        self.assertIn("AWAY", labels)
        self.assertIn("2 : 1", labels)
        self.assertIn("02:03", labels)
        self.assertIn("×3", labels)


if __name__ == "__main__":
    unittest.main()
