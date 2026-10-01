"""Presentation of the exhibition setup; no file access or match mutation."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from scripts.app.ui_theme import BACKGROUND, SURFACE, TEXT, MUTED, ACCENT, BORDER, fit_label
from scripts.core.settings import WIDTH, HEIGHT, darken_color
from scripts.core.stat_scale import denormalize_player_stat

if TYPE_CHECKING:
    from scripts.app.game_app import Game


class TeamSelectView:
    """Draw opposing team cards, their formation preview and setup controls."""

    @staticmethod
    def card_rects() -> tuple[pygame.Rect, pygame.Rect]:
        return pygame.Rect(48, 148, 548, 362), pygame.Rect(684, 148, 548, 362)

    def draw(self, game: Game) -> None:
        game.screen.fill(BACKGROUND)
        game.team_select_buttons.clear()
        self._header(game)
        home = game.team_choices[game.home_choice_index]
        away = game.team_choices[game.away_choice_index]
        for rect, choice, side, index in zip(
            self.card_rects(), (home, away), ("home", "away"),
            (game.home_choice_index, game.away_choice_index),
        ):
            self.draw_card(game, rect, choice, side, index)
        game.text("VS", 23, MUTED, (WIDTH // 2, 320), center=True, bold=True)
        if home["id"] == away["id"]:
            game.text("同チーム対戦：AWAY側は青ユニフォーム", 14, ACCENT, (48, 516))
        self._venue_controls(game, home, away)
        self._footer(game)

    @staticmethod
    def _header(game: Game) -> None:
        game.text("EXHIBITION / 試合テスト", 14, ACCENT, (48, 30), bold=True)
        game.text("対戦チームを選択", 32, TEXT, (48, 54), bold=True)
        game.text("両チームはAIでプレイします。編成と会場を確認して試合を開始。", 16, MUTED, (48, 100))
        game.text(f"選択可能 {len(game.team_choices)}チーム", 15, MUTED, (WIDTH - 48, 68), right=True)

    @staticmethod
    def _label(game: Game, value: str, size: int, color: tuple[int, int, int],
               x: int, y: int, width: int, *, bold: bool = False) -> None:
        label = fit_label(game.font(size, bold), value, width)
        game.text(label, size, color, (x, y), bold=bold)

    def draw_card(self, game: Game, rect: pygame.Rect, choice: dict, side: str, index: int) -> None:
        pygame.draw.rect(game.screen, SURFACE, rect, border_radius=14)
        pygame.draw.rect(game.screen, BORDER, rect, 1, border_radius=14)
        pygame.draw.rect(game.screen, choice["primary"], (rect.x + 24, rect.y + 22, 6, 18), border_radius=3)
        game.text(f"{side.upper()}側", 14, ACCENT, (rect.x + 40, rect.y + 22), bold=True)
        self._label(game, f"略称 {choice['short']}", 14, MUTED, rect.x + 244, rect.y + 22, 280)
        self._label(game, choice["name"].replace("_", " "), 26, TEXT,
                    rect.x + 24, rect.y + 48, rect.width - 48, bold=True)
        self._label(game, f"監督 {choice.get('manager') or '—'}", 15, MUTED,
                    rect.x + 24, rect.y + 89, rect.width - 48)
        self.draw_formation(game, choice, pygame.Rect(rect.x + 24, rect.y + 124, 196, 172))
        self._details(game, choice, rect)
        self._button(game, pygame.Rect(rect.x + 24, rect.bottom - 46, 42, 30), "‹", f"{side}_prev")
        self._button(game, pygame.Rect(rect.right - 66, rect.bottom - 46, 42, 30), "›", f"{side}_next")
        keys = "Q / E" if side == "home" else "A / D"
        game.text(f"{index + 1} / {len(game.team_choices)}　　{keys} で切替", 14, MUTED,
                  (rect.centerx, rect.bottom - 31), center=True)

    def _details(self, game: Game, choice: dict, rect: pygame.Rect) -> None:
        x, y, width = rect.x + 244, rect.y + 124, 280
        discipline = round(choice.get("tactical_discipline", 0.5) * 100)
        self._label(game, f"先発 {len(choice['starters'])}人  /  控え {len(choice.get('bench', []))}人",
                    17, TEXT, x, y, width, bold=True)
        self._label(game, f"戦術 {choice.get('tactic_label', 'バランス')}", 16, TEXT, x, y + 34, width)
        self._label(game, f"ゾーン {choice.get('zone_near', 3)}–{choice.get('zone_far', 7)}  /  忠実さ {discipline}",
                    15, MUTED, x, y + 61, width)
        game.text("監督能力：判断 / 戦術変更 / 交代", 14, MUTED, (x, y + 92))
        if choice.get("manager"):
            stats = [round(denormalize_player_stat(choice.get(key, default))) for key, default in (
                ("manager_intelligence", 0.542), ("manager_tactic_aggression", 0.375),
                ("manager_substitution_aggression", 0.375),
            )]
            game.text(" / ".join(map(str, stats)), 17, TEXT, (x, y + 115), bold=True)
        else:
            game.text("—", 17, MUTED, (x, y + 115))
        self._label(game, f"ホーム：{choice.get('home_court') or '—'}", 14, MUTED, x, y + 146, width)

    @staticmethod
    def draw_formation(game: Game, choice: dict, rect: pygame.Rect) -> None:
        pygame.draw.rect(game.screen, (24, 59, 53), rect, border_radius=8)
        field = rect.inflate(-24, -24)
        line = (77, 125, 107)
        pygame.draw.rect(game.screen, line, field, 1)
        pygame.draw.line(game.screen, line, (field.left, field.centery), (field.right, field.centery))
        pygame.draw.circle(game.screen, line, field.center, 22, 1)
        primary = choice["primary"]
        secondary = choice.get("secondary", darken_color(primary))
        number_color = BACKGROUND if sum(primary) > 420 else TEXT
        for record in choice["starters"]:
            if record["position_y"] == 11:
                nx, ny = 0.5, 0.94
            else:
                nx = (record["position_x"] - 0.5) / 15.0
                ny = 0.08 + (record["position_y"] - 1) / 9.0 * 0.75
            point = round(field.left + nx * field.width), round(field.top + ny * field.height)
            pygame.draw.circle(game.screen, secondary, point, 9)
            pygame.draw.circle(game.screen, primary, point, 7)
            game.text(str(record["number"]), 10, number_color, point, bold=True, center=True)

    @staticmethod
    def _button(game: Game, rect: pygame.Rect, label: str, action: str, *, active: bool = False) -> None:
        hovered = rect.collidepoint(game.logical_mouse_pos())
        color = ACCENT if active else (35, 57, 65) if hovered else SURFACE
        pygame.draw.rect(game.screen, color, rect, border_radius=8)
        pygame.draw.rect(game.screen, ACCENT if active else BORDER, rect, 1, border_radius=8)
        game.text(label, 15, BACKGROUND if active else TEXT, rect.center, center=True, bold=active)
        game.team_select_buttons.append((rect, action))

    def _venue_controls(self, game: Game, home: dict, away: dict) -> None:
        mode = game.venue_modes[game.venue_mode_index]
        game.text("会場", 17, TEXT, (48, 557), bold=True)
        for index, (key, label) in enumerate((("HOME", "HOMEのホーム"), ("NEUTRAL", "中立地"),
                                               ("AWAY", "AWAYのホーム"))):
            self._button(game, pygame.Rect(116 + index * 186, 548, 174, 40), label,
                         f"venue_{key.lower()}", active=mode == key)
        venue = "中立地" if mode == "NEUTRAL" else (home if mode == "HOME" else away).get("home_court", "—")
        self._label(game, f"開催地：{venue}", 14, MUTED, 116, 603, 670)
        self._button(game, pygame.Rect(876, 544, 356, 52), "この対戦で試合開始  →", "start", active=True)
        game.text("会場: V    開始: Enter / Space", 14, MUTED, (1054, 616), center=True)

    def _footer(self, game: Game) -> None:
        pygame.draw.line(game.screen, BORDER, (48, HEIGHT - 72), (WIDTH - 48, HEIGHT - 72))
        for x, width, label, action in ((48, 184, "← メインメニュー", "main_menu"),
                                       (248, 172, "チームエディタ", "editor"),
                                       (436, 156, "リーグ戦", "league")):
            self._button(game, pygame.Rect(x, HEIGHT - 48, width, 34), label, action)
        game.draw_settings_button(pygame.Rect(WIDTH - 232, HEIGHT - 48, 184, 34))
