"""Presentation of the exhibition setup; no file access or match mutation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from scripts.app.ui_theme import BACKGROUND, SURFACE, TEXT, MUTED, ACCENT, BORDER, fit_label
from scripts.core.settings import WIDTH, HEIGHT, darken_color
from scripts.core.stat_scale import denormalize_player_stat

if TYPE_CHECKING:
    from scripts.app.game_app import Game


# {
#   責務: [TeamSelectView: 読込済みの対戦チーム・編成・会場を表示し、準備画面の入力領域を登録する]
#   フィールド: []
# }
class TeamSelectView:
    """Draw opposing team cards, their formation preview and setup controls."""

    # {
    #   責務: [card_rects: 両側のチームカードの表示領域を返す]
    #   処理: [1: 固定論理画面の左右2矩形を生成する]
    #   引数: []
    #   戻り値: [tuple: HOME・AWAY順の独立したRect]
    # }
    @staticmethod
    def card_rects() -> tuple[pygame.Rect, pygame.Rect]:
        # 描画と領域試験で同じ配置を使う。
        return pygame.Rect(48, 148, 548, 362), pygame.Rect(684, 148, 548, 362)

    # {
    #   責務: [draw: 対戦準備画面を構成し、そのフレームの入力領域を公開する]
    #   処理: [1: 旧ボタンを消し見出しを描く; 2: 選択中の両チームを表示する; 3: 会場と移動先の操作を描く]
    #   引数: [game: 有効な選択番号と読込済みteam_choicesを持つアプリ]
    #   戻り値: [None: screen・team_select_buttons・設定ボタン領域を更新する。チームデータを読み直さない]
    # }
    def draw(self, game: Game) -> None:
        # 前のフレームの矩形を残さず、既存のメモリ入力だけを表示する。
        game.screen.fill(BACKGROUND)
        game.team_select_buttons.clear()
        self._header(game)
        home = game.team_choices[game.home_choice_index]
        away = game.team_choices[game.away_choice_index]
        for rect, choice, side, index in zip(
            self.card_rects(),
            (home, away),
            ("home", "away"),
            (game.home_choice_index, game.away_choice_index),
        ):
            self.draw_card(game, rect, choice, side, index)
        game.text("VS", 23, MUTED, (WIDTH // 2, 320), center=True, bold=True)
        if home["id"] == away["id"]:
            game.text("同チーム対戦：AWAY側は青ユニフォーム", 14, ACCENT, (48, 516))
        # 同チームの注意を含め、対戦条件と遷移操作を表示する。
        self._venue_controls(game, home, away)
        self._footer(game)

    # {
    #   責務: [_header: 対戦準備の見出しと選択可能なチーム数を示す]
    #   処理: [1: 固定の案内とメモリ上の件数を描く]
    #   引数: [game: テキスト描画機能とteam_choices]
    #   戻り値: [None: screenへ描画する]
    # }
    @staticmethod
    def _header(game: Game) -> None:
        # 件数はファイル走査ではなく、既に読み込んだ一覧から得る。
        game.text("EXHIBITION / 試合テスト", 14, ACCENT, (48, 30), bold=True)
        game.text("対戦チームを選択", 32, TEXT, (48, 54), bold=True)
        game.text("両チームはAIでプレイします。編成と会場を確認して試合を開始。", 16, MUTED, (48, 100))
        game.text(f"選択可能 {len(game.team_choices)}チーム", 15, MUTED, (WIDTH - 48, 68), right=True)

    # {
    #   責務: [_label: 長い表示値を指定幅に収めて描く]
    #   処理: [1: フォント実測に基づき省略する; 2: 同じサイズ・太さで描画する]
    #   引数: [game: フォント/描画機能; value: 表示値; size・color: 文字設定; x・y・width: 領域; bold: 太字か]
    #   戻り値: [None: screenへ描画する。元の表示値は変更しない]
    # }
    @staticmethod
    def _label(
        game: Game, value: str, size: int, color: tuple[int, int, int], x: int, y: int, width: int, *, bold: bool = False
    ) -> None:
        # 表示用の短縮値だけを作り、チーム名等を上書きしない。
        label = fit_label(game.font(size, bold), value, width)
        game.text(label, size, color, (x, y), bold=bold)

    # {
    #   責務: [draw_card: 一方のチーム情報と切替操作をカード内へ配置する]
    #   処理: [1: 色と名前・監督を描く; 2: 編成プレビューと詳細を委譲する; 3: 前後切替とキー案内を登録する]
    #   引数: [game: アプリ; rect: カード領域; choice: 読込済みチーム; side: home/awayの操作ID接頭辞; index: 選択番号]
    #   戻り値: [None: screenとteam_select_buttonsを更新する。choiceは変更しない]
    # }
    def draw_card(self, game: Game, rect: pygame.Rect, choice: dict, side: str, index: int) -> None:
        # 強調色以外の表示文字は、カード幅を超えないよう省略する。
        pygame.draw.rect(game.screen, SURFACE, rect, border_radius=14)
        pygame.draw.rect(game.screen, BORDER, rect, 1, border_radius=14)
        pygame.draw.rect(game.screen, choice["primary"], (rect.x + 24, rect.y + 22, 6, 18), border_radius=3)
        game.text(f"{side.upper()}側", 14, ACCENT, (rect.x + 40, rect.y + 22), bold=True)
        self._label(game, f"略称 {choice['short']}", 14, MUTED, rect.x + 244, rect.y + 22, 280)
        self._label(game, choice["name"].replace("_", " "), 26, TEXT, rect.x + 24, rect.y + 48, rect.width - 48, bold=True)
        self._label(game, f"監督 {choice.get('manager') or '—'}", 15, MUTED, rect.x + 24, rect.y + 89, rect.width - 48)
        # プレビューとチーム詳細は各担当へ渡す。
        self.draw_formation(game, choice, pygame.Rect(rect.x + 24, rect.y + 124, 196, 172))
        self._details(game, choice, rect)
        # HOME/AWAYを含む操作IDを登録し、実際の切替はGameへ任せる。
        self._button(game, pygame.Rect(rect.x + 24, rect.bottom - 46, 42, 30), "‹", f"{side}_prev")
        self._button(game, pygame.Rect(rect.right - 66, rect.bottom - 46, 42, 30), "›", f"{side}_next")
        keys = "Q / E" if side == "home" else "A / D"
        game.text(
            f"{index + 1} / {len(game.team_choices)}　　{keys} で切替",
            14,
            MUTED,
            (rect.centerx, rect.bottom - 31),
            center=True,
        )

    # {
    #   責務: [_details: 選手数・戦術・監督能力・ホーム会場を表示する]
    #   処理: [1: 編成と戦術を描く; 2: 監督がいれば能力値を編集スケールへ戻す; 3: 会場を表示する]
    #   引数: [game: 描画機能; choice: 正規化済みのチーム情報; rect: カード領域]
    #   戻り値: [None: screenへ描画する。監督不在時は能力欄をダッシュで示す]
    # }
    def _details(self, game: Game, choice: dict, rect: pygame.Rect) -> None:
        # 忠実さは0..100表示、監督能力は能力スケールの正本で逆変換する。
        x, y, width = rect.x + 244, rect.y + 124, 280
        discipline = round(choice.get("tactical_discipline", 0.5) * 100)
        self._label(
            game,
            f"先発 {len(choice['starters'])}人  /  控え {len(choice.get('bench', []))}人",
            17,
            TEXT,
            x,
            y,
            width,
            bold=True,
        )
        self._label(game, f"戦術 {choice.get('tactic_label', 'バランス')}", 16, TEXT, x, y + 34, width)
        self._label(
            game,
            f"ゾーン {choice.get('zone_near', 3)}–{choice.get('zone_far', 7)}  /  忠実さ {discipline}",
            15,
            MUTED,
            x,
            y + 61,
            width,
        )
        game.text("監督能力：判断 / 戦術変更 / 交代", 14, MUTED, (x, y + 92))
        if choice.get("manager"):
            stats = [
                round(denormalize_player_stat(choice.get(key, default)))
                for key, default in (
                    ("manager_intelligence", 0.542),
                    ("manager_tactic_aggression", 0.375),
                    ("manager_substitution_aggression", 0.375),
                )
            ]
            game.text(" / ".join(map(str, stats)), 17, TEXT, (x, y + 115), bold=True)
        else:
            game.text("—", 17, MUTED, (x, y + 115))
        self._label(game, f"ホーム：{choice.get('home_court') or '—'}", 14, MUTED, x, y + 146, width)

    # {
    #   責務: [draw_formation: 先発の15×10配置と中央固定GKをプレビューする]
    #   処理: [1: 装飾ピッチを描く; 2: 各先発の配置を領域内座標へ写し背番号を表示する]
    #   引数: [game: 描画機能; choice: 正規化済みのstartersと色; rect: プレビュー領域]
    #   戻り値: [None: screenだけを更新する。ポジションや先発を変更しない]
    # }
    @staticmethod
    def draw_formation(game: Game, choice: dict, rect: pygame.Rect) -> None:
        # 試合演算を動かさず、保存済みのポジションを図形へ写す。
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

    # {
    #   責務: [_button: 準備画面の操作ボタンを描き入力領域へ登録する]
    #   処理: [1: 選択中/ホバーの見た目を描く; 2: 矩形と操作IDを追加する]
    #   引数: [game: 描画とボタン一覧; rect: 入力領域; label: 表示文字; action: 操作ID; active: 強調状態]
    #   戻り値: [None: screenとteam_select_buttonsを更新する。操作そのものは実行しない]
    # }
    @staticmethod
    def _button(game: Game, rect: pygame.Rect, label: str, action: str, *, active: bool = False) -> None:
        # 窓座標ではなく論理マウス座標で描画時のホバーを判定する。
        hovered = rect.collidepoint(game.logical_mouse_pos())
        color = ACCENT if active else (35, 57, 65) if hovered else SURFACE
        pygame.draw.rect(game.screen, color, rect, border_radius=8)
        pygame.draw.rect(game.screen, ACCENT if active else BORDER, rect, 1, border_radius=8)
        game.text(label, 15, BACKGROUND if active else TEXT, rect.center, center=True, bold=active)
        game.team_select_buttons.append((rect, action))

    # {
    #   責務: [_venue_controls: 会場の選択肢と試合開始操作を表示する]
    #   処理: [1: HOME/中立/AWAYの選択状態を描く; 2: 開催地と開始ボタンを表示する]
    #   引数: [game: 会場選択番号を持つアプリ; home・away: 読込済みチーム]
    #   戻り値: [None: screenと操作領域を更新する。会場選択値やMatchは変更しない]
    # }
    def _venue_controls(self, game: Game, home: dict, away: dict) -> None:
        # 会場名は選択モードから表示用に求める。
        mode = game.venue_modes[game.venue_mode_index]
        game.text("会場", 17, TEXT, (48, 557), bold=True)
        for index, (key, label) in enumerate((("HOME", "HOMEのホーム"), ("NEUTRAL", "中立地"), ("AWAY", "AWAYのホーム"))):
            self._button(game, pygame.Rect(116 + index * 186, 548, 174, 40), label, f"venue_{key.lower()}", active=mode == key)
        venue = "中立地" if mode == "NEUTRAL" else (home if mode == "HOME" else away).get("home_court", "—")
        self._label(game, f"開催地：{venue}", 14, MUTED, 116, 603, 670)
        self._button(game, pygame.Rect(876, 544, 356, 52), "この対戦で試合開始  →", "start", active=True)
        game.text("会場: V    開始: Enter / Space", 14, MUTED, (1054, 616), center=True)

    # {
    #   責務: [_footer: メニュー・各編集画面・設定への戻り先を描く]
    #   処理: [1: 下端を区切る; 2: 遷移ボタンと共通設定を登録する]
    #   引数: [game: 描画先と操作領域を持つアプリ]
    #   戻り値: [None: screen・ボタン一覧・設定領域を更新する。遷移は入力時にGameが行う]
    # }
    def _footer(self, game: Game) -> None:
        # 対戦カードや会場操作と重ならない下端に戻り先をまとめる。
        pygame.draw.line(game.screen, BORDER, (48, HEIGHT - 72), (WIDTH - 48, HEIGHT - 72))
        for x, width, label, action in (
            (48, 184, "← メインメニュー", "main_menu"),
            (248, 172, "チームエディタ", "editor"),
            (436, 156, "リーグ戦", "league"),
        ):
            self._button(game, pygame.Rect(x, HEIGHT - 48, width, 34), label, action)
        game.draw_settings_button(pygame.Rect(WIDTH - 232, HEIGHT - 48, 184, 34))
