from __future__ import annotations

import colorsys
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

import pygame

from scripts.match.player_style_system import PLAYER_TYPES
from scripts.core.settings import CREAM, GOLD, HEIGHT, HOME_RED, INK, MUTED, PAPER, TACTIC_NAMES, TEAMS_DIR, WIDTH
from scripts.match.skill_system import ALL_SKILLS
from scripts.core.stat_scale import PLAYER_STAT_DEFAULT, PLAYER_STAT_MAX, PLAYER_STAT_MIN
from scripts.team.team_editor_config import load_editor_options, load_tuner_options
from scripts.team.team_editor_data import (
    FORMATION_TEMPLATES,
    STAT_GROUPS,
    TEAM_FIELDS,
    EditorIssue,
    add_default_player,
    apply_formation,
    create_team_template,
    delete_team_file,
    load_editor_payload,
    repair_payload,
    role_for_position_y,
    save_editor_payload,
    scan_team_directory,
    scan_team_files,
    team_id_for_path,
    team_relative_path,
    validate_payload,
)
from scripts.team.team_rating import category_average, rank_for_average, reload_rating_options
from scripts.team.team_template_profile import generation_profiles, profile_label, rank_labels, target_for_rank
from scripts.team.team_tuner import TeamTunerSession, auto_adjust_payload, payload_category_summary
from scripts.team.uniform_editor import UniformEditor


EDITOR_BG = (29, 38, 48)
CARD = (245, 241, 226)
FIELD_BG = (255, 252, 239)
FIELD_ACTIVE = (255, 240, 183)
BUTTON = (229, 225, 210)
BUTTON_HOVER = (239, 234, 214)
ERROR_RED = (204, 61, 58)
OK_GREEN = (47, 148, 82)
GRID_GREEN_A = (63, 143, 82)
GRID_GREEN_B = (70, 153, 88)


class TeamEditor:
    """Mouse-first JSON team editor rendered into the game's logical surface."""

    def __init__(self, game: Any) -> None:
        self.game = game
        self.mode = "LIST"
        self.tab = "TEAM"
        self.payload: dict = {}
        self.source_path: Path | None = None
        self.folder_settings = {"フォルダ": ""}
        self.team_entries: list[tuple[Path, dict, list[EditorIssue]]] = []
        self.folder_entries: list[Path] = []
        self.current_folder = Path()
        self.selected_player = 0
        self.player_scroll = 0
        self.error_scroll = 0
        self.list_scroll = 0
        self.template_scroll = 0
        self.stat_group = next(iter(STAT_GROUPS))
        self.target_mean = str(round(PLAYER_STAT_DEFAULT))
        self.target_input_mode = "number"
        self.target_rank = rank_for_average(float(self.target_mean))
        self.target_spread = "中"
        self.editor_options = load_editor_options()
        self.target_profile_id = str(generation_profiles(self.editor_options)[0].get("id", "balanced"))
        self.tuner_options = load_tuner_options()
        self.tuner_opponents: set[str] = set()
        self.tuner_opponent_scroll = 0
        self.tuner_session: TeamTunerSession | None = None
        self.tuner_result_applied = False
        self.tuner_adjust_scope = "player"
        self.uniform_editor = UniformEditor()
        self.message = ""
        self.message_color = MUTED
        self.dirty = False
        self.confirm_back = False
        self.pending_delete: Path | None = None
        self.load_issues: list[EditorIssue] = []
        self.buttons: list[tuple[pygame.Rect, str, Any]] = []
        self.input_fields: list[tuple[pygame.Rect, dict, str, str]] = []
        self.active_input: tuple[dict, str, str] | None = None
        self.input_replace_pending = False
        self.ime_composition = ""
        self.color_picker_open = False
        self.held_number_step: tuple[dict | None, str, str, int] | None = None
        self.number_hold_elapsed = 0.0
        self.number_hold_repeat = 0.0
        self.multiline_cursor = 0
        self.multiline_preferred_x: int | None = None
        self.multiline_view_start = 0
        self.multiline_layout_width = 700
        self.held_text_delete: int | None = None
        self.text_delete_hold_elapsed = 0.0
        self.text_delete_hold_repeat = 0.0
        self.rng = random.Random()

    @property
    def players(self) -> list[dict]:
        players = self.payload.get("選手一覧", [])
        return players if isinstance(players, list) else []

    @property
    def current_player(self) -> dict | None:
        if not self.players:
            return None
        self.selected_player = max(0, min(self.selected_player, len(self.players) - 1))
        player = self.players[self.selected_player]
        return player if isinstance(player, dict) else None

    @property
    def tabs(self) -> tuple[tuple[str, str], ...]:
        values = [
            (str(item.get("id")), str(item.get("label")))
            for item in self.editor_options.get("tabs", ()) if isinstance(item, dict)
        ]
        required = {
            "TEAM": "チーム情報", "PLAYER": "選手能力", "SKILLS": "スキル一覧",
            "FORMATION": "フォーメーション", "TUNER": "チューナー", "ERRORS": "エラー",
        }
        present = {item[0] for item in values}
        if "INTRO" not in present:
            team_index = next((index for index, item in enumerate(values) if item[0] == "TEAM"), -1)
            values.insert(team_index + 1, ("INTRO", "チーム紹介"))
            present.add("INTRO")
        values.extend((key, label) for key, label in required.items() if key not in present)
        return tuple(values)

    @property
    def stat_groups(self) -> dict[str, tuple[str, ...]]:
        groups = self.editor_options.get("stat_groups", STAT_GROUPS)
        return {
            str(group): tuple(str(field) for field in fields)
            for group, fields in groups.items() if isinstance(fields, (list, tuple))
        }

    @property
    def player_types(self) -> tuple[str, ...]:
        values = tuple(value for value in self.editor_options.get("player_types", PLAYER_TYPES) if value in PLAYER_TYPES)
        return values or PLAYER_TYPES

    @property
    def editor_skills(self) -> tuple[str, ...]:
        values = tuple(value for value in self.editor_options.get("skills", ALL_SKILLS) if value in ALL_SKILLS)
        return values or ALL_SKILLS

    @property
    def formation_templates(self) -> dict:
        values = self.editor_options.get("formation_templates", FORMATION_TEMPLATES)
        return values if isinstance(values, dict) and values else FORMATION_TEMPLATES

    @property
    def tuner_categories(self) -> tuple[dict, ...]:
        return tuple(category for category in self.tuner_options.get("categories", ()) if isinstance(category, dict))

    def _ensure_tuner_settings(self) -> dict:
        settings = self.payload.setdefault("チームチューナー", {})
        if not isinstance(settings, dict):
            settings = {}
            self.payload["チームチューナー"] = settings
        targets = settings.setdefault("基準値ステータス", {})
        if not isinstance(targets, dict):
            targets = {}
            settings["基準値ステータス"] = targets
        default_target = int(self.tuner_options.get("default_target", round(PLAYER_STAT_DEFAULT)))
        for category in self.tuner_categories:
            targets.setdefault(str(category.get("id")), str(default_target))
        settings.setdefault("裏パラメータ自動調整", bool(self.tuner_options.get("hidden_parameters_default", True)))
        settings.setdefault("時間上限秒", str(self.tuner_options.get("default_time_limit_seconds", 15)))
        settings.setdefault("終了条件", "時間上限")
        settings.setdefault("評価モード", str(self.tuner_options.get("default_evaluation_mode", "精度重視")))
        return settings

    def _tuner_targets(self) -> dict[str, int]:
        settings = self._ensure_tuner_settings()
        values = settings["基準値ステータス"]
        result: dict[str, int] = {}
        for category in self.tuner_categories:
            category_id = str(category.get("id"))
            try:
                value = int(values.get(category_id, self.tuner_options.get("default_target", round(PLAYER_STAT_DEFAULT))))
            except (TypeError, ValueError):
                value = int(self.tuner_options.get("default_target", round(PLAYER_STAT_DEFAULT)))
            result[category_id] = round(max(PLAYER_STAT_MIN, min(PLAYER_STAT_MAX, value)))
            values[category_id] = str(result[category_id])
        return result

    def _available_tuner_opponents(self) -> list[dict]:
        current_source = team_relative_path(self.source_path).as_posix() if self.source_path else ""
        return [choice for choice in self.game.team_choices if choice.get("source") != current_source]

    def _reset_tuner_selection(self) -> None:
        available = self._available_tuner_opponents()
        available_ids = {str(choice.get("id")) for choice in available}
        self.tuner_opponents.intersection_update(available_ids)
        if not self.tuner_opponents:
            self.tuner_opponents.update(str(choice.get("id")) for choice in available[:3])
        self.tuner_opponent_scroll = 0
        self.tuner_session = None
        self.tuner_result_applied = False
        self.tuner_adjust_scope = "player"

    def open(self) -> None:
        self.editor_options = load_editor_options()
        self.tuner_options = load_tuner_options()
        reload_rating_options()
        profile_ids = {str(entry.get("id")) for entry in generation_profiles(self.editor_options)}
        if self.target_profile_id not in profile_ids:
            self.target_profile_id = str(generation_profiles(self.editor_options)[0].get("id", "balanced"))
        if self.stat_group not in self.stat_groups:
            self.stat_group = next(iter(self.stat_groups), "")
        self.mode = "LIST"
        self.current_folder = Path()
        self.color_picker_open = False
        self.active_input = None
        self.refresh_files()
        self.message = "既存チームを開くか、テンプレートから新規作成してください"
        self.message_color = MUTED
        pygame.key.start_text_input()

    def update(self, dt: float) -> None:
        self._update_number_hold(dt)
        self._update_text_delete_hold(dt)
        session = self.tuner_session
        if session is None or session.finished:
            if session is not None and session.finished and not self.tuner_result_applied:
                self.tuner_result_applied = True
                if not session.cancelled:
                    self.payload = deepcopy(session.best_payload)
                    self.active_input = None
                    self._mark_dirty()
                    completion_label = "評価区間" if session.evaluation_mode == "speed" else "完走試合"
                    self._set_message(
                        f"チューニング完了：{session.finish_reason}（{completion_label}{session.completed_matches}回・採用{session.accepted_trials}回）",
                        OK_GREEN,
                    )
                else:
                    self._set_message("チューニングを中止しました。計算中の変更は適用していません", ERROR_RED)
            return
        budget = float(self.tuner_options.get("simulation_budget_ms_per_frame", 9))
        session.step(budget * int(getattr(self.game, "cpu_limit_percent", 100)) / 100.0)

    def close(self) -> None:
        if self.tuner_session is not None and not self.tuner_session.finished:
            self.tuner_session.cancel()
        self.active_input = None
        self.held_number_step = None
        self.number_hold_elapsed = 0.0
        self.number_hold_repeat = 0.0
        self._stop_text_delete_hold()
        pygame.key.stop_text_input()

    def refresh_files(self) -> None:
        self.folder_entries, self.team_entries = scan_team_directory(self.current_folder)
        self.list_scroll = min(self.list_scroll, max(0, self._browser_item_count() - 9))

    def _browser_item_count(self) -> int:
        return len(self.folder_entries) + len(self.team_entries)

    def _set_message(self, message: str, color: tuple[int, int, int] = MUTED) -> None:
        self.message = message
        self.message_color = color

    def _mark_dirty(self) -> None:
        self.dirty = True
        self.confirm_back = False

    def _register_button(self, rect: pygame.Rect, action: str, data: Any = None) -> None:
        self.buttons.append((rect, action, data))

    def _draw_button(
        self,
        rect: pygame.Rect,
        label: str,
        action: str,
        data: Any = None,
        *,
        active: bool = False,
        danger: bool = False,
        small: bool = False,
    ) -> None:
        mouse = self.game.logical_mouse_pos()
        hover = rect.collidepoint(mouse)
        if danger:
            color = (235, 108, 96) if hover else (220, 83, 74)
            text_color = CREAM
        elif active:
            color = GOLD
            text_color = INK
        else:
            color = BUTTON_HOVER if hover else BUTTON
            text_color = INK
        pygame.draw.rect(self.game.screen, color, rect, border_radius=6)
        pygame.draw.rect(self.game.screen, (174, 173, 164), rect, 2, border_radius=6)
        self._text_fit(label, 10 if small else 12, text_color, rect, bold=True, center=True)
        self._register_button(rect, action, data)

    def _text_fit(
        self,
        value: object,
        size: int,
        color: tuple[int, int, int],
        rect: pygame.Rect,
        *,
        bold: bool = False,
        center: bool = False,
        padding: int = 6,
    ) -> None:
        label = str(value)
        font = self.game.font(size, bold)
        while label and font.size(label)[0] > rect.width - padding * 2:
            label = label[:-1]
        if label != str(value) and label:
            label = label[:-1] + "…"
        surface = font.render(label, True, color)
        target = surface.get_rect()
        if center:
            target.center = rect.center
        else:
            target.midleft = (rect.left + padding, rect.centery)
        self.game.screen.blit(surface, target)

    def _draw_input(
        self,
        rect: pygame.Rect,
        target: dict,
        key: str,
        *,
        kind: str = "text",
        label: str | None = None,
    ) -> None:
        active = self.active_input is not None and self.active_input[0] is target and self.active_input[1] == key
        input_rect = rect.copy()
        if kind == "number":
            spinner_width = min(25, max(19, rect.width // 4))
            input_rect.width -= spinner_width + 3
            up_rect = pygame.Rect(input_rect.right + 3, rect.top, spinner_width, max(14, rect.height // 2 - 1))
            down_rect = pygame.Rect(input_rect.right + 3, up_rect.bottom + 2, spinner_width, rect.bottom - up_rect.bottom - 2)
            self._draw_button(up_rect, "^", "number_step", (target, key, kind, 1), small=True)
            self._draw_button(down_rect, "v", "number_step", (target, key, kind, -1), small=True)
        pygame.draw.rect(self.game.screen, FIELD_ACTIVE if active else FIELD_BG, input_rect, border_radius=5)
        pygame.draw.rect(self.game.screen, GOLD if active else (188, 185, 173), input_rect, 2, border_radius=5)
        if label:
            label_rect = pygame.Rect(rect.left, rect.top - 19, rect.width, 18)
            self._text_fit(label, 11, MUTED, label_rect, bold=True)
        value = str(target.get(key, ""))
        if active:
            value += self.ime_composition + "｜"
        self._text_fit(value, 13, INK, input_rect)
        self.input_fields.append((input_rect, target, key, kind))

    def _multiline_layout(self, value: object, width: int, *, size: int = 14) -> list[tuple[str, int, int]]:
        """Return visual lines with their start/end offsets in the source text."""
        font = self.game.font(size)
        text = str(value).replace("\r", "")
        lines: list[tuple[str, int, int]] = []
        current = ""
        line_start = 0
        for index, character in enumerate(text):
            if character == "\n":
                lines.append((current, line_start, index))
                current = ""
                line_start = index + 1
                continue
            candidate = current + character
            if current and font.size(candidate)[0] > max(1, width):
                lines.append((current, line_start, index))
                current = character
                line_start = index
            else:
                current = candidate
        lines.append((current, line_start, len(text)))
        return lines

    def _wrap_multiline(self, value: object, width: int, *, size: int = 14) -> list[str]:
        return [line for line, _, _ in self._multiline_layout(value, width, size=size)]

    @staticmethod
    def _multiline_line_index(lines: list[tuple[str, int, int]], cursor: int) -> int:
        for index, (_, start, end) in enumerate(lines):
            if start <= cursor <= end:
                # A soft-wrap boundary belongs to the beginning of the next
                # visual line, while an explicit newline stays on this line.
                if cursor == end and index + 1 < len(lines) and lines[index + 1][1] == cursor:
                    continue
                return index
        return max(0, len(lines) - 1)

    def _multiline_cursor_for_x(self, line: tuple[str, int, int], x: int, *, size: int = 14) -> int:
        text, start, _ = line
        font = self.game.font(size)
        offset = min(
            range(len(text) + 1),
            key=lambda candidate: abs(font.size(text[:candidate])[0] - max(0, x)),
        )
        return start + offset

    def _move_multiline_cursor(self, key: int, *, control: bool = False) -> None:
        if self.active_input is None or self.active_input[2] != "multiline":
            return
        target, field, _ = self.active_input
        value = str(target.get(field, ""))
        self.multiline_cursor = max(0, min(len(value), self.multiline_cursor))
        lines = self._multiline_layout(value, self.multiline_layout_width)
        line_index = self._multiline_line_index(lines, self.multiline_cursor)
        line_text, line_start, line_end = lines[line_index]
        if key == pygame.K_LEFT:
            self.multiline_cursor = max(0, self.multiline_cursor - 1)
            self.multiline_preferred_x = None
        elif key == pygame.K_RIGHT:
            self.multiline_cursor = min(len(value), self.multiline_cursor + 1)
            self.multiline_preferred_x = None
        elif key == pygame.K_HOME:
            self.multiline_cursor = 0 if control else line_start
            self.multiline_preferred_x = None
        elif key == pygame.K_END:
            self.multiline_cursor = len(value) if control else line_end
            self.multiline_preferred_x = None
        elif key in (pygame.K_UP, pygame.K_DOWN):
            target_line_index = max(0, min(len(lines) - 1, line_index + (-1 if key == pygame.K_UP else 1)))
            if target_line_index == line_index:
                return
            font = self.game.font(14)
            if self.multiline_preferred_x is None:
                offset = max(0, min(len(line_text), self.multiline_cursor - line_start))
                self.multiline_preferred_x = font.size(line_text[:offset])[0]
            self.multiline_cursor = self._multiline_cursor_for_x(
                lines[target_line_index], self.multiline_preferred_x,
            )
        self.input_replace_pending = False

    def _place_multiline_cursor(self, rect: pygame.Rect, target: dict, key: str, mouse_pos: tuple[int, int]) -> None:
        value = str(target.get(key, ""))
        self.multiline_layout_width = rect.width - 28
        lines = self._multiline_layout(value, self.multiline_layout_width)
        max_lines = max(1, (rect.height - 24) // 24)
        maximum_start = max(0, len(lines) - max_lines)
        self.multiline_view_start = max(0, min(maximum_start, self.multiline_view_start))
        clicked_row = max(0, (mouse_pos[1] - (rect.top + 12)) // 24)
        line_index = max(0, min(len(lines) - 1, self.multiline_view_start + clicked_row))
        self.multiline_cursor = self._multiline_cursor_for_x(
            lines[line_index], mouse_pos[0] - (rect.left + 14),
        )
        self.multiline_preferred_x = None

    def _insert_multiline_text(self, text: str) -> None:
        if self.active_input is None or self.active_input[2] != "multiline":
            return
        target, key, _ = self.active_input
        value = str(target.get(key, ""))
        cursor = max(0, min(len(value), self.multiline_cursor))
        insertion = text.replace("\r\n", "\n").replace("\r", "\n")[:max(0, 4000 - len(value))]
        if not insertion:
            return
        target[key] = value[:cursor] + insertion + value[cursor:]
        self.multiline_cursor = cursor + len(insertion)
        self.multiline_preferred_x = None
        self.input_replace_pending = False
        self._mark_dirty()

    def _delete_multiline_character(self, *, backward: bool) -> bool:
        if self.active_input is None or self.active_input[2] != "multiline":
            return False
        target, key, _ = self.active_input
        value = str(target.get(key, ""))
        cursor = max(0, min(len(value), self.multiline_cursor))
        if backward:
            if cursor <= 0:
                return False
            target[key] = value[:cursor - 1] + value[cursor:]
            self.multiline_cursor = cursor - 1
        else:
            if cursor >= len(value):
                return False
            target[key] = value[:cursor] + value[cursor + 1:]
            self.multiline_cursor = cursor
        self.multiline_preferred_x = None
        self.input_replace_pending = False
        self._mark_dirty()
        return True

    def _start_text_delete_hold(self, key: int) -> None:
        if self.held_text_delete == key:
            return
        self._stop_text_delete_hold()
        self.held_text_delete = key
        self._delete_multiline_character(backward=key == pygame.K_BACKSPACE)

    def _stop_text_delete_hold(self) -> None:
        self.held_text_delete = None
        self.text_delete_hold_elapsed = 0.0
        self.text_delete_hold_repeat = 0.0

    def _update_text_delete_hold(self, dt: float) -> None:
        if self.held_text_delete is None:
            return
        if self.active_input is None or self.active_input[2] != "multiline" or self.ime_composition:
            self._stop_text_delete_hold()
            return
        previous = self.text_delete_hold_elapsed
        self.text_delete_hold_elapsed += max(0.0, dt)
        initial_delay = 0.38
        if self.text_delete_hold_elapsed < initial_delay:
            return
        self.text_delete_hold_repeat += (
            dt if previous >= initial_delay else self.text_delete_hold_elapsed - initial_delay
        )
        interval = 0.055 if self.text_delete_hold_elapsed < 1.6 else 0.030
        repeats = 0
        while self.text_delete_hold_repeat >= interval and repeats < 24:
            self.text_delete_hold_repeat -= interval
            if not self._delete_multiline_character(backward=self.held_text_delete == pygame.K_BACKSPACE):
                self._stop_text_delete_hold()
                break
            repeats += 1

    def _draw_multiline_input(
        self,
        rect: pygame.Rect,
        target: dict,
        key: str,
        *,
        label: str,
    ) -> None:
        active = self.active_input is not None and self.active_input[0] is target and self.active_input[1] == key
        pygame.draw.rect(self.game.screen, FIELD_ACTIVE if active else FIELD_BG, rect, border_radius=7)
        pygame.draw.rect(self.game.screen, GOLD if active else (188, 185, 173), rect, 2, border_radius=7)
        self.game.text(label, 12, MUTED, (rect.left, rect.top - 23), bold=True)
        value = str(target.get(key, ""))
        self.multiline_layout_width = rect.width - 28
        cursor = max(0, min(len(value), self.multiline_cursor)) if active else 0
        composition = self.ime_composition if active else ""
        display_value = value[:cursor] + composition + value[cursor:] if active else value
        display_cursor = cursor + len(composition)
        lines = self._multiline_layout(display_value, self.multiline_layout_width)
        max_lines = max(1, (rect.height - 24) // 24)
        if active:
            cursor_line = self._multiline_line_index(lines, display_cursor)
            if cursor_line < self.multiline_view_start:
                self.multiline_view_start = cursor_line
            elif cursor_line >= self.multiline_view_start + max_lines:
                self.multiline_view_start = cursor_line - max_lines + 1
            self.multiline_view_start = max(0, min(max(0, len(lines) - max_lines), self.multiline_view_start))
        else:
            self.multiline_view_start = 0
        shown = lines[self.multiline_view_start:self.multiline_view_start + max_lines]
        for index, (line, _, _) in enumerate(shown):
            self.game.text(line, 14, INK, (rect.left + 14, rect.top + 12 + index * 24))
        if active and pygame.time.get_ticks() % 1000 < 650:
            cursor_line = self._multiline_line_index(lines, display_cursor)
            if self.multiline_view_start <= cursor_line < self.multiline_view_start + max_lines:
                line_text, line_start, _ = lines[cursor_line]
                offset = max(0, min(len(line_text), display_cursor - line_start))
                caret_x = rect.left + 14 + self.game.font(14).size(line_text[:offset])[0]
                caret_y = rect.top + 11 + (cursor_line - self.multiline_view_start) * 24
                pygame.draw.line(self.game.screen, INK, (caret_x, caret_y), (caret_x, caret_y + 19), 2)
        if not value and not active:
            self.game.text("チームの歴史・地域・特色などを自由に入力できます", 13, MUTED, (rect.left + 14, rect.top + 13))
        self.input_fields.append((rect, target, key, "multiline"))

    def _numeric_bounds(self, key: str, kind: str) -> tuple[int, int]:
        if kind == "editor_target":
            return round(PLAYER_STAT_MIN), round(PLAYER_STAT_MAX)
        stat_keys = {field for fields in self.stat_groups.values() for field in fields}
        tuner_keys = {str(category.get("id")) for category in self.tuner_categories}
        if key in stat_keys or key in tuner_keys or key in (
            "戦術変更への積極性", "選手交代への積極性",
        ):
            return round(PLAYER_STAT_MIN), round(PLAYER_STAT_MAX)
        if key == "戦術への忠実さ":
            return 0, 100
        if key in ("ゾーン手前", "ゾーン奥"):
            return 1, 10
        if key == "ポジションX":
            return 0, 15
        if key == "ポジションY":
            return 0, 11
        if key == "時間上限秒":
            return (
                int(self.tuner_options.get("minimum_time_limit_seconds", 1)),
                int(self.tuner_options.get("maximum_time_limit_seconds", 600)),
            )
        if key == "年齢":
            return 1, 99
        if key == "背番号":
            return 0, 999
        return 0, 9999

    def _step_numeric(self, target: dict | None, key: str, kind: str, delta: int) -> None:
        minimum, maximum = self._numeric_bounds(key, kind)
        raw = self.target_mean if kind == "editor_target" else str((target or {}).get(key, ""))
        try:
            current = int(raw)
        except (TypeError, ValueError):
            current = minimum
        value = str(max(minimum, min(maximum, current + int(delta))))
        if kind == "editor_target":
            self.target_mean = value
            self.active_input = ({}, "target", "editor_target")
        elif target is not None:
            target[key] = value
            self.active_input = (target, key, kind)
            self._mark_dirty()
        self.input_replace_pending = False

    def _update_number_hold(self, dt: float) -> None:
        if self.held_number_step is None:
            return
        previous = self.number_hold_elapsed
        self.number_hold_elapsed += dt
        initial_delay = 0.38
        if self.number_hold_elapsed < initial_delay:
            return
        self.number_hold_repeat += dt if previous >= initial_delay else self.number_hold_elapsed - initial_delay
        interval = 0.070 if self.number_hold_elapsed < 1.6 else 0.035
        repeats = 0
        while self.number_hold_repeat >= interval and repeats < 16:
            self.number_hold_repeat -= interval
            self._step_numeric(*self.held_number_step)
            repeats += 1

    def _draw_header(self) -> None:
        pygame.draw.rect(self.game.screen, INK, (0, 0, WIDTH, 58))
        self.game.text("TEAM EDITOR", 13, GOLD, (20, 10), bold=True)
        title = "チームエディタ" if self.mode == "LIST" else str(self.payload.get("チーム情報", {}).get("チーム名", "編集中"))
        if self.dirty and self.mode == "EDIT":
            title += "  ●未保存"
        self.game.text(title, 23, CREAM, (20, 27), bold=True)
        close_rect = pygame.Rect(WIDTH - 126, 13, 106, 34)
        self._draw_button(close_rect, "エディタを閉じる", "close", small=True)

    def draw(self) -> None:
        self.buttons.clear()
        self.input_fields.clear()
        self.game.screen.fill(EDITOR_BG)
        self._draw_header()
        if self.mode == "LIST":
            self._draw_team_list()
        else:
            self._draw_edit()
        if self.color_picker_open:
            self._draw_color_picker()
        if self.message:
            bar = pygame.Rect(18, HEIGHT - 34, WIDTH - 36, 24)
            pygame.draw.rect(self.game.screen, (239, 235, 219), bar, border_radius=5)
            self._text_fit(self.message, 11, self.message_color, bar, bold=True)

    def _draw_team_list(self) -> None:
        left = pygame.Rect(18, 74, 790, 596)
        right = pygame.Rect(826, 74, 436, 596)
        for panel in (left, right):
            pygame.draw.rect(self.game.screen, CARD, panel, border_radius=10)
            pygame.draw.rect(self.game.screen, (190, 187, 175), panel, 2, border_radius=10)
        location = "teams /" if self.current_folder == Path() else f"teams / {self.current_folder.as_posix()}"
        self.game.text("チームフォルダ", 18, INK, (left.left + 20, left.top + 14), bold=True)
        self._text_fit(location, 11, MUTED, pygame.Rect(left.left + 20, left.top + 40, left.width - 130, 22), bold=True)
        if self.current_folder != Path():
            self._draw_button(pygame.Rect(left.right - 102, left.top + 15, 82, 32), "← 上へ", "folder_up", small=True)

        browser_items = [
            ("folder", path, None, None) for path in self.folder_entries
        ] + [
            ("team", path, payload, issues) for path, payload, issues in self.team_entries
        ]
        visible = browser_items[self.list_scroll:self.list_scroll + 9]
        for row_index, (kind, path, payload, issues) in enumerate(visible):
            y = left.top + 70 + row_index * 55
            row = pygame.Rect(left.left + 16, y, left.width - 32, 44)
            pygame.draw.rect(self.game.screen, (237, 233, 217) if row_index % 2 == 0 else (244, 240, 226), row, border_radius=5)
            if kind == "folder":
                folder_icon = pygame.Rect(row.left + 11, row.top + 11, 27, 20)
                pygame.draw.rect(self.game.screen, (225, 174, 66), folder_icon, border_radius=3)
                pygame.draw.rect(self.game.screen, (244, 199, 91), (folder_icon.left + 3, folder_icon.top - 4, 13, 6), border_radius=2)
                self._text_fit(path.name, 14, INK, pygame.Rect(row.left + 50, row.top, 430, row.height), bold=True)
                self._text_fit("フォルダ", 10, MUTED, pygame.Rect(row.left + 480, row.top, 90, row.height), center=True)
                self._draw_button(pygame.Rect(row.right - 104, row.top + 6, 92, 32), "開く", "open_folder", path, small=True)
                continue
            assert payload is not None and issues is not None
            name = payload.get("チーム情報", {}).get("チーム名") or path.stem
            self._text_fit(name, 14, INK, pygame.Rect(row.left + 12, row.top + 2, 330, 23), bold=True)
            self._text_fit(path.name, 9, MUTED, pygame.Rect(row.left + 12, row.top + 23, 330, 18))
            status = "試合可能" if not issues else f"エラー {len(issues)}件"
            status_color = OK_GREEN if not issues else ERROR_RED
            self._text_fit(status, 11, status_color, pygame.Rect(row.left + 345, row.top, 120, row.height), bold=True, center=True)
            open_rect = pygame.Rect(row.right - 190, row.top + 6, 92, 32)
            delete_rect = pygame.Rect(row.right - 90, row.top + 6, 78, 32)
            self._draw_button(open_rect, "編集", "open", path, small=True)
            deleting = self.pending_delete == path
            self._draw_button(delete_rect, "確認" if deleting else "削除", "delete", path, danger=True, small=True)

        if self._browser_item_count() > 9:
            up = pygame.Rect(left.right - 92, left.top + 18, 30, 30)
            down = pygame.Rect(left.right - 54, left.top + 18, 30, 30)
            self._draw_button(up, "▲", "list_up", small=True)
            self._draw_button(down, "▼", "list_down", small=True)

        self.game.text("新しいチームを作成", 18, INK, (right.left + 20, right.top + 16), bold=True)
        self.game.text("作成後も全項目を編集できます", 11, MUTED, (right.left + 20, right.top + 45))
        template_info = [item for item in self.editor_options.get("team_templates", ()) if isinstance(item, dict)]
        self.template_scroll = min(self.template_scroll, max(0, len(template_info) - 2))
        if len(template_info) > 2:
            self._draw_button(pygame.Rect(right.right - 76, right.top + 16, 24, 26), "▲", "template_scroll", -1, small=True)
            self._draw_button(pygame.Rect(right.right - 46, right.top + 16, 24, 26), "▼", "template_scroll", 1, small=True)
        for index, template in enumerate(template_info[self.template_scroll:self.template_scroll + 2]):
            title = str(template.get("label", template.get("id", "テンプレート")))
            detail = str(template.get("description", ""))
            action = f"create_{template.get('id', 'initial')}"
            y = right.top + 86 + index * 78
            rect = pygame.Rect(right.left + 20, y, right.width - 40, 60)
            self._draw_button(rect, title, action)
            self._text_fit(detail, 9, MUTED, pygame.Rect(rect.left, rect.bottom + 1, rect.width, 16), center=True)

        target_card = pygame.Rect(right.left + 20, right.top + 264, right.width - 40, 242)
        pygame.draw.rect(self.game.screen, (236, 232, 216), target_card, border_radius=8)
        pygame.draw.rect(self.game.screen, (190, 187, 175), target_card, 2, border_radius=8)
        self.game.text("基準値テンプレート", 16, INK, (target_card.left + 16, target_card.top + 14), bold=True)
        mode_label = "ランク入力" if self.target_input_mode == "rank" else "数値入力"
        self._draw_button(
            pygame.Rect(target_card.right - 108, target_card.top + 9, 92, 27),
            mode_label, "target_mode", small=True, active=self.target_input_mode == "rank",
        )
        self.game.text("全能力の平均目標", 11, MUTED, (target_card.left + 16, target_card.top + 52))
        target_rect = pygame.Rect(target_card.left + 190, target_card.top + 43, 122, 34)
        target_up = pygame.Rect(target_rect.right + 3, target_rect.top, 25, 16)
        target_down = pygame.Rect(target_rect.right + 3, target_rect.top + 18, 25, 16)
        rank_mode = self.target_input_mode == "rank"
        active = not rank_mode and self.active_input is not None and self.active_input[2] == "editor_target"
        pygame.draw.rect(self.game.screen, FIELD_ACTIVE if active else FIELD_BG, target_rect, border_radius=5)
        pygame.draw.rect(self.game.screen, GOLD if active else (188, 185, 173), target_rect, 2, border_radius=5)
        target_display = self.target_rank if rank_mode else self.target_mean + ("｜" if active else "")
        self._text_fit(target_display, 13, INK, target_rect, center=rank_mode, bold=rank_mode)
        if rank_mode:
            self._draw_button(target_up, "^", "target_rank_step", -1, small=True)
            self._draw_button(target_down, "v", "target_rank_step", 1, small=True)
        else:
            self._register_button(target_rect, "target_input")
            self._draw_button(target_up, "^", "number_step", (None, "target_mean", "editor_target", 1), small=True)
            self._draw_button(target_down, "v", "number_step", (None, "target_mean", "editor_target", -1), small=True)
        self.game.text("誤差", 11, MUTED, (target_card.left + 16, target_card.top + 98))
        spread_rect = pygame.Rect(target_card.left + 190, target_card.top + 88, 150, 34)
        self._draw_button(spread_rect, f"{self.target_spread}（クリックで変更）", "spread", small=True)
        self.game.text("チーム補正", 11, MUTED, (target_card.left + 16, target_card.top + 142))
        profile_rect = pygame.Rect(target_card.left + 190, target_card.top + 132, 150, 34)
        self._draw_button(
            profile_rect, f"{profile_label(self.editor_options, self.target_profile_id)}（変更）",
            "generation_profile", small=True,
        )
        available_profiles = generation_profiles(self.editor_options)
        selected_profile = next(
            (entry for entry in available_profiles if str(entry.get("id")) == self.target_profile_id),
            available_profiles[0],
        )
        self._text_fit(
            str(selected_profile.get("description", "")), 8, MUTED,
            pygame.Rect(target_card.left + 16, target_card.top + 169, target_card.width - 32, 16), center=True,
        )
        create_rect = pygame.Rect(target_card.left + 42, target_card.top + 190, target_card.width - 84, 38)
        self._draw_button(create_rect, "この条件で作成", "create_target", active=True)

    def _draw_edit(self) -> None:
        back = pygame.Rect(18, 68, 92, 34)
        save = pygame.Rect(WIDTH - 260, 68, 112, 34)
        validate = pygame.Rect(WIDTH - 140, 68, 122, 34)
        self._draw_button(back, "破棄して戻る" if self.confirm_back else "一覧へ戻る", "back", danger=self.confirm_back, small=True)
        self._draw_button(save, "JSONへ上書き" if self.source_path else "新規JSON保存", "save", active=True, small=True)
        issue_count = len(validate_payload(self.payload)) + len(self.load_issues)
        self._draw_button(validate, f"エラー {issue_count}件", "tab", "ERRORS", active=issue_count == 0, small=True)

        tab_x = 124
        available_width = max(540, save.left - tab_x - 10)
        tab_width = min(128, max(86, (available_width - max(0, len(self.tabs) - 1) * 6) // max(1, len(self.tabs))))
        for tab, label in self.tabs:
            rect = pygame.Rect(tab_x, 68, tab_width, 34)
            self._draw_button(rect, label, "tab", tab, active=self.tab == tab, small=True)
            tab_x += tab_width + 6

        content = pygame.Rect(18, 112, WIDTH - 36, HEIGHT - 156)
        pygame.draw.rect(self.game.screen, CARD, content, border_radius=10)
        pygame.draw.rect(self.game.screen, (190, 187, 175), content, 2, border_radius=10)
        if self.tab == "TEAM":
            self._draw_team_fields(content)
        elif self.tab == "INTRO":
            self._draw_team_description(content)
        elif self.tab == "UNIFORM":
            self.uniform_editor.draw(self, content)
        elif self.tab in ("PLAYER", "SKILLS"):
            self._draw_player_sidebar(content)
            if self.tab == "PLAYER":
                self._draw_player_fields(content)
            else:
                self._draw_skills(content)
        elif self.tab == "FORMATION":
            self._draw_formation(content)
        elif self.tab == "TUNER":
            self._draw_tuner(content)
        else:
            self._draw_errors(content)

    def _draw_team_fields(self, content: pygame.Rect) -> None:
        info = self.payload.setdefault("チーム情報", {})
        self.game.text("チーム情報", 20, INK, (content.left + 24, content.top + 18), bold=True)
        field_layout = (
            ("チーム名", "text"), ("チームの略称", "text"),
            ("監督名", "text"), ("チームカラー", "text"),
            ("ホームコート", "text"),
            ("ゾーン手前", "number"), ("ゾーン奥", "number"),
            ("戦術への忠実さ", "number"),
            ("戦術変更への積極性", "number"),
            ("選手交代への積極性", "number"),
            ("インテリジェンス", "number"),
        )
        for index, (key, kind) in enumerate(field_layout):
            column = index % 3
            row = index // 3
            rect = pygame.Rect(content.left + 32 + column * 390, content.top + 86 + row * 82, 350, 38)
            self._draw_input(rect, info, key, kind=kind, label=key)

        tactic_y = content.top + 455
        self.game.text("戦術", 11, MUTED, (content.left + 32, tactic_y - 19), bold=True)
        prev_rect = pygame.Rect(content.left + 32, tactic_y, 44, 38)
        value_rect = pygame.Rect(content.left + 82, tactic_y, 300, 38)
        next_rect = pygame.Rect(content.left + 388, tactic_y, 44, 38)
        self._draw_button(prev_rect, "◀", "tactic", -1)
        pygame.draw.rect(self.game.screen, FIELD_BG, value_rect, border_radius=5)
        pygame.draw.rect(self.game.screen, (188, 185, 173), value_rect, 2, border_radius=5)
        self._text_fit(info.get("戦術", ""), 14, INK, value_rect, bold=True, center=True)
        self._draw_button(next_rect, "▶", "tactic", 1)
        folder_rect = pygame.Rect(content.left + 500, tactic_y, 300, 38)
        self._draw_input(folder_rect, self.folder_settings, "フォルダ", label="保存フォルダ（teams内・空欄は直下）")
        self._draw_button(
            pygame.Rect(folder_rect.right + 12, tactic_y, 158, 38),
            "フォルダへ移動" if self.source_path else "保存先に設定", "folder_apply", small=True,
        )
        self.game.text("チーム名を保存するとJSONファイル名も同じ名前へ変わります。", 11, MUTED, (content.left + 500, tactic_y + 50), bold=True)
        self.game.text("忠実さは能力値ではありません。低いほど柔軟、高いほど指示を徹底します。", 11, MUTED, (content.left + 32, tactic_y + 54))

        color = str(info.get("チームカラー", ""))
        try:
            preview_color = pygame.Color(color)
        except ValueError:
            preview_color = ERROR_RED
        pygame.draw.rect(self.game.screen, preview_color, (content.right - 92, content.top + 24, 54, 36), border_radius=6)
        pygame.draw.rect(self.game.screen, INK, (content.right - 92, content.top + 24, 54, 36), 2, border_radius=6)
        self._draw_button(
            pygame.Rect(content.right - 184, content.top + 24, 82, 36),
            "色を選ぶ", "color_open", small=True,
        )

    def _draw_team_description(self, content: pygame.Rect) -> None:
        info = self.payload.setdefault("チーム情報", {})
        info.setdefault("チーム紹介", "")
        self.game.text("チーム紹介", 20, INK, (content.left + 24, content.top + 18), bold=True)
        self.game.text(
            "リーグ画面の詳細に表示。矢印・Home/End・クリックで移動、Backspace/Delete長押し対応。Ctrl+Enterで閉じます。",
            11, MUTED, (content.left + 24, content.top + 52),
        )
        self._draw_multiline_input(
            pygame.Rect(content.left + 28, content.top + 104, content.width - 56, content.height - 142),
            info,
            "チーム紹介",
            label="紹介文",
        )

    def _draw_color_picker(self) -> None:
        """Draw an HSV swatch dialog while keeping hexadecimal editing available."""
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((13, 18, 24, 190))
        self.game.screen.blit(shade, (0, 0))
        self._register_button(pygame.Rect(0, 0, WIDTH, HEIGHT), "color_close")
        card = pygame.Rect(WIDTH // 2 - 330, HEIGHT // 2 - 225, 660, 450)
        pygame.draw.rect(self.game.screen, (247, 245, 236), card, border_radius=15)
        pygame.draw.rect(self.game.screen, GOLD, card, 3, border_radius=15)
        self.game.text("チームカラーを選択", 22, INK, (card.left + 26, card.top + 20), bold=True)
        current = str(self.payload.setdefault("チーム情報", {}).get("チームカラー", "#D84442"))
        self.game.text(f"現在色  {current}", 12, MUTED, (card.left + 28, card.top + 55), bold=True)
        self._draw_button(pygame.Rect(card.right - 104, card.top + 18, 76, 34), "閉じる", "color_close", small=True)

        columns, rows = 12, 5
        gap = 7
        swatch_width = (card.width - 52 - gap * (columns - 1)) // columns
        swatch_height = 52
        for row in range(rows):
            saturation = 0.35 + row * 0.15
            value = 0.96 - row * 0.065
            for column in range(columns):
                red, green, blue = colorsys.hsv_to_rgb(column / columns, saturation, value)
                rgb = (round(red * 255), round(green * 255), round(blue * 255))
                hex_color = "#{:02X}{:02X}{:02X}".format(*rgb)
                rect = pygame.Rect(
                    card.left + 26 + column * (swatch_width + gap),
                    card.top + 91 + row * (swatch_height + 9),
                    swatch_width,
                    swatch_height,
                )
                pygame.draw.rect(self.game.screen, rgb, rect, border_radius=7)
                selected = current.upper() == hex_color
                pygame.draw.rect(self.game.screen, GOLD if selected else (72, 76, 80), rect, 3 if selected else 1, border_radius=7)
                self._register_button(rect, "color_pick", hex_color)
        self.game.text(
            "クリックで編集値へ反映します。保存するとJSONへ上書きされます。",
            11, MUTED, (card.centerx, card.bottom - 25), center=True,
        )

    def _draw_player_sidebar(self, content: pygame.Rect) -> None:
        side = pygame.Rect(content.left + 12, content.top + 12, 252, content.height - 24)
        pygame.draw.rect(self.game.screen, (232, 228, 213), side, border_radius=8)
        self.game.text(f"選手一覧  {len(self.players)}人", 15, INK, (side.left + 12, side.top + 10), bold=True)
        add_rect = pygame.Rect(side.right - 78, side.top + 7, 66, 28)
        self._draw_button(add_rect, "＋追加", "add_player", small=True)
        visible_count = 11
        self.player_scroll = min(self.player_scroll, max(0, len(self.players) - visible_count))
        for row, index in enumerate(range(self.player_scroll, min(len(self.players), self.player_scroll + visible_count))):
            player = self.players[index]
            y = side.top + 46 + row * 41
            rect = pygame.Rect(side.left + 8, y, side.width - 16, 35)
            selected = index == self.selected_player
            pygame.draw.rect(self.game.screen, GOLD if selected else (244, 240, 226), rect, border_radius=5)
            number = player.get("背番号", "-") if isinstance(player, dict) else "-"
            name = player.get("名前", f"選手{index + 1}") if isinstance(player, dict) else f"選手{index + 1}"
            pos = player.get("ポジション", "?") if isinstance(player, dict) else "?"
            self._text_fit(f"{number:>2}  {name}", 11, INK, pygame.Rect(rect.left + 6, rect.top, 164, rect.height), bold=selected)
            self._text_fit(pos, 9, MUTED, pygame.Rect(rect.right - 52, rect.top, 48, rect.height), center=True)
            self._register_button(rect, "select_player", index)
        if len(self.players) > visible_count:
            self.game.text("ホイールで一覧移動", 9, MUTED, (side.left + 54, side.bottom - 24))
        if self.current_player is not None:
            delete_rect = pygame.Rect(side.left + 12, side.bottom - 38, side.width - 24, 28)
            self._draw_button(delete_rect, "選択中の選手を削除", "delete_player", danger=True, small=True)

    def _draw_player_fields(self, content: pygame.Rect) -> None:
        player = self.current_player
        if player is None:
            self.game.text("選手を追加してください", 20, MUTED, (content.centerx, content.centery), center=True)
            return
        x0 = content.left + 286
        self.game.text("基本情報", 16, INK, (x0, content.top + 15), bold=True)
        identities = (("名前", "text"), ("選手ID", "text"), ("背番号", "number"), ("年齢", "number"), ("性別", "text"), ("戦術への忠実さ", "number"))
        for index, (key, kind) in enumerate(identities):
            col = index % 3
            row = index // 3
            rect = pygame.Rect(x0 + col * 306, content.top + 52 + row * 56, 274, 32)
            self._draw_input(rect, player, key, kind=kind, label=key)
        type_y = content.top + 154
        self.game.text("プレイヤータイプ", 11, MUTED, (x0, type_y - 18), bold=True)
        self._draw_button(pygame.Rect(x0, type_y, 38, 31), "◀", "player_type", -1, small=True)
        type_rect = pygame.Rect(x0 + 44, type_y, 224, 31)
        pygame.draw.rect(self.game.screen, FIELD_BG, type_rect, border_radius=5)
        pygame.draw.rect(self.game.screen, (188, 185, 173), type_rect, 2, border_radius=5)
        self._text_fit(player.get("プレイヤータイプ", ""), 12, INK, type_rect, bold=True, center=True)
        self._draw_button(pygame.Rect(x0 + 274, type_y, 38, 31), "▶", "player_type", 1, small=True)
        position = f"配置 X{player.get('ポジションX', '?')} / Y{player.get('ポジションY', '?')} / {player.get('ポジション', '?')}"
        self.game.text(position, 11, MUTED, (x0 + 342, type_y + 8))

        group_y = content.top + 202
        for index, group in enumerate(self.stat_groups):
            rect = pygame.Rect(x0 + index * 150, group_y, 142, 29)
            self._draw_button(rect, group, "stat_group", group, active=self.stat_group == group, small=True)
        fields = self.stat_groups.get(self.stat_group, ())
        stats_y = group_y + 52
        for index, key in enumerate(fields):
            col = index // 6
            row = index % 6
            rect = pygame.Rect(x0 + col * 462 + 210, stats_y + row * 48, 214, 30)
            label_rect = pygame.Rect(x0 + col * 462, stats_y + row * 48, 202, 30)
            self._text_fit(key, 10, MUTED, label_rect, bold=True)
            self._draw_input(rect, player, key, kind="number")

    def _draw_skills(self, content: pygame.Rect) -> None:
        player = self.current_player
        if player is None:
            self.game.text("選手を追加してください", 20, MUTED, (content.centerx, content.centery), center=True)
            return
        x0 = content.left + 286
        held = player.setdefault("スキル", [])
        if not isinstance(held, list):
            held = []
            player["スキル"] = held
        self.game.text(f"{player.get('名前', '選手')} のスキル　{len(held)}/{len(self.editor_skills)}", 17, INK, (x0, content.top + 18), bold=True)
        all_rect = pygame.Rect(content.right - 218, content.top + 12, 88, 30)
        clear_rect = pygame.Rect(content.right - 122, content.top + 12, 88, 30)
        self._draw_button(all_rect, "全選択", "skills_all", small=True)
        self._draw_button(clear_rect, "全解除", "skills_clear", small=True)
        for index, skill in enumerate(self.editor_skills):
            col = index // 10
            row = index % 10
            rect = pygame.Rect(x0 + col * 232, content.top + 58 + row * 46, 220, 36)
            checked = skill in held
            pygame.draw.rect(self.game.screen, FIELD_ACTIVE if checked else FIELD_BG, rect, border_radius=5)
            pygame.draw.rect(self.game.screen, GOLD if checked else (188, 185, 173), rect, 2, border_radius=5)
            box = pygame.Rect(rect.left + 8, rect.top + 8, 19, 19)
            pygame.draw.rect(self.game.screen, GOLD if checked else (224, 221, 209), box, border_radius=3)
            pygame.draw.rect(self.game.screen, INK, box, 1, border_radius=3)
            if checked:
                self.game.text("✓", 14, INK, box.center, bold=True, center=True)
            self._text_fit(skill, 10, INK, pygame.Rect(rect.left + 31, rect.top, rect.width - 33, rect.height), bold=checked)
            self._register_button(rect, "toggle_skill", skill)

    def _draw_formation(self, content: pygame.Rect) -> None:
        self.game.text("15×10 フォーメーションエディタ", 17, INK, (content.left + 18, content.top + 12), bold=True)
        self.game.text("選手を選び、マスをクリックして配置。既に選手がいれば位置を交換します。", 10, MUTED, (content.left + 290, content.top + 18))
        template_x = content.left + 18
        for index, formation in enumerate(self.formation_templates):
            rect = pygame.Rect(template_x + index * 116, content.top + 48, 108, 29)
            self._draw_button(rect, formation, "formation_template", formation, small=True)

        grid = pygame.Rect(content.left + 56, content.top + 94, 675, 410)
        cell_w, cell_h = grid.width // 15, grid.height // 10
        for y in range(1, 11):
            for x in range(1, 16):
                rect = pygame.Rect(grid.left + (x - 1) * cell_w, grid.top + (y - 1) * cell_h, cell_w, cell_h)
                pygame.draw.rect(self.game.screen, GRID_GREEN_A if (x + y) % 2 else GRID_GREEN_B, rect)
                pygame.draw.rect(self.game.screen, (185, 218, 182), rect, 1)
                self._register_button(rect, "formation_cell", (x, y))
        for x in range(1, 16):
            self.game.text(str(x), 9, MUTED, (grid.left + (x - 1) * cell_w + cell_w // 2, grid.top - 10), center=True)
        for y in range(1, 11):
            self.game.text(str(y), 9, MUTED, (grid.left - 16, grid.top + (y - 1) * cell_h + cell_h // 2 - 5), center=True)
        self.game.text("前線（Y=1）", 9, MUTED, (grid.right + 8, grid.top + 4))
        self.game.text("自陣（Y=10）", 9, MUTED, (grid.right + 8, grid.bottom - 16))

        positions: dict[tuple[int, int], list[tuple[int, dict]]] = {}
        bench: list[tuple[int, dict]] = []
        keeper_entries: list[tuple[int, dict]] = []
        for index, player in enumerate(self.players):
            if not isinstance(player, dict):
                continue
            try:
                x, y = int(player.get("ポジションX", 0)), int(player.get("ポジションY", 0))
            except (TypeError, ValueError):
                bench.append((index, player))
                continue
            if y == 0:
                bench.append((index, player))
            elif y == 11:
                keeper_entries.append((index, player))
            elif 1 <= x <= 15 and 1 <= y <= 10:
                positions.setdefault((x, y), []).append((index, player))
        for (x, y), occupants in positions.items():
            center = pygame.Vector2(grid.left + (x - 0.5) * cell_w, grid.top + (y - 0.5) * cell_h)
            for offset, (index, player) in enumerate(occupants):
                point = center + pygame.Vector2((offset % 2) * 9 - 4, (offset // 2) * 8)
                selected = index == self.selected_player
                pygame.draw.circle(self.game.screen, GOLD if selected else HOME_RED, point, 14)
                pygame.draw.circle(self.game.screen, CREAM, point, 14, 2)
                self.game.text(str(player.get("背番号", "?")), 9, INK, point, bold=True, center=True)
                pick = pygame.Rect(round(point.x - 15), round(point.y - 15), 30, 30)
                self._register_button(pick, "select_player", index)

        keeper_box = pygame.Rect(grid.centerx - 110, grid.bottom + 8, 220, 32)
        pygame.draw.rect(self.game.screen, (55, 111, 72), keeper_box, border_radius=6)
        keeper_label = "GKゾーン（Xは中央固定）"
        if keeper_entries:
            index, player = keeper_entries[0]
            keeper_label = f"GK  {player.get('背番号', '?')} {player.get('名前', '')}"
            self._register_button(keeper_box, "select_player", index)
            if index == self.selected_player:
                pygame.draw.rect(self.game.screen, GOLD, keeper_box, 3, border_radius=6)
        self._text_fit(keeper_label, 10, CREAM, keeper_box, bold=True, center=True)
        self._register_button(keeper_box, "formation_gk")

        side = pygame.Rect(content.left + 760, content.top + 92, content.width - 780, content.height - 110)
        pygame.draw.rect(self.game.screen, (232, 228, 213), side, border_radius=8)
        self.game.text("配置する選手", 14, INK, (side.left + 12, side.top + 10), bold=True)
        for row, index in enumerate(range(self.player_scroll, min(len(self.players), self.player_scroll + 10))):
            player = self.players[index]
            rect = pygame.Rect(side.left + 8, side.top + 42 + row * 39, side.width - 16, 33)
            selected = index == self.selected_player
            pygame.draw.rect(self.game.screen, GOLD if selected else FIELD_BG, rect, border_radius=5)
            self._text_fit(f"{player.get('背番号', '?')} {player.get('名前', '')}  {player.get('ポジション', '')}", 10, INK, rect, bold=selected)
            self._register_button(rect, "select_player", index)
        if len(self.players) > 10:
            self.game.text("ホイールで選手移動", 9, MUTED, (side.left + 24, side.bottom - 20))

    def _draw_tuner(self, content: pygame.Rect) -> None:
        settings = self._ensure_tuner_settings()
        targets = settings["基準値ステータス"]
        summaries = payload_category_summary(self.payload, self.tuner_categories)
        info = self.payload.get("チーム情報", {})
        self.game.text("チームチューナー", 20, INK, (content.left + 22, content.top + 15), bold=True)
        self.game.text(
            f"{info.get('チーム名', 'チーム')}　戦術:{info.get('戦術', '?')}　"
            f"ゾーン:{info.get('ゾーン手前', '?')}〜{info.get('ゾーン奥', '?')}　忠実さ:{info.get('戦術への忠実さ', '?')}",
            11, MUTED, (content.left + 215, content.top + 22),
        )

        rank_colors = {
            "S": (190, 123, 25), "A": (42, 137, 78), "B": (52, 116, 171),
            "C": (97, 106, 119), "D": (147, 98, 72), "E": ERROR_RED,
        }
        left_x = content.left + 22
        selected = self.current_player
        player_name = selected.get("名前", "選手なし") if selected else "選手なし"
        scope_is_player = self.tuner_adjust_scope == "player" and selected is not None
        scope_label = f"選手単体：{player_name}" if scope_is_player else "チーム全体"
        scope_rect = pygame.Rect(left_x, content.top + 48, 694, 27)
        pygame.draw.rect(self.game.screen, GOLD if scope_is_player else OK_GREEN, scope_rect, border_radius=6)
        self.game.text(f"現在の表示・調整対象　{scope_label}", 11, INK if scope_is_player else CREAM, (scope_rect.left + 12, scope_rect.top + 6), bold=True)

        cards_top = content.top + 82
        card_width, card_height = 224, 91
        for index, category in enumerate(self.tuner_categories):
            col, row = index % 3, index // 3
            card = pygame.Rect(left_x + col * 235, cards_top + row * 101, card_width, card_height)
            pygame.draw.rect(self.game.screen, (237, 233, 217), card, border_radius=7)
            pygame.draw.rect(self.game.screen, (194, 190, 177), card, 2, border_radius=7)
            label = str(category.get("label", category.get("id", "能力")))
            if category.get("hidden"):
                label += "  ※裏"
            self._text_fit(label, 11, INK, pygame.Rect(card.left + 8, card.top + 4, card.width - 16, 20), bold=True)
            category_id = str(category.get("id"))
            self.game.text("基準", 9, MUTED, (card.left + 9, card.top + 40), bold=True)
            target_rect = pygame.Rect(card.left + 39, card.top + 31, 70, 30)
            self._draw_input(target_rect, targets, category_id, kind="number")
            team_average, team_grade = summaries.get(category_id, (0.0, "E"))
            player_average = category_average(selected, category) if selected is not None else 0.0
            player_grade = rank_for_average(player_average) if selected is not None else "E"
            display_average = player_average if scope_is_player else team_average
            display_grade = player_grade if scope_is_player else team_grade
            display_prefix = "PLAYER" if scope_is_player else "TEAM"
            self.game.text(f"{display_prefix} {display_average:.0f}", 9, MUTED, (card.left + 117, card.top + 32))
            self.game.text(display_grade, 22, rank_colors.get(display_grade, INK), (card.right - 20, card.top + 28), bold=True, center=True)
            if selected is not None:
                try:
                    target_average = float(targets.get(category_id, round(PLAYER_STAT_DEFAULT)) or round(PLAYER_STAT_DEFAULT))
                except (TypeError, ValueError):
                    target_average = float(self.tuner_options.get("default_target", round(PLAYER_STAT_DEFAULT)))
                secondary_label = (
                    f"TEAM {team_average:.0f}  {team_grade}"
                    if scope_is_player else f"選手 {player_average:.0f}  {player_grade}"
                )
                self.game.text(
                    f"{secondary_label}　目標{rank_for_average(target_average)}",
                    9, MUTED, (card.left + 117, card.top + 56),
                )

        player_y = content.bottom - 104
        pygame.draw.line(self.game.screen, (202, 198, 184), (left_x, player_y - 12), (left_x + 694, player_y - 12), 2)
        self.game.text(f"単体調整対象：{player_name}", 12, INK, (left_x, player_y), bold=True)
        self._draw_button(pygame.Rect(left_x + 190, player_y - 5, 36, 29), "◀", "tuner_player", -1, small=True)
        self._draw_button(pygame.Rect(left_x + 232, player_y - 5, 36, 29), "▶", "tuner_player", 1, small=True)
        self._draw_button(
            pygame.Rect(left_x, player_y + 34, 176, 38),
            "● 選手単体" if scope_is_player else "選手単体",
            "tuner_scope_player", active=scope_is_player, small=True,
        )
        self._draw_button(
            pygame.Rect(left_x + 186, player_y + 34, 176, 38),
            "● チーム全体" if not scope_is_player else "チーム全体",
            "tuner_scope_team", active=not scope_is_player, small=True,
        )
        self._draw_button(
            pygame.Rect(left_x + 372, player_y + 34, 322, 38),
            "選択中の対象を基準値へ自動調整",
            "tuner_adjust_selected", small=True,
        )
        self.game.text("左の2ボタンは対象の切り替えだけです。右ボタンを押した時だけ能力値を変更します", 9, MUTED, (left_x + 4, player_y + 78))

        side = pygame.Rect(content.left + 736, content.top + 54, content.width - 756, content.height - 72)
        pygame.draw.rect(self.game.screen, (232, 228, 213), side, border_radius=8)
        pygame.draw.rect(self.game.screen, (194, 190, 177), side, 2, border_radius=8)
        self.game.text("ヘッドレス試合シミュレーション", 15, INK, (side.left + 14, side.top + 10), bold=True)

        convergence_only = settings.get("終了条件") == "収束まで"
        self.game.text("時間上限（秒）" if not convergence_only else "時間（不使用）", 10, MUTED, (side.left + 14, side.top + 48), bold=True)
        time_rect = pygame.Rect(side.left + 126, side.top + 39, 82, 30)
        self._draw_input(time_rect, settings, "時間上限秒", kind="number")
        hidden = bool(settings.get("裏パラメータ自動調整", True))
        option_width = (side.width - 250) // 3
        self._draw_button(
            pygame.Rect(side.left + 220, side.top + 39, option_width, 30),
            "終了：収束まで" if convergence_only else "終了：時間上限",
            "tuner_end_mode", active=convergence_only, small=True,
        )
        self._draw_button(
            pygame.Rect(side.left + 226 + option_width, side.top + 39, option_width, 30),
            f"裏能力 {'ON' if hidden else 'OFF'}", "tuner_hidden", active=hidden, small=True,
        )
        accuracy_mode = settings.get("評価モード", "精度重視") != "速度重視"
        speed_minutes = float(self.tuner_options.get("speed_evaluation_minutes", 5.0))
        self._draw_button(
            pygame.Rect(side.left + 232 + option_width * 2, side.top + 39, option_width, 30),
            "精度重視" if accuracy_mode else f"速度{speed_minutes:g}分", "tuner_evaluation_mode",
            active=accuracy_mode, small=True,
        )

        opponents = self._available_tuner_opponents()
        active_session = self.tuner_session
        visible_count = 8
        self.tuner_opponent_scroll = min(self.tuner_opponent_scroll, max(0, len(opponents) - visible_count))
        self.game.text(
            f"対戦相手（複数選択） {len(self.tuner_opponents)}チーム", 11, INK,
            (side.left + 14, side.top + 84), bold=True,
        )
        if len(opponents) > visible_count:
            self._draw_button(pygame.Rect(side.right - 72, side.top + 78, 26, 25), "▲", "tuner_opp_scroll", -1, small=True)
            self._draw_button(pygame.Rect(side.right - 40, side.top + 78, 26, 25), "▼", "tuner_opp_scroll", 1, small=True)
        for row, choice in enumerate(opponents[self.tuner_opponent_scroll:self.tuner_opponent_scroll + visible_count]):
            choice_id = str(choice.get("id"))
            y = side.top + 112 + row * 34
            rect = pygame.Rect(side.left + 12, y, side.width - 24, 29)
            selected_opponent = choice_id in self.tuner_opponents
            pygame.draw.rect(self.game.screen, FIELD_ACTIVE if selected_opponent else FIELD_BG, rect, border_radius=5)
            pygame.draw.rect(self.game.screen, GOLD if selected_opponent else (188, 185, 173), rect, 2, border_radius=5)
            box = pygame.Rect(rect.left + 7, rect.top + 6, 17, 17)
            pygame.draw.rect(self.game.screen, GOLD if selected_opponent else BUTTON, box, border_radius=3)
            self.game.text("✓" if selected_opponent else "", 12, INK, box.center, bold=True, center=True)
            opponent_label = str(choice.get("name", "TEAM"))
            if active_session is not None and selected_opponent:
                weight, match_class = active_session.opponent_weight_info(choice)
                if active_session.opponent_weights_ready:
                    if active_session.evaluation_mode == "accuracy":
                        active_label = "全評価"
                    else:
                        active_label = "重点" if active_session.opponent_is_active(choice) else "予備"
                    opponent_label += f"　×{weight:.2f} {match_class} [{active_label}]"
                elif not active_session.finished:
                    opponent_label += "　偵察中"
            self._text_fit(opponent_label, 10, INK, pygame.Rect(rect.left + 30, rect.top, rect.width - 36, rect.height), bold=selected_opponent)
            self._register_button(rect, "tuner_opponent", choice_id)

        session = self.tuner_session
        start_rect = pygame.Rect(side.left + 14, side.bottom - 87, side.width - 28, 39)
        if session is not None and not session.finished:
            self._draw_button(start_rect, "シミュレーションを中止", "tuner_cancel", danger=True)
        else:
            self._draw_button(start_rect, "チーム全体を試合でチューニング開始", "tuner_start", active=True)
        progress = session.progress if session is not None else 0.0
        bar = pygame.Rect(side.left + 14, side.bottom - 38, side.width - 28, 12)
        pygame.draw.rect(self.game.screen, (190, 188, 178), bar, border_radius=5)
        if progress > 0:
            fill = bar.copy()
            fill.width = round(bar.width * progress)
            pygame.draw.rect(self.game.screen, GOLD if session and not session.finished else OK_GREEN, fill, border_radius=5)
        status = session.status_text() if session is not None else "各分野の開始時平均を±10以内に固定し、能力配分だけを試合で最適化します"
        self._text_fit(status, 9, MUTED, pygame.Rect(side.left + 14, side.bottom - 24, side.width - 28, 18), bold=session is not None)

    def _draw_errors(self, content: pygame.Rect) -> None:
        issues = [*self.load_issues, *validate_payload(self.payload)]
        self.game.text("JSON・試合読込エラー", 18, INK, (content.left + 22, content.top + 16), bold=True)
        repair_rect = pygame.Rect(content.right - 258, content.top + 12, 112, 34)
        recheck_rect = pygame.Rect(content.right - 138, content.top + 12, 112, 34)
        self._draw_button(repair_rect, "自動修正", "repair", active=True, small=True)
        self._draw_button(recheck_rect, "再検証", "recheck", small=True)
        if not issues:
            pygame.draw.circle(self.game.screen, OK_GREEN, (content.centerx, content.centery - 28), 32)
            self.game.text("✓", 32, CREAM, (content.centerx, content.centery - 31), bold=True, center=True)
            self.game.text("エラーはありません。試合に読み込めます。", 18, OK_GREEN, (content.centerx, content.centery + 25), bold=True, center=True)
            return
        self.game.text(f"{len(issues)}件あります。途中保存は可能です。", 12, ERROR_RED, (content.left + 22, content.top + 54), bold=True)
        self.error_scroll = min(self.error_scroll, max(0, len(issues) - 15))
        for row, issue in enumerate(issues[self.error_scroll:self.error_scroll + 15]):
            y = content.top + 85 + row * 31
            rect = pygame.Rect(content.left + 20, y, content.width - 40, 27)
            pygame.draw.rect(self.game.screen, (255, 233, 225) if row % 2 == 0 else (250, 239, 226), rect, border_radius=4)
            self._text_fit(str(issue), 10, ERROR_RED, rect, bold=True)
        if len(issues) > 15:
            self.game.text("マウスホイールで続きを表示", 10, MUTED, (content.centerx, content.bottom - 20), center=True)

    def handle_event(self, event: pygame.event.Event, mouse_pos: tuple[int, int] | None = None) -> None:
        if event.type == pygame.WINDOWFOCUSLOST:
            self.held_number_step = None
            self._stop_text_delete_hold()
            return
        if event.type == pygame.KEYUP and event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            if self.held_text_delete == event.key:
                self._stop_text_delete_hold()
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.held_number_step = None
            self.number_hold_elapsed = 0.0
            self.number_hold_repeat = 0.0
            return
        if event.type == pygame.TEXTINPUT:
            self._handle_text(event.text)
            self.ime_composition = ""
            return
        if event.type == pygame.TEXTEDITING:
            self.ime_composition = event.text if self.active_input is not None else ""
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.color_picker_open:
                    self.color_picker_open = False
                    return
                if self.active_input is not None:
                    self.active_input = None
                    self.ime_composition = ""
                    self._stop_text_delete_hold()
                elif self.mode == "EDIT":
                    self._back_to_list()
                else:
                    self.game.close_team_editor()
                return
            if event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL and self.active_input is not None:
                target, key, kind = self.active_input
                if kind == "editor_target":
                    self.target_mean = ""
                else:
                    target[key] = ""
                    self._mark_dirty()
                    if kind == "multiline":
                        self.multiline_cursor = 0
                        self.multiline_preferred_x = None
                self.input_replace_pending = False
                return
            if event.key == pygame.K_BACKSPACE and self.active_input is not None:
                target, key, kind = self.active_input
                if kind == "multiline":
                    if not self.ime_composition:
                        self._start_text_delete_hold(event.key)
                    return
                if kind == "editor_target":
                    self.target_mean = self.target_mean[:-1]
                else:
                    target[key] = str(target.get(key, ""))[:-1]
                    self._mark_dirty()
                self.input_replace_pending = False
                return
            if event.key == pygame.K_DELETE and self.active_input is not None:
                if self.active_input[2] == "multiline":
                    if not self.ime_composition:
                        self._start_text_delete_hold(event.key)
                    return
            if (
                event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN, pygame.K_HOME, pygame.K_END)
                and self.active_input is not None
                and self.active_input[2] == "multiline"
            ):
                if not self.ime_composition:
                    self._move_multiline_cursor(event.key, control=bool(event.mod & pygame.KMOD_CTRL))
                return
            if event.key in (pygame.K_UP, pygame.K_DOWN) and self.active_input is not None:
                target, key, kind = self.active_input
                if kind in ("number", "editor_target"):
                    self._step_numeric(target if kind == "number" else None, key, kind, 1 if event.key == pygame.K_UP else -1)
                    return
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
                if (
                    event.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                    and self.active_input is not None
                    and self.active_input[2] == "multiline"
                    and not event.mod & pygame.KMOD_CTRL
                ):
                    if not self.ime_composition:
                        self._insert_multiline_text("\n")
                    return
                self._stop_text_delete_hold()
                self.active_input = None
                return
        if event.type == pygame.MOUSEWHEEL:
            if self.mode == "LIST":
                self.list_scroll = max(0, min(max(0, self._browser_item_count() - 9), self.list_scroll - event.y))
            elif self.tab == "ERRORS":
                count = len(self.load_issues) + len(validate_payload(self.payload))
                self.error_scroll = max(0, min(max(0, count - 15), self.error_scroll - event.y))
            elif self.tab == "TUNER":
                count = len(self._available_tuner_opponents())
                self.tuner_opponent_scroll = max(0, min(max(0, count - 8), self.tuner_opponent_scroll - event.y))
            elif self.tab in ("PLAYER", "SKILLS", "FORMATION"):
                visible = 10 if self.tab == "FORMATION" else 11
                self.player_scroll = max(0, min(max(0, len(self.players) - visible), self.player_scroll - event.y))
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1 or mouse_pos is None:
            return
        self.held_number_step = None
        self._stop_text_delete_hold()
        if self.color_picker_open:
            for rect, action, data in reversed(self.buttons):
                if rect.collidepoint(mouse_pos):
                    self._perform(action, data)
                    return
        for rect, target, key, kind in reversed(self.input_fields):
            if rect.collidepoint(mouse_pos):
                was_active = self.active_input is not None and self.active_input[0] is target and self.active_input[1] == key
                self.active_input = (target, key, kind)
                self.input_replace_pending = kind != "multiline"
                self.ime_composition = ""
                if kind == "multiline":
                    if not was_active:
                        self.multiline_view_start = 0
                    self._place_multiline_cursor(rect, target, key, mouse_pos)
                return
        self.active_input = None
        self.ime_composition = ""
        self.input_replace_pending = False
        for rect, action, data in reversed(self.buttons):
            if rect.collidepoint(mouse_pos):
                self._perform(action, data)
                return

    def _handle_text(self, text: str) -> None:
        if self.active_input is None:
            return
        target, key, kind = self.active_input
        if kind in ("number", "editor_target"):
            text = "".join(character for character in text if character.isdigit())
        elif kind == "multiline":
            self._stop_text_delete_hold()
            self._insert_multiline_text(text)
            return
        else:
            text = text.replace("\r", "").replace("\n", "")
        if not text:
            return
        if self.input_replace_pending:
            if kind == "editor_target":
                self.target_mean = ""
            else:
                target[key] = ""
            self.input_replace_pending = False
        if kind == "editor_target":
            self.target_mean = (self.target_mean + text)[:4]
        else:
            limit = 4000 if kind == "multiline" else 80
            target[key] = (str(target.get(key, "")) + text)[:limit]
            self._mark_dirty()

    def _perform(self, action: str, data: Any) -> None:
        if action.startswith("uniform_") and self.uniform_editor.perform(self, action, data):
            return
        if action == "color_open":
            self.color_picker_open = True
            self.active_input = None
            return
        if action == "color_close":
            self.color_picker_open = False
            return
        if action == "color_pick":
            self.payload.setdefault("チーム情報", {})["チームカラー"] = str(data)
            self.color_picker_open = False
            self._mark_dirty()
            self._set_message(f"チームカラーを {data} に変更しました", OK_GREEN)
            return
        if action == "open_folder":
            self.current_folder = Path(data).resolve().relative_to(TEAMS_DIR.resolve())
            self.list_scroll = 0
            self.pending_delete = None
            self.refresh_files()
            return
        if action == "folder_up":
            self.current_folder = self.current_folder.parent if self.current_folder != Path() else Path()
            if self.current_folder == Path("."):
                self.current_folder = Path()
            self.list_scroll = 0
            self.pending_delete = None
            self.refresh_files()
            return
        if action == "close":
            if self.mode == "EDIT" and self.dirty and not self.confirm_back:
                self.confirm_back = True
                self._set_message("未保存です。閉じる前に保存するか、もう一度閉じるを押してください", ERROR_RED)
            else:
                self.game.close_team_editor()
        elif action == "open":
            self.payload, self.load_issues = load_editor_payload(data)
            self.source_path = data
            relative_parent = team_relative_path(data).parent
            self.folder_settings["フォルダ"] = "" if relative_parent == Path(".") else relative_parent.as_posix()
            self.mode, self.tab = "EDIT", "TEAM"
            self.selected_player = self.player_scroll = self.error_scroll = 0
            self.dirty = False
            self.pending_delete = None
            self._ensure_tuner_settings()
            self._reset_tuner_selection()
            self._set_message(f"{data.name} を開きました")
        elif action == "delete":
            target_entry = next((entry for entry in self.team_entries if entry[0] == data), None)
            valid_count = sum(1 for _, _, issues in scan_team_files() if not issues)
            if target_entry is not None and not target_entry[2] and valid_count <= 1:
                self._set_message("最後の試合可能チームは削除できません。先に別チームを完成・保存してください", ERROR_RED)
                return
            if self.pending_delete != data:
                self.pending_delete = data
                self._set_message(f"削除確認：{data.name} の削除ボタンをもう一度押してください", ERROR_RED)
            else:
                try:
                    delete_team_file(data)
                    self.pending_delete = None
                    self.refresh_files()
                    self.game.refresh_team_choices()
                    self._set_message(f"{data.name} を削除しました", ERROR_RED)
                except (OSError, ValueError) as error:
                    self._set_message(f"削除できません: {error}", ERROR_RED)
        elif action == "list_up":
            self.list_scroll = max(0, self.list_scroll - 1)
        elif action == "list_down":
            self.list_scroll = min(max(0, self._browser_item_count() - 9), self.list_scroll + 1)
        elif action == "template_scroll":
            templates = [item for item in self.editor_options.get("team_templates", ()) if isinstance(item, dict)]
            self.template_scroll = max(0, min(max(0, len(templates) - 2), self.template_scroll + int(data)))
        elif action.startswith("create_"):
            mode = action.removeprefix("create_")
            try:
                target = int(self.target_mean or round(PLAYER_STAT_DEFAULT))
            except ValueError:
                target = round(PLAYER_STAT_DEFAULT)
            self.payload = create_team_template(
                mode, target=target, spread=self.target_spread, rng=self.rng,
                options=self.editor_options, profile_id=self.target_profile_id,
            )
            self.source_path = None
            self.folder_settings["フォルダ"] = ""
            self.load_issues = []
            self.mode, self.tab = "EDIT", "TEAM"
            self.selected_player = self.player_scroll = self.error_scroll = 0
            self.dirty = True
            self._ensure_tuner_settings()
            self._reset_tuner_selection()
            self._set_message("新規チームを作成しました。名前を変更して途中保存できます")
        elif action == "target_input":
            if self.target_input_mode == "rank":
                return
            self.active_input = ({}, "target", "editor_target")
            self.input_replace_pending = True
        elif action == "target_mode":
            if self.target_input_mode == "number":
                try:
                    numeric_target = float(self.target_mean)
                except ValueError:
                    numeric_target = PLAYER_STAT_DEFAULT
                self.target_rank = rank_for_average(numeric_target)
                self.target_mean = str(target_for_rank(self.target_rank))
                self.target_input_mode = "rank"
                self.active_input = None
            else:
                self.target_input_mode = "number"
        elif action == "target_rank_step":
            labels = rank_labels()
            if self.target_rank not in labels:
                self.target_rank = rank_for_average(float(self.target_mean or PLAYER_STAT_DEFAULT))
            index = (labels.index(self.target_rank) + int(data)) % len(labels)
            self.target_rank = labels[index]
            self.target_mean = str(target_for_rank(self.target_rank))
            self.active_input = None
        elif action == "generation_profile":
            profiles = generation_profiles(self.editor_options)
            ids = tuple(str(entry.get("id")) for entry in profiles)
            index = ids.index(self.target_profile_id) if self.target_profile_id in ids else 0
            self.target_profile_id = ids[(index + 1) % len(ids)]
        elif action == "number_step":
            target, key, kind, delta = data
            self._step_numeric(target, key, kind, int(delta))
            self.held_number_step = (target, key, kind, int(delta))
            self.number_hold_elapsed = 0.0
            self.number_hold_repeat = 0.0
        elif action == "spread":
            spreads = tuple(str(value) for value in self.editor_options.get("spread_options", ("小", "中", "大"))) or ("小", "中", "大")
            if self.target_spread not in spreads:
                self.target_spread = spreads[0]
            self.target_spread = spreads[(spreads.index(self.target_spread) + 1) % len(spreads)]
        elif action == "back":
            self._back_to_list()
        elif action == "save":
            try:
                overwriting = self.source_path is not None
                old_path = self.source_path
                old_id = team_id_for_path(old_path) if old_path is not None else ""
                self.source_path = save_editor_payload(
                    self.payload, self.source_path, self.folder_settings.get("フォルダ", ""),
                )
                new_id = team_id_for_path(self.source_path)
                relative_parent = team_relative_path(self.source_path).parent
                self.folder_settings["フォルダ"] = "" if relative_parent == Path(".") else relative_parent.as_posix()
                self.current_folder = Path() if relative_parent == Path(".") else relative_parent
                if old_id and old_id != new_id:
                    self.game.league_manager.rename_team_reference(old_id, new_id)
                    for choice in self.game.team_choices:
                        if choice.get("id") == old_id:
                            choice["id"] = new_id
                            choice["source"] = team_relative_path(self.source_path).as_posix()
                self.dirty = False
                self.confirm_back = False
                self.load_issues = []
                self.refresh_files()
                self.game.refresh_team_choices()
                count = len(validate_payload(self.payload))
                suffix = "試合に読込可能" if count == 0 else f"エラー{count}件のまま途中保存"
                save_kind = "上書き保存" if overwriting else "新規保存"
                relative_name = team_relative_path(self.source_path).as_posix()
                changed_path = old_path is not None and old_path.resolve() != self.source_path.resolve()
                if changed_path:
                    save_kind = "ファイル名・保存フォルダを更新"
                self._set_message(f"{relative_name} を{save_kind}しました（{suffix}）", OK_GREEN if count == 0 else ERROR_RED)
            except (OSError, ValueError) as error:
                self._set_message(f"保存できません: {error}", ERROR_RED)
        elif action == "folder_apply":
            self._perform("save", None)
        elif action == "tab":
            self.tab = data
            self.active_input = None
            self.error_scroll = 0
        elif action == "tactic":
            info = self.payload.setdefault("チーム情報", {})
            tactics = tuple(value for value in self.editor_options.get("tactics", TACTIC_NAMES) if value in TACTIC_NAMES) or tuple(TACTIC_NAMES)
            current = info.get("戦術")
            index = tactics.index(current) if current in tactics else 0
            info["戦術"] = tactics[(index + int(data)) % len(tactics)]
            self._mark_dirty()
        elif action == "select_player":
            self.selected_player = int(data)
            self.active_input = None
        elif action == "add_player":
            self.selected_player = add_default_player(self.payload, self.rng)
            self.player_scroll = max(0, self.selected_player - 10)
            self.tab = "PLAYER"
            self._mark_dirty()
            self._set_message("控え選手を追加しました。フォーメーションで先発配置できます")
        elif action == "delete_player":
            if self.current_player is not None:
                removed = self.players.pop(self.selected_player)
                self.selected_player = max(0, min(self.selected_player, len(self.players) - 1))
                self._mark_dirty()
                self._set_message(f"{removed.get('名前', '選手')} を削除しました", ERROR_RED)
        elif action == "player_type":
            player = self.current_player
            if player is not None:
                current = player.get("プレイヤータイプ")
                index = self.player_types.index(current) if current in self.player_types else 0
                player["プレイヤータイプ"] = self.player_types[(index + int(data)) % len(self.player_types)]
                self._mark_dirty()
        elif action == "stat_group":
            self.stat_group = str(data)
        elif action == "toggle_skill":
            player = self.current_player
            if player is not None:
                skills = player.setdefault("スキル", [])
                if data in skills:
                    skills.remove(data)
                else:
                    skills.append(data)
                self._mark_dirty()
        elif action == "skills_all":
            if self.current_player is not None:
                self.current_player["スキル"] = list(self.editor_skills)
                self._mark_dirty()
        elif action == "skills_clear":
            if self.current_player is not None:
                self.current_player["スキル"] = []
                self._mark_dirty()
        elif action == "formation_template":
            apply_formation(self.payload, str(data), self.formation_templates)
            self._mark_dirty()
            self._set_message(f"{data}を適用しました。現在位置が近い選手から割り当てています")
        elif action == "formation_cell":
            self._place_selected(*data)
        elif action == "formation_gk":
            self._place_selected(8, 11)
        elif action == "repair":
            self.payload = repair_payload(self.payload, self.rng)
            self.load_issues = []
            self.selected_player = min(self.selected_player, max(0, len(self.players) - 1))
            self._mark_dirty()
            remaining = len(validate_payload(self.payload))
            self._set_message("必要なキーと不正値を自動修正しました" if remaining == 0 else f"自動修正後も{remaining}件を確認してください", OK_GREEN if remaining == 0 else ERROR_RED)
        elif action == "recheck":
            count = len(validate_payload(self.payload))
            self._set_message("エラーはありません" if count == 0 else f"{count}件のエラーがあります", OK_GREEN if count == 0 else ERROR_RED)
        elif action == "tuner_player":
            if self.players:
                self.selected_player = (self.selected_player + int(data)) % len(self.players)
                self.tuner_adjust_scope = "player"
        elif action == "tuner_hidden":
            if self.tuner_session is not None and not self.tuner_session.finished:
                return
            settings = self._ensure_tuner_settings()
            settings["裏パラメータ自動調整"] = not bool(settings.get("裏パラメータ自動調整", True))
            self._mark_dirty()
        elif action == "tuner_end_mode":
            if self.tuner_session is not None and not self.tuner_session.finished:
                return
            settings = self._ensure_tuner_settings()
            settings["終了条件"] = "時間上限" if settings.get("終了条件") == "収束まで" else "収束まで"
            self._mark_dirty()
            self._set_message(f"チューナーの終了条件を「{settings['終了条件']}」に切り替えました", OK_GREEN)
        elif action == "tuner_evaluation_mode":
            if self.tuner_session is not None and not self.tuner_session.finished:
                return
            settings = self._ensure_tuner_settings()
            settings["評価モード"] = "速度重視" if settings.get("評価モード") == "精度重視" else "精度重視"
            self._set_message(f"チューナーを「{settings['評価モード']}」に切り替えました", OK_GREEN)
        elif action == "tuner_opponent":
            choice_id = str(data)
            if choice_id in self.tuner_opponents:
                self.tuner_opponents.remove(choice_id)
            else:
                self.tuner_opponents.add(choice_id)
        elif action == "tuner_opp_scroll":
            maximum = max(0, len(self._available_tuner_opponents()) - 8)
            self.tuner_opponent_scroll = max(0, min(maximum, self.tuner_opponent_scroll + int(data)))
        elif action in ("tuner_scope_player", "tuner_scope_team"):
            self.tuner_adjust_scope = "player" if action == "tuner_scope_player" else "team"
            scope = self.current_player.get("名前", "選択選手") if self.tuner_adjust_scope == "player" and self.current_player else "チーム全体"
            self._set_message(f"表示・調整対象を「{scope}」に切り替えました（能力値は変更していません）", OK_GREEN)
        elif action == "tuner_adjust_selected":
            if self.tuner_session is not None and not self.tuner_session.finished:
                self._set_message("シミュレーション中は基準値を変更できません", ERROR_RED)
                return
            targets = self._tuner_targets()
            settings = self._ensure_tuner_settings()
            indices = [self.selected_player] if self.tuner_adjust_scope == "player" and self.current_player is not None else None
            changes = auto_adjust_payload(
                self.payload, targets, self.tuner_categories,
                player_indices=indices,
                include_hidden=bool(settings.get("裏パラメータ自動調整", True)),
                rng=self.rng,
            )
            self._mark_dirty()
            scope = self.current_player.get("名前", "選択選手") if indices is not None and self.current_player else "チーム全体"
            self._set_message(f"{scope}をタイプ・ポジションに合わせて自動調整しました（{changes}項目）", OK_GREEN)
        elif action == "tuner_start":
            if validate_payload(self.payload):
                self._set_message("先にエラータブの問題を修正してください。試合可能なチームだけチューニングできます", ERROR_RED)
                return
            available = {str(choice.get("id")): choice for choice in self._available_tuner_opponents()}
            opponents = [available[choice_id] for choice_id in self.tuner_opponents if choice_id in available]
            if not opponents:
                self._set_message("対戦相手を1チーム以上選択してください", ERROR_RED)
                return
            settings = self._ensure_tuner_settings()
            minimum = int(self.tuner_options.get("minimum_time_limit_seconds", 1))
            maximum = int(self.tuner_options.get("maximum_time_limit_seconds", 600))
            try:
                time_limit = int(settings.get("時間上限秒", self.tuner_options.get("default_time_limit_seconds", 15)))
            except (TypeError, ValueError):
                time_limit = int(self.tuner_options.get("default_time_limit_seconds", 15))
            time_limit = max(minimum, min(maximum, time_limit))
            settings["時間上限秒"] = str(time_limit)
            convergence_only = settings.get("終了条件") == "収束まで"
            accuracy_mode = settings.get("評価モード", "精度重視") != "速度重視"
            if accuracy_mode and not convergence_only:
                accuracy_minimum = int(self.tuner_options.get("accuracy_minimum_time_limit_seconds", 600))
                if time_limit < accuracy_minimum:
                    time_limit = min(maximum, accuracy_minimum)
                    settings["時間上限秒"] = str(time_limit)
            try:
                self.tuner_session = TeamTunerSession(
                    self.payload,
                    opponents,
                    self._tuner_targets(),
                    self.tuner_categories,
                    time_limit=None if convergence_only else time_limit,
                    include_hidden=bool(settings.get("裏パラメータ自動調整", True)),
                    stagnant_limit=int(self.tuner_options.get("convergence_stagnant_trials", 6)),
                    clock_acceleration=float(self.tuner_options.get("headless_clock_acceleration", 10.0)),
                    worker_count=int(self.tuner_options.get("multicore_workers", 0)),
                    max_workers=int(self.tuner_options.get("multicore_max_workers", 4)),
                    cpu_limit_percent=int(getattr(self.game, "cpu_limit_percent", 100)),
                    worker_match_time_limit=float(self.tuner_options.get("worker_match_time_limit_seconds", 8.0)),
                    adaptive_opponent_limit=int(self.tuner_options.get("adaptive_opponent_limit", 5)),
                    evaluation_mode="speed" if not accuracy_mode else "accuracy",
                    speed_evaluation_minutes=float(self.tuner_options.get("speed_evaluation_minutes", 10.0)),
                    minimum_score_improvement=float(self.tuner_options.get("minimum_score_improvement", 0.10)),
                    speed_max_trials=int(self.tuner_options.get("speed_max_trials", 16)),
                    rng=self.rng,
                )
                self.tuner_result_applied = False
                self.active_input = None
                cores = self.tuner_session.parallel_worker_count if self.tuner_session.parallel_enabled else 1
                end_text = "収束するまで" if convergence_only else f"最大{time_limit}秒"
                self._set_message(
                    f"{settings.get('評価モード', '精度重視')}で{len(opponents)}チームを相手に{end_text}、"
                    f"CPU上限{self.tuner_session.cpu_limit_percent}%・{cores}コアでヘッドレス試合を開始しました",
                    OK_GREEN,
                )
            except (TypeError, ValueError) as error:
                self._set_message(f"チューニングを開始できません: {error}", ERROR_RED)
        elif action == "tuner_cancel":
            if self.tuner_session is not None:
                self.tuner_session.cancel()

    def _back_to_list(self) -> None:
        if self.dirty and not self.confirm_back:
            self.confirm_back = True
            self._set_message("未保存です。保存するか、もう一度「破棄して戻る」を押してください", ERROR_RED)
            return
        if self.tuner_session is not None and not self.tuner_session.finished:
            self.tuner_session.cancel()
        self.mode = "LIST"
        self.payload = {}
        self.source_path = None
        self.active_input = None
        self.dirty = False
        self.confirm_back = False
        self.refresh_files()
        self._set_message("チーム一覧へ戻りました")

    def _place_selected(self, x: int, y: int) -> None:
        player = self.current_player
        if player is None:
            return
        old_x = str(player.get("ポジションX", "0"))
        old_y = str(player.get("ポジションY", "0"))
        occupant = next((
            other for index, other in enumerate(self.players)
            if index != self.selected_player
            and str(other.get("ポジションX", "")) == str(x)
            and str(other.get("ポジションY", "")) == str(y)
        ), None)
        if y == 11:
            occupant = next((
                other for index, other in enumerate(self.players)
                if index != self.selected_player and str(other.get("ポジションY", "")) == "11"
            ), occupant)
        if occupant is not None:
            occupant["ポジションX"] = old_x
            occupant["ポジションY"] = old_y
            try:
                occupant["ポジション"] = role_for_position_y(int(old_y))
            except ValueError:
                occupant["ポジション"] = "控え"
        player["ポジションX"] = str(8 if y == 11 else x)
        player["ポジションY"] = str(y)
        player["ポジション"] = role_for_position_y(y)
        self._mark_dirty()
        self._set_message(f"{player.get('名前', '選手')} を X{x} / Y{y} に配置しました")
