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


# {
#   責務: [game: 対戦準備の描画・入力だけを実行できる独立アプリ状態を返す]
#   処理: [1: メモリSurfaceと描画キャッシュを用意する; 2: 架空2チームと選択状態を設定する]
#   引数: []
#   戻り値: [Game: ファイル読込・実Match構築・実ウィンドウを伴わないpytest fixture]
# }
@pytest.fixture
def game():
    # 対戦データは試験内だけで作り、実チームやセーブへ触れない。
    pygame.font.init()
    app = Game.__new__(Game)
    app.screen = pygame.Surface((WIDTH, HEIGHT))
    app.fonts = {}
    app.text_surface_cache = {}
    app.logical_mouse_pos = lambda: (-1, -1)
    app.team_select_view = TeamSelectView()
    app.team_select_buttons = []
    choice = {
        "id": "home",
        "name": "テストチーム",
        "short": "試験",
        "manager": "監督",
        "primary": (245, 245, 245),
        "secondary": (70, 80, 90),
        "home_court": "テスト会場",
        "starters": [
            {"number": i + 1, "position_x": x, "position_y": y}
            for i, (x, y) in enumerate(((1, 1), (15, 1), (1, 10), (15, 10), (8, 11)))
        ],
    }
    app.team_choices = [choice, {**deepcopy(choice), "id": "away"}]
    app.home_choice_index, app.away_choice_index = 0, 1
    app.venue_modes = ("HOME", "NEUTRAL", "AWAY")
    app.venue_mode_index = 0
    app.settings_open = app.other_matches_open = app.player_list_open = app.league_screen_open = False
    app.match = SimpleNamespace(state="TEAM_SELECT")
    return app


# {
#   責務: [test_layout_contains_labels_and_disjoint_controls_even_with_long_names: 長文と全会場で表示の収容・読込非発生を確認する]
#   処理: [1: 表示値を長い日本語へ置換する; 2: 描画時の文字とI/Oを監視する; 3: 領域・入力データ・再描画画像を照合する]
#   引数: [game: 独立アプリ; mode: 会場番号; monkeypatch: 試験中だけの差替え機能]
#   戻り値: [None: 領域外・重複・データ変更・ファイル走査は試験失敗。実GUI E2Eではない]
# }
@pytest.mark.parametrize("mode", range(3))
def test_layout_contains_labels_and_disjoint_controls_even_with_long_names(game, mode, monkeypatch):
    # 文字列の改行と長さを同時に厳しくし、元入力の非変更も比較する。
    game.venue_mode_index = mode
    for choice in game.team_choices:
        for key in ("name", "short", "manager", "tactic_label", "home_court"):
            choice[key] = "非常に長い日本語の表示項目\n" * 15
    before = deepcopy(game.team_choices)
    labels = []
    text = game.text

    # {
    #   責務: [checked_text: 通常描画の文字と矩形を採取し画面境界を検査する]
    #   処理: [1: 元の描画を実行する; 2: 結果を記録し画面内か照合する]
    #   引数: [value: 表示文字; args・kwargs: 通常の文字描画指定]
    #   戻り値: [Rect: 通常の描画結果。画面外ならAssertionError]
    # }
    def checked_text(value, *args, **kwargs):
        # 短縮文字列そのものと通常フォントによる結果を調べる。
        rect = text(value, *args, **kwargs)
        labels.append((value, rect))
        assert game.screen.get_rect().contains(rect), value
        return rect

    # {
    #   責務: [forbidden_io: 描画中のチーム走査やファイル状態参照を検出する]
    #   処理: [1: 呼出しを即座に試験失敗とする]
    #   引数: [args・kwargs: 禁止したPathメソッドの指定]
    #   戻り値: [戻らない: AssertionError。ファイル操作は実行しない]
    # }
    def forbidden_io(*args, **kwargs):
        # 描画処理のI/O再導入を見逃さない。
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
        next_index = i + 1
        assert all(not rect.colliderect(other) for other in controls[next_index:])
    assert len(game.team_select_buttons) == 11
    # 同じ入力の2フレーム目も同じピクセル・操作一覧になることを確認する。
    first_frame = pygame.image.tostring(game.screen, "RGB")
    game.draw_team_select()
    assert pygame.image.tostring(game.screen, "RGB") == first_frame


# {
#   責務: [test_same_team_notice_and_missing_manager_draw: 同チーム対戦と監督不在の案内を確認する]
#   処理: [1: 同じチームを両側へ選ぶ; 2: 描画文字から注意表示と監督不在表示を照合する]
#   引数: [game: 独立した準備画面のfixture]
#   戻り値: [None: 注意の欠落や不要な所属/操作チーム表示は試験失敗]
# }
def test_same_team_notice_and_missing_manager_draw(game):
    # 実データを変更せず、このfixtureだけ監督を空にする。
    game.away_choice_index = 0
    game.team_choices[0]["manager"] = ""
    labels = []
    original = game.text

    # {
    #   責務: [capture: 描画を維持したまま検査用の表示文字列を集める]
    #   処理: [1: 値を記録する; 2: 元の描画へ委譲する]
    #   引数: [value: 表示文字; args・kwargs: 文字描画の指定]
    #   戻り値: [Rect: 元の文字描画結果]
    # }
    def capture(value, *args, **kwargs):
        # 表示の実行自体を省略せず、案内だけを採取する。
        labels.append(value)
        return original(value, *args, **kwargs)

    game.text = capture
    game.draw_team_select()
    assert "同チーム対戦：AWAY側は青ユニフォーム" in labels
    assert "監督 —" in labels
    assert all("未所属" not in label and "操作チーム" not in label for label in labels)


# {
#   責務: [test_actual_rendered_controls_route_to_existing_selection_logic: 描画済みのチーム/会場ボタンと既存入力処理を接続確認する]
#   処理: [1: 通常画面を描く; 2: 操作IDから矩形を得てクリックする; 3: 両チーム/会場番号を照合する]
#   引数: [game: 独立アプリ; action: 操作ID; expected: 期待するHOME・AWAY・会場の番号]
#   戻り値: [None: 描画矩形と入力先がずれると試験失敗]
# }
@pytest.mark.parametrize(
    "action, expected",
    [
        ("home_prev", (1, 1, 0)),
        ("home_next", (1, 1, 0)),
        ("away_prev", (0, 0, 0)),
        ("away_next", (0, 0, 0)),
        ("venue_home", (0, 1, 0)),
        ("venue_neutral", (0, 1, 1)),
        ("venue_away", (0, 1, 2)),
    ],
)
def test_actual_rendered_controls_route_to_existing_selection_logic(game, action, expected):
    # 手書きの模擬矩形でなく、描画が登録した実領域をクリックする。
    game.draw_team_select()
    rect = next(rect for rect, value in game.team_select_buttons if value == action)
    game.handle_click(rect.center)
    assert (game.home_choice_index, game.away_choice_index, game.venue_mode_index) == expected


# {
#   責務: [test_rendered_navigation_invokes_the_existing_action: 準備画面からの遷移ボタンが既存入口を呼ぶことを確認する]
#   処理: [1: 呼出し先を記録用へ置換する; 2: 描画領域をクリックし操作を照合する]
#   引数: [game: 独立アプリ; action: 表示操作ID; method: 対応するGameメソッド名]
#   戻り値: [None: 別入口や重複呼出しは試験失敗。実エディタ/試合は起動しない]
# }
@pytest.mark.parametrize(
    "action, method",
    [
        ("start", "start_selected_match"),
        ("editor", "open_team_editor"),
        ("league", "open_league_screen"),
        ("main_menu", "return_to_main_menu"),
    ],
)
def test_rendered_navigation_invokes_the_existing_action(game, action, method):
    # 遷移先の副作用を避け、公開入力入口からの配線を調べる。
    called = []
    setattr(game, method, lambda: called.append(action))
    game.draw_team_select()
    rect = next(rect for rect, value in game.team_select_buttons if value == action)
    game.handle_click(rect.center)
    assert called == [action]


# {
#   責務: [test_fit_label_keeps_short_text_normalizes_newlines_and_bounds_ellipsis: 日本語ラベルの全文・改行・省略の境界を確認する]
#   処理: [1: 短い値と幅ゼロを検査する; 2: 複数の幅で省略記号と実測幅を照合する]
#   引数: [game: 実フォント取得用fixture]
#   戻り値: [None: 文字サイズを変えずに収容できなければ試験失敗]
# }
def test_fit_label_keeps_short_text_normalizes_newlines_and_bounds_ellipsis(game):
    # 文字数ではなくフォントの実測ピクセル幅で判定する。
    font = game.font(26, True)
    assert fit_label(font, "蜜柑山", 500) == "蜜柑山"
    assert fit_label(font, "蜜柑山\n学園", 500) == "蜜柑山 学園"
    assert fit_label(font, "チーム", 0) == ""
    for width in (20, 100, 280, 500):
        value = fit_label(font, "長いチーム名" * 100, width)
        assert value.endswith("…") or value == ""
        assert font.size(value)[0] <= width
