"""Layout and input contracts for the single-match setup screen."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pygame
import pytest

from scripts.app.game_app import Game
from scripts.app.team_select_view import TeamSelectView
from scripts.app.ui_theme import fit_label
from scripts.core.settings import WIDTH, HEIGHT


@pytest.fixture
def game():
    pygame.font.init()
    app = Game.__new__(Game)
    app.screen = pygame.Surface((WIDTH, HEIGHT))
    app.fonts = {}
    app.text_surface_cache = {}
    app.logical_mouse_pos = lambda: (-1, -1)
    app.team_select_view = TeamSelectView()
    app.team_select_buttons = []
    choice = {
        "id": "home", "name": "テストチーム", "short": "試験", "manager": "監督",
        "primary": (245, 245, 245), "secondary": (70, 80, 90), "home_court": "テスト会場",
        "starters": [{"number": i + 1, "position_x": x, "position_y": y}
                     for i, (x, y) in enumerate(((1, 1), (15, 1), (1, 10), (15, 10), (8, 11)))],
    }
    app.team_choices = [choice, {**deepcopy(choice), "id": "away"}]
    app.home_choice_index, app.away_choice_index = 0, 1
    app.venue_modes = ("HOME", "NEUTRAL", "AWAY")
    app.venue_mode_index = 0
    app.settings_open = app.other_matches_open = app.player_list_open = app.league_screen_open = False
    app.match = SimpleNamespace(state="TEAM_SELECT")
    return app


@pytest.mark.parametrize("mode", range(3))
def test_layout_contains_labels_and_disjoint_controls_even_with_long_names(game, mode, monkeypatch):
    game.venue_mode_index = mode
    for choice in game.team_choices:
        for key in ("name", "short", "manager", "tactic_label", "home_court"):
            choice[key] = "非常に長い日本語の表示項目\n" * 15
    before = deepcopy(game.team_choices)
    labels = []
    text = game.text

    def checked_text(value, *args, **kwargs):
        rect = text(value, *args, **kwargs)
        labels.append((value, rect))
        assert game.screen.get_rect().contains(rect), value
        return rect

    def forbidden_io(*args, **kwargs):
        raise AssertionError("Rendering must not scan team files")

    game.text = checked_text
    monkeypatch.setattr(Path, "glob", forbidden_io)
    monkeypatch.setattr(Path, "rglob", forbidden_io)
    monkeypatch.setattr(Path, "stat", forbidden_io)
    game.draw_team_select()
    assert game.team_choices == before
    assert any(value.endswith("…") for value, _ in labels)
    for card in TeamSelectView.card_rects():
        for value, rect in labels:
            if card.colliderect(rect):
                assert card.contains(rect), value
    controls = [rect for rect, _ in game.team_select_buttons] + [game.settings_button]
    for i, rect in enumerate(controls):
        assert game.screen.get_rect().contains(rect)
        assert all(not rect.colliderect(other) for other in controls[i + 1:])
    assert len(game.team_select_buttons) == 11
    first_frame = pygame.image.tostring(game.screen, "RGB")
    game.draw_team_select()
    assert pygame.image.tostring(game.screen, "RGB") == first_frame


def test_same_team_notice_and_missing_manager_draw(game):
    game.away_choice_index = 0
    game.team_choices[0]["manager"] = ""
    labels = []
    original = game.text

    def capture(value, *args, **kwargs):
        labels.append(value)
        return original(value, *args, **kwargs)

    game.text = capture
    game.draw_team_select()
    assert "同チーム対戦：AWAY側は青ユニフォーム" in labels
    assert "監督 —" in labels
    assert all("未所属" not in label and "操作チーム" not in label for label in labels)


@pytest.mark.parametrize("action, expected", [
    ("home_prev", (1, 1, 0)), ("home_next", (1, 1, 0)),
    ("away_prev", (0, 0, 0)), ("away_next", (0, 0, 0)),
    ("venue_home", (0, 1, 0)), ("venue_neutral", (0, 1, 1)), ("venue_away", (0, 1, 2)),
])
def test_actual_rendered_controls_route_to_existing_selection_logic(game, action, expected):
    game.draw_team_select()
    rect = next(rect for rect, value in game.team_select_buttons if value == action)
    game.handle_click(rect.center)
    assert (game.home_choice_index, game.away_choice_index, game.venue_mode_index) == expected


@pytest.mark.parametrize("action, method", [
    ("start", "start_selected_match"), ("editor", "open_team_editor"),
    ("league", "open_league_screen"), ("main_menu", "return_to_main_menu"),
])
def test_rendered_navigation_invokes_the_existing_action(game, action, method):
    called = []
    setattr(game, method, lambda: called.append(action))
    game.draw_team_select()
    rect = next(rect for rect, value in game.team_select_buttons if value == action)
    game.handle_click(rect.center)
    assert called == [action]


def test_fit_label_keeps_short_text_normalizes_newlines_and_bounds_ellipsis(game):
    font = game.font(26, True)
    assert fit_label(font, "蜜柑山", 500) == "蜜柑山"
    assert fit_label(font, "蜜柑山\n学園", 500) == "蜜柑山 学園"
    assert fit_label(font, "チーム", 0) == ""
    for width in (20, 100, 280, 500):
        value = fit_label(font, "長いチーム名" * 100, width)
        assert value.endswith("…") or value == ""
        assert font.size(value)[0] <= width
