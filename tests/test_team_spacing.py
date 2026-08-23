import unittest

import pygame

from scripts.match.match_engine import Match
from scripts.match.player_commands import PlayerCommand
from scripts.core.settings import FIELD
from scripts.team.team_data import discover_team_choices


class TeamSpacingTests(unittest.TestCase):
    def setUp(self):
        choices = discover_team_choices()
        self.match = Match(choices[0], choices[1], "HOME")
        self.match.state = "PLAYING"
        self.owner = next(player for player in self.match.home.players if not player.is_keeper)
        self.owner.pos.update(FIELD.center)
        self.match.ball.owner = self.owner
        self.match.ball.pos.update(self.owner.pos)

    def test_stationary_possession_builds_stagnation_and_movement_releases_it(self):
        self.match.update_possession_stagnation(0.05)
        for _ in range(60):
            self.match.update_possession_stagnation(0.05)
        held_value = self.match.possession_stagnation
        self.assertGreater(held_value, 2.8)

        self.owner.pos.x += 120
        self.match.update_possession_stagnation(0.05)

        self.assertLess(self.match.possession_stagnation, held_value)
        self.assertEqual(self.match.possession_anchor, self.owner.pos)

    def test_support_priority_is_unique_when_teammates_crowd_the_owner(self):
        teammates = [
            player for player in self.match.home.players
            if player is not self.owner and not player.is_keeper
        ]
        for index, player in enumerate(teammates):
            player.pos.update(self.owner.pos.x - 30 + index * 3, self.owner.pos.y + (index % 3 - 1) * 12)

        contexts = [self.match.attacking_support_context(player, self.owner) for player in teammates]
        ranks = [rank for rank, _ in contexts]

        self.assertEqual(sorted(ranks), list(range(len(teammates))))
        self.assertTrue(all(congestion > 0.5 for _, congestion in contexts))

    def test_stale_possession_spreads_non_supporters_across_the_pitch(self):
        teammates = [
            player for player in self.match.home.players
            if player is not self.owner and not player.is_keeper
        ]
        for player in teammates:
            player.pos.update(self.owner.pos)
        self.match.possession_stagnation = 6.0

        spread_targets = []
        for player in teammates:
            rank, congestion = self.match.attacking_support_context(player, self.owner)
            if rank < 2:
                continue
            spread_targets.append(
                self.match.spread_attacking_target(
                    player, self.owner, pygame.Vector2(self.owner.pos), rank, congestion,
                )
            )

        self.assertGreater(max(target.y for target in spread_targets) - min(target.y for target in spread_targets), 220)
        self.assertGreater(max(target.x for target in spread_targets) - min(target.x for target in spread_targets), 80)
        self.assertTrue(all(target.distance_to(self.owner.pos) > 45 for target in spread_targets))

    def test_support_marginal_value_falls_for_occupied_and_claimed_locations(self):
        teammates = [
            player for player in self.match.home.players
            if player is not self.owner and not player.is_keeper
        ]
        player, occupant, committed = teammates[:3]
        target = self.owner.pos + pygame.Vector2(-self.owner.team.direction * 62, 58)
        for index, teammate in enumerate(teammates):
            far = pygame.Vector2(FIELD.left + 80 + index * 90, FIELD.top + 40)
            teammate.pos.update(far)
            teammate.target.update(far)

        empty_value, empty_occupancy = self.match.support_location_value(player, self.owner, target)

        occupant.pos.update(target)
        occupied_value, occupied_occupancy = self.match.support_location_value(player, self.owner, target)

        occupant.pos.update(FIELD.left + 80, FIELD.top + 40)
        committed.pos.update(FIELD.right - 80, FIELD.bottom - 40)
        committed.target.update(target)
        committed.action_command = PlayerCommand.SUPPORT
        claimed_value, claimed_occupancy = self.match.support_location_value(player, self.owner, target)

        self.assertLess(empty_occupancy, 0.1)
        self.assertGreater(occupied_occupancy, empty_occupancy)
        self.assertGreater(claimed_occupancy, empty_occupancy)
        self.assertLess(occupied_value, empty_value - 0.25)
        self.assertLess(claimed_value, empty_value - 0.20)

    def test_stale_owner_reconsiders_before_normal_decision_timer(self):
        self.match.decision_timer = 1.0
        self.match.possession_stagnation = 6.0
        for opponent in self.match.away.players:
            opponent.pos.update(FIELD.left + 40, FIELD.top + 30)

        self.match.update_owner_decision(0.05)

        self.assertLessEqual(self.match.decision_timer, 0.20)

    def test_pass_selection_prefers_equally_advanced_uncrowded_receiver(self):
        players = [player for player in self.match.home.players if not player.is_keeper]
        owner, crowded, open_receiver = players[:3]
        owner.pos.update(FIELD.center)
        crowded.pos.update(owner.pos.x + 140, owner.pos.y - 100)
        open_receiver.pos.update(owner.pos.x + 140, owner.pos.y + 100)
        for index, teammate in enumerate(players[3:]):
            teammate.pos.update(crowded.pos.x + (index % 3) * 8, crowded.pos.y + (index // 3) * 8)
        for index, opponent in enumerate(self.match.away.players):
            opponent.pos.update(FIELD.left + 30, FIELD.top + 30 + index * 12)
        self.match.rng.seed(7)

        chosen = self.match.choose_pass_target(owner)

        self.assertIs(chosen, open_receiver)

    def test_mark_selection_discounts_an_opponent_already_claimed_by_teammate(self):
        defenders = [player for player in self.match.home.players if not player.is_keeper]
        opponents = [player for player in self.match.away.players if not player.is_keeper]
        defender, teammate = defenders[:2]
        claimed, free = opponents[:2]
        defender.pos.update(FIELD.center)
        claimed.pos.update(FIELD.centerx + 100, FIELD.centery - 50)
        free.pos.update(FIELD.centerx + 100, FIELD.centery + 50)
        defender.alertness[claimed] = 0.8
        defender.alertness[free] = 0.8
        teammate.action_command = PlayerCommand.MARK
        teammate.command_target.update(claimed.pos)

        selected = self.match.most_alert_opponent(defender, claimed)

        self.assertIs(selected, free)


if __name__ == "__main__":
    unittest.main()
