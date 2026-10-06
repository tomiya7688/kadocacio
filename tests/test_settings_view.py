"""Common settings geometry, persistence and real input dispatch contracts."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pygame
import pytest

from scripts.app.game_app import Game
from scripts.app.settings_view import CARD, SettingsView
from scripts.core.performance_settings import PerformanceSettings, load_performance_settings
from scripts.core.settings import WIDTH, HEIGHT


# {
#   責務: [game: 保存や実ワーカーに触れない設定UI試験用ホストを準備する]
#   処理: [1: 論理画面と初期設定を生成; 2: 設定を開き焦点と前状態を用意]
#   引数: []
#   戻り値: [Game: 最小状態を注入した試験ホスト]
# }
@pytest.fixture
def game():
    pygame.font.init()
    app = Game.__new__(Game)
    app.screen = pygame.Surface((WIDTH, HEIGHT))
    app.fonts, app.text_surface_cache = {}, {}
    app.logical_mouse_pos = lambda: (-1, -1)
    app.settings_view = SettingsView()
    app.settings_buttons = []
    app.settings_open = False
    app.settings_previous_match_state = ""
    app.match = SimpleNamespace(state="MAIN_MENU")
    app.performance_settings = PerformanceSettings()
    app.cpu_limit_percent = 100
    app.league_simulation_mode = "PRECISE"
    app.window_size_index = 1
    app.fullscreen = False
    app.gpu_presenter = None
    app.league_auto_running = False
    app.visible_simulation = SimpleNamespace(wall_time_budget=0.008)
    app.open_settings()
    return app


# {
#   責務: [labels_for: 設定内の文字と描画領域を捕捉する]
#   処理: [1: 元の描画関数を保持; 2: 捕捉関数へ置換して追記先を返す]
#   引数: [game: 設定表示ホスト]
#   戻り値: [list: 表示文字と領域の観測一覧]
# }
def labels_for(game):
    labels = []
    text = game.text

    # {
    #   責務: [capture: 実描画が設定カード内に収まることを確認して記録する]
    #   処理: [1: 元の文字描画を実行; 2: カード内を検査して領域を追記]
    #   引数: [value: 表示文字; args: 描画の位置等; kwargs: 描画指定]
    #   戻り値: [Rect: 描画領域。カード外ならassert失敗]
    # }
    def capture(value, *args, **kwargs):
        rect = text(value, *args, **kwargs)
        assert CARD.contains(rect), value
        labels.append((value, rect))
        return rect

    game.text = capture
    return labels


# {
#   責務: [test_settings_layout_fits_all_contexts_without_overlapping_text_or_controls: 全表示状態で文字と設定ボタンが重ならないことを確認する]
#   処理: [1: 試合状態とオートを設定; 2: 文字・操作領域の内包と非重複を確認; 3: 状況依存操作と初期焦点を確認]
#   引数: [game: 表示ホスト; state: 試合またはメニュー状態; auto: オート実行設定]
#   戻り値: [None: 見切れ・重なり・誤操作の表示は試験失敗]
# }
@pytest.mark.parametrize("state,auto", [("MAIN_MENU", False), ("TEAM_SELECT", False),
                                      ("PLAYING", False), ("PAUSED", False), ("FULLTIME", False),
                                      ("PLAYING", True), ("MAIN_MENU", True)])
def test_settings_layout_fits_all_contexts_without_overlapping_text_or_controls(game, state, auto):
    game.close_settings()
    game.match.state, game.league_auto_running = state, auto
    game.open_settings()
    labels = labels_for(game)
    game.draw_settings_modal()
    buttons = game.settings_buttons
    assert buttons == SettingsView.buttons(game)
    for index, (rect, action) in enumerate(buttons):
        assert CARD.contains(rect)
        assert all(not rect.colliderect(other) for other, _ in buttons[index + 1:])
        for label, text_rect in labels:
            if rect.colliderect(text_rect):
                assert rect.contains(text_rect), (action, label)
    assert all(not rect.colliderect(other) for i, (_, rect) in enumerate(labels)
               for _, other in labels[i + 1:])
    actions = [action for _, action in buttons]
    assert ("abort" in actions) == (state in ("PLAYING", "PAUSED"))
    assert ("skip" in actions) == (state in ("PLAYING", "PAUSED"))
    assert ("auto_stop" in actions) == auto
    assert game.settings_focus == len(buttons) - 1


# {
#   責務: [test_display_subtitles_are_inside_buttons_and_custom_cpu_value_is_visible: 規定選択肢以外のCPU値と画面の補足表示を確認する]
#   処理: [1: 任意CPU値・全画面・サイズを設定; 2: 現在値とボタン内の文字数を確認; 3: 誤ったCPU選択表示を拒否]
#   引数: [game: 表示ホスト]
#   戻り値: [None: 現在値欠落や選択状態の誤りは試験失敗]
# }
def test_display_subtitles_are_inside_buttons_and_custom_cpu_value_is_visible(game):
    game.cpu_limit_percent = 63
    game.window_size_index = 3
    game.fullscreen = True
    labels = labels_for(game)
    game.draw_settings_modal()
    assert "現在 63%" in [label for label, _ in labels]
    assert "1920 × 1080" in [label for label, _ in labels]
    display_buttons = [rect for rect, action in game.settings_buttons
                       if action in ("window_size", "fullscreen", "gpu_rendering")]
    assert all(sum(rect.contains(text_rect) for _, text_rect in labels) == 2 for rect in display_buttons)
    assert all(not SettingsView._label(game, action)[2] for _, action in game.settings_buttons
               if action.startswith("cpu:"))


# {
#   責務: [test_long_backend_and_mode_labels_stay_within_bounds: 長い演算品質と描画バックエンド名が省略されることを確認する]
#   処理: [1: 長い名称を一時注入; 2: 描画で省略表示を確認]
#   引数: [game: 設定ホスト]
#   戻り値: [None: 領域超過や省略不足は試験失敗]
# }
def test_long_backend_and_mode_labels_stay_within_bounds(game):
    from scripts.app.settings_view import LEAGUE_SIMULATION_MODES
    profile = dict(LEAGUE_SIMULATION_MODES["PRECISE"], label="とても長い精密モードの名前" * 20)
    with patch.dict(LEAGUE_SIMULATION_MODES, {"PRECISE": profile}), \
            patch.object(Game, "render_backend_name", "GPU " * 100):
        labels = labels_for(game)
        game.draw_settings_modal()
    assert len([value for value, _ in labels if value.endswith("…")]) == 2


# {
#   責務: [test_drawing_never_saves_configuration_or_changes_match_state: 再描画だけで保存や試合状態変更を起こさないことを確認する]
#   処理: [1: 試合中に設定を開く; 2: 二回の描画を比較; 3: 保存未呼出しと停止状態維持を確認]
#   引数: [game: 設定ホスト]
#   戻り値: [None: 描画による副作用は試験失敗]
# }
def test_drawing_never_saves_configuration_or_changes_match_state(game):
    game.close_settings()
    game.match.state = "PLAYING"
    game.open_settings()
    with patch("scripts.app.game_app.save_performance_settings") as save:
        game.draw_settings_modal()
        frame = pygame.image.tostring(game.screen, "RGB")
        game.screen.fill((0, 0, 0))
        game.draw_settings_modal()
    save.assert_not_called()
    assert frame == pygame.image.tostring(game.screen, "RGB")
    assert game.match.state == "PAUSED"


# {
#   責務: [test_tab_and_shift_tab_visit_every_control_and_enter_dispatches_focused_action: 全設定の焦点巡回と確定キーの操作一致を確認する]
#   処理: [1: Tabで全操作を巡回しEnter先を照合; 2: 逆巡回とSpace・テンキーEnterを照合]
#   引数: [game: 入力ホスト]
#   戻り値: [None: 操作の到達不能や焦点ずれは試験失敗]
# }
def test_tab_and_shift_tab_visit_every_control_and_enter_dispatches_focused_action(game):
    actions = [action for _, action in SettingsView.buttons(game)]
    game.handle_settings_action = Mock()
    visited = []
    for _ in actions:
        game.handle_key(pygame.K_TAB)
        visited.append(game.settings_focus)
        game.handle_key(pygame.K_RETURN)
        assert game.handle_settings_action.call_args.args == (actions[game.settings_focus],)
    assert visited == list(range(len(actions)))
    game.handle_key(pygame.K_TAB, shift=True)
    assert game.settings_focus == len(actions) - 2
    game.handle_key(pygame.K_SPACE)
    assert game.handle_settings_action.call_args.args == (actions[-2],)
    game.handle_key(pygame.K_KP_ENTER)
    assert game.handle_settings_action.call_args.args == (actions[-2],)


# {
#   責務: [test_escape_and_default_enter_restore_previous_state_and_clear_buttons: 設定終了時に元状態と入力領域を正しく復帰することを確認する]
#   処理: [1: 各状態からEscで設定を開く; 2: 既定Enterで閉じて前状態を確認; 3: Esc二回での復帰を確認]
#   引数: [game: 設定ホスト; state: 開く前の状態]
#   戻り値: [None: 意図しない再開や古い領域残留は試験失敗]
# }
@pytest.mark.parametrize("state", ["PLAYING", "PAUSED", "MAIN_MENU", "FULLTIME"])
def test_escape_and_default_enter_restore_previous_state_and_clear_buttons(game, state):
    game.close_settings()
    game.match.state = state
    game.handle_key(pygame.K_ESCAPE)
    game.draw_settings_modal()
    assert game.match.state == ("PAUSED" if state == "PLAYING" else state)
    game.handle_key(pygame.K_RETURN)
    assert not game.settings_open and not game.settings_buttons
    assert game.match.state == state
    game.handle_key(pygame.K_ESCAPE)
    game.handle_key(pygame.K_ESCAPE)
    assert not game.settings_open and game.match.state == state


# {
#   責務: [test_actual_setting_actions_persist_to_isolated_json_and_update_runtime: 実クリックが設定値を保存し必要な演算枠へ反映することを確認する]
#   処理: [1: 保存先を隔離; 2: 操作を実クリック; 3: 読戻しとホスト値・CPU時間枠を確認]
#   引数: [game: 設定ホスト; tmp_path: 隔離保存先; action: 変更操作; value: 期待設定値]
#   戻り値: [None: 保存と実行設定の不一致は試験失敗]
# }
@pytest.mark.parametrize("action,value", [("cpu:25", 25), ("league_mode:LIGHT", "LIGHT"),
                                         ("gpu_rendering", False)])
def test_actual_setting_actions_persist_to_isolated_json_and_update_runtime(game, tmp_path, action, value):
    from scripts.core.performance_settings import save_performance_settings
    path = tmp_path / "settings.json"
    with patch("scripts.app.game_app.save_performance_settings",
               side_effect=lambda settings: save_performance_settings(settings, path)):
        game.draw_settings_modal()
        rect = next(rect for rect, selected in game.settings_buttons if selected == action)
        game.handle_click(rect.center)
    assert game.settings_open
    saved = load_performance_settings(path)
    attribute = {"cpu:25": "cpu_limit_percent", "league_mode:LIGHT": "league_simulation_mode",
                 "gpu_rendering": "gpu_rendering"}[action]
    assert getattr(saved, attribute) == getattr(game.performance_settings, attribute) == value
    if action.startswith("cpu:"):
        assert game.visible_simulation.wall_time_budget == 0.002


# {
#   責務: [test_existing_match_and_auto_actions_use_same_routes: 中断・スキップ・オート停止が既存処理へ渡ることを確認する]
#   処理: [1: 試合中の設定と焦点を準備; 2: 確定キーで対象処理を実行; 3: 閉じた設定と停止状態を確認]
#   引数: [game: 設定ホスト; action: 終了操作; method: 呼び出す既存メソッド]
#   戻り値: [None: 経路や復帰状態の違いは試験失敗]
# }
@pytest.mark.parametrize("action,method", [("skip", "start_match_skip"), ("abort", "abort_current_match"),
                                          ("auto_stop", "stop_league_auto_progress")])
def test_existing_match_and_auto_actions_use_same_routes(game, action, method):
    game.close_settings()
    game.match.state = "PLAYING"
    game.league_auto_running = True
    game.open_settings()
    game.draw_settings_modal()
    setattr(game, method, Mock())
    index = next(index for index, (_, selected) in enumerate(game.settings_buttons) if selected == action)
    game.settings_focus = index
    game.handle_key(pygame.K_RETURN)
    getattr(game, method).assert_called_once_with()
    assert not game.settings_open
    assert game.match.state == ("PLAYING" if action == "auto_stop" else "PAUSED")


# {
#   責務: [test_background_shortcuts_and_outside_clicks_are_blocked: 設定中の背景操作を遮断し画面ショートカットだけを許可することを確認する]
#   処理: [1: 背景キーと領域外クリックを入力; 2: 操作未呼出しを確認; 3: F10/F11の設定経路を確認]
#   引数: [game: 設定ホスト]
#   戻り値: [None: 背景への入力漏れは試験失敗]
# }
def test_background_shortcuts_and_outside_clicks_are_blocked(game):
    game.handle_settings_action = Mock()
    game.draw_settings_modal()
    for key in (pygame.K_f, pygame.K_p, pygame.K_o, pygame.K_1, pygame.K_EQUALS):
        game.handle_key(key)
    game.handle_click((0, 0))
    game.handle_settings_action.assert_not_called()
    game.handle_key(pygame.K_F10)
    game.handle_settings_action.assert_called_with("window_size")
    game.handle_key(pygame.K_F11)
    game.handle_settings_action.assert_called_with("fullscreen")


# {
#   責務: [test_close_click_uses_logical_coordinates_with_letterboxing: ウィンドウ拡縮と余白でも閉じる当たり判定が一致することを確認する]
#   処理: [1: 実画面のクリック座標を算出; 2: 論理座標へ変換して入力; 3: 設定と入力領域の終了を確認]
#   引数: [game: 設定ホスト; window_size: 実画面寸法]
#   戻り値: [None: 入力の座標ずれは試験失敗]
# }
@pytest.mark.parametrize("window_size", [(960, 540), (1600, 1000)])
def test_close_click_uses_logical_coordinates_with_letterboxing(game, window_size):
    game.draw_settings_modal()
    game.display_surface = pygame.Surface(window_size)
    rect = game.settings_buttons[-1][0]
    scale = min(window_size[0] / WIDTH, window_size[1] / HEIGHT)
    offset = ((window_size[0] - WIDTH * scale) / 2, (window_size[1] - HEIGHT * scale) / 2)
    position = (round(rect.centerx * scale + offset[0]), round(rect.centery * scale + offset[1]))
    game.handle_click(Game.logical_mouse_pos(game, position))
    assert not game.settings_open and not game.settings_buttons


# {
#   責務: [test_actual_loop_routes_shift_tab_and_enter_then_resumes_simulation: 実イベントループで逆巡回と確定後の固定試合更新を確認する]
#   処理: [1: 実ホストで設定を開く; 2: Shift付きキーイベントを配送; 3: 焦点履歴と復帰後の時計・更新数を確認]
#   引数: []
#   戻り値: [None: 修飾キー欠落や試合再開失敗は試験失敗]
# }
def test_actual_loop_routes_shift_tab_and_enter_then_resumes_simulation():
    app = Game()
    try:
        app.start_selected_match()
        app.match.game_time = 60
        app.match.banner_timer = 0
        app.open_settings()
        count = len(SettingsView.buttons(app))
        app.clock = SimpleNamespace(tick=lambda _fps: 20)
        # Shift+Tab focuses skip, Tab returns to close, then Enter resumes play.
        events = [pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod) for key, mod in
                  ((pygame.K_TAB, pygame.KMOD_SHIFT), (pygame.K_TAB, 0), (pygame.K_RETURN, 0))]
        observed_focus = []
        handler = app.handle_key

        # {
        #   責務: [record: 元のキー処理後の焦点移動を観測する]
        #   処理: [1: 元ハンドラへ入力を配送; 2: 焦点番号を履歴へ追加]
        #   引数: [key: 入力キー; kwargs: Shift等の修飾指定]
        #   戻り値: [None: 観測履歴を更新]
        # }
        def record(key, **kwargs):
            handler(key, **kwargs)
            observed_focus.append(app.settings_focus)

        app.handle_key = record
        app.draw = lambda: setattr(app, "running", False)
        with patch("pygame.event.get", return_value=events):
            app.run()
        assert observed_focus[:2] == [count - 2, count - 1]
        assert not app.settings_open and app.match.state == "PLAYING"
        assert app.match.game_time > 60 and app.visible_simulation.last_step_count > 0
    finally:
        pygame.quit()
