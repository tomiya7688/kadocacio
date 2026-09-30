"""Main menu presentation; match state and navigation stay in Game."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from scripts.core.settings import HEIGHT, WIDTH

if TYPE_CHECKING:
    from scripts.app.game_app import Game


MENU_ACTIONS = ("league_start", "match_test", "team_editor", "league_editor")
SHORTCUT_ACTIONS = ("team_editor", "league_editor", "league_start", "match_test")
BACKGROUND = (12, 22, 29)
SURFACE = (23, 38, 47)
TEXT = (238, 244, 240)
MUTED = (169, 188, 190)
ACCENT = (126, 229, 187)
BORDER = (56, 78, 85)


class MainMenuView:
    """Draw the entry hub with a shared, keyboard-focusable card layout."""

    @staticmethod
    def buttons() -> list[tuple[pygame.Rect, str]]:
        bounds = ((48, 190, 728, 270), (796, 190, 436, 270),
                  (48, 530, 582, 116), (650, 530, 582, 116))
        return [(pygame.Rect(rect), action) for rect, action in zip(bounds, MENU_ACTIONS)]

    def draw(self, game: Game) -> None:
        game.screen.fill(BACKGROUND)
        self._header(game)
        game.main_menu_buttons = self.buttons()
        mouse = game.logical_mouse_pos()
        focus = getattr(game, "main_menu_focus", 0)
        for index, (rect, action) in enumerate(game.main_menu_buttons):
            self._card_surface(game.screen, rect, index == focus, rect.collidepoint(mouse))
            shortcut = SHORTCUT_ACTIONS.index(action) + 1
            badge = pygame.Rect(rect.right - 46, rect.top + 20, 26, 26)
            pygame.draw.rect(game.screen, BORDER, badge, border_radius=6)
            game.text(str(shortcut), 14, TEXT, badge.center, center=True, bold=True)
        self._season(game, game.main_menu_buttons[0][0])
        self._match_test(game, game.main_menu_buttons[1][0])
        self._editors(game)
        self._footer(game)

    @staticmethod
    def _card_surface(screen: pygame.Surface, rect: pygame.Rect, focused: bool, hovered: bool) -> None:
        pygame.draw.rect(screen, (29, 49, 57) if hovered else SURFACE, rect, border_radius=14)
        pygame.draw.rect(screen, ACCENT if focused else BORDER, rect,
                         2 if focused else 1, border_radius=14)

    @staticmethod
    def _header(game: Game) -> None:
        pygame.draw.rect(game.screen, ACCENT, (48, 38, 6, 62), border_radius=3)
        game.text("KADOCALCIO", 14, ACCENT, (72, 34), bold=True)
        game.text("カドカルチョ", 38, TEXT, (70, 57), bold=True)
        game.text("FOOTBALL SIMULATION", 14, MUTED, (WIDTH - 48, 56), right=True)
        pygame.draw.line(game.screen, BORDER, (48, 124), (WIDTH - 48, 124))
        game.text("プレイ", 20, TEXT, (48, 148), bold=True)
        game.text("シーズンを進める、または1試合を試す", 15, MUTED, (138, 152))

    def _season(self, game: Game, rect: pygame.Rect) -> None:
        x, y = rect.left + 28, rect.top + 28
        game.text("SEASON / リーグシミュレーション", 14, ACCENT, (x, y), bold=True)
        game.text("リーグ戦を開始", 32, TEXT, (x, y + 38), bold=True)
        game.text("新しいシーズンも、セーブの続きも。", 17, TEXT, (x, y + 98))
        game.text("大会と参加チームを選んでリーグを進行します。", 15, MUTED, (x, y + 128))
        button = pygame.Rect(x, rect.bottom - 62, 230, 38)
        pygame.draw.rect(game.screen, ACCENT, button, border_radius=8)
        game.text("新規 / セーブを選ぶ  →", 16, BACKGROUND, button.center, center=True, bold=True)
        self._pitch(game.screen, pygame.Rect(rect.right - 208, rect.top + 78, 174, 146))

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

    @staticmethod
    def _match_test(game: Game, rect: pygame.Rect) -> None:
        x, y = rect.left + 28, rect.top + 28
        game.text("EXHIBITION / 単体試合", 14, ACCENT, (x, y), bold=True)
        game.text("試合テスト", 28, TEXT, (x, y + 40), bold=True)
        game.text("2チームと会場を選んで対戦。", 17, TEXT, (x, y + 98))
        game.text("編成や戦術の動きを、すぐに確認できます。", 15, MUTED, (x, y + 128))
        game.text("対戦チームを選ぶ  →", 17, ACCENT, (x, rect.bottom - 52), bold=True)

    @staticmethod
    def _editors(game: Game) -> None:
        game.text("編集ツール", 20, TEXT, (48, 488), bold=True)
        game.text("チームと大会の初期データを整える", 15, MUTED, (190, 493))
        for index, (title, detail) in enumerate((
            ("チームエディタ", "選手・能力・ユニフォーム・フォーメーション"),
            ("リーグ戦エディタ", "大会・参加チーム・日程・テンプレート"),
        ), start=2):
            rect = game.main_menu_buttons[index][0]
            game.text(title, 23, TEXT, (rect.left + 26, rect.top + 22), bold=True)
            game.text(detail, 16, MUTED, (rect.left + 26, rect.top + 64))

    @staticmethod
    def _footer(game: Game) -> None:
        game.text("Tab / 矢印で選択    Enterで開く    1–4で直接開く", 14, MUTED, (48, HEIGHT - 38))
        game.draw_settings_button(pygame.Rect(WIDTH - 232, HEIGHT - 48, 184, 34))
