"""Team-editor tab for painting and exchanging five-part pixel uniforms."""

from __future__ import annotations

from typing import Any

import pygame

from scripts.core.settings import CREAM, GOLD, INK, MUTED
from scripts.team.uniform_data import (
    UNIFORM_PART_SIZES,
    default_uniform,
    export_uniform,
    list_uniform_files,
    load_uniform,
    normalize_uniform,
)


class UniformEditor:
    """Own uniform-painting selection, rendering, and import/export actions."""

    def __init__(self) -> None:
        self.selected_part = "胸"
        self.selected_color = "P"
        self.file_scroll = 0

    @staticmethod
    def _secondary(primary: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple(max(0, round(channel * 0.66)) for channel in primary)

    @staticmethod
    def _hex_rgb(value: object, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
        try:
            color = pygame.Color(str(value))
            return color.r, color.g, color.b
        except ValueError:
            return fallback

    def _team_colors(self, editor: Any) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        primary = self._hex_rgb(
            editor.payload.setdefault("チーム情報", {}).get("チームカラー", "#D84442"),
            (216, 68, 66),
        )
        return primary, self._secondary(primary)

    def _resolve_color(self, editor: Any, value: str) -> tuple[int, int, int]:
        primary, secondary = self._team_colors(editor)
        if value == "P":
            return primary
        if value == "S":
            return secondary
        return self._hex_rgb(value, primary)

    @staticmethod
    def _uniform(editor: Any) -> dict:
        info = editor.payload.setdefault("チーム情報", {})
        uniform = normalize_uniform(info.get("ユニフォーム"))
        info["ユニフォーム"] = uniform
        return uniform

    def _draw_grid_rect(self, editor: Any, rect: pygame.Rect, rows: list[list[str]]) -> None:
        if not rows or not rows[0]:
            return
        height, width = len(rows), len(rows[0])
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                cell = pygame.Rect(
                    rect.left + round(x * rect.width / width),
                    rect.top + round(y * rect.height / height),
                    max(1, round((x + 1) * rect.width / width) - round(x * rect.width / width)),
                    max(1, round((y + 1) * rect.height / height) - round(y * rect.height / height)),
                )
                pygame.draw.rect(editor.game.screen, self._resolve_color(editor, value), cell)
        pygame.draw.rect(editor.game.screen, INK, rect, 1)

    def _draw_preview(self, editor: Any, uniform: dict, area: pygame.Rect) -> None:
        editor.game.text("試合表示プレビュー", 13, INK, (area.centerx, area.top), bold=True, center=True)
        center_x = area.centerx
        chest = pygame.Rect(center_x - 42, area.top + 34, 84, 84)
        left_arm = pygame.Rect(chest.left - 31, chest.top + 6, 28, 65)
        right_arm = pygame.Rect(chest.right + 3, chest.top + 6, 28, 65)
        left_leg = pygame.Rect(center_x - 38, chest.bottom + 3, 34, 72)
        right_leg = pygame.Rect(center_x + 4, chest.bottom + 3, 34, 72)
        for part, rect in (
            ("胸", chest), ("左腕", left_arm), ("右腕", right_arm),
            ("左脚", left_leg), ("右脚", right_leg),
        ):
            self._draw_grid_rect(editor, rect, uniform["パーツ"][part])

    def draw(self, editor: Any, content: pygame.Rect) -> None:
        uniform = self._uniform(editor)
        editor.game.text("ユニフォーム・ドットエディタ", 20, INK, (content.left + 24, content.top + 18), bold=True)
        editor.game.text("P=チームカラー　S=自動生成したサブカラー", 10, MUTED, (content.left + 25, content.top + 48))

        for index, part in enumerate(UNIFORM_PART_SIZES):
            rect = pygame.Rect(content.left + 24, content.top + 82 + index * 48, 120, 36)
            editor._draw_button(rect, part, "uniform_part", part, active=self.selected_part == part, small=True)

        rows = uniform["パーツ"][self.selected_part]
        width, height = UNIFORM_PART_SIZES[self.selected_part]
        canvas = pygame.Rect(content.left + 176, content.top + 82, 410, 410)
        cell_size = min(canvas.width // width, canvas.height // height)
        grid_rect = pygame.Rect(0, 0, cell_size * width, cell_size * height)
        grid_rect.center = canvas.center
        pygame.draw.rect(editor.game.screen, (221, 217, 203), canvas, border_radius=8)
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                cell = pygame.Rect(grid_rect.left + x * cell_size, grid_rect.top + y * cell_size, cell_size, cell_size)
                pygame.draw.rect(editor.game.screen, self._resolve_color(editor, value), cell)
                pygame.draw.rect(editor.game.screen, (64, 69, 73), cell, 1)
                editor._register_button(cell, "uniform_pixel", (self.selected_part, x, y))
        editor.game.text(f"{self.selected_part}　{width}×{height}", 13, INK, (canvas.centerx, canvas.bottom + 8), bold=True, center=True)

        palette = ["P", "S", *(
            str(value).upper() for value in editor.editor_options.get("uniform_palette", ())
        )]
        palette = list(dict.fromkeys(value for value in palette if value in ("P", "S") or value.startswith("#")))
        palette_area = pygame.Rect(content.left + 620, content.top + 75, 260, 172)
        editor.game.text("描画色", 14, INK, (palette_area.left, palette_area.top), bold=True)
        for index, value in enumerate(palette[:18]):
            x, y = index % 6, index // 6
            cell = pygame.Rect(palette_area.left + x * 40, palette_area.top + 31 + y * 40, 32, 32)
            pygame.draw.rect(editor.game.screen, self._resolve_color(editor, value), cell, border_radius=4)
            pygame.draw.rect(editor.game.screen, GOLD if value == self.selected_color else INK, cell, 3 if value == self.selected_color else 1, border_radius=4)
            editor._register_button(cell, "uniform_color", value)
            if value in ("P", "S"):
                editor.game.text(value, 11, CREAM, cell.center, bold=True, center=True)

        for index, (label, action) in enumerate((
            ("全面を塗る", "uniform_fill"),
            ("左右反転", "uniform_mirror"),
            ("パーツ初期化", "uniform_reset_part"),
        )):
            rect = pygame.Rect(palette_area.left + index * 92, palette_area.bottom + 12, 84, 34)
            editor._draw_button(rect, label, action, small=True)

        preview = pygame.Rect(content.right - 326, content.top + 75, 286, 235)
        self._draw_preview(editor, uniform, preview)

        files = list_uniform_files()
        self.file_scroll = min(self.file_scroll, max(0, len(files) - 4))
        exchange = pygame.Rect(content.left + 620, content.top + 310, content.width - 660, 230)
        pygame.draw.rect(editor.game.screen, (235, 231, 216), exchange, border_radius=8)
        pygame.draw.rect(editor.game.screen, (185, 182, 170), exchange, 2, border_radius=8)
        editor.game.text("ユニフォームの読込・書出し", 14, INK, (exchange.left + 14, exchange.top + 12), bold=True)
        editor._draw_button(
            pygame.Rect(exchange.right - 152, exchange.top + 9, 136, 34),
            "現在の模様を書出し", "uniform_export", active=True, small=True,
        )
        for index, path in enumerate(files[self.file_scroll:self.file_scroll + 4]):
            row = pygame.Rect(exchange.left + 14, exchange.top + 54 + index * 40, exchange.width - 28, 34)
            pygame.draw.rect(editor.game.screen, (247, 244, 232), row, border_radius=4)
            editor._text_fit(path.stem.removesuffix(".uniform"), 10, INK, pygame.Rect(row.left + 9, row.top, row.width - 100, row.height), bold=True)
            editor._draw_button(pygame.Rect(row.right - 82, row.top + 3, 74, 28), "読込", "uniform_import", path, small=True)
        if len(files) > 4:
            editor._draw_button(pygame.Rect(exchange.right - 74, exchange.bottom - 34, 26, 25), "▲", "uniform_file_scroll", -1, small=True)
            editor._draw_button(pygame.Rect(exchange.right - 40, exchange.bottom - 34, 26, 25), "▼", "uniform_file_scroll", 1, small=True)
        if not files:
            editor.game.text("書き出したユニフォームがここに表示されます", 11, MUTED, (exchange.centerx, exchange.centery + 14), center=True)

    def perform(self, editor: Any, action: str, data: Any) -> bool:
        if not action.startswith("uniform_"):
            return False
        uniform = self._uniform(editor)
        if action == "uniform_part":
            if str(data) in UNIFORM_PART_SIZES:
                self.selected_part = str(data)
            return True
        if action == "uniform_color":
            self.selected_color = str(data)
            return True
        if action == "uniform_pixel":
            part, x, y = data
            uniform["パーツ"][part][int(y)][int(x)] = self.selected_color
            editor._mark_dirty()
            return True
        if action == "uniform_fill":
            rows = uniform["パーツ"][self.selected_part]
            for row in rows:
                row[:] = [self.selected_color] * len(row)
            editor._mark_dirty()
            return True
        if action == "uniform_mirror":
            rows = uniform["パーツ"][self.selected_part]
            for row in rows:
                row.reverse()
            editor._mark_dirty()
            return True
        if action == "uniform_reset_part":
            uniform["パーツ"][self.selected_part] = default_uniform()["パーツ"][self.selected_part]
            editor._mark_dirty()
            return True
        if action == "uniform_export":
            try:
                name = editor.payload.get("チーム情報", {}).get("チーム名", "ユニフォーム")
                path = export_uniform(uniform, name)
                editor._set_message(f"{path.name} へユニフォームを書き出しました")
            except OSError as error:
                editor._set_message(f"書き出せません: {error}", (204, 61, 58))
            return True
        if action == "uniform_import":
            try:
                editor.payload.setdefault("チーム情報", {})["ユニフォーム"] = load_uniform(data)
                editor._mark_dirty()
                editor._set_message(f"{data.name} を読み込みました")
            except (OSError, ValueError) as error:
                editor._set_message(f"読み込めません: {error}", (204, 61, 58))
            return True
        if action == "uniform_file_scroll":
            self.file_scroll = max(0, min(max(0, len(list_uniform_files()) - 4), self.file_scroll + int(data)))
            return True
        return True


__all__ = ("UniformEditor",)
