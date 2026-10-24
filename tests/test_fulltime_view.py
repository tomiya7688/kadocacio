"""Result paging, completion guards and isolation from hidden match controls."""
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from scripts.app.fulltime_view import FulltimeView, SCORERS_PER_PAGE, RESULTS_PER_PAGE
from scripts.app.fulltime_pagination import FulltimePagination
from scripts.app.game_app import Game
from scripts.core.settings import WIDTH, HEIGHT


@pytest.fixture
def game():
    pygame.font.init()
    app = Game.__new__(Game)
    app.screen = pygame.Surface((WIDTH, HEIGHT))
    app.fonts = {}
    app.text_surface_cache = {}
    app.logical_mouse_pos = lambda: (-1, -1)
    home = SimpleNamespace(name="ホーム", score=3, shots=8, possession=60, primary=(220, 80, 80))
    away = SimpleNamespace(name="アウェー", score=2, shots=7, possession=40, primary=(80, 120, 220))
    app.match = SimpleNamespace(state="FULLTIME", home=home, away=away,
                                goal_scorers=[], start_new=Mock())
    app.fulltime_view = FulltimeView()
    app.fulltime_buttons = []
    app.speed_buttons = []
    app.zoom_buttons = []
    app.active_league_fixture_id = ""
    app.league_match_finalized = True
    app.league_simulation_session = None
    app.league_manager = SimpleNamespace(last_results=[])
    app.settings_open = app.league_screen_open = app.other_matches_open = app.player_list_open = False
    app.change_camera_zoom = Mock()
    app.visible_simulation = SimpleNamespace(reset=Mock())
    app.roll_stadium_guests = Mock()
    app.reset_camera = Mock()
    app.present = Mock()
    return app


def capture_labels(game):
    labels = []
    text = game.text

    def captured(value, *args, **kwargs):
        rect = text(value, *args, **kwargs)
        assert game.screen.get_rect().contains(rect), value
        labels.append(value)
        return rect

    game.text = captured
    return labels


def click_action(game, action):
    rect = next(rect for rect, value in game.fulltime_buttons if value == action)
    game.handle_click(rect.center)


def add_results(game, total):
    game.active_league_fixture_id = "watched"
    game.league_manager.last_results = [dict(league="K1リーグ", home_name=f"ホーム{i}",
                                           away_name=f"アウェー{i}", home_score=i % 5, away_score=1)
                                       for i in range(total)]


def test_every_scorer_can_be_read_through_rendered_paging_buttons(game):
    game.match.goal_scorers = [(i, f"得点者{i}") for i in range(23)]
    labels = capture_labels(game)
    seen = set()
    for _ in range(FulltimePagination.count(23, SCORERS_PER_PAGE)):
        labels.clear()
        game.fulltime_view.draw(game)
        seen.update(label for label in labels if label.startswith("得点者"))
        if any(action == "scorers_next" for _, action in game.fulltime_buttons):
            click_action(game, "scorers_next")
    assert seen == {f"得点者{i}" for i in range(23)}
    assert not any(action == "scorers_next" for _, action in game.fulltime_buttons)
    game.fulltime_view.change_page(game, "scorers", 1000)
    assert game.fulltime_view.pagination.pages["scorers"] == 3
    game.fulltime_view.change_page(game, "scorers", -1000)
    assert game.fulltime_view.pagination.pages["scorers"] == 0


def test_all_ninety_results_are_readable_and_mousewheel_uses_the_hovered_list(game):
    add_results(game, 90)
    labels = capture_labels(game)
    seen = set()
    for _ in range(FulltimePagination.count(90, RESULTS_PER_PAGE)):
        labels.clear()
        game.fulltime_view.draw(game)
        seen.update(label for label in labels if label.startswith("ホーム"))
        if any(action == "results_next" for _, action in game.fulltime_buttons):
            click_action(game, "results_next")
    assert {f"ホーム{i}" for i in range(90)} <= seen
    view = game.fulltime_view
    view.handle_wheel(game, -1, view.list_rects["results"].center)
    assert view.pagination.pages == {"scorers": 0, "results": 16}
    view.handle_wheel(game, -1, (-1, -1))
    assert view.pagination.pages["results"] == 16


@pytest.mark.parametrize("waiting", [False, True])
def test_league_return_waits_for_background_completion_for_click_and_keys(game, waiting):
    add_results(game, 4)
    if waiting:
        game.league_simulation_session = SimpleNamespace(display_completed=3, total=4)
    game.fulltime_view.draw(game)
    actions = {action for _, action in game.fulltime_buttons}
    assert ("league_results" in actions) is not waiting
    game.handle_key(pygame.K_r)
    game.match.start_new.assert_not_called()
    for key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_t):
        game.handle_key(key)
        assert game.league_screen_open is not waiting
        if not waiting:
            break
    if waiting:
        game.league_simulation_session = None
        game.fulltime_view.draw(game)
        click_action(game, "league_results")
        assert game.league_screen_open


def test_single_match_rematch_resets_same_match_pages_and_runtime(game):
    game.match.goal_scorers = [(i, "得点者") for i in range(20)]
    game.fulltime_view.draw(game)
    game.fulltime_view.change_page(game, "scorers", 2)
    click_action(game, "rematch")
    assert game.fulltime_view.pagination.pages == {"scorers": 0, "results": 0}
    game.match.start_new.assert_called_once_with()
    game.visible_simulation.reset.assert_called_once_with(game.match)
    game.roll_stadium_guests.assert_called_once_with()
    game.reset_camera.assert_called_once_with()


def test_new_match_and_shrinking_results_reset_or_clamp_pages(game):
    add_results(game, 20)
    game.fulltime_view.draw(game)
    game.fulltime_view.change_page(game, "results", 3)
    game.league_manager.last_results.clear()
    game.fulltime_view.draw(game)
    assert game.fulltime_view.pagination.pages["results"] == 0
    game.fulltime_view.pagination.pages["scorers"] = 2
    game.match = SimpleNamespace(**vars(game.match))
    game.fulltime_view.draw(game)
    assert game.fulltime_view.pagination.pages["scorers"] == 0


@pytest.mark.parametrize("league", [False, True])
def test_long_labels_zero_possession_and_draw_are_contained(game, league):
    labels = capture_labels(game)
    game.match.home.name = "日本語のとても長いチーム名" * 40
    game.match.away.name = "日本語のとても長い相手名" * 40
    game.match.home.possession = game.match.away.possession = 0
    game.match.home.score = game.match.away.score = 0
    game.match.goal_scorers = [(90, "非常に長い得点者名" * 20)]
    if league:
        add_results(game, 6)
        game.league_manager.last_results[0].update(
            home_name=game.match.home.name, away_name=game.match.away.name,
            home_penalties=4, away_penalties=3, watched=True,
        )
    game.fulltime_view.draw(game)
    assert "引き分け" in labels
    assert any("50% : 50%" in value for value in labels)
    assert any(value.endswith("…") for value in labels)
    if league:
        assert any("PK 4 – 3" in value for value in labels)
    buttons = [rect for rect, _ in game.fulltime_buttons] + [game.settings_button]
    for i, rect in enumerate(buttons):
        assert game.screen.get_rect().contains(rect)
        assert all(not rect.colliderect(other) for other in buttons[i + 1:])


def test_fulltime_does_not_draw_pitch_or_trigger_hidden_camera_controls(game):
    game.draw_pitch = Mock(side_effect=AssertionError("Finished match must not render pitch"))
    game.draw()
    game.draw_pitch.assert_not_called()
    old_control = pygame.Rect(610, 650, 100, 40)
    game.zoom_buttons = [(old_control, 1)]
    game.other_matches_button = old_control
    game.handle_click(old_control.center)
    game.handle_key(pygame.K_MINUS)
    game.handle_key(pygame.K_EQUALS)
    game.change_camera_zoom.assert_not_called()


def test_players_and_other_matches_actions_remain_available(game):
    add_results(game, 1)
    game.fulltime_view.draw(game)
    click_action(game, "players")
    assert game.player_list_open
    game.player_list_open = False
    click_action(game, "other_matches")
    assert game.other_matches_open
