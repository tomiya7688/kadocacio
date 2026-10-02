"""Presentation of independent venues' latest live match information."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from scripts.app.ui_theme import BACKGROUND, SURFACE, TEXT, MUTED, ACCENT, BORDER, fit_label
from scripts.core.settings import WIDTH, HEIGHT
from scripts.league.league_live_view import (
    OTHER_MATCH_COLUMNS, OTHER_MATCH_VISIBLE_ROWS, clamp_other_match_scroll,
    other_match_max_scroll, visible_other_matches, merged_live_results,
)

if TYPE_CHECKING:
    from scripts.app.game_app import Game


class OtherMatchesView:
    """Render a scrollable venue grid without modifying its source snapshots."""

    def draw(self, game: Game) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((5, 10, 17, 208))
        game.screen.blit(shade, (0, 0))
        modal = pygame.Rect(32, 24, WIDTH - 64, HEIGHT - 48)
        pygame.draw.rect(game.screen, SURFACE, modal, border_radius=16)
        pygame.draw.rect(game.screen, BORDER, modal, 1, border_radius=16)
        self._header(game, modal)
        session = game.league_simulation_session
        source = list(session.live_status.values()) if session is not None else game.league_live_last_status
        statuses = merged_live_results(source, game.league_manager.last_results)
        game.other_matches_scroll = clamp_other_match_scroll(game.other_matches_scroll, len(statuses))
        game.other_matches_scroll_track = pygame.Rect(0, 0, 0, 0)
        game.other_matches_scroll_thumb = pygame.Rect(0, 0, 0, 0)
        if not statuses:
            game.text("同時開催の他の試合はありません", 17, MUTED, modal.center, center=True)
            return
        visible, first, last = visible_other_matches(statuses, game.other_matches_scroll)
        game.text(f"全{len(statuses)}試合 · 表示 {first + 1}～{last}", 12, TEXT,
                  (modal.right - 20, modal.y + 88), right=True, bold=True)
        grid = pygame.Rect(modal.x + 20, modal.y + 120, modal.width - 60, 508)
        gap = 8
        width = (grid.width - gap * (OTHER_MATCH_COLUMNS - 1)) // OTHER_MATCH_COLUMNS
        for index, status in enumerate(visible):
            column, row = index % OTHER_MATCH_COLUMNS, index // OTHER_MATCH_COLUMNS
            card = pygame.Rect(grid.x + column * (width + gap), grid.y + row * 57, width, 52)
            self._card(game, status, card)
        self._scrollbar(game, modal, grid, len(statuses))

    def _header(self, game: Game, modal: pygame.Rect) -> None:
        game.text("他会場の速報", 23, TEXT, (modal.x + 20, modal.y + 17), bold=True)
        game.other_matches_close_button = pygame.Rect(modal.right - 132, modal.y + 16, 112, 34)
        rect = game.other_matches_close_button
        hover = rect.collidepoint(game.logical_mouse_pos())
        pygame.draw.rect(game.screen, (35, 57, 65) if hover else BACKGROUND, rect, border_radius=7)
        pygame.draw.rect(game.screen, BORDER, rect, 1, border_radius=7)
        game.text("O  閉じる", 12, TEXT, rect.center, center=True, bold=True)
        session = game.league_simulation_session
        if session is None:
            subtitle = "同日開催の最新情報 · 各会場の時計とスコアを表示"
        else:
            if game.match.state == "FULLTIME":
                subtitle = "残りの試合を計算中 · 各会場の最新情報を表示"
            elif session.live_updates:
                subtitle = "観戦の進行ペースを基準に演算 · 各会場の時計は独立"
            else:
                subtitle = "各会場の試合を計算中 · 最新情報を表示"
            subtitle += f" · 並列処理 {session.worker_count}枠"
        self._label(game, subtitle, 12, MUTED, modal.x + 20, modal.y + 58, modal.width - 40)
        game.text("ホイール / ↑↓ / PageUp・PageDown / Home・End", 12, MUTED,
                  (modal.x + 20, modal.y + 88))

    def _card(self, game: Game, status: dict, rect: pygame.Rect) -> None:
        pygame.draw.rect(game.screen, BACKGROUND, rect, border_radius=7)
        pygame.draw.rect(game.screen, BORDER, rect, 1, border_radius=7)
        self._label(game, str(status.get("league", "")), 11, MUTED, rect.x + 10,
                    rect.y + 5, rect.width - 84, bold=True)
        if status.get("state") == "FULLTIME":
            clock = "終了"
        else:
            game_time = status.get("game_time")
            if game_time is None:
                game_time = float(status.get("minute", 0)) * 60.0
            game_time = max(0.0, min(5400.0, float(game_time)))
            clock = f"{int(game_time // 60):02d}:{int(game_time % 60):02d}"
        game.text(clock, 11, ACCENT, (rect.right - 10, rect.y + 5), right=True, bold=True)
        name_width = rect.width // 2 - 50
        self._label(game, str(status.get("home_name", "")), 12, TEXT, rect.x + 10,
                    rect.y + 29, name_width, bold=True)
        self._label(game, str(status.get("away_name", "")), 12, TEXT, rect.centerx + 40,
                    rect.y + 29, name_width, bold=True)
        game.text(f"{status.get('home_score', 0)} : {status.get('away_score', 0)}", 15, ACCENT,
                  (rect.centerx, rect.y + 36), center=True, bold=True)

    @staticmethod
    def _scrollbar(game: Game, modal: pygame.Rect, grid: pygame.Rect, count: int) -> None:
        maximum = other_match_max_scroll(count)
        track = pygame.Rect(modal.right - 24, grid.y, 8, grid.height)
        game.other_matches_scroll_track = track
        pygame.draw.rect(game.screen, BORDER, track, border_radius=4)
        if maximum:
            total_rows = maximum + OTHER_MATCH_VISIBLE_ROWS
            height = max(34, round(track.height * OTHER_MATCH_VISIBLE_ROWS / total_rows))
            y = track.y + round((track.height - height) * game.other_matches_scroll / maximum)
            thumb = pygame.Rect(track.x, y, track.width, height)
        else:
            thumb = track.copy()
        pygame.draw.rect(game.screen, ACCENT if maximum else MUTED, thumb, border_radius=4)
        game.other_matches_scroll_thumb = thumb

    @staticmethod
    def _label(game: Game, value: str, size: int, color: tuple[int, int, int],
               x: int, y: int, width: int, *, bold: bool = False) -> None:
        game.text(fit_label(game.font(size, bold), value, width), size, color, (x, y), bold=bold)
