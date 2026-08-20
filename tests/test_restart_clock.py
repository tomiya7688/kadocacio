import unittest

import pygame

from match_engine import Match
from league_manager import LeagueSimulationSession
from settings import FIELD, GAME_CLOCK_RATE
from team_data import discover_team_choices


class RestartClockTests(unittest.TestCase):
    def setUp(self):
        choices = discover_team_choices()
        self.match = Match(choices[0], choices[1], "NEUTRAL")
        self.match.start_new()
        self.match.banner_timer = 0.0
        self.match.game_time = 100.0

    def test_free_kick_preparation_does_not_advance_match_clock(self):
        self.match.start_set_piece("FREE_KICK", self.match.home, pygame.Vector2(FIELD.center))
        self.match.update_step(0.05)
        self.assertEqual(self.match.game_time, 100.0)
        self.assertAlmostEqual(self.match.simulation_elapsed, 0.05)
        self.assertAlmostEqual(self.match.restart_elapsed, 0.05)

    def test_throw_in_preparation_does_not_advance_match_clock(self):
        self.match.ball.last_touch = self.match.away.players[0]
        self.match.ball.pos.update(FIELD.centerx, FIELD.top - 2)
        self.match.start_throw_in()
        self.match.update_step(0.05)
        self.assertEqual(self.match.game_time, 100.0)
        self.assertAlmostEqual(self.match.simulation_elapsed, 0.05)
        self.assertAlmostEqual(self.match.restart_elapsed, 0.05)

    def test_live_play_still_advances_match_clock(self):
        self.match.throw_in_team = None
        self.match.thrower = None
        self.match.restart_type = ""
        self.match.restart_team = None
        self.match.restart_taker = None
        self.match.update_step(0.05)
        self.assertAlmostEqual(self.match.game_time, 100.0 + 0.05 * GAME_CLOCK_RATE)
        self.assertAlmostEqual(self.match.simulation_elapsed, 0.05)

    def test_live_league_pacing_uses_physics_time_then_releases_to_full_speed(self):
        class Clock:
            value = 0.0

        session = LeagueSimulationSession.__new__(LeagueSimulationSession)
        session.sync_clock = Clock()
        session.set_target_simulation_time(12.75)
        self.assertEqual(session.sync_clock.value, 12.75)
        session.finish_remaining_as_fast_as_possible()
        self.assertEqual(session.sync_clock.value, -1.0)
        # A later UI update must not accidentally restore paced mode.
        session.set_target_simulation_time(13.0)
        self.assertEqual(session.sync_clock.value, -1.0)


if __name__ == "__main__":
    unittest.main()
