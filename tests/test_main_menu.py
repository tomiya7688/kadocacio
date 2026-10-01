import unittest
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_legacy_title_routes_match_visible_cards_and_ignore_background(self) -> None:
        for action in ("team_editor", "league_editor", "league_start", "match_test"):
            with self.subTest(action=action):
                game = self._game(action)
                game.match.state = "TITLE"
                game.handle_click((200, 200))
                self.assertEqual(game.match.state, "TITLE")
                game.handle_click((20, 20))
                if action == "match_test":
                    self.assertEqual(game.match.state, "TEAM_SELECT")
                else:
                    self.assertEqual(game.route, action)

    def test_numeric_shortcuts_keep_existing_routes_on_both_menu_states(self) -> None:
        for state in ("MAIN_MENU", "TITLE"):
            for key, action in ((pygame.K_1, "team_editor"), (pygame.K_2, "league_editor"),
                                (pygame.K_3, "league_start"), (pygame.K_4, "match_test")):
                with self.subTest(state=state, action=action):
                    game = self._game(action)
                    game.match.state = state
                    game.handle_key(key)
                    if action == "match_test":
                        self.assertEqual(game.match.state, "TEAM_SELECT")
                    else:
                        self.assertEqual(game.route, action)

    def test_keyboard_focus_follows_visual_grid(self) -> None:
        game = self._game("league_start")
        game.main_menu_focus = 0
        for key, expected in ((pygame.K_RIGHT, 1), (pygame.K_DOWN, 3),
                              (pygame.K_LEFT, 2), (pygame.K_UP, 0)):
            game.handle_key(key)
            self.assertEqual(game.main_menu_focus, expected)
        with patch("pygame.key.get_mods", return_value=pygame.KMOD_SHIFT):
            game.handle_key(pygame.K_TAB)
        self.assertEqual(game.main_menu_focus, 3)
        with patch("pygame.key.get_mods", return_value=0):
            game.handle_key(pygame.K_TAB)
        self.assertEqual(game.main_menu_focus, 0)
        game.handle_key(pygame.K_RETURN)
        self.assertEqual(game.route, "league_start")

    def test_settings_modal_blocks_menu_keys_at_handler_boundary(self) -> None:
        game = self._game("team_editor")
        game.settings_open = True
        for key in (pygame.K_1, pygame.K_RETURN, pygame.K_RIGHT, pygame.K_TAB):
            game.handle_key(key)
        self.assertFalse(hasattr(game, "route"))
        self.assertFalse(hasattr(game, "main_menu_focus"))
        game.close_settings = lambda: setattr(game, "settings_open", False)
        game.handle_key(pygame.K_ESCAPE)
        self.assertFalse(game.settings_open)


if __name__ == "__main__":
    unittest.main()
