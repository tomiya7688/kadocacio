"""Match information presentation using the shared UI theme."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from scripts.app.ui_theme import BACKGROUND, SURFACE, TEXT, MUTED, ACCENT, BORDER, fit_label
from scripts.core.settings import PANEL, SPEED_OPTIONS
from scripts.match.prediction_system import percentage_triplet

if TYPE_CHECKING:
    from scripts.app.game_app import Game


class MatchHudView:
    """Render the scoreboard, live statistics, recent log and viewing controls."""

    @staticmethod
    def _label(game: Game, value: str, size: int, color: tuple[int, int, int],
               x: int, y: int, width: int, *, bold: bool = False) -> None:
        game.text(fit_label(game.font(size, bold), value, width), size, color, (x, y), bold=bold)

    @staticmethod
    def _surface(game: Game, rect: pygame.Rect) -> None:
        pygame.draw.rect(game.screen, SURFACE, rect, border_radius=12)
        pygame.draw.rect(game.screen, BORDER, rect, 1, border_radius=12)

    def draw_scoreboard(self, game: Game) -> None:
        status = game.match.status_snapshot()
        board = pygame.Rect(PANEL.left // 2 - 235, 16, 470, 52)
        self._surface(game, board)
        self._label(game, status.home_short_name, 17, TEXT, board.x + 18, 32, 145, bold=True)
        self._label(game, status.away_short_name, 17, TEXT, board.x + 307, 32, 145, bold=True)
        game.text(f"{status.home_score} : {status.away_score}", 27, ACCENT, board.center, center=True, bold=True)
        clock = pygame.Rect(24, 16, 108, 52)
        self._surface(game, clock)
        minute = min(90, int(status.game_time // 60))
        second = 0 if minute >= 90 else int(status.game_time % 60)
        label = "HT" if status.banner == "HALF TIME" and status.banner_timer > 0 else f"{minute:02d}:{second:02d}"
        game.text(label, 21, TEXT, clock.center, center=True, bold=True)
        speed = pygame.Rect(PANEL.left - 156, 16, 132, 52)
        self._surface(game, speed)
        game.text(f"×{status.speed_multiplier}", 21, ACCENT, speed.center, center=True, bold=True)

    def draw_panel(self, game: Game) -> None:
        panel = pygame.Rect(PANEL.left, PANEL.top, PANEL.width, PANEL.height)
        self._surface(game, panel)
        self._teams(game, panel)
        self._speeds(game, panel)
        self._statistics(game, panel)
        self._log(game, panel)
        self._controls(game, panel)

    def draw_prediction(self, game: Game) -> None:
        rect = pygame.Rect(64, 78, PANEL.left - 128, 62)
        self._surface(game, rect)
        percentages = percentage_triplet(game.match.predicted_probabilities())
        labels = (game.match.home.name.replace("_", " "), "引き分け", game.match.away.name.replace("_", " "))
        column = (rect.width - 32) // 3
        for index, (name, percent) in enumerate(zip(labels, percentages)):
            x = rect.x + 16 + index * column
            self._label(game, name, 14, TEXT, x, rect.y + 7, column - 16, bold=True)
            game.text(f"{percent}%", 16, ACCENT, (x, rect.y + 30), bold=True)

    def _teams(self, game: Game, panel: pygame.Rect) -> None:
        x, y, width = panel.x + 16, panel.y, panel.width - 32
        game.text("試合情報", 18, TEXT, (x, y + 16), bold=True)
        for index, team in enumerate((game.match.home, game.match.away)):
            row_y = y + 46 + index * 24
            pygame.draw.rect(game.screen, team.primary, (x, row_y + 3, 5, 16), border_radius=2)
            side = "H" if index == 0 else "A"
            self._label(game, f"{side}  {team.name.replace('_', ' ')}", 15, TEXT, x + 12, row_y, width - 12, bold=True)
        coaches = f"監督 {game.match.home.manager or '—'} / {game.match.away.manager or '—'}"
        self._label(game, coaches, 13, MUTED, x, y + 96, width)
        self._label(game, f"会場 {game.match.venue_name}", 13, MUTED, x, y + 120, width)

    def _speeds(self, game: Game, panel: pygame.Rect) -> None:
        x, y = panel.x + 16, panel.y
        game.text("試合速度", 16, TEXT, (x, y + 148), bold=True)
        game.text("Fで切替", 13, MUTED, (panel.right - 16, y + 150), right=True)
        game.speed_buttons.clear()
        for index, speed in enumerate(SPEED_OPTIONS):
            rect = pygame.Rect(x + index * 46, y + 174, 42, 32)
            self._button(game, rect, f"×{speed}", active=game.match.speed_multiplier == speed)
            game.speed_buttons.append((rect, speed))
        pygame.draw.line(game.screen, BORDER, (x, y + 222), (panel.right - 16, y + 222))

    def _statistics(self, game: Game, panel: pygame.Rect) -> None:
        x, y, width = panel.x + 16, panel.y, panel.width - 32
        game.text("試合統計", 16, TEXT, (x, y + 226), bold=True)
        self._label(game, game.match.home.short_name, 13, MUTED, x + 90, y + 250, 85)
        self._label(game, game.match.away.short_name, 13, MUTED, x + 188, y + 250, 86)
        game.text("シュート", 14, MUTED, (x, y + 277))
        game.text(str(game.match.home.shots), 18, TEXT, (x + 128, y + 286), center=True, bold=True)
        game.text(str(game.match.away.shots), 18, TEXT, (x + 230, y + 286), center=True, bold=True)
        total = game.match.home.possession + game.match.away.possession
        share = game.match.home.possession / total if total else 0.5
        bar = pygame.Rect(x, y + 300, width, 10)
        pygame.draw.rect(game.screen, game.match.away.primary, bar, border_radius=4)
        if share > 0:
            home_bar = pygame.Rect(bar.x, bar.y, round(width * share), bar.height)
            pygame.draw.rect(game.screen, game.match.home.primary, home_bar, border_radius=4)
        home_percent = round(100 * share)
        game.text(f"支配率  {home_percent}%", 13, TEXT, (x, y + 314))
        game.text(f"{100 - home_percent}%", 13, TEXT, (panel.right - 16, y + 314), right=True)

    def _log(self, game: Game, panel: pygame.Rect) -> None:
        x = panel.x + 16
        game.text("試合ログ", 16, TEXT, (x, panel.y + 338), bold=True)
        for index, (minute, event) in enumerate(game.match.events):
            y = panel.y + 362 + index * 18
            if y + 18 > panel.bottom - 166:
                break
            game.text(f"{minute:02d}'", 13, ACCENT if index == 0 else MUTED, (x, y), bold=True)
            self._label(game, event, 13, TEXT, x + 38, y, panel.width - 70)

    @staticmethod
    def _button(game: Game, rect: pygame.Rect, label: str, *, active: bool = False) -> None:
        hover = rect.collidepoint(game.logical_mouse_pos())
        color = ACCENT if active else (35, 57, 65) if hover else BACKGROUND
        pygame.draw.rect(game.screen, color, rect, border_radius=7)
        pygame.draw.rect(game.screen, ACCENT if active else BORDER, rect, 1, border_radius=7)
        game.text(label, 13, BACKGROUND if active else TEXT, rect.center, center=True, bold=active)

    def _controls(self, game: Game, panel: pygame.Rect) -> None:
        x, width = panel.x + 16, panel.width - 32
        game.other_matches_button = pygame.Rect(0, 0, 0, 0)
        if game.active_league_fixture_id:
            game.other_matches_button = pygame.Rect(x, panel.bottom - 166, width, 30)
            self._button(game, game.other_matches_button, "O  他会場の経過")
        game.text(f"ズーム {round(game.camera_zoom * 100)}%", 14, TEXT, (x, panel.bottom - 119), bold=True)
        game.zoom_buttons.clear()
        for index, (step, label) in enumerate(((-1, "−"), (1, "＋"))):
            rect = pygame.Rect(panel.right - 100 + index * 44, panel.bottom - 126, 38, 32)
            self._button(game, rect, label)
            game.zoom_buttons.append((rect, step))
        game.draw_settings_button(pygame.Rect(x, panel.bottom - 86, width, 32))
        game.player_list_button = pygame.Rect(x, panel.bottom - 46, width, 32)
        self._button(game, game.player_list_button, "P / Tab  選手一覧・状態")
