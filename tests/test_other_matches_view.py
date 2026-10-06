"""Live venue rendering, all-record navigation and read-only reconciliation."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pygame
import pytest

from scripts.app.game_app import Game
from scripts.app.other_matches_view import OtherMatchesView
from scripts.core.settings import WIDTH, HEIGHT
from scripts.league.league_live_view import other_match_max_scroll


# {
#   責務: [game: 他会場UIを試合・保存に触れず検査できるホストを作る]
#   処理: [1: 論理画面と表示状態を準備; 2: 独立時計を持つ90会場の速報を設定]
#   引数: []
#   戻り値: [Game: ワーカーを起動しない試験用ホスト]
# }
@pytest.fixture
def game():
    pygame.font.init()
    app = Game.__new__(Game)
    app.screen = pygame.Surface((WIDTH, HEIGHT))
    app.fonts = {}
    app.text_surface_cache = {}
    app.logical_mouse_pos = lambda: (-1, -1)
    app.other_matches_view = OtherMatchesView()
    app.other_matches_open = True
    app.other_matches_scroll = 0
    app.settings_open = app.player_list_open = app.league_screen_open = False
    app.active_league_fixture_id = "watched"
    app.match = SimpleNamespace(state="PLAYING")
    app.league_simulation_session = None
    app.league_manager = SimpleNamespace(last_results=[])
    app.league_live_last_status = [dict(fixture_id=str(i), league=f"リーグ{i % 9}",
                                      home_name=f"ホーム{i}", away_name=f"アウェー{i}",
                                      home_score=i % 4, away_score=i % 3, game_time=120 + i,
                                      state="PLAYING") for i in range(90)]
    app.change_camera_zoom = Mock()
    return app


# {
#   責務: [capture_labels: 描画された文字と領域を観測できるようにする]
#   処理: [1: 元の描画呼出しを保持; 2: 捕捉関数へ差し替え; 3: 追記される観測一覧を返す]
#   引数: [game: 描画を検査するホスト]
#   戻り値: [list: 文字と表示領域の捕捉先]
# }
def capture_labels(game):
    labels = []
    text = game.text

    # {
    #   責務: [captured: 実際の文字描画が画面に収まることを検査し記録する]
    #   処理: [1: 元の描画を実行; 2: 画面内の領域を確認して一覧へ追記]
    #   引数: [value: 表示文字; args: 位置等の描画引数; kwargs: 描画指定]
    #   戻り値: [Rect: 元描画の領域。画面外ならassert失敗]
    # }
    def captured(value, *args, **kwargs):
        rect = text(value, *args, **kwargs)
        assert game.screen.get_rect().contains(rect), value
        labels.append((value, rect))
        return rect

    game.text = captured
    return labels


# {
#   責務: [test_every_one_of_ninety_records_is_readable_through_actual_page_keys: 90会場すべてを実入力で到達・表示できることを確認する]
#   処理: [1: PageDownごとの会場を集計; 2: 全90件の到達を確認; 3: 端点・上下・ページ戻りを確認]
#   引数: [game: 90会場の試験ホスト]
#   戻り値: [None: 欠落やスクロール範囲違反は試験失敗]
# }
def test_every_one_of_ninety_records_is_readable_through_actual_page_keys(game):
    labels = capture_labels(game)
    seen = set()
    for _ in range(4):
        labels.clear()
        game.draw_other_matches()
        homes = {label for label, _ in labels if label.startswith("ホーム")}
        assert len(homes) == 27
        seen.update(homes)
        game.handle_key(pygame.K_PAGEDOWN)
    assert seen == {f"ホーム{i}" for i in range(90)}
    assert game.other_matches_scroll == other_match_max_scroll(90)
    game.handle_key(pygame.K_HOME)
    assert game.other_matches_scroll == 0
    game.handle_key(pygame.K_DOWN)
    assert game.other_matches_scroll == 1
    game.handle_key(pygame.K_UP)
    assert game.other_matches_scroll == 0
    game.handle_key(pygame.K_END)
    game.handle_key(pygame.K_PAGEUP)
    assert game.other_matches_scroll == other_match_max_scroll(90) - 9


# {
#   責務: [test_long_names_and_league_labels_do_not_cover_scores_clocks_or_other_cards: 長い名称でも時計・得点・他カードと重ならないことを確認する]
#   処理: [1: 名称を極端に伸ばす; 2: 得点表示数と全文字領域の非重複を確認]
#   引数: [game: 他会場表示ホスト]
#   戻り値: [None: 重なりや得点欠落は試験失敗]
# }
def test_long_names_and_league_labels_do_not_cover_scores_clocks_or_other_cards(game):
    for status in game.league_live_last_status:
        for key in ("home_name", "away_name", "league"):
            status[key] += "非常に長い名前" * 20
        status["home_score"], status["away_score"] = 123, 456
    labels = capture_labels(game)
    game.draw_other_matches()
    assert len([label for label, _ in labels if label == "123 : 456"]) == 27
    assert all(not rect.colliderect(other) for i, (_, rect) in enumerate(labels)
               for _, other in labels[i + 1:])


# {
#   責務: [test_final_score_overlay_does_not_change_cached_or_worker_records: 確定結果表示がワーカーとキャッシュの元値を壊さないことを確認する]
#   処理: [1: 情報源を選ぶ; 2: 確定得点と終了表示を確認; 3: 元速報と結果の不変を確認]
#   引数: [game: 表示ホスト; worker: ワーカー速報を使うか]
#   戻り値: [None: 元データ変更や未反映は試験失敗]
# }
@pytest.mark.parametrize("worker", [False, True])
def test_final_score_overlay_does_not_change_cached_or_worker_records(game, worker):
    source = game.league_live_last_status
    if worker:
        game.league_simulation_session = SimpleNamespace(
            live_status={status["fixture_id"]: status for status in source}, live_updates=True, worker_count=8)
    game.league_manager.last_results = [dict(fixture_id="0", home_score=7, away_score=8)]
    original, results = deepcopy(source), deepcopy(game.league_manager.last_results)
    labels = capture_labels(game)
    game.draw_other_matches()
    assert "7 : 8" in [label for label, _ in labels]
    assert "終了" in [label for label, _ in labels]
    assert source == original and game.league_manager.last_results == results


# {
#   責務: [test_header_describes_actual_pacing_and_only_advertises_o_to_close: 会場の独立時計と終了待ちに合う説明を確認する]
#   処理: [1: 試合とワーカーの状態を設定; 2: 進行説明・枠数・閉じるキーを確認; 3: 同一時計等の誤案内を拒否]
#   引数: [game: 表示ホスト; state: 観戦状態; live: リアルタイム更新設定; expected: 必要な案内]
#   戻り値: [None: 状況と矛盾する案内は試験失敗]
# }
@pytest.mark.parametrize("state,live,expected", [
    ("PLAYING", True, "各会場の時計は独立"),
    ("FULLTIME", True, "残りの試合を計算中"),
    ("PLAYING", False, "各会場の試合を計算中"),
])
def test_header_describes_actual_pacing_and_only_advertises_o_to_close(game, state, live, expected):
    game.match.state = state
    game.league_simulation_session = SimpleNamespace(live_status={}, live_updates=live, worker_count=4)
    labels = capture_labels(game)
    game.draw_other_matches()
    values = [label for label, _ in labels]
    assert any(expected in label for label in values)
    assert any("並列処理 4枠" in label for label in values)
    assert "O  閉じる" in values
    assert not any("ESC" in label or "同じ試合時計" in label for label in values)


# {
#   責務: [test_each_venue_keeps_its_own_clock_and_zero_clock_does_not_use_stale_minute: 会場別の秒時計とゼロ値を優先して表示することを確認する]
#   処理: [1: 異なる会場時計と古いminute値を設定; 2: 表示を確認; 3: 元時計の不変を確認]
#   引数: [game: 他会場表示ホスト]
#   戻り値: [None: 共通時計化やゼロ値上書きは試験失敗]
# }
def test_each_venue_keeps_its_own_clock_and_zero_clock_does_not_use_stale_minute(game):
    game.league_live_last_status[0].update(game_time=125, minute=0)
    game.league_live_last_status[1].update(game_time=600, minute=0)
    game.league_live_last_status[2].update(game_time=0, minute=90)
    labels = capture_labels(game)
    game.draw_other_matches()
    values = [label for label, _ in labels]
    assert {"02:05", "10:00", "00:00"} <= set(values)
    assert game.league_live_last_status[0]["game_time"] == 125


# {
#   責務: [test_legacy_minute_only_record_has_a_display_clock: 旧minute形式でも速報時計を表示できることを確認する]
#   処理: [1: 秒時計を除去; 2: minute値に対応する表示を確認]
#   引数: [game: 旧形式を注入するホスト]
#   戻り値: [None: 表示互換の欠落は試験失敗]
# }
def test_legacy_minute_only_record_has_a_display_clock(game):
    record = game.league_live_last_status[0]
    del record["game_time"]
    record["minute"] = 7
    labels = capture_labels(game)
    game.draw_other_matches()
    assert "07:00" in [label for label, _ in labels]


# {
#   責務: [test_scrollbar_clicks_and_count_shrink_stay_within_valid_rows: スクロール操作と速報減少後の当たり判定が有効範囲に収まることを確認する]
#   処理: [1: つまみの端点移動を検査; 2: 会場数縮小とゼロ件の状態を検査; 3: 閉じるクリックを検査]
#   引数: [game: 他会場表示ホスト]
#   戻り値: [None: 古い領域・範囲外位置は試験失敗]
# }
def test_scrollbar_clicks_and_count_shrink_stay_within_valid_rows(game):
    game.draw_other_matches()
    track = game.other_matches_scroll_track
    game.handle_click((track.centerx, track.bottom - 1))
    assert game.other_matches_scroll == other_match_max_scroll(90)
    game.draw_other_matches()
    assert game.other_matches_scroll_thumb.bottom == track.bottom
    game.handle_click((track.centerx, track.top))
    assert game.other_matches_scroll == 0
    game.scroll_other_matches(1000)
    game.league_live_last_status = game.league_live_last_status[:2]
    game.draw_other_matches()
    assert game.other_matches_scroll == 0
    assert game.other_matches_scroll_thumb == game.other_matches_scroll_track
    game.league_live_last_status = []
    game.draw_other_matches()
    assert game.other_matches_scroll_track.size == game.other_matches_scroll_thumb.size == (0, 0)
    game.handle_click(game.other_matches_close_button.center)
    assert not game.other_matches_open


# {
#   責務: [test_scaled_window_close_button_returns_without_pausing_match: 拡縮と余白がある画面で速報を正しく閉じることを確認する]
#   処理: [1: 実画面上のクリック位置を算出; 2: 論理座標へ変換して入力; 3: 閉じても試合進行状態が続くか確認]
#   引数: [game: 表示ホスト; window_size: 実ウィンドウ寸法]
#   戻り値: [None: 座標ずれや意図しない停止は試験失敗]
# }
@pytest.mark.parametrize("window_size", [(960, 540), (1600, 1000)])
def test_scaled_window_close_button_returns_without_pausing_match(game, window_size):
    game.draw_other_matches()
    game.gpu_presenter = None
    game.display_surface = pygame.Surface(window_size)
    rect = game.other_matches_close_button
    scale = min(window_size[0] / WIDTH, window_size[1] / HEIGHT)
    offset = ((window_size[0] - WIDTH * scale) / 2, (window_size[1] - HEIGHT * scale) / 2)
    point = (round(rect.centerx * scale + offset[0]), round(rect.centery * scale + offset[1]))
    game.handle_click(Game.logical_mouse_pos(game, point))
    assert not game.other_matches_open and game.match.state == "PLAYING"


# {
#   責務: [test_o_closes_while_escape_keeps_global_settings_behavior: Oは速報を閉じEscは共通設定を開くという優先度を確認する]
#   処理: [1: Escで設定停止と復帰を確認; 2: Oで速報だけを閉じることを確認]
#   引数: [game: 他会場表示ホスト]
#   戻り値: [None: 背景状態への誤操作は試験失敗]
# }
def test_o_closes_while_escape_keeps_global_settings_behavior(game):
    game.handle_key(pygame.K_ESCAPE)
    assert game.settings_open and game.match.state == "PAUSED" and game.other_matches_open
    game.handle_key(pygame.K_ESCAPE)
    assert not game.settings_open and game.match.state == "PLAYING" and game.other_matches_open
    game.handle_key(pygame.K_o)
    assert not game.other_matches_open and game.match.state == "PLAYING"


# {
#   責務: [test_venue_modal_does_not_send_keys_to_background_controls: 速報で無関係なキーが背景操作へ漏れないことを確認する]
#   処理: [1: 背景の各ショートカットを入力; 2: ズーム・能力表示・停止が変わらないことを確認]
#   引数: [game: 表示ホスト; key: 速報中に抑止するキー]
#   戻り値: [None: 入力漏れは試験失敗]
# }
@pytest.mark.parametrize("key", [pygame.K_EQUALS, pygame.K_SPACE, pygame.K_p, pygame.K_f])
def test_venue_modal_does_not_send_keys_to_background_controls(game, key):
    game.handle_key(key)
    game.change_camera_zoom.assert_not_called()
    assert not game.player_list_open and game.match.state == "PLAYING"


# {
#   責務: [test_real_application_loop_keeps_simulating_with_venue_modal_open: 速報を開いても実アプリの固定試合更新が続くことを確認する]
#   処理: [1: 実ホストで試合を開始; 2: 速報付き一フレームを実行; 3: 時計と更新数の増加を確認して終了処理]
#   引数: []
#   戻り値: [None: 表示中の意図しない停止は試験失敗]
# }
def test_real_application_loop_keeps_simulating_with_venue_modal_open():
    app = Game()
    try:
        app.start_selected_match()
        app.other_matches_open = True
        app.match.game_time = 60
        app.match.banner_timer = 0
        app.clock = SimpleNamespace(tick=lambda _fps: 20)

        # {
        #   責務: [draw_one_frame: 速報を実描画して試験ループを一フレームで閉じる]
        #   処理: [1: 他会場ビューを描画; 2: runningを終了状態にする]
        #   引数: []
        #   戻り値: [None: 描画後にホストの継続フラグを更新]
        # }
        def draw_one_frame():
            app.draw_other_matches()
            app.running = False

        app.draw = draw_one_frame
        with patch("pygame.event.get", return_value=[]):
            app.run()
        assert app.match.game_time > 60
        assert app.visible_simulation.last_step_count > 0
        assert app.other_matches_open and app.match.state == "PLAYING"
    finally:
        pygame.quit()
