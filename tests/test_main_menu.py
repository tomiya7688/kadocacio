import unittest
from types import SimpleNamespace

import pygame

from scripts.app.game_app import Game


class MainMenuTests(unittest.TestCase):
    def _game(self, action: str) -> Game:
        game = Game.__new__(Game)
        game.match = SimpleNamespace(state="MAIN_MENU")
        game.main_menu_buttons = [(pygame.Rect(10, 10, 100, 40), action)]
        game.settings_open = False
        game.other_matches_open = False
        game.player_list_open = False
        game.league_screen_open = False
        game.settings_button = pygame.Rect(0, 0, 0, 0)
        game.open_team_editor = lambda: setattr(game, "route", "team_editor")
        game.open_league_editor = lambda: setattr(game, "route", "league_editor")
        game.open_league_screen = lambda: setattr(game, "route", "league_start")
        return game

    def test_four_main_menu_routes_are_distinct(self) -> None:
        for action in ("team_editor", "league_editor", "league_start"):
            with self.subTest(action=action):
                game = self._game(action)
                game.handle_click((20, 20))
                self.assertEqual(game.route, action)

        match_game = self._game("match_test")
        match_game.handle_click((20, 20))
        self.assertEqual(match_game.match.state, "TEAM_SELECT")

    def test_topmost_league_button_receives_click_when_controls_overlap(self) -> None:
        game = self._game("match_test")
        game.league_screen_open = True
        shared = pygame.Rect(10, 10, 100, 40)
        game.league_buttons = [(shared, "covered"), (shared, "back")]
        game.handle_league_action = lambda action: setattr(game, "clicked_action", action)

        game.handle_click((20, 20))

        self.assertEqual(game.clicked_action, "back")


if __name__ == "__main__":
    unittest.main()
