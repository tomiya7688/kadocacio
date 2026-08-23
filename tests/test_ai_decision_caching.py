import unittest

import pygame

from scripts.match.match_engine import Match
from scripts.match.player_commands import PlayerCommand
from scripts.team.team_data import discover_team_choices


class AiDecisionCachingTests(unittest.TestCase):
    def setUp(self):
        choices = discover_team_choices()
        self.match = Match(choices[0], choices[1], "NEUTRAL")

    @staticmethod
    def _decision(target_x=100.0):
        return PlayerCommand.SUPPORT, pygame.Vector2(target_x, 200.0), PlayerCommand.WALK

    def test_high_intelligence_reconsiders_cached_tactics_sooner(self):
        low = self.match.home.players[0]
        high = self.match.home.players[1]
        owner = self.match.home.players[2]
        low.intelligence = 0.0
        high.intelligence = 1.0
        self.match.cached_off_ball_decision(low, ("attack", owner, 0), self._decision)
        self.match.cached_off_ball_decision(high, ("attack", owner, 0), self._decision)
        self.assertGreater(low.ai_rethink_timer, high.ai_rethink_timer)
        self.assertAlmostEqual(low.ai_rethink_timer, 0.28)
        self.assertAlmostEqual(high.ai_rethink_timer, 0.12)

    def test_same_owner_uses_cache_but_turnover_replans_immediately(self):
        player = self.match.home.players[0]
        first_owner = self.match.home.players[2]
        new_owner = self.match.away.players[2]
        calls = []

        def chooser():
            calls.append(True)
            return self._decision(300.0)

        self.match.cached_off_ball_decision(player, ("attack", first_owner, 0), chooser)
        self.match.cached_off_ball_decision(player, ("press", first_owner, True), chooser)
        self.assertEqual(len(calls), 1)
        self.match.cached_off_ball_decision(player, ("defend", new_owner, True), chooser)
        self.assertEqual(len(calls), 2)

    def test_headless_quality_mode_scales_rethink_interval_only(self):
        choices = discover_team_choices()
        light = Match(choices[0], choices[1], "NEUTRAL", ai_rethink_multiplier=2.4)
        player = light.home.players[0]
        owner = light.home.players[2]
        player.intelligence = 1.0
        light.cached_off_ball_decision(player, ("attack", owner, 0), self._decision)
        self.assertAlmostEqual(player.ai_rethink_timer, 0.12 * 2.4)

    def test_tactical_settings_reuse_stable_player_mix(self):
        player = self.match.home.players[0]
        first = player.team.tactical_settings(player)
        second = player.team.tactical_settings(player)
        self.assertIs(first, second)
        player.tactical_loyalty = min(1.0, player.tactical_loyalty + 0.02)
        changed = player.team.tactical_settings(player)
        self.assertIsNot(first, changed)


if __name__ == "__main__":
    unittest.main()
