"""Layout contracts without starting a match or reading/writing league saves."""

import pygame
import pytest

from scripts.app.game_app import Game
from scripts.app.main_menu_view import MainMenuView, MENU_ACTIONS
from scripts.core.settings import HEIGHT, WIDTH


# {
#   責務: [test_menu_hitboxes_are_contained_and_disjoint: 起動カードの表示順・画面内配置・非重複を確認する]
#   処理: [1: 共通矩形一覧を得る; 2: 操作ID順と矩形の境界を照合する]
#   引数: []
#   戻り値: [None: 順序変更・画面外・カード重複は試験失敗]
# }
def test_menu_hitboxes_are_contained_and_disjoint():
    # 描画とは独立に、入力の基本配置を確認する。
    buttons = MainMenuView.buttons()
    assert tuple(action for _, action in buttons) == MENU_ACTIONS
    screen = pygame.Rect(0, 0, WIDTH, HEIGHT)
    for index, (rect, _) in enumerate(buttons):
        assert screen.contains(rect)
        next_index = index + 1
        assert all(not rect.colliderect(other) for other, _ in buttons[next_index:])


# {
#   責務: [test_menu_draw_preserves_text_bounds_focus_and_hitboxes: 全フォーカスで文字・領域・再描画の不変性を確認する]
#   処理: [1: メモリSurface上に起動画面を描く; 2: 文字の画面/カード内配置を照合する; 3: 焦点と再描画画像の一致を確認する]
#   引数: [focus: pytestが渡す選択カード番号0〜3]
#   戻り値: [None: 表示のはみ出し・設定との重複・描画による焦点変更は試験失敗。実GUI入力の検証ではない]
# }
@pytest.mark.parametrize("focus", range(4))
def test_menu_draw_preserves_text_bounds_focus_and_hitboxes(focus):
    # 実ウィンドウを作らず通常の描画入口を呼ぶ。
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

    # {
    #   責務: [checked_text: 通常の文字描画結果を記録し画面境界を監視する]
    #   処理: [1: 元の描画を呼ぶ; 2: 文字と矩形を記録し画面内か確認する]
    #   引数: [args・kwargs: Game.textへ渡された描画指定]
    #   戻り値: [Rect: 元の描画矩形。画面外ならAssertionError]
    # }
    def checked_text(*args, **kwargs):
        # 計測用の描画へ置換せず、通常フォントの結果を使う。
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
    # 同じ入力の再描画で、領域登録やピクセルが変わらないことを確認する。
    first_frame = pygame.image.tostring(game.screen, "RGB")
    game.draw_title()
    assert pygame.image.tostring(game.screen, "RGB") == first_frame
