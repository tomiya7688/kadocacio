"""Completed-match presentation and paging; simulation stays in Match."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from scripts.app.ui_theme import BACKGROUND, SURFACE, TEXT, MUTED, ACCENT, BORDER, fit_label
from scripts.app.fulltime_pagination import FulltimePagination
from scripts.core.settings import WIDTH, HEIGHT

if TYPE_CHECKING:
    from scripts.app.game_app import Game

SCORERS_PER_PAGE = 6
RESULTS_PER_PAGE = 5


class FulltimeView:
    """Display scores, statistics and paged records with explicit next actions."""

    def __init__(self) -> None:
        self.pagination = FulltimePagination()
        self.list_rects: dict[str, pygame.Rect] = {}

    def change_page(self, game: Game, section: str, step: int) -> None:
        self.pagination.bind(game.match)
        if section == "scorers":
            total, size = len(game.match.goal_scorers), SCORERS_PER_PAGE
        else:
            total, size = len(game.league_manager.last_results), RESULTS_PER_PAGE
        self.pagination.change(section, total, size, step)

    def handle_wheel(self, game: Game, step: int, pos: tuple[int, int]) -> None:
        for section, rect in self.list_rects.items():
            if rect.collidepoint(pos):
                self.change_page(game, section, step)
                return

    def draw(self, game: Game) -> None:
        self.pagination.bind(game.match)
        game.screen.fill(BACKGROUND)
        game.fulltime_buttons.clear()
        game.zoom_buttons.clear()
        game.speed_buttons.clear()
        game.other_matches_button = pygame.Rect(0, 0, 0, 0)
        game.text("FULL TIME / 試合終了", 14, ACCENT, (48, 28), bold=True)
        game.text("試合結果", 32, TEXT, (48, 52), bold=True)
        player_rect = pygame.Rect(WIDTH - 232, 46, 184, 34)
        self._button(game, player_rect, "P  選手一覧", "players")
        game.player_list_button = player_rect
        self._score(game)
        league = bool(game.active_league_fixture_id)
        scorer_rect = pygame.Rect(48, 300, 424 if league else 744, 300)
        self.list_rects = {"scorers": scorer_rect}
        self._scorers(game, scorer_rect)
        if league:
            results_rect = pygame.Rect(496, 300, 736, 300)
            self.list_rects["results"] = results_rect
            self._results(game, results_rect)
        else:
            self._single_match_note(game, pygame.Rect(816, 300, 416, 300))
        self._footer(game, league)

    @staticmethod
    def _card(game: Game, rect: pygame.Rect) -> None:
        pygame.draw.rect(game.screen, SURFACE, rect, border_radius=14)
        pygame.draw.rect(game.screen, BORDER, rect, 1, border_radius=14)

    @staticmethod
    def _label(game: Game, value: str, size: int, color: tuple[int, int, int],
               x: int, y: int, width: int, *, bold: bool = False) -> None:
        game.text(fit_label(game.font(size, bold), value, width), size, color, (x, y), bold=bold)

    def _score(self, game: Game) -> None:
        match = game.match
        self._card(game, pygame.Rect(48, 110, WIDTH - 96, 170))
        for team, x in ((match.home, 76), (match.away, 828)):
            pygame.draw.rect(game.screen, team.primary, (x, 140, 5, 22), border_radius=2)
            label = "HOME" if team is match.home else "AWAY"
            game.text(label, 14, MUTED, (x + 16, 142), bold=True)
            self._label(game, team.name, 25, TEXT, x, 175, 376, bold=True)
        game.text(f"{match.home.score}  :  {match.away.score}", 56, ACCENT, (640, 164), center=True, bold=True)
        winner = "ホームチーム勝利" if match.home.score > match.away.score else (
            "アウェーチーム勝利" if match.home.score < match.away.score else "引き分け")
        game.text(winner, 17, TEXT, (640, 216), center=True, bold=True)
        total = match.home.possession + match.away.possession
        share = round(100 * match.home.possession / total) if total else 50
        stats = f"シュート {match.home.shots} : {match.away.shots}     支配率 {share}% : {100 - share}%"
        game.text(stats, 15, MUTED, (640, 251), center=True)

    def _pager(self, game: Game, rect: pygame.Rect, section: str, total: int, size: int) -> None:
        pages = self.pagination.count(total, size)
        current = self.pagination.pages[section]
        start = current * size + 1 if total else 0
        end = min(total, (current + 1) * size)
        label = f"{start}–{end} / {total}件　 {current + 1} / {pages}ページ"
        game.text(label, 13, MUTED, (rect.centerx, rect.bottom - 29), center=True)
        self._button(game, pygame.Rect(rect.left + 18, rect.bottom - 46, 38, 30), "‹",
                     f"{section}_prev", enabled=current > 0)
        self._button(game, pygame.Rect(rect.right - 56, rect.bottom - 46, 38, 30), "›",
                     f"{section}_next", enabled=current + 1 < pages)

    def _scorers(self, game: Game, rect: pygame.Rect) -> None:
        self._card(game, rect)
        game.text("得点記録", 19, TEXT, (rect.x + 24, rect.y + 18), bold=True)
        scorers = game.match.goal_scorers
        self.pagination.change("scorers", len(scorers), SCORERS_PER_PAGE)
        offset = self.pagination.pages["scorers"] * SCORERS_PER_PAGE
        for index, (minute, name) in enumerate(scorers[offset:offset + SCORERS_PER_PAGE]):
            y = rect.y + 60 + index * 30
            game.text(f"{minute}'", 16, ACCENT, (rect.x + 24, y), bold=True)
            self._label(game, name, 16, TEXT, rect.x + 86, y, rect.width - 110)
        if not scorers:
            game.text("得点はありません", 16, MUTED, (rect.x + 24, rect.y + 70))
        self._pager(game, rect, "scorers", len(scorers), SCORERS_PER_PAGE)

    def _results(self, game: Game, rect: pygame.Rect) -> None:
        self._card(game, rect)
        game.text("同日開催の試合", 19, TEXT, (rect.x + 24, rect.y + 18), bold=True)
        session = game.league_simulation_session
        status = f"完了 {session.display_completed}/{session.total}" if session is not None else "全試合終了"
        game.text(status, 14, ACCENT, (rect.right - 24, rect.y + 22), right=True)
        results = game.league_manager.last_results
        self.pagination.change("results", len(results), RESULTS_PER_PAGE)
        offset = self.pagination.pages["results"] * RESULTS_PER_PAGE
        for index, result in enumerate(results[offset:offset + RESULTS_PER_PAGE]):
            y = rect.y + 60 + index * 38
            score = f"{result['home_score']} – {result['away_score']}"
            self._label(game, result["home_name"], 16, TEXT, rect.x + 24, y, 270)
            game.text(score, 16, ACCENT, (rect.centerx, y + 10), center=True, bold=True)
            self._label(game, result["away_name"], 16, TEXT, rect.x + 414, y, rect.width - 438)
            details = str(result["league"])
            if result.get("home_penalties") is not None:
                details += f"　PK {result['home_penalties']} – {result['away_penalties']}"
            if result.get("watched"):
                details += "　観戦試合"
            self._label(game, details, 12, MUTED, rect.x + 24, y + 20, rect.width - 48)
        if not results:
            game.text("他会場の結果を待っています" if session else "同日の試合はありません",
                      16, MUTED, (rect.x + 24, rect.y + 70))
        self._pager(game, rect, "results", len(results), RESULTS_PER_PAGE)

    def _single_match_note(self, game: Game, rect: pygame.Rect) -> None:
        self._card(game, rect)
        game.text("次の試合へ", 22, TEXT, (rect.x + 24, rect.y + 22), bold=True)
        for index, line in enumerate(("再戦では同じ2チームで", "新しい試合を開始します。", "チーム選択に戻ると", "対戦相手や会場を変更できます。")):
            game.text(line, 17, MUTED, (rect.x + 24, rect.y + 78 + index * 34))

    @staticmethod
    def _button(game: Game, rect: pygame.Rect, label: str, action: str,
                *, primary: bool = False, enabled: bool = True) -> None:
        hovered = enabled and rect.collidepoint(game.logical_mouse_pos())
        color = ACCENT if primary and enabled else (35, 57, 65) if hovered else SURFACE
        pygame.draw.rect(game.screen, color, rect, border_radius=8)
        pygame.draw.rect(game.screen, ACCENT if primary and enabled else BORDER, rect, 1, border_radius=8)
        text_color = BACKGROUND if primary and enabled else TEXT if enabled else MUTED
        game.text(label, 15, text_color, rect.center, center=True, bold=primary)
        if enabled:
            game.fulltime_buttons.append((rect, action))

    def _footer(self, game: Game, league: bool) -> None:
        ready = game.league_simulation_session is None
        if league:
            label = "リーグ結果・成績へ  →" if ready else "他会場の試合を計算中"
            self._button(game, pygame.Rect(48, HEIGHT - 76, 290, 46), label,
                         "league_results", primary=True, enabled=ready)
            self._button(game, pygame.Rect(356, HEIGHT - 76, 184, 46), "O  他会場の経過", "other_matches")
            note = "T / Enter / Space：リーグ画面へ" if ready else "全試合の完了後に移動できます"
        else:
            self._button(game, pygame.Rect(48, HEIGHT - 76, 184, 46), "R  再戦", "rematch")
            self._button(game, pygame.Rect(248, HEIGHT - 76, 268, 46), "チーム選択へ戻る  →", "team_select", primary=True)
            note = "T / Enter / Space：チーム選択へ"
        game.text(note, 13, MUTED, (48, HEIGHT - 20))
        game.draw_settings_button(pygame.Rect(WIDTH - 232, HEIGHT - 76, 184, 46))
