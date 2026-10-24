"""Live HUD containment, statistics and the real viewing-control routes."""
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from scripts.app.game_app import Game
from scripts.app.match_hud_view import MatchHudView
from scripts.core.settings import WIDTH, HEIGHT, PANEL, SPEED_OPTIONS, CAMERA_ZOOM_LEVELS
from scripts.match.match_status_snapshot import MatchStatusSnapshot


@pytest.fixture
def game():
    pygame.font.init()
    app = Game.__new__(Game)
    app.screen = pygame.Surface((WIDTH, HEIGHT))
    app.fonts = {}
    app.text_surface_cache = {}
    app.logical_mouse_pos = lambda: (-1, -1)
    home = SimpleNamespace(name="ホーム", short_name="ホーム", manager="監督甲", score=3,
                           shots=8, possession=60, primary=(220, 80, 80))
    away = SimpleNamespace(name="アウェー", short_name="アウェー", manager="監督乙", score=2,
                           shots=7, possession=40, primary=(80, 120, 220))
    app.match = SimpleNamespace(state="PLAYING", home=home, away=away, game_time=125,
                                banner="", banner_timer=0, speed_multiplier=1,
                                events=deque(maxlen=8), venue_name="ホーム球技場")
    app.match.status_snapshot = lambda: MatchStatusSnapshot(
        home.short_name, away.short_name, home.score, away.score, app.match.game_time,
        app.match.state, app.match.banner, app.match.banner_timer, app.match.speed_multiplier)
    app.match.predicted_probabilities = Mock(return_value=(0.555, 0.245, 0.2))
    app.match_hud_view = MatchHudView()
    app.speed_buttons = []
    app.zoom_buttons = []
    app.camera_zoom_index = CAMERA_ZOOM_LEVELS.index(1.0)
    app.active_league_fixture_id = ""
    app.settings_open = app.league_screen_open = app.other_matches_open = app.player_list_open = False
    return app


def capture_labels(game):
    labels = []
    text = game.text

    def captured(value, *args, **kwargs):
        rect = text(value, *args, **kwargs)
        assert game.screen.get_rect().contains(rect), value
        labels.append((value, rect))
        return rect

    game.text = captured
    return labels


def test_long_panel_labels_and_all_eight_logs_fit_above_viewing_controls(game):
    game.active_league_fixture_id = "watched"
    for team in (game.match.home, game.match.away):
        team.name *= 20
        team.short_name *= 20
        team.manager *= 20
    game.match.venue_name *= 20
    game.match.events.extend((i, f"試合記録{i} " + "長い選手名とスキル名" * 20) for i in range(8))
    events = list(game.match.events)
    labels = capture_labels(game)
    game.draw_panel()
    panel = pygame.Rect(PANEL.left, PANEL.top, PANEL.width, PANEL.height)
    assert all(panel.contains(rect) for _, rect in labels)
    log_rows = [rect for label, rect in labels if label.startswith("試合記録")]
    assert len(log_rows) == 8
    assert max(rect.bottom for rect in log_rows) < game.other_matches_button.top
    coaches = next(rect for label, rect in labels if label.startswith("監督 "))
    venue = next(rect for label, rect in labels if label.startswith("会場 "))
    assert coaches.bottom < venue.top
    assert list(game.match.events) == events
    assert game.match.game_time == 125


def test_scoreboard_long_abbreviations_do_not_cover_score_or_clock(game):
    game.match.home.short_name = "長いホームの略称" * 20
    game.match.away.short_name = "長いアウェーの略称" * 20
    labels = capture_labels(game)
    game.draw_scoreboard()
    score = next(rect for label, rect in labels if label == "3 : 2")
    home = next(rect for label, rect in labels if label.startswith("長いホーム"))
    away = next(rect for label, rect in labels if label.startswith("長いアウェー"))
    assert home.right < score.left < score.right < away.left
    assert "02:05" in [label for label, _ in labels]


def test_prediction_keeps_all_three_probabilities_visible_with_long_names(game):
    game.match.home.name *= 50
    game.match.away.name *= 50
    labels = capture_labels(game)
    game.match_hud_view.draw_prediction(game)
    percentages = [(label, rect) for label, rect in labels if label.endswith("%")]
    assert [label for label, _ in percentages] == ["56%", "24%", "20%"]
    names = [rect for label, rect in labels if not label.endswith("%")]
    for name, (_, percent) in zip(names, percentages):
        assert name.bottom <= percent.top
    assert names[0].right < names[1].left < names[2].left
    game.match.predicted_probabilities.assert_called_once_with()


@pytest.mark.parametrize("speed", SPEED_OPTIONS)
def test_rendered_speed_buttons_control_actual_match_speed(game, speed):
    game.draw_panel()
    assert [value for _, value in game.speed_buttons] == list(SPEED_OPTIONS)
    button = next(rect for rect, value in game.speed_buttons if value == speed)
    game.handle_click(button.center)
    assert game.match.speed_multiplier == speed


def test_live_buttons_are_disjoint_and_keep_existing_routes(game):
    game.active_league_fixture_id = "watched"
    game.draw_panel()
    buttons = [rect for rect, _ in game.speed_buttons + game.zoom_buttons]
    buttons.extend([game.settings_button, game.player_list_button, game.other_matches_button])
    assert not any(rect.colliderect(other) for i, rect in enumerate(buttons) for other in buttons[i + 1:])
    original_zoom = game.camera_zoom_index
    for rect, step in game.zoom_buttons:
        game.handle_click(rect.center)
        assert game.camera_zoom_index == original_zoom + step
        game.camera_zoom_index = original_zoom
    game.handle_click(game.other_matches_button.center)
    assert game.other_matches_open and game.other_matches_scroll == 0
    game.other_matches_open = False
    game.handle_click(game.player_list_button.center)
    assert game.player_list_open
    assert game.match.state == "PLAYING"
    game.player_list_open = False
    game.handle_click(game.settings_button.center)
    assert game.settings_open and game.match.state == "PAUSED"
    game.close_settings()
    assert not game.settings_open and game.match.state == "PLAYING"


def test_single_match_removes_stale_other_venues_hitbox(game):
    game.active_league_fixture_id = "watched"
    game.draw_panel()
    old_button = game.other_matches_button.copy()
    game.active_league_fixture_id = ""
    game.draw_panel()
    assert game.other_matches_button.size == (0, 0)
    game.handle_click(old_button.center)
    assert not game.other_matches_open


@pytest.mark.parametrize("window_size", [(960, 540), (1600, 1000)])
def test_hud_controls_accept_scaled_and_letterboxed_window_clicks(game, window_size):
    game.draw_panel()
    game.gpu_presenter = None
    game.display_surface = pygame.Surface(window_size)
    rect = game.player_list_button
    scale = min(window_size[0] / WIDTH, window_size[1] / HEIGHT)
    offset_x = (window_size[0] - WIDTH * scale) / 2
    offset_y = (window_size[1] - HEIGHT * scale) / 2
    window_point = (round(rect.centerx * scale + offset_x), round(rect.centery * scale + offset_y))
    game.handle_click(Game.logical_mouse_pos(game, window_point))
    assert game.player_list_open


@pytest.mark.parametrize("home,away,expected", [(0, 0, (50, 50)), (1, 2, (33, 67)), (1, 0, (100, 0))])
def test_possession_percentages_are_based_on_live_statistics_and_sum_to_100(game, home, away, expected):
    game.match.home.possession, game.match.away.possession = home, away
    labels = capture_labels(game)
    game.draw_panel()
    values = [label for label, _ in labels]
    assert f"支配率  {expected[0]}%" in values
    assert f"{expected[1]}%" in values
    assert (game.match.home.possession, game.match.away.possession) == (home, away)


@pytest.mark.parametrize("time,banner,timer,expected", [
    (5399, "", 0, "89:59"), (5400, "", 0, "90:00"), (5401, "", 0, "90:00"),
    (2700, "HALF TIME", 1, "HT"), (2700, "HALF TIME", 0, "45:00"),
])
def test_clock_reads_snapshot_without_advancing_match(game, time, banner, timer, expected):
    game.match.game_time, game.match.banner, game.match.banner_timer = time, banner, timer
    labels = capture_labels(game)
    game.draw_scoreboard()
    assert expected in [label for label, _ in labels]
    assert game.match.game_time == time
