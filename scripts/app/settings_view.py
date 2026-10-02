"""Shared settings presentation and focus; persistence stays in Game."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from scripts.app.ui_theme import BACKGROUND, SURFACE, TEXT, MUTED, ACCENT, BORDER, fit_label
from scripts.core.performance_settings import CPU_LIMIT_OPTIONS, LEAGUE_SIMULATION_MODES
from scripts.core.settings import HEIGHT, WIDTH

if TYPE_CHECKING:
    from scripts.app.game_app import Game


CARD = pygame.Rect(200, 24, 880, 672)
CPU_PANEL = pygame.Rect(224, 130, 832, 122)
QUALITY_PANEL = pygame.Rect(224, 264, 832, 170)
DISPLAY_PANEL = pygame.Rect(224, 446, 832, 138)


class SettingsView:
    """Display bounded settings controls with a single mouse/keyboard layout."""

    @staticmethod
    def buttons(game: Game) -> list[tuple[pygame.Rect, str]]:
        buttons = [(pygame.Rect(CARD.right - 60, 44, 36, 36), "close")]
        for index, value in enumerate(CPU_LIMIT_OPTIONS):
            buttons.append((pygame.Rect(240 + index * 160, 200, 152, 36), f"cpu:{value}"))
        for index, key in enumerate(LEAGUE_SIMULATION_MODES):
            buttons.append((pygame.Rect(240 + index * 200, 336, 192, 52), f"league_mode:{key}"))
        for index, action in enumerate(("window_size", "fullscreen", "gpu_rendering")):
            buttons.append((pygame.Rect(240 + index * 268, 498, 260, 64), action))
        actions = []
        if getattr(game, "league_auto_running", False):
            actions.append("auto_stop")
        if (getattr(game, "settings_previous_match_state", "") in ("PLAYING", "PAUSED")
                and game.match.state in ("PLAYING", "PAUSED")):
            actions.extend(("abort", "skip"))
        actions.append("close")
        for index, action in enumerate(actions):
            x = CARD.right - 224 if action == "close" else 224 + index * 208
            buttons.append((pygame.Rect(x, 640, 200, 40), action))
        return buttons

    def handle_key(self, game: Game, key: int, *, shift: bool = False) -> None:
        buttons = self.buttons(game)
        focus = getattr(game, "settings_focus", len(buttons) - 1) % len(buttons)
        if key == pygame.K_TAB:
            game.settings_focus = (focus + (-1 if shift else 1)) % len(buttons)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            game.handle_settings_action(buttons[focus][1])
        elif key == pygame.K_F10:
            game.handle_settings_action("window_size")
        elif key == pygame.K_F11:
            game.handle_settings_action("fullscreen")

    def draw(self, game: Game) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((5, 10, 17, 208))
        game.screen.blit(shade, (0, 0))
        pygame.draw.rect(game.screen, BACKGROUND, CARD, border_radius=18)
        pygame.draw.rect(game.screen, BORDER, CARD, 1, border_radius=18)
        pygame.draw.rect(game.screen, ACCENT, (224, 44, 4, 48), border_radius=2)
        game.text("SETTINGS", 12, ACCENT, (242, 43), bold=True)
        game.text("ゲーム設定", 28, TEXT, (240, 62), bold=True)
        game.text("設定は自動保存。Escまたは閉じるで元の画面へ戻ります", 13, MUTED, (224, 104))
        for panel in (CPU_PANEL, QUALITY_PANEL, DISPLAY_PANEL):
            pygame.draw.rect(game.screen, SURFACE, panel, border_radius=12)
            pygame.draw.rect(game.screen, BORDER, panel, 1, border_radius=12)
        self._explanations(game)
        game.settings_buttons = self.buttons(game)
        focus = getattr(game, "settings_focus", len(game.settings_buttons) - 1) % len(game.settings_buttons)
        mouse = game.logical_mouse_pos()
        for index, (rect, action) in enumerate(game.settings_buttons):
            label, subtitle, selected = self._label(game, action)
            self._button(game, rect, label, subtitle, selected, index == focus,
                         rect.collidepoint(mouse), action in ("abort", "auto_stop"))

    @staticmethod
    def _explanations(game: Game) -> None:
        game.text("CPU演算枠の上限", 18, TEXT, (240, 143), bold=True)
        value = int(getattr(game, "cpu_limit_percent", 100))
        game.text(f"現在 {value}%", 16, ACCENT, (1040, 147), right=True, bold=True)
        game.text("OSの使用率ではなく処理量の制限です。低い値ほど試合処理に時間がかかります。",
                  13, MUTED, (240, 174))
        game.text("リーグ戦の裏試合", 18, TEXT, (240, 277), bold=True)
        game.text("戦術AIの再判断頻度を変更。ボール・衝突は全モード共通の固定ステップです。",
                  13, MUTED, (240, 308))
        game.text("次に開始する裏試合から反映 / 判断間隔が短いほど高負荷 / 精密が標準", 13, MUTED, (240, 403))
        game.text("画面・描画", 18, TEXT, (240, 459), bold=True)
        backend = (f"現在の実行環境  |  演算: {game.compute_backend_name}"
                   f"  /  描画: {game.render_backend_name}  （GPUは描画用）")
        game.text(fit_label(game.font(13), backend, 832), 13, MUTED, (224, 595))
        game.text("Tab / Shift+Tabで選択   Enter / Spaceで実行   Escで戻る", 12, MUTED, (224, 618))

    @staticmethod
    def _label(game: Game, action: str) -> tuple[str, str, bool]:
        if action.startswith("cpu:"):
            value = int(action.split(":", 1)[1])
            return f"{value}%", "", value == int(getattr(game, "cpu_limit_percent", 100))
        if action.startswith("league_mode:"):
            key = action.split(":", 1)[1]
            profile = LEAGUE_SIMULATION_MODES[key]
            interval = float(profile["ai_rethink_multiplier"])
            return str(profile["label"]), f"AI判断間隔 {interval:.2f}×", key == game.league_simulation_mode
        if action == "window_size":
            width, height = game.current_window_size
            return f"{width} × {height}", "F10 ウィンドウサイズ / 16:9", False
        if action == "fullscreen":
            return "全画面 ON" if game.fullscreen else "全画面 OFF", "F11 表示モード", game.fullscreen
        if action == "gpu_rendering":
            enabled = game.performance_settings.gpu_rendering
            return "GPU描画 ON" if enabled else "GPU描画 OFF", "次回起動から反映", enabled
        labels = {"close": "閉じる", "abort": "試合を中断", "skip": "残りをスキップ", "auto_stop": "オート停止"}
        return labels[action], "", False

    @staticmethod
    def _button(game: Game, rect: pygame.Rect, label: str, subtitle: str, selected: bool,
                focused: bool, hovered: bool, danger: bool) -> None:
        fill = (74, 36, 45) if danger else (31, 82, 71) if selected else (29, 49, 57) if hovered else BACKGROUND
        pygame.draw.rect(game.screen, fill, rect, border_radius=8)
        edge = ACCENT if focused or selected else (193, 109, 116) if danger else BORDER
        pygame.draw.rect(game.screen, edge, rect, 2 if focused else 1, border_radius=8)
        if rect.width < 50 and label == "閉じる":
            label = "×"
        label = fit_label(game.font(16, True), label, rect.width - 20)
        y = rect.centery - 10 if subtitle else rect.centery
        game.text(label, 16, TEXT, (rect.centerx, y), bold=True, center=True)
        if subtitle:
            subtitle = fit_label(game.font(12), subtitle, rect.width - 20)
            game.text(subtitle, 12, MUTED, (rect.centerx, rect.centery + 14), center=True)
