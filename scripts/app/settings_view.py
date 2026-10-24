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


# {
#   責務: [SettingsView: 共通設定の描画とキーボード焦点を同じ操作配置で提供する]
#   フィールド: []
# }
class SettingsView:
    """Display bounded settings controls with a single mouse/keyboard layout."""

    # {
    #   責務: [buttons: 状況に応じて表示と入力で共用する設定操作領域を生成する]
    #   処理: [1: CPU・演算品質・画面の操作を配置; 2: 試合とオート状況に合う終了操作を追加]
    #   引数: [game: 設定と試合状況を提供するホスト]
    #   戻り値: [list: 画面領域とアクションIDの順序付き一覧]
    # }
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

    # {
    #   責務: [handle_key: 設定内だけの焦点移動と確定操作を処理する]
    #   処理: [1: 焦点を有効範囲へ正規化; 2: Tabで移動または確定・画面ショートカットを既存操作へ委譲]
    #   引数: [game: 入力ホスト; key: pygameキー; shift: 逆方向のTab指定]
    #   戻り値: [None: 焦点または既存設定操作を更新。背景の試合操作へ伝播しない]
    # }
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

    # {
    #   責務: [draw: 設定説明と共通操作配置を一つのモーダルへ描画する]
    #   処理: [1: カードと区分を描画; 2: 説明とボタン一覧を取得; 3: 選択・焦点・危険操作の表示を分ける]
    #   引数: [game: 描画とUI状態のホスト]
    #   戻り値: [None: 設定ボタン領域を更新。保存と試合変更は行わない]
    # }
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

    # {
    #   責務: [_explanations: CPU上限とAI頻度・描画の作用範囲を明示する]
    #   処理: [1: CPU演算枠の説明; 2: 裏試合判断頻度の説明; 3: 実バックエンドと操作案内を幅内に表示]
    #   引数: [game: 現在の設定とバックエンドを持つ描画ホスト]
    #   戻り値: [None: 設定値を変更せず説明を描画]
    # }
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

    # {
    #   責務: [_label: 設定操作IDを現在値に合う見出し・補足・選択状態へ変換する]
    #   処理: [1: CPU・判断頻度・画面操作を区別; 2: 現在値と操作説明を返す]
    #   引数: [game: 現在設定のホスト; action: buttonsで生成した操作ID]
    #   戻り値: [tuple: 見出し・補足説明・選択済みかの真偽値]
    # }
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

    # {
    #   責務: [_button: 状態が識別できる設定ボタンと幅内の文字を描画する]
    #   処理: [1: 危険・選択・hoverに合う色を決定; 2: 焦点の枠を描画; 3: 主文字と補足を省略・配置]
    #   引数: [game: 描画ホスト; rect: ボタン領域; label: 主文字; subtitle: 補足; selected: 選択済み; focused: キー焦点; hovered: マウス焦点; danger: 危険操作]
    #   戻り値: [None: 描画のみ。アクションは実行しない]
    # }
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
