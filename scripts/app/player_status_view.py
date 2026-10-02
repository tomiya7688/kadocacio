"""Read-only presentation of both teams' on-pitch players."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from scripts.app.ui_theme import BACKGROUND, SURFACE, TEXT, MUTED, ACCENT, BORDER, fit_label
from scripts.core.settings import WIDTH, HEIGHT, TACTICS
from scripts.team import team_rating

if TYPE_CHECKING:
    from scripts.app.game_app import Game
    from scripts.match.player import Player
    from scripts.match.team import Team


class PlayerStatusView:
    """Render live roster status and category grades without changing the match."""

    def draw(self, game: Game) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((5, 10, 17, 208))
        game.screen.blit(shade, (0, 0))
        modal = pygame.Rect(32, 24, WIDTH - 64, HEIGHT - 48)
        pygame.draw.rect(game.screen, SURFACE, modal, border_radius=16)
        pygame.draw.rect(game.screen, BORDER, modal, 1, border_radius=16)
        self._header(game, modal)
        gap = 24
        width = (modal.width - 40 - gap) // 2
        for index, team in enumerate(game.match.teams):
            column = pygame.Rect(modal.x + 20 + index * (width + gap), modal.y + 88, width, 56)
            self._team(game, team, column)
            for row_index, player in enumerate(team.players):
                row = pygame.Rect(column.x, column.bottom + 8 + row_index * 46, column.width, 44)
                self._player(game, player, row, row_index)

    def _header(self, game: Game, modal: pygame.Rect) -> None:
        game.text("選手一覧", 23, TEXT, (modal.x + 20, modal.y + 17), bold=True)
        game.player_list_close_button = pygame.Rect(modal.right - 132, modal.y + 16, 112, 34)
        game.player_list_rank_button = pygame.Rect(modal.right - 328, modal.y + 16, 184, 34)
        self._button(game, game.player_list_close_button, "P / Tab  閉じる")
        label = "G  表示：能力ランク" if game.player_list_rank_mode else "G  表示：試合中状態"
        self._button(game, game.player_list_rank_button, label, active=game.player_list_rank_mode)
        if game.player_list_rank_mode:
            subtitle = " / ".join(f"{category.get('short', '?')}:{category.get('label', '')}"
                                  for category in team_rating.TUNER_CATEGORIES)
        else:
            subtitle = "ピッチ上の選手をリアルタイム表示中 · 一覧を開いても試合は進行します"
        self._label(game, subtitle, 12, MUTED, modal.x + 20, modal.y + 58, modal.width - 40)

    def _team(self, game: Game, team: Team, rect: pygame.Rect) -> None:
        pygame.draw.rect(game.screen, BACKGROUND, rect, border_radius=8)
        pygame.draw.rect(game.screen, team.primary, (rect.x, rect.y + 8, 4, rect.height - 16), border_radius=2)
        self._label(game, team.name.replace("_", " "), 17, TEXT, rect.x + 16, rect.y + 5,
                    rect.width - 32, bold=True)
        tactic = TACTICS.get(team.tactic, TACTICS["BALANCE"])["label"]
        self._label(game, f"{tactic} · 選手交代 {team.substitutions_used}/3", 12, MUTED,
                    rect.x + 16, rect.y + 32, rect.width - 32)

    def _player(self, game: Game, player: Player, row: pygame.Rect, index: int) -> None:
        owner = game.match.ball.owner is player
        color = (31, 57, 58) if owner else BACKGROUND if index % 2 == 0 else (28, 44, 53)
        pygame.draw.rect(game.screen, color, row, border_radius=6)
        if owner:
            pygame.draw.rect(game.screen, ACCENT, row, 1, border_radius=6)
            pygame.draw.circle(game.screen, ACCENT, (row.x + 8, row.y + 13), 3)
        self._label(game, f"{player.number:>2} {player.role}", 11, MUTED, row.x + 17, row.y + 6, 54, bold=True)
        self._label(game, player.name, 14, TEXT, row.x + 78, row.y + 3, row.width - 266, bold=True)
        if player.sent_off:
            game.text("退場", 11, (255, 135, 137), (row.right - 184, row.y + 6), bold=True)
        elif player.yellow_cards:
            game.text(f"黄{player.yellow_cards}", 11, (244, 207, 114), (row.right - 184, row.y + 6), bold=True)
        self._details(game, player, row)
        self._stamina(game, player, row)

    def _details(self, game: Game, player: Player, row: pygame.Rect) -> None:
        if game.player_list_rank_mode:
            text = team_rating.compact_entity_grade_text(player)
            self._label(game, text, 12, TEXT, row.x + 17, row.y + 25, row.width - 133, bold=True)
        else:
            self._label(game, player.player_type, 11, MUTED, row.x + 17, row.y + 26, 135)
            alert = max(player.alertness.items(), key=lambda item: item[1], default=(None, 0.0))[0]
            number = alert.number if alert is not None else "-"
            text = (f"忠{player.tactical_loyalty * 100:.0f} 自{player.confidence * 100:.0f} "
                    f"Z{player.zone_awareness * 100:.0f} P{player.position_awareness * 100:.0f} "
                    f"積{player.aggressiveness * 100:.0f} 警#{number}")
            self._label(game, text, 11, MUTED, row.x + 160, row.y + 26, row.width - 276)

    def _stamina(self, game: Game, player: Player, row: pygame.Rect) -> None:
        ratio = max(0.0, min(1.0, player.stamina_ratio))
        text = f"{player.stamina:.0f}/{player.stamina_max:.0f} · {ratio * 100:.0f}%"
        self._label(game, text, 11, TEXT, row.right - 148, row.y + 6, 136, bold=True)
        bar = pygame.Rect(row.right - 100, row.y + 29, 88, 6)
        pygame.draw.rect(game.screen, BORDER, bar, border_radius=3)
        fill = bar.copy()
        fill.width = round(bar.width * ratio)
        color = ACCENT if ratio > 0.5 else (244, 207, 114) if ratio > 0.25 else (255, 135, 137)
        if fill.width > 0:
            pygame.draw.rect(game.screen, color, fill, border_radius=3)

    @staticmethod
    def _label(game: Game, value: str, size: int, color: tuple[int, int, int],
               x: int, y: int, width: int, *, bold: bool = False) -> None:
        game.text(fit_label(game.font(size, bold), value, width), size, color, (x, y), bold=bold)

    @staticmethod
    def _button(game: Game, rect: pygame.Rect, label: str, *, active: bool = False) -> None:
        hover = rect.collidepoint(game.logical_mouse_pos())
        color = ACCENT if active else (35, 57, 65) if hover else BACKGROUND
        pygame.draw.rect(game.screen, color, rect, border_radius=7)
        pygame.draw.rect(game.screen, ACCENT if active else BORDER, rect, 1, border_radius=7)
        game.text(label, 12, BACKGROUND if active else TEXT, rect.center, center=True, bold=True)
