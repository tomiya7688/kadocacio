"""Layout contracts without starting a match or reading/writing league saves."""
import pygame
import pytest

from scripts.app.game_app import Game
from scripts.app.main_menu_view import MainMenuView, MENU_ACTIONS
from scripts.core.settings import HEIGHT, WIDTH


def test_menu_hitboxes_are_contained_and_disjoint():
    buttons = MainMenuView.buttons()
    assert tuple(action for _, action in buttons) == MENU_ACTIONS
    screen = pygame.Rect(0, 0, WIDTH, HEIGHT)
    for index, (rect, _) in enumerate(buttons):
        assert screen.contains(rect)
        assert all(not rect.colliderect(other) for other, _ in buttons[index + 1:])


@pytest.mark.parametrize("focus", range(4))
def test_menu_draw_preserves_text_bounds_focus_and_hitboxes(focus):
    pygame.font.init()
    game = Game.__new__(Game)
    game.screen = pygame.Surface((WIDTH, HEIGHT))
    game.fonts = {}
    game.text_surface_cache = {}
    game.main_menu_focus = focus
    game.main_menu_view = MainMenuView()
    game.logical_mouse_pos = lambda: (-1, -1)
    drawn_text = []
    original_text = game.text

    def checked_text(*args, **kwargs):
        rect = original_text(*args, **kwargs)
        drawn_text.append((args[0], rect))
        assert game.screen.get_rect().contains(rect), args[0]
        return rect

    game.text = checked_text
    game.draw_title()
    assert game.main_menu_focus == focus
    assert game.main_menu_buttons == MainMenuView.buttons()
    for card, _ in game.main_menu_buttons:
        for label, rect in drawn_text:
            if card.colliderect(rect):
                assert card.contains(rect), label
        assert not card.colliderect(game.settings_button)
    first_frame = pygame.image.tostring(game.screen, "RGB")
    game.draw_title()
    assert pygame.image.tostring(game.screen, "RGB") == first_frame
