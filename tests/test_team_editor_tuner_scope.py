import copy
import unittest

from scripts.team.team_editor import TeamEditor


class TeamEditorTunerScopeTests(unittest.TestCase):
    def _editor(self) -> TeamEditor:
        editor = TeamEditor.__new__(TeamEditor)
        editor.payload = {
            "選手一覧": [
                {"名前": "選手1", "シュート力": 321},
                {"名前": "選手2", "シュート力": 987},
            ]
        }
        editor.selected_player = 0
        editor.tuner_adjust_scope = "player"
        editor.message = ""
        editor.message_color = (0, 0, 0)
        editor.dirty = False
        editor.confirm_back = False
        editor.tuner_session = None
        editor.color_picker_open = True
        editor.tuner_options = {
            "categories": [], "default_target": 700,
            "default_time_limit_seconds": 15, "hidden_parameters_default": True,
        }
        return editor

    def test_switching_to_team_scope_does_not_adjust_player_values(self) -> None:
        editor = self._editor()
        before = copy.deepcopy(editor.payload)

        editor._perform("tuner_scope_team", None)

        self.assertEqual(editor.tuner_adjust_scope, "team")
        self.assertEqual(editor.payload, before)
        self.assertFalse(editor.dirty)
        self.assertIn("能力値は変更していません", editor.message)

    def test_switching_back_to_player_scope_does_not_adjust_values(self) -> None:
        editor = self._editor()
        editor.tuner_adjust_scope = "team"
        before = copy.deepcopy(editor.payload)

        editor._perform("tuner_scope_player", None)

        self.assertEqual(editor.tuner_adjust_scope, "player")
        self.assertEqual(editor.payload, before)
        self.assertFalse(editor.dirty)
        self.assertIn("選手1", editor.message)

    def test_end_mode_can_switch_to_convergence_without_starting_adjustment(self) -> None:
        editor = self._editor()
        before_players = copy.deepcopy(editor.payload["選手一覧"])

        editor._perform("tuner_end_mode", None)

        self.assertEqual(editor.payload["チームチューナー"]["終了条件"], "収束まで")
        self.assertEqual(editor.payload["選手一覧"], before_players)
        self.assertTrue(editor.dirty)
        self.assertIn("収束まで", editor.message)

    def test_gui_color_pick_updates_the_json_value_without_saving_implicitly(self) -> None:
        editor = self._editor()

        editor._perform("color_pick", "#3FA7D6")

        self.assertEqual(editor.payload["チーム情報"]["チームカラー"], "#3FA7D6")
        self.assertTrue(editor.dirty)
        self.assertFalse(editor.color_picker_open)


if __name__ == "__main__":
    unittest.main()
