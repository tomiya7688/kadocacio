"""Player-list readability, live values and modal input isolation."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pygame
import pytest

from scripts.app.game_app import Game
from scripts.app.player_status_view import PlayerStatusView
from scripts.core.settings import WIDTH, HEIGHT
from scripts.team import team_rating


@pytest.fixture
def game():
    pygame.font.init()
    app = Game.__new__(Game)
    app.screen = pygame.Surface((WIDTH, HEIGHT))
    app.fonts = {}
    app.text_surface_cache = {}
    app.logical_mouse_pos = lambda: (-1, -1)
    app.player_status_view = PlayerStatusView()
    app.player_list_open = True
    app.player_list_rank_mode = False
    app.settings_open = app.other_matches_open = app.league_screen_open = False
    app.active_league_fixture_id = "watched"
    teams = []
    for side in ("ホーム", "アウェー"):
        raw = {team_rating.JAPANESE_TO_CANONICAL.get(field, field): 5500
               for category in team_rating.TUNER_CATEGORIES for field in category["fields"]}
        players = [SimpleNamespace(name=f"{side}選手{i}", number=i, role="GK" if i == 11 else "MF",
                                   sent_off=False, yellow_cards=0, player_type="チャンスメーカー",
                                   stamina=500, stamina_max=1000, stamina_ratio=0.5, alertness={},
                                   tactical_loyalty=0.5, confidence=0.6, zone_awareness=0.7,
                                   position_awareness=0.8, aggressiveness=0.9, data={"raw": raw.copy()})
                   for i in range(1, 12)]
        teams.append(SimpleNamespace(name=side, primary=(255, 255, 255), tactic="BALANCE",
                                     substitutions_used=0, players=players))
    app.match = SimpleNamespace(state="PLAYING", teams=teams, ball=SimpleNamespace(owner=teams[0].players[0]))
    app.change_camera_zoom = Mock()
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


@pytest.mark.parametrize("rank_mode", [False, True])
def test_all_twenty_two_players_and_long_labels_fit_without_text_overlap(game, rank_mode):
    game.player_list_rank_mode = rank_mode
    for team in game.match.teams:
        team.name *= 60
        for player in team.players:
            player.name += "非常に長い選手名" * 30
            player.player_type *= 20
    game.match.teams[0].players[0].yellow_cards = 1
    game.match.teams[1].players[0].sent_off = True
    labels = capture_labels(game)
    game.draw_player_list()
    names = [rect for label, rect in labels if "選手" in label and not label.startswith("選手一覧")
             and not label.startswith("ピッチ") and "交代" not in label]
    assert len(names) == 22
    assert all(not rect.colliderect(other) for i, (_, rect) in enumerate(labels)
               for _, other in labels[i + 1:])
    assert "黄1" in [label for label, _ in labels]
    assert "退場" in [label for label, _ in labels]
    assert game.match.state == "PLAYING"


def test_rank_mode_shows_every_configured_category_and_current_raw_values(game):
    game.player_list_rank_mode = True
    labels = capture_labels(game)
    game.draw_player_list()
    legend = next(label for label, _ in labels if "フィジカル" in label)
    for category in team_rating.TUNER_CATEGORIES:
        assert f"{category['short']}:{category['label']}" in legend
    grades = [label for label, _ in labels if label.startswith("キS")]
    assert len(grades) == 22
    for category in team_rating.TUNER_CATEGORIES:
        assert f"{category['short']}S" in grades[0]
    player = game.match.teams[0].players[0]
    for key in player.data["raw"]:
        player.data["raw"][key] = 0
    labels.clear()
    game.draw_player_list()
    assert len([label for label, _ in labels if label.startswith("キE-")]) == 1
    assert len([label for label, _ in labels if label.startswith("キS")]) == 21


def test_stamina_and_alertness_are_refreshed_without_changing_player_state(game):
    labels = capture_labels(game)
    game.draw_player_list()
    assert "500/1000 · 50%" in [label for label, _ in labels]
    player = game.match.teams[0].players[0]
    player.stamina, player.stamina_ratio = 0, 0
    target = Mock(number=9)
    player.alertness = {target: 0.9}
    labels.clear()
    game.draw_player_list()
    values = [label for label, _ in labels]
    assert "0/1000 · 0%" in values
    assert any(label.endswith("警#9") for label in values)
    assert player.stamina == 0 and player.alertness == {target: 0.9}
    assert game.match.ball.owner is player


@pytest.mark.parametrize("value,rank", [(0, "E-"), (4500, "A+"), (5500, "S")])
def test_longer_rank_codes_do_not_hide_any_of_the_ten_categories(game, value, rank):
    game.player_list_rank_mode = True
    for team in game.match.teams:
        for player in team.players:
            for field in player.data["raw"]:
                player.data["raw"][field] = value
    labels = capture_labels(game)
    game.draw_player_list()
    grades = [label for label, _ in labels if label.startswith(f"キ{rank}")]
    assert len(grades) == 22
    for label in grades:
        assert "…" not in label
        assert all(f"{category['short']}{rank}" in label for category in team_rating.TUNER_CATEGORIES)


@pytest.mark.parametrize("window_size", [(960, 540), (1600, 1000)])
def test_scaled_window_can_switch_mode_and_close_list(game, window_size):
    game.draw_player_list()
    game.gpu_presenter = None
    game.display_surface = pygame.Surface(window_size)
    scale = min(window_size[0] / WIDTH, window_size[1] / HEIGHT)
    offset = ((window_size[0] - WIDTH * scale) / 2, (window_size[1] - HEIGHT * scale) / 2)
    for rect in (game.player_list_rank_button, game.player_list_close_button):
        point = (round(rect.centerx * scale + offset[0]), round(rect.centery * scale + offset[1]))
        game.handle_click(Game.logical_mouse_pos(game, point))
    assert game.player_list_rank_mode and not game.player_list_open


@pytest.mark.parametrize("key", [pygame.K_p, pygame.K_TAB])
def test_close_key_and_rendered_close_button_leave_match_running(game, key):
    game.draw_player_list()
    game.handle_click(game.player_list_close_button.center)
    assert not game.player_list_open and game.match.state == "PLAYING"
    game.player_list_open = True
    game.handle_key(key)
    assert not game.player_list_open and game.match.state == "PLAYING"


@pytest.mark.parametrize("state", ["PLAYING", "PAUSED", "FULLTIME"])
def test_mouse_and_g_key_switch_display_mode_without_changing_match_state(game, state):
    game.match.state = state
    game.draw_player_list()
    game.handle_click(game.player_list_rank_button.center)
    assert game.player_list_rank_mode
    game.handle_key(pygame.K_g)
    assert not game.player_list_rank_mode and game.match.state == state


@pytest.mark.parametrize("key", [pygame.K_o, pygame.K_EQUALS, pygame.K_MINUS, pygame.K_SPACE, pygame.K_f])
def test_player_list_does_not_send_keys_to_background_match_controls(game, key):
    game.handle_key(key)
    game.change_camera_zoom.assert_not_called()
    assert not game.other_matches_open
    assert game.match.state == "PLAYING" and game.player_list_open


def test_escape_keeps_global_settings_and_restores_underlying_player_list(game):
    game.handle_key(pygame.K_ESCAPE)
    assert game.settings_open and game.match.state == "PAUSED"
    assert game.player_list_open
    game.handle_key(pygame.K_ESCAPE)
    assert not game.settings_open and game.match.state == "PLAYING"
    assert game.player_list_open


@pytest.mark.parametrize("rank_mode", [False, True])
def test_real_application_loop_advances_match_with_player_list_open(rank_mode):
    app = Game()
    try:
        app.start_selected_match()
        app.player_list_open = True
        app.player_list_rank_mode = rank_mode
        app.match.game_time = 60
        app.match.banner_timer = 0
        app.clock = SimpleNamespace(tick=lambda _fps: 20)

        def draw_one_frame():
            app.draw_player_list()
            app.running = False

        app.draw = draw_one_frame
        with patch("pygame.event.get", return_value=[]):
            app.run()
        assert app.match.game_time > 60
        assert app.visible_simulation.last_step_count > 0
        assert app.player_list_open and app.match.state == "PLAYING"
    finally:
        pygame.quit()
