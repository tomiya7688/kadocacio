import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("KADOKA_DISABLE_GPU", "1")

import pygame

from scripts.app.game_app import Game
from scripts.core.simulation_runtime import advance_match_fixed
from scripts.team.team_editor_data import create_team_template


class RenderingSmokeTests(unittest.TestCase):
    def test_main_menu_editor_and_modern_match_models_draw(self) -> None:
        game = Game()
        try:
            self.assertEqual(game.match.state, "MAIN_MENU")
            game.draw_title()
            self.assertEqual(len(game.main_menu_buttons), 4)

            game.open_team_editor()
            game.team_editor.draw()
            editor_actions = {action for _rect, action, _data in game.team_editor.buttons}
            self.assertIn("target_mode", editor_actions)
            self.assertIn("generation_profile", editor_actions)
            self.assertIn("create_target", editor_actions)
            game.team_editor.payload = create_team_template("initial")
            game.team_editor.mode = "EDIT"
            game.team_editor.tab = "UNIFORM"
            game.team_editor.draw()
            uniform_actions = {action for _rect, action, _data in game.team_editor.buttons}
            self.assertIn("uniform_pixel", uniform_actions)
            self.assertIn("uniform_export", uniform_actions)
            self.assertIn("uniform_part", uniform_actions)
            game.close_team_editor()

            runtime_manager = game.league_manager
            game.open_league_editor()
            self.assertIsNot(game.league_manager, runtime_manager)
            self.assertFalse(game.league_manager.season_has_started())
            game.draw_league_screen()
            actions = {action for _rect, action in game.league_buttons}
            self.assertIn("template_duplicate", actions)
            back_rect = next(rect for rect, action in game.league_buttons if action == "back")
            game.handle_click(back_rect.center)
            self.assertFalse(game.league_screen_open)
            self.assertIs(game.league_manager, runtime_manager)

            game.league_screen_open = True
            game.league_save_select_open = False
            game.league_editor_only = False
            game.league_tab = "standings"
            game.draw_league_screen()
            actions = {action for _rect, action in game.league_buttons}
            self.assertIn("auto_open", actions)
            self.assertIn("history_mode|team", actions)
            game.handle_league_action("history_mode|team")
            game.draw_league_screen()
            actions = {action for _rect, action in game.league_buttons}
            self.assertIn("history_mode|league", actions)
            self.assertIn("history_team_cycle|1", actions)
            game.handle_league_action("auto_open")
            game.draw_league_screen()
            actions = {action for _rect, action in game.league_buttons}
            self.assertIn("auto_start", actions)
            self.assertIn("auto_watch|NONE", actions)
            game.handle_league_action("auto_cancel")
            game.close_league_screen()

            game.match.state = "TEAM_SELECT"
            game.draw_team_select()
            game.start_selected_match()
            for _ in range(3):
                advance_match_fixed(game.match)
            game.draw_pitch()
            for team in game.match.teams:
                game.draw_player(team.players[0])
        finally:
            if game.gpu_presenter is not None:
                game.gpu_presenter.destroy()
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
