import unittest
from unittest.mock import Mock

import pygame

from game_app import Game


class _SteppingMatch:
    def __init__(self, state="PLAYING", finish_after=3):
        self.state = state
        self.steps = 0
        self.finish_after = finish_after

    def update_step(self, _dt):
        self.steps += 1
        if self.steps >= self.finish_after:
            self.state = "FULLTIME"


def bare_game(match):
    game = Game.__new__(Game)
    game.match = match
    game.league_screen_open = False
    game.league_save_select_open = False
    game.other_matches_open = False
    game.player_list_open = False
    game.active_league_fixture_id = ""
    game.league_match_finalized = False
    game.league_simulation_session = None
    game.league_live_last_status = []
    game.pause_menu_buttons = []
    game.fulltime_buttons = []
    game.skip_match_in_progress = False
    game.league_skip_auto_return = False
    game.running = True
    return game


class PauseMenuTests(unittest.TestCase):
    def test_escape_opens_pause_and_escape_again_resumes(self):
        game = bare_game(_SteppingMatch())

        game.handle_key(pygame.K_ESCAPE)
        self.assertEqual(game.match.state, "PAUSED")
        self.assertTrue(game.running)

        game.handle_key(pygame.K_ESCAPE)
        self.assertEqual(game.match.state, "PLAYING")

    def test_skip_uses_fixed_match_steps_until_fulltime(self):
        game = bare_game(_SteppingMatch(state="PAUSED", finish_after=4))
        game.finalize_league_match = Mock()

        game.start_match_skip()
        game.update_match_skip()

        self.assertEqual(game.match.state, "FULLTIME")
        self.assertEqual(game.match.steps, 4)
        self.assertFalse(game.skip_match_in_progress)
        game.finalize_league_match.assert_called_once_with()

    def test_league_skip_marks_automatic_result_return(self):
        game = bare_game(_SteppingMatch(state="PAUSED"))
        game.active_league_fixture_id = "A-001"

        game.start_match_skip()

        self.assertTrue(game.league_skip_auto_return)

    def test_aborting_league_watch_cancels_background_and_keeps_fixture_unrecorded(self):
        game = bare_game(_SteppingMatch(state="PAUSED"))
        game.active_league_fixture_id = "A-001"
        session = Mock()
        game.league_simulation_session = session

        game.abort_current_match()

        session.cancel.assert_called_once_with()
        self.assertIsNone(game.league_simulation_session)
        self.assertEqual(game.active_league_fixture_id, "")
        self.assertTrue(game.league_screen_open)
        self.assertEqual(game.league_tab, "schedule")


if __name__ == "__main__":
    unittest.main()
