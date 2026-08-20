import unittest

import pygame

from match_engine import Match
from player_commands import PlayerCommand
from team_data import discover_team_choices


class AiPlanningTests(unittest.TestCase):
    def setUp(self):
        choices = discover_team_choices()
        self.match = Match(choices[0], choices[1], "NEUTRAL")
        self.match.start_new()
        self.match.banner_timer = 0.0
        self.outfield = [player for player in self.match.home.players if not player.is_keeper]

    def test_pass_creates_a_short_follow_up_plan(self):
        passer, receiver = self.outfield[:2]
        self.match.plan_combination_run(passer, receiver, pygame.Vector2(receiver.pos), 0.7)

        self.assertIs(passer.combination_partner, receiver)
        self.assertGreater(passer.combination_timer, 0.7)
        self.assertGreaterEqual(passer.combination_quality, 0.0)
        self.assertLessEqual(passer.combination_quality, 1.0)

        self.match.change_owner(receiver)
        self.match.update_player_movement(0.05)
        self.assertEqual(passer.action_command, PlayerCommand.CREATE_PASS_LANE)

    def test_relevant_stats_change_combination_plan_quality(self):
        passer, receiver = self.outfield[:2]
        passer.passing_technique = 0.05
        passer.support = 0.05
        passer.intelligence = 0.05
        self.match.plan_combination_run(passer, receiver, pygame.Vector2(receiver.pos), 0.6)
        low_quality = passer.combination_quality

        passer.passing_technique = 1.0
        passer.support = 1.0
        passer.intelligence = 1.0
        self.match.plan_combination_run(passer, receiver, pygame.Vector2(receiver.pos), 0.6)
        high_quality = passer.combination_quality

        self.assertGreater(high_quality, low_quality + 0.60)

    def test_pass_route_reuses_clearance_work(self):
        passer, receiver = self.outfield[:2]
        route = self.match.evaluate_pass_route(passer, receiver)
        self.assertGreaterEqual(route.lane_clearance, 0.0)
        self.assertGreaterEqual(route.opponent_clearance, 0.0)


if __name__ == "__main__":
    unittest.main()
