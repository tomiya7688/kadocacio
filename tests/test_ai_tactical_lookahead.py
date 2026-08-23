import unittest

import pygame

from scripts.match.match_engine import Match
from scripts.core.settings import FIELD
from scripts.team.team_data import discover_team_choices


class TacticalLookaheadTests(unittest.TestCase):
    def setUp(self) -> None:
        choices = discover_team_choices()
        self.match = Match(choices[0], choices[1], "NEUTRAL")
        self.match.state = "PLAYING"
        self.home = [player for player in self.match.home.players if not player.is_keeper]
        self.away = [player for player in self.match.away.players if not player.is_keeper]

    def test_receiver_continuation_detects_a_boxed_in_second_action(self) -> None:
        owner, receiver = self.home[:2]
        owner.pos.update(FIELD.centerx - 120, FIELD.centery)
        receiver.pos.update(FIELD.centerx + 40, FIELD.centery)
        owner.intelligence = 1.0
        destination = pygame.Vector2(receiver.pos)
        for index, opponent in enumerate(self.match.away.players):
            opponent.pos.update(FIELD.left + 25, FIELD.top + 25 + index * 9)
        open_value = self.match.receiver_continuation_value(owner, receiver, destination)

        next_points = (
            (96, 0), (75, -72), (75, 72), (27, -97), (27, 97),
        )
        for opponent, offset in zip(self.match.away.players, next_points):
            opponent.pos.update(destination.x + offset[0], destination.y + offset[1])
        boxed_value = self.match.receiver_continuation_value(owner, receiver, destination)

        self.assertGreater(open_value, boxed_value + 0.30)

    def test_interceptor_prioritizes_an_accessible_dangerous_lane(self) -> None:
        defender = self.home[0]
        owner, dangerous, harmless = self.away[:3]
        owner.pos.update(FIELD.centerx + 120, FIELD.centery)
        dangerous.pos.update(FIELD.centerx - 170, FIELD.centery + 55)
        harmless.pos.update(FIELD.centerx + 220, FIELD.centery - 40)
        defender.pos.update(FIELD.centerx - 25, FIELD.centery + 20)
        defender.intelligence = 1.0
        defender.interception = 1.0
        defender.pass_interception = 1.0
        for index, receiver in enumerate(self.away[3:]):
            receiver.pos.update(FIELD.right - 35, FIELD.top + 30 + index * 14)
        self.match.rng.seed(12)

        target = self.match.defensive_intercept_target(defender, owner)

        dangerous_lane_distance = self.match.distance_to_pass_lane(target, owner.pos, dangerous.pos)
        harmless_lane_distance = self.match.distance_to_pass_lane(target, owner.pos, harmless.pos)
        self.assertLess(dangerous_lane_distance, harmless_lane_distance)

    def test_intelligence_recognizes_an_open_side_shot_lane(self) -> None:
        shooter = self.home[0]
        shooter.pos.update(FIELD.right - 260, FIELD.centery)
        for index, opponent in enumerate(self.match.away.players):
            opponent.pos.update(FIELD.left + 30, FIELD.top + 30 + index * 10)
        blocker = self.away[0]
        blocker.pos.update(FIELD.right - 125, FIELD.centery)
        shooter.shooting_technique = 0.35

        shooter.intelligence = 0.05
        low_read = self.match.shot_lane_quality(shooter, self.match.away.players)
        shooter.intelligence = 1.0
        high_read = self.match.shot_lane_quality(shooter, self.match.away.players)

        self.assertGreater(high_read, low_read + 0.06)


if __name__ == "__main__":
    unittest.main()
