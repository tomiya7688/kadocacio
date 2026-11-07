"""Main menu presentation; match state and navigation stay in Game."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from scripts.core.settings import HEIGHT, WIDTH
from scripts.app.ui_theme import BACKGROUND, SURFACE, TEXT, MUTED, ACCENT, BORDER

if TYPE_CHECKING:
    from scripts.app.game_app import Game


MENU_ACTIONS = ("league_start", "match_test", "team_editor", "league_editor")
SHORTCUT_ACTIONS = ("team_editor", "league_editor", "league_start", "match_test")


# {
#   責務: [MainMenuView: 起動画面のカード・案内・設定入口を描画し、入力用の矩形を公開する]
#   フィールド: []
# }
class MainMenuView:
    """Draw the entry hub with a shared, keyboard-focusable card layout."""

    # {
    #   責務: [buttons: 表示順と一致するメニューの当たり判定を返す]
    #   処理: [1: 論理画面上の4矩形へ操作IDを対応付ける]
    #   引数: []
    #   戻り値: [list: 呼出しごとに独立したRectと操作ID。数字キーの順序とは区別する]
    # }
    @staticmethod
    def buttons() -> list[tuple[pygame.Rect, str]]:
        # 表示とクリック処理が同じ配置を参照する。
        bounds = ((48, 190, 728, 270), (796, 190, 436, 270), (48, 530, 582, 116), (650, 530, 582, 116))
        return [(pygame.Rect(rect), action) for rect, action in zip(bounds, MENU_ACTIONS)]

    # {
    #   責務: [draw: 起動画面を構成し、描画したカードの入力領域をGameへ渡す]
    #   処理: [1: 背景・見出しを描く; 2: フォーカスとポインタを各カードへ反映する; 3: 案内と設定入口を描く]
    #   引数: [game: 描画先・テキスト描画・論理入力座標を提供するアプリ]
    #   戻り値: [None: screen・main_menu_buttons・設定ボタン領域を更新する。画面遷移や保存はしない]
    # }
    def draw(self, game: Game) -> None:
        # 起動メニューの背景と見出しを描く。
        game.screen.fill(BACKGROUND)
        self._header(game)
        # 入力領域をこのフレームの表示配置へ揃える。
        game.main_menu_buttons = self.buttons()
        mouse = game.logical_mouse_pos()
        focus = getattr(game, "main_menu_focus", 0)
        for index, (rect, action) in enumerate(game.main_menu_buttons):
            self._card_surface(game.screen, rect, index == focus, rect.collidepoint(mouse))
            shortcut = SHORTCUT_ACTIONS.index(action) + 1
            badge = pygame.Rect(rect.right - 46, rect.top + 20, 26, 26)
            pygame.draw.rect(game.screen, BORDER, badge, border_radius=6)
            game.text(str(shortcut), 14, TEXT, badge.center, center=True, bold=True)
        # 個別カードの説明と、画面共通の下部案内を重ねる。
        self._season(game, game.main_menu_buttons[0][0])
        self._match_test(game, game.main_menu_buttons[1][0])
        self._editors(game)
        self._footer(game)

    # {
    #   責務: [_card_surface: 選択状態とポインタ位置をカード面へ反映する]
    #   処理: [1: 面と枠を描く]
    #   引数: [screen: 描画先; rect: カード矩形; focused: キー選択中か; hovered: ポインタが内側か]
    #   戻り値: [None: 指定Surfaceだけを描き換える]
    # }
    @staticmethod
    def _card_surface(screen: pygame.Surface, rect: pygame.Rect, focused: bool, hovered: bool) -> None:
        # 選択枠とホバー面を別々に示す。
        pygame.draw.rect(screen, (29, 49, 57) if hovered else SURFACE, rect, border_radius=14)
        pygame.draw.rect(screen, ACCENT if focused else BORDER, rect, 2 if focused else 1, border_radius=14)

    # {
    #   責務: [_header: 起動画面のタイトルとプレイ欄の見出しを描く]
    #   処理: [1: タイトル・区切り・案内を論理画面へ配置する]
    #   引数: [game: 描画先とテキスト描画を提供するアプリ]
    #   戻り値: [None: screenへ描画する。入力領域は追加しない]
    # }
    @staticmethod
    def _header(game: Game) -> None:
        # 固定の論理画面座標へタイトルと見出しを配置する。
        pygame.draw.rect(game.screen, ACCENT, (48, 38, 6, 62), border_radius=3)
        game.text("KADOCALCIO", 14, ACCENT, (72, 34), bold=True)
        game.text("カドカルチョ", 38, TEXT, (70, 57), bold=True)
        game.text("FOOTBALL SIMULATION", 14, MUTED, (WIDTH - 48, 56), right=True)
        pygame.draw.line(game.screen, BORDER, (48, 124), (WIDTH - 48, 124))
        game.text("プレイ", 20, TEXT, (48, 148), bold=True)
        game.text("シーズンを進める、または1試合を試す", 15, MUTED, (138, 152))

    # {
    #   責務: [_season: リーグ開始カードの説明とピッチ装飾を描く]
    #   処理: [1: カード内の説明を配置する; 2: 開始案内と装飾を描く]
    #   引数: [game: 描画機能; rect: リーグカードの領域]
    #   戻り値: [None: screenへ描画する。カード内の案内は独立したボタンとして登録しない]
    # }
    def _season(self, game: Game, rect: pygame.Rect) -> None:
        # 全体が一つの操作カードであり、内側の案内と入力矩形を重複登録しない。
        x, y = rect.left + 28, rect.top + 28
        game.text("SEASON / リーグシミュレーション", 14, ACCENT, (x, y), bold=True)
        game.text("リーグ戦を開始", 32, TEXT, (x, y + 38), bold=True)
        game.text("新しいシーズンも、セーブの続きも。", 17, TEXT, (x, y + 98))
        game.text("大会と参加チームを選んでリーグを進行します。", 15, MUTED, (x, y + 128))
        button = pygame.Rect(x, rect.bottom - 62, 230, 38)
        pygame.draw.rect(game.screen, ACCENT, button, border_radius=8)
        game.text("新規 / セーブを選ぶ  →", 16, BACKGROUND, button.center, center=True, bold=True)
        self._pitch(game.screen, pygame.Rect(rect.right - 208, rect.top + 78, 174, 146))

    # {
    #   責務: [_pitch: メニューの装飾用ピッチを画像読込なしで描く]
    #   処理: [1: 面と白線に相当する図形を描く; 2: 固定位置の点を置く]
    #   引数: [screen: 描画先; rect: 装飾領域]
    #   戻り値: [None: Surfaceへ描画する。試合状態や乱数は使わない]
    # }
    @staticmethod
    def _pitch(screen: pygame.Surface, rect: pygame.Rect) -> None:
        # Code-native decoration: no image loading or per-frame alpha surfaces.
        pygame.draw.rect(screen, (24, 59, 53), rect, border_radius=8)
        field = rect.inflate(-22, -22)
        line = (77, 125, 107)
        pygame.draw.rect(screen, line, field, 1)
        pygame.draw.line(screen, line, (field.centerx, field.top), (field.centerx, field.bottom))
        pygame.draw.circle(screen, line, field.center, 23, 1)
        for x in (field.left, field.right - 20):
            pygame.draw.rect(screen, line, (x, field.centery - 27, 20, 54), 1)
        for dx, dy in ((28, 28), (54, 84), (100, 42), (130, 94)):
            pygame.draw.circle(screen, ACCENT, (rect.x + dx, rect.y + dy), 4)

    # {
    #   責務: [_match_test: 単体試合カードに対戦準備の案内を描く]
    #   処理: [1: カード内へ見出し・説明・開始案内を配置する]
    #   引数: [game: テキスト描画機能; rect: 単体試合カードの領域]
    #   戻り値: [None: screenへ描画する。試合を構築しない]
    # }
    @staticmethod
    def _match_test(game: Game, rect: pygame.Rect) -> None:
        # カードの余白を基準に、入力案内まで同じ領域へ収める。
        x, y = rect.left + 28, rect.top + 28
        game.text("EXHIBITION / 単体試合", 14, ACCENT, (x, y), bold=True)
        game.text("試合テスト", 28, TEXT, (x, y + 40), bold=True)
        game.text("2チームと会場を選んで対戦。", 17, TEXT, (x, y + 98))
        game.text("編成や戦術の動きを、すぐに確認できます。", 15, MUTED, (x, y + 128))
        game.text("対戦チームを選ぶ  →", 17, ACCENT, (x, rect.bottom - 52), bold=True)

    # {
    #   責務: [_editors: 下段のチーム・リーグ編集カードへ用途を表示する]
    #   処理: [1: 編集欄の見出しを描く; 2: 登録済みの下段カードへ説明を置く]
    #   引数: [game: 表示順に構築済みのmain_menu_buttonsを持つアプリ]
    #   戻り値: [None: screenだけを更新する。エディタ起動やファイル操作は行わない]
    # }
    @staticmethod
    def _editors(game: Game) -> None:
        # 下段カードの矩形はbuttons()と共有する。
        game.text("編集ツール", 20, TEXT, (48, 488), bold=True)
        game.text("チームと大会の初期データを整える", 15, MUTED, (190, 493))
        for index, (title, detail) in enumerate(
            (
                ("チームエディタ", "選手・能力・ユニフォーム・フォーメーション"),
                ("リーグ戦エディタ", "大会・参加チーム・日程・テンプレート"),
            ),
            start=2,
        ):
            rect = game.main_menu_buttons[index][0]
            game.text(title, 23, TEXT, (rect.left + 26, rect.top + 22), bold=True)
            game.text(detail, 16, MUTED, (rect.left + 26, rect.top + 64))

    # {
    #   責務: [_footer: キーボード案内と共通設定の入口を表示する]
    #   処理: [1: 下端に操作説明を描く; 2: 設定ボタンの描画・領域登録を委譲する]
    #   引数: [game: テキストと設定ボタンの描画機能]
    #   戻り値: [None: screenと設定ボタン領域を更新する]
    # }
    @staticmethod
    def _footer(game: Game) -> None:
        # 設定入口をカード群と重ならない共通位置へ置く。
        game.text("Tab / 矢印で選択    Enterで開く    1–4で直接開く", 14, MUTED, (48, HEIGHT - 38))
        game.draw_settings_button(pygame.Rect(WIDTH - 232, HEIGHT - 48, 184, 34))
