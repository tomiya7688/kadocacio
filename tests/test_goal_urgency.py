import unittest

import pygame

from scripts.match.match_engine import Match
from scripts.match.player_commands import PlayerCommand
from scripts.core.settings import FIELD
from scripts.team.team_data import discover_team_choices


class GoalUrgencyTests(unittest.TestCase):
    def setUp(self):
        choices = discover_team_choices()
        self.match = Match(choices[0], choices[1], "HOME")
        self.match.state = "PLAYING"
        self.match.ball.owner = None
        self.match.ball.intended = None
        self.match.ball.flight_type = ""
        self.match.ball.vel.update(0, 0)

    def test_low_stamina_players_still_attack_and_defend_loose_goal_ball(self):
        ball_position = pygame.Vector2(FIELD.right - 115, FIELD.centery)
        self.match.ball.pos.update(ball_position)

        home_runners = [player for player in self.match.home.players if not player.is_keeper][:3]
        away_runners = [player for player in self.match.away.players if not player.is_keeper][:3]
        for index, player in enumerate(home_runners + away_runners):
            player.pos.update(ball_position.x - 170 - index % 3 * 18, FIELD.centery + (index % 3 - 1) * 34)
            player.stamina = player.stamina_max * 0.10

        self.match.update_player_movement(0.05)

        urgent_commands = {PlayerCommand.RECOVER_LOOSE_BALL, PlayerCommand.BLOCK_SHOT}
        self.assertTrue(any(player.action_command in urgent_commands for player in home_runners))
        self.assertTrue(any(player.action_command in urgent_commands for player in away_runners))
        self.assertTrue(any(player.movement_command is PlayerCommand.DASH for player in home_runners))
        self.assertTrue(any(player.movement_command is PlayerCommand.DASH for player in away_runners))


if __name__ == "__main__":
    unittest.main()
