import unittest

import pygame

from scripts.team.team_editor import TeamEditor


class _FixedFont:
    def size(self, text: str) -> tuple[int, int]:
        return len(text) * 10, 18


class _FakeGame:
    def font(self, _size: int, *_args, **_kwargs) -> _FixedFont:
        return _FixedFont()


class TeamEditorMultilineTests(unittest.TestCase):
    def _editor(self, text: str) -> tuple[TeamEditor, dict]:
        editor = TeamEditor.__new__(TeamEditor)
        target = {"チーム紹介": text}
        editor.game = _FakeGame()
        editor.active_input = (target, "チーム紹介", "multiline")
        editor.input_replace_pending = False
        editor.ime_composition = ""
        editor.multiline_cursor = len(text)
        editor.multiline_preferred_x = None
        editor.multiline_view_start = 0
        editor.multiline_layout_width = 700
        editor.held_number_step = None
        editor.number_hold_elapsed = 0.0
        editor.number_hold_repeat = 0.0
        editor.held_text_delete = None
        editor.text_delete_hold_elapsed = 0.0
        editor.text_delete_hold_repeat = 0.0
        editor.tuner_session = None
        editor.dirty = False
        editor.confirm_back = False
        return editor, target

    def test_cursor_moves_and_text_is_inserted_at_that_position(self) -> None:
        editor, target = self._editor("abcd\nef")
        editor.multiline_cursor = 4

        editor._move_multiline_cursor(pygame.K_DOWN)
        self.assertEqual(editor.multiline_cursor, 7)
        editor._move_multiline_cursor(pygame.K_UP)
        self.assertEqual(editor.multiline_cursor, 4)
        editor._move_multiline_cursor(pygame.K_LEFT)
        editor.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="X"))

        self.assertEqual(target["チーム紹介"], "abcXd\nef")
        self.assertEqual(editor.multiline_cursor, 4)
        self.assertTrue(editor.dirty)

    def test_home_end_and_click_choose_a_real_cursor_position(self) -> None:
        editor, _ = self._editor("abc\nde")
        editor.multiline_cursor = 5

        editor._move_multiline_cursor(pygame.K_HOME)
        self.assertEqual(editor.multiline_cursor, 4)
        editor._move_multiline_cursor(pygame.K_END)
        self.assertEqual(editor.multiline_cursor, 6)
        editor._move_multiline_cursor(pygame.K_HOME, control=True)
        self.assertEqual(editor.multiline_cursor, 0)
        editor._move_multiline_cursor(pygame.K_END, control=True)
        self.assertEqual(editor.multiline_cursor, 6)

        rect = pygame.Rect(100, 100, 200, 100)
        editor._place_multiline_cursor(rect, editor.active_input[0], "チーム紹介", (134, 112))
        self.assertEqual(editor.multiline_cursor, 2)
        editor._place_multiline_cursor(rect, editor.active_input[0], "チーム紹介", (124, 136))
        self.assertEqual(editor.multiline_cursor, 5)

    def test_backspace_hold_repeats_until_key_up(self) -> None:
        editor, target = self._editor("abcdef")

        editor.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, mod=0))
        self.assertEqual(target["チーム紹介"], "abcde")
        editor.update(0.50)
        self.assertLess(len(target["チーム紹介"]), 5)

        editor.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_BACKSPACE, mod=0))
        after_release = target["チーム紹介"]
        editor.update(1.0)
        self.assertEqual(target["チーム紹介"], after_release)

    def test_delete_removes_in_front_of_the_cursor(self) -> None:
        editor, target = self._editor("前後")
        editor.multiline_cursor = 1

        editor.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DELETE, mod=0))
        editor.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_DELETE, mod=0))

        self.assertEqual(target["チーム紹介"], "前")
        self.assertEqual(editor.multiline_cursor, 1)


if __name__ == "__main__":
    unittest.main()
