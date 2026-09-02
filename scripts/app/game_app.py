from __future__ import annotations

import math
import os
import random
from copy import deepcopy

import pygame

from scripts.match.match_engine import Match
from scripts.app.performance_backend import GpuPresenter
from scripts.league.league_auto_progress import (
    LeagueAutoProgressConfig,
    WATCH_FOCUS,
    WATCH_MODES,
    choose_auto_watch_fixture,
)
from scripts.league.league_manager import YEAR_DAYS, LeagueManager
from scripts.league.league_simulation_session import LeagueSimulationSession
from scripts.league.league_live_view import (
    OTHER_MATCH_VISIBLE_ROWS,
    clamp_other_match_scroll,
    other_match_max_scroll,
)
from scripts.league.league_schedule_view import (
    SCHEDULE_VISIBLE_ROWS,
    clamp_schedule_scroll,
    schedule_max_scroll,
)
from scripts.app.rendering import RendererMixin
from scripts.core.simulation_runtime import advance_match_fixed
from scripts.core.realtime_simulation_driver import RealtimeSimulationDriver
from scripts.core.performance_settings import (
    load_performance_settings,
    normalize_cpu_limit,
    normalize_league_simulation_mode,
    save_performance_settings,
    simulation_wall_time_budget,
)
from scripts.app.stadium_system import (
    build_stadium_crowd,
    load_special_spectator_sprites,
    load_stadium_seats,
    roll_special_spectators,
)
from scripts.core.settings import (
    AWAY_BLUE, CAMERA_BACK, CAMERA_FOCAL_LENGTHS, CAMERA_HEIGHT, CAMERA_MAX_SPEED,
    CAMERA_ZOOM_LEVELS, CREAM, FIELD, FPS, GOLD, HEIGHT, HOME_RED, PANEL, SPEED_OPTIONS, WIDTH,
    WINDOW_SIZE_OPTIONS, PROJECT_NAME, clamp,
)
from scripts.team.team_data import discover_team_choices
from scripts.team.team_editor import TeamEditor


class Game(RendererMixin):
    def __init__(self) -> None:
        pygame.init()
        title = PROJECT_NAME
        self.window_title = title
        self.window_size_index = WINDOW_SIZE_OPTIONS.index((WIDTH, HEIGHT))
        self.fullscreen = False
        self.performance_settings = load_performance_settings()
        self.cpu_limit_percent = self.performance_settings.cpu_limit_percent
        self.league_simulation_mode = self.performance_settings.league_simulation_mode
        self.settings_open = False
        self.settings_previous_match_state = ""
        self.settings_buttons: list[tuple[pygame.Rect, str]] = []
        self.settings_button = pygame.Rect(0, 0, 0, 0)
        self.gpu_presenter: GpuPresenter | None = None
        self.display_surface: pygame.Surface | None = None
        if self.performance_settings.gpu_rendering and os.environ.get("KADOKA_DISABLE_GPU", "0") != "1":
            try:
                self.gpu_presenter = GpuPresenter(
                    title,
                    WINDOW_SIZE_OPTIONS[self.window_size_index],
                    (WIDTH, HEIGHT),
                )
            except Exception:
                self.gpu_presenter = None
        if self.gpu_presenter is None:
            pygame.display.set_caption(title)
            self.display_surface = pygame.display.set_mode(WINDOW_SIZE_OPTIONS[self.window_size_index])
        # Everything is drawn at one logical 16:9 size.  Only the final frame is
        # scaled, so changing window size cannot alter UI layout or hitboxes.
        self.screen = pygame.Surface((WIDTH, HEIGHT))
        if self.display_surface is not None:
            self.screen = self.screen.convert()
        self.clock = pygame.time.Clock()
        self.fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self.text_surface_cache: dict[tuple[str, int, tuple[int, int, int], bool], pygame.Surface] = {}
        self.team_choices = discover_team_choices()
        self.league_manager = LeagueManager(self.team_choices)
        self.league_manager_before_editor: LeagueManager | None = None
        self.league_screen_open = False
        self.league_editor_only = False
        self.league_buttons: list[tuple[pygame.Rect, str]] = []
        self.league_save_select_open = False
        self.league_new_save_name = "新しいリーグ戦"
        self.league_save_input_active = False
        self.league_save_message = ""
        self.league_delete_confirm = ""
        self.league_template_entries = LeagueManager.template_entries()
        self.league_template_index = next(
            (
                index for index, entry in enumerate(self.league_template_entries)
                if entry["id"] == self.league_manager.template_id
            ),
            0,
        )
        self.league_template_name = self.league_manager.template_name
        self.league_template_input_active = False
        self.league_template_delete_confirm = ""
        self.league_view_name = next(
            iter(self.league_manager.selected_leagues),
            self.league_manager.league_names[0],
        )
        self.league_tab = "standings"
        self.league_editor_mode = "teams"
        self.league_editor_name = ""
        self.league_editor_input_active = False
        self.league_editor_delete_confirm = ""
        self.league_editor_schedule_page = 0
        self.league_team_scroll = 0
        self.league_team_scroll_rect = pygame.Rect(0, 0, 0, 0)
        self.league_team_detail_id = ""
        self.league_competition_scroll = 0
        self.league_tab_scroll = 0
        self.league_schedule_scroll = 0
        self.league_schedule_scroll_rect = pygame.Rect(0, 0, 0, 0)
        self.league_schedule_scroll_track = pygame.Rect(0, 0, 0, 0)
        self.league_schedule_scroll_thumb = pygame.Rect(0, 0, 0, 0)
        self.league_structure_kind = "league"
        self.tournament_view_name = self.league_manager.tournament_names[0] if self.league_manager.tournament_names else ""
        self.tournament_source_scroll = 0
        self.ime_composition = ""
        self.league_history_year = self.league_manager.year
        self.league_standings_mode = "league"
        self.league_history_team_id = ""
        self.league_history_result_scroll = 0
        self.active_league_fixture_id = ""
        self.league_match_finalized = False
        self.league_simulation_session: LeagueSimulationSession | None = None
        self.league_live_last_status: list[dict] = []
        self.league_auto_config = LeagueAutoProgressConfig()
        self.league_auto_config_open = False
        self.league_auto_running = False
        self.league_auto_rng = random.Random()
        self.league_auto_result_delay = 0.0
        self.league_auto_matchdays = 0
        self.other_matches_open = False
        self.other_matches_scroll = 0
        self.other_matches_button = pygame.Rect(0, 0, 0, 0)
        self.other_matches_close_button = pygame.Rect(0, 0, 0, 0)
        self.other_matches_scroll_track = pygame.Rect(0, 0, 0, 0)
        self.other_matches_scroll_thumb = pygame.Rect(0, 0, 0, 0)
        self.home_choice_index = next(
            (index for index, choice in enumerate(self.team_choices) if "夕張kadoka" in choice["name"]),
            0,
        )
        self.away_choice_index = next(
            (index for index, choice in enumerate(self.team_choices) if choice["name"] == "AOBA UNITED"),
            1 if len(self.team_choices) > 1 else 0,
        )
        self.venue_modes = ("HOME", "NEUTRAL", "AWAY")
        self.venue_mode_index = 0
        self.match = Match(
            self.team_choices[self.home_choice_index],
            self.team_choices[self.away_choice_index],
            self.venue_modes[self.venue_mode_index],
        )
        self.match.state = "MAIN_MENU"
        self.visible_simulation = RealtimeSimulationDriver(
            wall_time_budget=simulation_wall_time_budget(self.cpu_limit_percent),
        )
        self.running = True
        self.speed_buttons: list[tuple[pygame.Rect, int]] = []
        self.team_select_buttons: list[tuple[pygame.Rect, str]] = []
        self.main_menu_buttons: list[tuple[pygame.Rect, str]] = []
        self.fulltime_buttons: list[tuple[pygame.Rect, str]] = []
        self.pause_menu_buttons: list[tuple[pygame.Rect, str]] = []
        self.skip_match_in_progress = False
        self.league_skip_auto_return = False
        self.player_list_open = False
        self.player_list_rank_mode = False
        self.player_list_button = pygame.Rect(0, 0, 0, 0)
        self.player_list_close_button = pygame.Rect(0, 0, 0, 0)
        self.player_list_rank_button = pygame.Rect(0, 0, 0, 0)
        self.window_size_button = pygame.Rect(0, 0, 0, 0)
        self.fullscreen_button = pygame.Rect(0, 0, 0, 0)
        self.cpu_limit_button = pygame.Rect(0, 0, 0, 0)
        self.zoom_buttons: list[tuple[pygame.Rect, int]] = []
        self.team_editor_open = False
        self.camera_focus = pygame.Vector2(FIELD.center)
        self.camera_velocity = pygame.Vector2()
        self.camera = pygame.Vector3()
        self.camera_target = pygame.Vector3()
        self.camera_forward = pygame.Vector3()
        self.camera_right = pygame.Vector3()
        self.camera_up = pygame.Vector3()
        self.camera_zoom_index = CAMERA_ZOOM_LEVELS.index(1.00)
        self.focal_length = CAMERA_FOCAL_LENGTHS[1] * self.camera_zoom
        self.view_center = pygame.Vector2(PANEL.left / 2, 350)
        self.reset_camera()
        crowd_rng = random.Random(824)
        self.crowd = build_stadium_crowd(crowd_rng, PANEL.left)
        self.stadium_seats = load_stadium_seats(PANEL.left)
        self.special_spectator_sprites = load_special_spectator_sprites()
        self.special_spectator_rng = random.Random()
        self.special_spectators: list[tuple[str, int, int, int]] = []
        self.roll_stadium_guests()
        self.team_editor = TeamEditor(self)

    def roll_stadium_guests(self) -> None:
        self.special_spectators = roll_special_spectators(self.special_spectator_rng)

    @property
    def current_window_size(self) -> tuple[int, int]:
        return WINDOW_SIZE_OPTIONS[self.window_size_index]

    def cycle_window_size(self) -> None:
        self.fullscreen = False
        self.window_size_index = (self.window_size_index + 1) % len(WINDOW_SIZE_OPTIONS)
        if self.gpu_presenter is not None:
            self.gpu_presenter.set_window_size(self.current_window_size)
        else:
            self.display_surface = pygame.display.set_mode(self.current_window_size)

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        if self.gpu_presenter is not None:
            self.gpu_presenter.set_fullscreen(self.fullscreen)
        elif self.fullscreen:
            self.display_surface = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.display_surface = pygame.display.set_mode(self.current_window_size)

    @property
    def display_size(self) -> tuple[int, int]:
        if self.gpu_presenter is not None:
            return self.gpu_presenter.size
        if self.display_surface is not None:
            return self.display_surface.get_size()
        return self.current_window_size

    @property
    def render_backend_name(self) -> str:
        return "GPU (SDL2)" if self.gpu_presenter is not None else "CPU (Surface)"

    @property
    def compute_backend_name(self) -> str:
        return "CPU"

    def cycle_cpu_limit(self) -> None:
        """Compatibility helper; settings UI normally selects an explicit value."""
        options = (10, 25, 50, 75, 100)
        current = normalize_cpu_limit(getattr(self, "cpu_limit_percent", 100))
        selected = next((value for value in options if value > current), options[0])
        self.set_cpu_limit(selected)

    def set_cpu_limit(self, value: object) -> None:
        settings = getattr(self, "performance_settings", None) or load_performance_settings()
        self.performance_settings = settings
        self.cpu_limit_percent = normalize_cpu_limit(value)
        settings.cpu_limit_percent = self.cpu_limit_percent
        save_performance_settings(settings)
        if hasattr(self, "visible_simulation"):
            self.visible_simulation.wall_time_budget = simulation_wall_time_budget(self.cpu_limit_percent)

    def set_league_simulation_mode(self, value: object) -> None:
        settings = getattr(self, "performance_settings", None) or load_performance_settings()
        self.performance_settings = settings
        self.league_simulation_mode = normalize_league_simulation_mode(value)
        settings.league_simulation_mode = self.league_simulation_mode
        save_performance_settings(settings)

    def toggle_gpu_rendering_setting(self) -> None:
        settings = getattr(self, "performance_settings", None) or load_performance_settings()
        self.performance_settings = settings
        settings.gpu_rendering = not settings.gpu_rendering
        save_performance_settings(settings)

    def open_settings(self) -> None:
        if getattr(self, "settings_open", False):
            return
        self.settings_open = True
        self.settings_previous_match_state = str(getattr(self.match, "state", ""))
        if self.match.state == "PLAYING":
            self.match.state = "PAUSED"

    def close_settings(self, *, restore_state: bool = True) -> None:
        if not getattr(self, "settings_open", False):
            return
        previous = getattr(self, "settings_previous_match_state", "")
        self.settings_open = False
        getattr(self, "settings_buttons", []).clear()
        if restore_state and previous == "PLAYING" and self.match.state == "PAUSED":
            self.match.state = "PLAYING"
        self.settings_previous_match_state = ""

    def handle_settings_action(self, action: str) -> None:
        if action == "close":
            self.close_settings()
        elif action.startswith("cpu:"):
            self.set_cpu_limit(action.split(":", 1)[1])
        elif action.startswith("league_mode:"):
            self.set_league_simulation_mode(action.split(":", 1)[1])
        elif action == "window_size":
            self.cycle_window_size()
        elif action == "fullscreen":
            self.toggle_fullscreen()
        elif action == "gpu_rendering":
            self.toggle_gpu_rendering_setting()
        elif action == "abort":
            self.close_settings(restore_state=False)
            self.abort_current_match()
        elif action == "skip":
            self.close_settings(restore_state=False)
            self.start_match_skip()
        elif action == "auto_stop":
            self.stop_league_auto_progress()
            self.close_settings()

    def handle_settings_click(self, pos: tuple[int, int]) -> None:
        for rect, action in reversed(getattr(self, "settings_buttons", ())):
            if rect.collidepoint(pos):
                self.handle_settings_action(action)
                return

    @property
    def camera_zoom(self) -> float:
        return CAMERA_ZOOM_LEVELS[self.camera_zoom_index]

    def change_camera_zoom(self, step: int) -> None:
        self.camera_zoom_index = int(clamp(
            self.camera_zoom_index + step,
            0,
            len(CAMERA_ZOOM_LEVELS) - 1,
        ))

    def logical_mouse_pos(self, pos: tuple[int, int] | None = None) -> tuple[int, int]:
        if pos is None:
            pos = pygame.mouse.get_pos()
        window_width, window_height = self.display_size
        scale = min(window_width / WIDTH, window_height / HEIGHT)
        render_width = WIDTH * scale
        render_height = HEIGHT * scale
        offset_x = (window_width - render_width) * 0.5
        offset_y = (window_height - render_height) * 0.5
        return (
            round((pos[0] - offset_x) / max(0.001, scale)),
            round((pos[1] - offset_y) / max(0.001, scale)),
        )

    def present(self) -> None:
        if self.gpu_presenter is not None:
            try:
                self.gpu_presenter.present(self.screen)
                return
            except Exception:
                # Renderer availability differs by driver.  A presentation
                # failure must never make the game itself unplayable.
                fallback_size = self.gpu_presenter.size
                self.gpu_presenter.destroy()
                self.gpu_presenter = None
                pygame.display.set_caption(self.window_title)
                if self.fullscreen:
                    self.display_surface = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                else:
                    self.display_surface = pygame.display.set_mode(fallback_size)
        if self.display_surface is None:
            return
        size = self.display_surface.get_size()
        if size == (WIDTH, HEIGHT):
            self.display_surface.blit(self.screen, (0, 0))
        else:
            scale = min(size[0] / WIDTH, size[1] / HEIGHT)
            scaled_size = (max(1, round(WIDTH * scale)), max(1, round(HEIGHT * scale)))
            offset = ((size[0] - scaled_size[0]) // 2, (size[1] - scaled_size[1]) // 2)
            self.display_surface.fill((10, 12, 15))
            scaled = pygame.transform.smoothscale(self.screen, scaled_size)
            self.display_surface.blit(scaled, offset)
        pygame.display.flip()

    def cycle_team_choice(self, side: str, amount: int) -> None:
        if side == "home":
            self.home_choice_index = (self.home_choice_index + amount) % len(self.team_choices)
        else:
            self.away_choice_index = (self.away_choice_index + amount) % len(self.team_choices)

    def refresh_team_choices(self) -> None:
        home_id = self.team_choices[self.home_choice_index]["id"] if self.team_choices else ""
        away_id = self.team_choices[self.away_choice_index]["id"] if self.team_choices else ""
        try:
            refreshed = discover_team_choices()
        except RuntimeError:
            return
        self.team_choices = refreshed
        self.league_manager.refresh_teams(refreshed)
        self.home_choice_index = next(
            (index for index, choice in enumerate(refreshed) if choice["id"] == home_id),
            0,
        )
        self.away_choice_index = next(
            (index for index, choice in enumerate(refreshed) if choice["id"] == away_id),
            1 if len(refreshed) > 1 else 0,
        )

    def open_team_editor(self) -> None:
        self.team_editor_open = True
        self.team_editor.open()

    def close_team_editor(self) -> None:
        self.team_editor.close()
        self.team_editor_open = False
        self.refresh_team_choices()

    def open_league_screen(self) -> None:
        self.league_auto_config_open = False
        self.league_auto_running = False
        self.league_manager.refresh_teams(self.team_choices)
        self.refresh_league_template_entries(self.league_manager.template_id)
        self.league_editor_only = False
        self.league_screen_open = True
        self.league_save_select_open = True
        self.league_save_message = ""
        self.league_delete_confirm = ""
        self.league_team_scroll = 0
        self.player_list_open = False
        self.match.state = "MAIN_MENU"

    def open_league_editor(self) -> None:
        """Open the reusable leagues.json definition editor without starting a season."""
        self.refresh_league_template_entries(getattr(self.league_manager, "template_id", "default"))
        if self.league_manager_before_editor is None:
            self.league_manager.save()
            self.league_manager_before_editor = self.league_manager
            template_id = self.current_league_template_id()
            editor_manager = LeagueManager(self.team_choices, template_id=template_id, load_state=False)
            editor_manager.save_path = None
            editor_manager.year = 1
            editor_manager.day = 1
            editor_manager.fixtures = []
            editor_manager.last_results = []
            editor_manager.history = []
            editor_manager.league_participations = editor_manager.definition_participations()
            editor_manager.league_memberships = editor_manager.definition_memberships()
            for choice in editor_manager.team_choices:
                choice["league"] = editor_manager.league_memberships.get(str(choice["id"]), "")
            editor_manager._rebuild_editor_schedule()
            self.league_manager = editor_manager
        self.league_editor_only = True
        self.league_screen_open = True
        self.league_save_select_open = False
        self.league_tab = "structure"
        self.league_structure_kind = "league"
        self.league_editor_mode = "teams"
        self.league_save_message = "リーグ構成テンプレートを編集中です"
        self.league_team_scroll = 0
        self.player_list_open = False
        self.match.state = "MAIN_MENU"

    def refresh_league_template_entries(self, preferred_id: str = "") -> None:
        entries = LeagueManager.template_entries()
        self.league_template_entries = entries
        wanted = preferred_id or getattr(self.league_manager, "template_id", "default")
        self.league_template_index = next(
            (index for index, entry in enumerate(entries) if entry["id"] == wanted),
            0,
        )
        if entries:
            self.league_template_name = str(entries[self.league_template_index]["name"])

    def current_league_template_id(self) -> str:
        if not self.league_template_entries:
            return "default"
        self.league_template_index %= len(self.league_template_entries)
        return str(self.league_template_entries[self.league_template_index]["id"])

    def activate_league_template(self, template_id: str) -> None:
        manager = LeagueManager(self.team_choices, template_id=template_id, load_state=False)
        manager.save_path = None
        self.league_manager = manager
        self.refresh_league_template_entries(manager.template_id)
        self.league_view_name = manager.league_names[0] if manager.league_names else ""
        self.tournament_view_name = manager.tournament_names[0] if manager.tournament_names else ""
        self.league_editor_name = self.league_view_name
        self.league_template_input_active = False
        self.league_template_delete_confirm = ""
        self.league_competition_scroll = 0
        self.league_team_scroll = 0

    def suggest_league_template_copy_name(self) -> str:
        existing = {str(entry["name"]) for entry in self.league_template_entries}
        base = f"{self.league_manager.template_name} のコピー"
        candidate = base
        number = 2
        while candidate in existing:
            candidate = f"{base}{number}"
            number += 1
        return candidate[:40]

    def close_league_screen(self) -> None:
        self.stop_league_auto_progress(announce=False)
        if self.league_editor_only and self.league_manager_before_editor is not None:
            runtime_manager = self.league_manager_before_editor
            runtime_manager.refresh_teams(self.team_choices)
            self.league_manager = runtime_manager
            self.league_manager_before_editor = None
        self.league_screen_open = False
        self.league_editor_only = False
        self.match.state = "MAIN_MENU"

    def return_to_main_menu(self) -> None:
        self.stop_league_auto_progress(announce=False)
        self.league_screen_open = False
        self.league_editor_only = False
        self.team_editor_open = False
        self.player_list_open = False
        self.other_matches_open = False
        self.active_league_fixture_id = ""
        self.match.state = "MAIN_MENU"

    def start_league_fixture(self, fixture: dict) -> None:
        home_choice = self.league_manager.choices_by_id.get(str(fixture.get("home_id")))
        away_choice = self.league_manager.choices_by_id.get(str(fixture.get("away_id")))
        if home_choice is None or away_choice is None:
            return
        other_fixtures = [
            other for other in self.league_manager.fixtures_on_day(self.league_manager.day, unplayed_only=True)
            if other.get("id") != fixture.get("id")
        ]
        self.start_league_simulations(other_fixtures, live_updates=True)
        self.active_league_fixture_id = str(fixture["id"])
        self.league_match_finalized = False
        self.league_screen_open = False
        self.match = Match(home_choice, away_choice, "HOME")
        self.match.start_new()
        self.visible_simulation.reset(self.match)
        self.roll_stadium_guests()
        self.player_list_open = False
        self.other_matches_open = False
        self.other_matches_scroll = 0
        self.league_live_last_status = []
        self.reset_camera()

    def start_league_simulations(self, fixtures: list[dict], *, live_updates: bool = False) -> None:
        fixtures = [fixture for fixture in fixtures if not fixture.get("played")]
        if not fixtures:
            return
        if self.league_simulation_session is not None and not self.league_simulation_session.finished:
            return
        self.league_simulation_session = LeagueSimulationSession(
            fixtures,
            self.league_manager.choices_by_id,
            live_updates=live_updates,
            cpu_limit_percent=int(getattr(self, "cpu_limit_percent", 100)),
            simulation_mode=str(getattr(self, "league_simulation_mode", "PRECISE")),
        )

    def update_league_simulations(self) -> None:
        session = self.league_simulation_session
        if session is None:
            return
        if session.live_updates and self.active_league_fixture_id:
            session.set_target_simulation_time(self.match.simulation_elapsed)
        session.poll()
        self.league_live_last_status = [dict(status) for status in session.live_status.values()]
        if not session.finished:
            return
        self.league_manager.apply_headless_results(session.results)
        if session.errors and self.league_auto_running:
            self.stop_league_auto_progress(announce=False)
            self.league_save_message = "オート進行を停止しました: " + str(session.errors[0])
        self.league_simulation_session = None

    def league_live_clock_ready(self) -> bool:
        """The watched match never waits for another venue's independent clock."""
        return True

    def other_matches_status_count(self) -> int:
        session = self.league_simulation_session
        if session is not None:
            return len(session.live_status)
        return len(self.league_live_last_status)

    def scroll_other_matches(self, row_delta: int) -> None:
        self.other_matches_scroll = clamp_other_match_scroll(
            self.other_matches_scroll + int(row_delta),
            self.other_matches_status_count(),
        )

    def scroll_league_schedule(self, row_delta: int) -> None:
        self.league_schedule_scroll = clamp_schedule_scroll(
            self.league_schedule_scroll + int(row_delta),
            len(self.league_manager.next_fixtures()),
        )

    def league_auto_focus_choices(self) -> list[dict]:
        manager = self.league_manager
        participating_ids: set[str] = set()
        for fixture in manager.fixtures:
            if not manager._fixture_selected(fixture):
                continue
            participating_ids.add(str(fixture.get("home_id", "")))
            participating_ids.add(str(fixture.get("away_id", "")))
        choices = [
            choice for choice in manager.team_choices
            if not participating_ids or str(choice.get("id", "")) in participating_ids
        ]
        return sorted(choices, key=lambda choice: str(choice.get("name", "")).casefold())

    def current_league_auto_focus_choice(self) -> dict | None:
        choices = self.league_auto_focus_choices()
        if not choices:
            self.league_auto_config.focus_team_id = ""
            return None
        current_id = self.league_auto_config.focus_team_id
        choice = next((entry for entry in choices if str(entry.get("id", "")) == current_id), choices[0])
        self.league_auto_config.focus_team_id = str(choice.get("id", ""))
        return choice

    def cycle_league_auto_focus(self, amount: int) -> None:
        choices = self.league_auto_focus_choices()
        if not choices:
            self.league_auto_config.focus_team_id = ""
            return
        current_id = self.league_auto_config.focus_team_id
        current = next(
            (index for index, choice in enumerate(choices) if str(choice.get("id", "")) == current_id),
            0,
        )
        selected = choices[(current + int(amount)) % len(choices)]
        self.league_auto_config.focus_team_id = str(selected.get("id", ""))

    def open_league_auto_config(self) -> None:
        if self.league_editor_only or self.league_save_select_open or self.league_simulation_session is not None:
            return
        self.league_auto_config.normalize()
        self.current_league_auto_focus_choice()
        self.league_auto_config_open = True
        self.league_save_message = ""

    def start_league_auto_progress(self) -> None:
        if not (self.league_manager.selected_leagues or self.league_manager.selected_tournaments):
            self.league_save_message = "オート進行するリーグかトーナメントを選択してください"
            return
        self.league_auto_config.normalize()
        if self.league_auto_config.watch_mode == WATCH_FOCUS and self.current_league_auto_focus_choice() is None:
            self.league_save_message = "フォーカスするチームが見つかりません"
            return
        self.league_auto_config_open = False
        self.league_auto_running = True
        self.league_auto_result_delay = 0.0
        self.league_auto_matchdays = 0
        self.league_save_message = "デバッグ用オート進行を開始しました"
        self.advance_league_auto_progress()

    def stop_league_auto_progress(self, *, announce: bool = True) -> None:
        was_active = bool(
            getattr(self, "league_auto_running", False)
            or getattr(self, "league_auto_config_open", False)
        )
        self.league_auto_running = False
        self.league_auto_config_open = False
        self.league_auto_result_delay = 0.0
        if announce and was_active:
            self.league_save_message = "オート進行を停止しました（進行中の試合は最後まで処理します）"

    def _begin_league_auto_matchday(self, fixtures: list[dict], *, advance_calendar: bool) -> None:
        if not fixtures:
            return
        watched = choose_auto_watch_fixture(fixtures, self.league_auto_config, self.league_auto_rng)
        self.league_manager.watch_fixture_id = str(watched.get("id", "")) if watched else ""
        if advance_calendar:
            watched = self.league_manager.advance_to_next_matchday()
            due = self.league_manager.fixtures_on_day(self.league_manager.day, unplayed_only=True)
        else:
            self.league_manager.last_results = []
            self.league_manager.save()
            due = fixtures
        self.league_auto_matchdays += 1
        if watched is not None:
            self.start_league_fixture(watched)
            self.match.speed_multiplier = self.league_auto_config.speed_multiplier
            self.league_auto_result_delay = 0.0
        else:
            self.start_league_simulations(due)

    def advance_league_auto_progress(self) -> None:
        if not self.league_auto_running or self.league_simulation_session is not None or self.active_league_fixture_id:
            return
        manager = self.league_manager
        current_due = manager.fixtures_on_day(manager.day, unplayed_only=True)
        if current_due:
            self._begin_league_auto_matchday(current_due, advance_calendar=False)
            return
        next_day = manager.next_matchday()
        if next_day is None:
            previous_year = manager.year
            manager.day = YEAR_DAYS
            manager.advance_day()
            if manager.year == previous_year:
                self.stop_league_auto_progress(announce=False)
                self.league_save_message = "次のシーズンへ進めなかったためオート進行を停止しました"
                return
            next_day = manager.next_matchday()
        if next_day is None:
            self.stop_league_auto_progress(announce=False)
            self.league_save_message = "進行できる試合がないためオート進行を停止しました"
            return
        fixtures = manager.fixtures_on_day(next_day, unplayed_only=True)
        self._begin_league_auto_matchday(fixtures, advance_calendar=True)

    def update_league_auto_progress(self, dt: float) -> None:
        if not self.league_auto_running or self.league_auto_config_open or self.settings_open:
            return
        if self.active_league_fixture_id:
            if self.match.state != "FULLTIME":
                return
            self.finalize_league_match()
            if self.league_simulation_session is not None:
                return
            self.league_auto_result_delay += max(0.0, float(dt))
            if self.league_auto_result_delay >= 1.5:
                self.return_to_league_screen()
                self.league_auto_result_delay = 0.0
            return
        if self.league_simulation_session is None and self.league_screen_open:
            self.advance_league_auto_progress()

    def finalize_league_match(self) -> None:
        if not self.active_league_fixture_id or self.league_match_finalized or self.match.state != "FULLTIME":
            return
        if self.league_simulation_session is not None:
            self.league_simulation_session.finish_remaining_as_fast_as_possible()
        remaining = self.league_manager.complete_watched_fixture(
            self.active_league_fixture_id,
            self.match.home.score,
            self.match.away.score,
        )
        self.start_league_simulations(remaining)
        self.league_match_finalized = True

    def return_to_league_screen(self) -> None:
        self.finalize_league_match()
        # Keep the result screen responsive while unfinished same-day matches
        # run without pacing. Enter the league screen only after their real
        # physics simulations and result recording have completed.
        if self.league_simulation_session is not None:
            return
        self.active_league_fixture_id = ""
        self.league_match_finalized = False
        self.match.state = "TEAM_SELECT"
        self.player_list_open = False
        self.fulltime_buttons.clear()
        self.league_screen_open = True
        self.league_save_select_open = False
        self.league_tab = "schedule"

    def handle_league_action(self, action: str) -> None:
        if action == "team_detail_close":
            self.league_team_detail_id = ""
            return
        if action.startswith("team_detail|"):
            self.league_team_detail_id = action.split("|", 1)[1]
            return
        if self.league_team_detail_id:
            return
        if action == "save_back":
            self.close_league_screen()
            return
        if self.league_auto_config_open and not action.startswith("auto_"):
            return
        if action == "auto_open":
            self.open_league_auto_config()
            return
        if action == "auto_cancel":
            self.league_auto_config_open = False
            return
        if action == "auto_start":
            self.start_league_auto_progress()
            return
        if action == "auto_stop":
            self.stop_league_auto_progress()
            return
        if action.startswith("auto_watch|"):
            mode = action.split("|", 1)[1]
            if mode in WATCH_MODES:
                self.league_auto_config.watch_mode = mode
            return
        if action.startswith("auto_speed|"):
            current = SPEED_OPTIONS.index(self.league_auto_config.speed_multiplier)
            amount = int(action.split("|", 1)[1])
            self.league_auto_config.speed_multiplier = SPEED_OPTIONS[(current + amount) % len(SPEED_OPTIONS)]
            return
        if action.startswith("auto_focus|"):
            self.cycle_league_auto_focus(int(action.split("|", 1)[1]))
            return
        if action == "template_input":
            self.league_template_input_active = True
            self.league_save_input_active = False
            self.league_editor_input_active = False
            self.ime_composition = ""
            pygame.key.start_text_input()
            return
        if action.startswith("template_cycle|"):
            if self.league_template_entries:
                amount = int(action.split("|", 1)[1])
                self.league_template_index = (self.league_template_index + amount) % len(self.league_template_entries)
                self.activate_league_template(self.current_league_template_id())
            return
        if action == "template_duplicate":
            requested = self.league_template_name.strip()
            if not requested or requested == self.league_manager.template_name:
                requested = self.suggest_league_template_copy_name()
            try:
                template_id = self.league_manager.duplicate_template(requested)
                self.refresh_league_template_entries(template_id)
                self.activate_league_template(template_id)
                self.league_save_message = f"テンプレート『{requested}』を複製しました"
            except (OSError, ValueError) as error:
                self.league_save_message = str(error)
            return
        if action == "template_rename":
            try:
                self.league_manager.rename_template(self.league_template_name)
                self.refresh_league_template_entries(self.league_manager.template_id)
                self.league_save_message = "テンプレート名を変更しました"
            except (OSError, ValueError) as error:
                self.league_save_message = str(error)
            return
        if action == "template_delete":
            template_id = self.league_manager.template_id
            if template_id == "default":
                self.league_save_message = "標準テンプレートは削除できません"
            elif self.league_template_delete_confirm != template_id:
                self.league_template_delete_confirm = template_id
                self.league_save_message = "もう一度『削除する』を押すとテンプレートを削除します"
            else:
                try:
                    self.league_manager.delete_template()
                    self.refresh_league_template_entries("default")
                    self.activate_league_template("default")
                    self.league_save_message = "テンプレートを削除しました"
                except (OSError, ValueError) as error:
                    self.league_save_message = str(error)
            return
        if self.league_editor_only and (
            action in {"advance_day", "advance_matchday", "save_current", "manage_saves"}
            or action.startswith(("toggle|", "toggle_tournament|", "watch|"))
            or action in {"tab|standings", "tab|schedule"}
        ):
            return
        if action == "save_input":
            self.league_save_input_active = True
            self.league_template_input_active = False
            self.ime_composition = ""
            pygame.key.start_text_input()
            return
        if action == "new_save":
            self.league_manager.create_new_save(self.league_new_save_name)
            self.league_save_select_open = False
            self.league_save_input_active = False
            self.league_history_year = self.league_manager.year
            self.league_view_name = next(iter(self.league_manager.selected_leagues), self.league_manager.league_names[0])
            self.league_save_message = "新しいリーグ戦を作成しました"
            return
        if action.startswith("resume|"):
            errors = self.league_manager.load_save(action.split("|", 1)[1])
            if errors:
                self.league_save_message = " / ".join(errors[:2])
            else:
                self.refresh_league_template_entries(self.league_manager.template_id)
                self.league_save_select_open = False
                self.league_history_year = self.league_manager.year
                self.league_view_name = next(iter(self.league_manager.selected_leagues), self.league_manager.league_names[0])
                self.league_save_message = "セーブデータを読み込みました"
            return
        if action.startswith("delete|"):
            file_name = action.split("|", 1)[1]
            if self.league_delete_confirm != file_name:
                self.league_delete_confirm = file_name
                self.league_save_message = "もう一度『削除する』を押すと削除します"
            else:
                error = self.league_manager.delete_save(file_name)
                self.league_save_message = error or "セーブデータを削除しました"
                self.league_delete_confirm = ""
            return
        if action == "manage_saves":
            self.league_manager.save()
            self.league_save_select_open = True
            self.league_save_message = "現在の進行を保存しました"
            return
        if action == "save_current":
            self.league_manager.save()
            self.league_save_message = "途中経過をJSONへ保存しました" if not self.league_manager.last_save_error else self.league_manager.last_save_error
            return
        if action.startswith("history|"):
            self.league_history_year = int(action.split("|", 1)[1])
            self.league_history_result_scroll = 0
            return
        if action.startswith("history_mode|"):
            self.league_standings_mode = action.split("|", 1)[1]
            self.league_history_result_scroll = 0
            return
        if action.startswith("history_team_open|"):
            self.league_history_team_id = action.split("|", 1)[1]
            self.league_standings_mode = "team"
            self.league_history_result_scroll = 0
            return
        if action.startswith("history_team_cycle|"):
            teams = self.league_manager.historical_teams()
            if teams:
                ids = [str(team["team_id"]) for team in teams]
                current = ids.index(self.league_history_team_id) if self.league_history_team_id in ids else 0
                amount = int(action.split("|", 1)[1])
                self.league_history_team_id = ids[(current + amount) % len(ids)]
                self.league_history_result_scroll = 0
            return
        if action.startswith("history_results_scroll|"):
            amount = int(action.split("|", 1)[1])
            results = self.league_manager.team_results_for_year(
                self.league_history_team_id,
                self.league_history_year,
            )
            maximum = max(0, len(results) - 9)
            self.league_history_result_scroll = max(
                0,
                min(maximum, self.league_history_result_scroll + amount),
            )
            return
        if action == "editor_name_input":
            self.league_editor_input_active = True
            self.league_template_input_active = False
            self.ime_composition = ""
            pygame.key.start_text_input()
            return
        if action.startswith("structure_kind|"):
            self.league_structure_kind = action.split("|", 1)[1]
            self.league_editor_input_active = False
            self.ime_composition = ""
            if self.league_structure_kind == "league":
                self.league_editor_name = self.league_view_name
                self.league_team_scroll = 0
            else:
                self.league_editor_name = self.tournament_view_name
            return
        if action.startswith("league_tabs|"):
            maximum = max(0, len(self.league_manager.league_names) - 5)
            self.league_tab_scroll = max(0, min(maximum, self.league_tab_scroll + int(action.split("|", 1)[1])))
            return
        if action.startswith("league_cycle|"):
            names = self.league_manager.league_names
            if names:
                current = names.index(self.league_view_name) if self.league_view_name in names else 0
                self.league_view_name = names[(current + int(action.split("|", 1)[1])) % len(names)]
                if self.league_structure_kind == "league":
                    self.league_editor_name = self.league_view_name
                self.league_editor_delete_confirm = ""
                self.league_editor_schedule_page = 0
                self.league_team_scroll = 0
            return
        if action.startswith("competition_scroll|"):
            total = len(self.league_manager.league_names) + len(self.league_manager.tournament_names)
            maximum = max(0, total - 7)
            self.league_competition_scroll = max(0, min(maximum, self.league_competition_scroll + int(action.split("|", 1)[1])))
            return
        if action.startswith("editor_mode|"):
            self.league_editor_mode = action.split("|", 1)[1]
            self.league_editor_schedule_page = 0
            if self.league_editor_mode == "teams":
                self.league_team_scroll = 0
            return
        if action.startswith("team_scroll|"):
            self.league_team_scroll = max(0, self.league_team_scroll + int(action.split("|", 1)[1]))
            return
        if action == "editor_rename":
            old_name = self.league_view_name
            error = self.league_manager.rename_league(old_name, self.league_editor_name)
            if not error:
                self.league_view_name = self.league_editor_name.strip()[:30]
                self.league_editor_name = self.league_view_name
            self.league_save_message = error or "リーグ名を変更しました"
            return
        if action == "editor_add":
            try:
                name = self.league_manager.add_league(self.league_editor_name)
                self.league_view_name = name
                self.league_editor_name = name
                self.league_save_message = "リーグを追加しました"
            except (OSError, ValueError) as error:
                self.league_save_message = str(error)
            return
        if action == "tournament_add":
            try:
                name = self.league_manager.add_tournament(self.league_editor_name)
                self.tournament_view_name = name
                self.league_editor_name = name
                self.league_save_message = "トーナメントを追加しました"
            except (OSError, ValueError) as error:
                self.league_save_message = str(error)
            return
        if action == "tournament_rename":
            old_name = self.tournament_view_name
            error = self.league_manager.rename_tournament(old_name, self.league_editor_name)
            if not error:
                self.tournament_view_name = self.league_editor_name.strip()[:30]
            self.league_save_message = error or "トーナメント名を変更しました"
            return
        if action == "tournament_delete":
            error = self.league_manager.delete_tournament(self.tournament_view_name)
            self.league_save_message = error or "トーナメントを削除しました"
            if not error:
                self.tournament_view_name = self.league_manager.tournament_names[0] if self.league_manager.tournament_names else ""
            return
        if action.startswith("tournament_view|"):
            self.tournament_view_name = action.split("|", 1)[1]
            definition = self.league_manager.tournament_definition(self.tournament_view_name)
            self.league_editor_name = str(definition.get("トーナメント名", self.tournament_view_name))
            return
        if action.startswith("tournament_cycle|"):
            names = self.league_manager.tournament_names
            if names:
                current = names.index(self.tournament_view_name) if self.tournament_view_name in names else 0
                self.tournament_view_name = names[(current + int(action.split("|", 1)[1])) % len(names)]
                self.league_editor_name = self.tournament_view_name
            return
        if action.startswith("tournament_source_toggle|"):
            league_name = action.split("|", 1)[1]
            self.league_save_message = self.league_manager.toggle_tournament_source(self.tournament_view_name, league_name) or "参加元リーグを変更しました"
            return
        if action.startswith("tournament_source_page|"):
            maximum = max(0, len(self.league_manager.league_names) - 6)
            self.tournament_source_scroll = max(0, min(maximum, self.tournament_source_scroll + int(action.split("|", 1)[1])))
            return
        if action == "tournament_mode":
            definition = self.league_manager.tournament_definition(self.tournament_view_name)
            mode = "前年順位" if definition.get("参加方式") == "リーグ全体" else "リーグ全体"
            self.league_save_message = self.league_manager.configure_tournament(self.tournament_view_name, participation=mode) or "参加方式を変更しました"
            return
        if action.startswith("tournament_rank|"):
            definition = self.league_manager.tournament_definition(self.tournament_view_name)
            value = int(definition.get("前年順位上限", 4)) + int(action.split("|", 1)[1])
            self.league_save_message = self.league_manager.configure_tournament(self.tournament_view_name, rank_limit=value) or "前年順位の範囲を変更しました"
            return
        if action.startswith("tournament_day|"):
            definition = self.league_manager.tournament_definition(self.tournament_view_name)
            value = int(definition.get("開始希望日", 40)) + int(action.split("|", 1)[1])
            self.league_save_message = self.league_manager.configure_tournament(self.tournament_view_name, preferred_day=value) or "開始希望日を変更しました"
            return
        if action == "editor_delete":
            if self.league_editor_delete_confirm != self.league_view_name:
                self.league_editor_delete_confirm = self.league_view_name
                self.league_save_message = "もう一度削除を押すと、このリーグを削除します"
            else:
                error = self.league_manager.delete_league(self.league_view_name)
                self.league_save_message = error or "リーグを削除しました"
                self.league_editor_delete_confirm = ""
                if not error:
                    self.league_view_name = self.league_manager.league_names[0]
                    self.league_editor_name = self.league_view_name
            return
        if action.startswith("assign_team|"):
            team_id = action.split("|", 1)[1]
            was_selected = self.league_manager.team_in_league(team_id, self.league_view_name)
            error = self.league_manager.assign_team_to_league(team_id, self.league_view_name)
            self.league_save_message = error or (f"{self.league_view_name}から外しました" if was_selected else f"{self.league_view_name}へ追加しました")
            return
        if action.startswith("priority_team|"):
            team_id = action.split("|", 1)[1]
            error = self.league_manager.set_priority_league(team_id, self.league_view_name)
            self.league_save_message = error or f"{self.league_view_name}を優先リーグにしました"
            return
        if action.startswith("fixture_day|"):
            _, fixture_id, amount = action.split("|", 2)
            fixture = self.league_manager.fixture(fixture_id)
            error = self.league_manager.set_fixture_day(fixture_id, int(fixture.get("day", 1)) + int(amount)) if fixture else "試合が見つかりません"
            self.league_save_message = error or "試合日を変更しました"
            return
        if action.startswith("schedule_page|"):
            self.league_editor_schedule_page = max(0, self.league_editor_schedule_page + int(action.split("|", 1)[1]))
            return
        if action.startswith("upper|"):
            _, league_name, amount = action.split("|", 2)
            error = self.league_manager.cycle_upper_league(league_name, int(amount))
            self.league_save_message = error or "リーグの上下関係を保存しました"
            return
        if self.league_simulation_session is not None:
            return
        if action == "back":
            self.close_league_screen()
        elif action == "advance_day":
            self.league_schedule_scroll = 0
            fixture = self.league_manager.advance_day()
            if fixture is not None:
                self.start_league_fixture(fixture)
            else:
                self.start_league_simulations(self.league_manager.fixtures_on_day(self.league_manager.day, unplayed_only=True))
        elif action == "advance_matchday":
            self.league_schedule_scroll = 0
            fixture = self.league_manager.advance_to_next_matchday()
            if fixture is not None:
                self.start_league_fixture(fixture)
            else:
                self.start_league_simulations(self.league_manager.fixtures_on_day(self.league_manager.day, unplayed_only=True))
        elif action.startswith("toggle|"):
            self.league_schedule_scroll = 0
            overdue = self.league_manager.toggle_league(action.split("|", 1)[1])
            self.start_league_simulations(overdue)
        elif action.startswith("toggle_tournament|"):
            self.league_schedule_scroll = 0
            overdue = self.league_manager.toggle_tournament(action.split("|", 1)[1])
            self.start_league_simulations(overdue)
        elif action.startswith("view|"):
            self.league_view_name = action.split("|", 1)[1]
            self.league_editor_name = self.league_view_name
            self.league_editor_delete_confirm = ""
            self.league_team_scroll = 0
        elif action.startswith("tab|"):
            self.league_tab = action.split("|", 1)[1]
            if self.league_tab == "schedule":
                self.league_schedule_scroll = 0
        elif action.startswith("schedule_scroll|"):
            self.scroll_league_schedule(int(action.split("|", 1)[1]))
        elif action.startswith("watch|"):
            self.league_manager.toggle_watch(action.split("|", 1)[1])

    def handle_league_save_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            self.league_save_input_active = False
            self.league_template_input_active = False
            self.ime_composition = ""
            pygame.key.stop_text_input()
            return
        if getattr(self, "league_template_input_active", False):
            if event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
                self.league_template_name = ""
            elif event.key == pygame.K_BACKSPACE:
                self.league_template_name = self.league_template_name[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.handle_league_action("template_rename")
            return
        if not self.league_save_input_active:
            self.handle_key(event.key)
            return
        if event.key == pygame.K_BACKSPACE:
            self.league_new_save_name = self.league_new_save_name[:-1]
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.handle_league_action("new_save")

    def handle_league_editor_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            self.league_editor_input_active = False
            self.league_template_input_active = False
            self.ime_composition = ""
            pygame.key.stop_text_input()
        elif getattr(self, "league_template_input_active", False) and event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
            self.league_template_name = ""
        elif getattr(self, "league_template_input_active", False) and event.key == pygame.K_BACKSPACE:
            self.league_template_name = self.league_template_name[:-1]
        elif getattr(self, "league_template_input_active", False) and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.handle_league_action("template_rename")
            self.league_template_input_active = False
            self.ime_composition = ""
            pygame.key.stop_text_input()
        elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
            self.league_editor_name = ""
        elif event.key == pygame.K_BACKSPACE:
            self.league_editor_name = self.league_editor_name[:-1]
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.league_structure_kind == "league":
                self.handle_league_action("editor_rename")
            elif self.tournament_view_name:
                self.handle_league_action("tournament_rename")
            self.league_editor_input_active = False
            self.ime_composition = ""
            pygame.key.stop_text_input()

    def handle_league_text_input(self, text: str) -> None:
        if not text:
            return
        if getattr(self, "league_template_input_active", False):
            self.league_template_name = (self.league_template_name + text)[:40]
        elif self.league_save_select_open and self.league_save_input_active:
            self.league_new_save_name = (self.league_new_save_name + text)[:32]
        elif self.league_tab == "structure" and self.league_editor_input_active:
            self.league_editor_name = (self.league_editor_name + text)[:30]
        self.ime_composition = ""

    def start_selected_match(self) -> None:
        self.match = Match(
            self.team_choices[self.home_choice_index],
            self.team_choices[self.away_choice_index],
            self.venue_modes[self.venue_mode_index],
        )
        self.match.start_new()
        self.visible_simulation.reset(self.match)
        self.roll_stadium_guests()
        self.player_list_open = False
        self.reset_camera()

    def return_to_team_select(self) -> None:
        """Return from a finished or paused match to the initial team picker."""
        self.match.state = "TEAM_SELECT"
        self.league_screen_open = False
        self.active_league_fixture_id = ""
        self.league_match_finalized = False
        self.player_list_open = False
        self.fulltime_buttons.clear()
        self.pause_menu_buttons.clear()
        self.skip_match_in_progress = False
        self.league_skip_auto_return = False
        self.reset_camera()

    def resume_match(self) -> None:
        if self.match.state == "PAUSED":
            self.match.state = "PLAYING"
        self.pause_menu_buttons.clear()

    def abort_current_match(self) -> None:
        """Abandon this match without recording an unfinished league result."""
        self.stop_league_auto_progress(announce=False)
        self.skip_match_in_progress = False
        self.league_skip_auto_return = False
        self.pause_menu_buttons.clear()
        if self.active_league_fixture_id:
            if self.league_simulation_session is not None:
                self.league_simulation_session.cancel()
                self.league_simulation_session = None
            self.active_league_fixture_id = ""
            self.league_match_finalized = False
            self.league_live_last_status = []
            self.other_matches_open = False
            self.match.state = "TEAM_SELECT"
            self.league_screen_open = True
            self.league_save_select_open = False
            self.league_tab = "schedule"
            return
        self.return_to_team_select()

    def start_match_skip(self) -> None:
        """Finish the real match engine quickly while keeping the UI responsive."""
        if self.match.state not in ("PLAYING", "PAUSED"):
            return
        self.player_list_open = False
        self.other_matches_open = False
        self.pause_menu_buttons.clear()
        self.match.state = "PLAYING"
        self.skip_match_in_progress = True
        self.league_skip_auto_return = bool(self.active_league_fixture_id)

    def update_match_skip(self) -> None:
        if not self.skip_match_in_progress:
            return
        # Use the exact same fixed physics/AI step as normal and headless play.
        # A bounded batch leaves time for events and redraws between chunks.
        # CPU上限を下げても物理ステップそのものは省略せず、フレーム間に
        # 分散する。したがって結果の計算方法は通常観戦時と同じまま。
        step_budget = max(20, round(600 * int(getattr(self, "cpu_limit_percent", 100)) / 100.0))
        for _ in range(step_budget):
            if self.match.state == "FULLTIME":
                break
            advance_match_fixed(self.match)
        if self.match.state != "FULLTIME":
            return
        self.skip_match_in_progress = False
        self.finalize_league_match()

    def refresh_camera_transform(self) -> None:
        self.camera.update(self.camera_focus.x, self.camera_focus.y + CAMERA_BACK, CAMERA_HEIGHT)
        self.camera_target.update(self.camera_focus.x, self.camera_focus.y, 0)
        self.camera_forward = (self.camera_target - self.camera).normalize()
        self.camera_right = pygame.Vector3(0, 0, 1).cross(self.camera_forward).normalize()
        self.camera_up = self.camera_forward.cross(self.camera_right).normalize()

    def reset_camera(self) -> None:
        self.camera_focus.update(FIELD.center)
        self.camera_velocity.update(0, 0)
        self.focal_length = (
            CAMERA_FOCAL_LENGTHS.get(self.match.speed_multiplier, CAMERA_FOCAL_LENGTHS[1])
            * self.camera_zoom
        )
        self.refresh_camera_transform()

    def update_camera(self, dt: float) -> None:
        if self.match.state in ("MAIN_MENU", "TEAM_SELECT", "TITLE"):
            return

        desired = pygame.Vector2(self.match.ball.pos)
        desired.x = clamp(desired.x, FIELD.left + 300, FIELD.right - 300)
        desired.y = clamp(desired.y, FIELD.top + 230, FIELD.bottom - 230)

        target_focal = (
            CAMERA_FOCAL_LENGTHS.get(self.match.speed_multiplier, CAMERA_FOCAL_LENGTHS[1])
            * self.camera_zoom
        )
        zoom_blend = 1.0 - math.exp(-dt * 2.4)
        self.focal_length += (target_focal - self.focal_length) * zoom_blend

        # Keep small ball movements inside a stable screen region. At high match
        # speeds the dead zone grows while the camera zooms out, preventing rapid
        # end-to-end panning from becoming uncomfortable.
        zoom_out = CAMERA_FOCAL_LENGTHS[1] - self.focal_length
        dead_zone_x = clamp(88 + zoom_out * 0.48, 40, 205)
        dead_zone_y = clamp(68 + zoom_out * 0.36, 32, 160)
        error = desired - self.camera_focus
        correction = pygame.Vector2(
            math.copysign(max(0.0, abs(error.x) - dead_zone_x), error.x),
            math.copysign(max(0.0, abs(error.y) - dead_zone_y), error.y),
        )

        wanted_velocity = correction * 2.0
        if wanted_velocity.length() > CAMERA_MAX_SPEED:
            wanted_velocity.scale_to_length(CAMERA_MAX_SPEED)
        velocity_blend = 1.0 - math.exp(-dt * 4.0)
        self.camera_velocity += (wanted_velocity - self.camera_velocity) * velocity_blend
        self.camera_focus += self.camera_velocity * dt
        self.camera_focus.x = clamp(self.camera_focus.x, FIELD.left + 300, FIELD.right - 300)
        self.camera_focus.y = clamp(self.camera_focus.y, FIELD.top + 230, FIELD.bottom - 230)
        self.refresh_camera_transform()

    def handle_key(self, key: int) -> None:
        match = self.match
        if key == pygame.K_ESCAPE:
            if getattr(self, "settings_open", False):
                self.close_settings()
            else:
                self.open_settings()
            return
        if key == pygame.K_F10:
            self.cycle_window_size()
            return
        if key == pygame.K_F11:
            self.toggle_fullscreen()
            return
        if self.league_screen_open:
            if key == pygame.K_ESCAPE:
                if self.league_save_select_open:
                    self.close_league_screen()
                else:
                    self.league_manager.save()
                    self.league_save_select_open = True
            return
        if self.other_matches_open:
            if key in (pygame.K_ESCAPE, pygame.K_o):
                self.other_matches_open = False
            elif key == pygame.K_HOME:
                self.other_matches_scroll = 0
            elif key == pygame.K_END:
                self.other_matches_scroll = other_match_max_scroll(self.other_matches_status_count())
            elif key == pygame.K_PAGEUP:
                self.scroll_other_matches(-OTHER_MATCH_VISIBLE_ROWS)
            elif key == pygame.K_PAGEDOWN:
                self.scroll_other_matches(OTHER_MATCH_VISIBLE_ROWS)
            elif key == pygame.K_UP:
                self.scroll_other_matches(-1)
            elif key == pygame.K_DOWN:
                self.scroll_other_matches(1)
            return
        if match.state in ("PLAYING", "PAUSED", "FULLTIME"):
            if key == pygame.K_o and self.active_league_fixture_id:
                self.other_matches_open = not self.other_matches_open
                if self.other_matches_open:
                    self.other_matches_scroll = 0
                return
            if key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_LEFTBRACKET):
                self.change_camera_zoom(-1)
                return
            if key in (pygame.K_EQUALS, pygame.K_KP_PLUS, pygame.K_RIGHTBRACKET):
                self.change_camera_zoom(1)
                return
        if self.player_list_open:
            if key in (pygame.K_ESCAPE, pygame.K_p, pygame.K_TAB):
                self.player_list_open = False
            return
        if match.state == "MAIN_MENU":
            if key == pygame.K_1:
                self.open_team_editor()
            elif key == pygame.K_2:
                self.open_league_editor()
            elif key == pygame.K_3:
                self.open_league_screen()
            elif key == pygame.K_4:
                match.state = "TEAM_SELECT"
            return
        if match.state == "TEAM_SELECT":
            if key == pygame.K_q:
                self.cycle_team_choice("home", -1)
            elif key == pygame.K_e:
                self.cycle_team_choice("home", 1)
            elif key == pygame.K_a:
                self.cycle_team_choice("away", -1)
            elif key == pygame.K_d:
                self.cycle_team_choice("away", 1)
            elif key == pygame.K_v:
                self.venue_mode_index = (self.venue_mode_index + 1) % len(self.venue_modes)
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_selected_match()
        elif key in (pygame.K_RETURN, pygame.K_SPACE) and match.state == "FULLTIME":
            if self.active_league_fixture_id:
                self.return_to_league_screen()
            else:
                self.return_to_team_select()
        elif key == pygame.K_SPACE:
            if match.state == "TITLE":
                match.start_new()
                self.visible_simulation.reset(match)
                self.roll_stadium_guests()
                self.reset_camera()
            elif match.state == "PLAYING":
                match.state = "PAUSED"
            elif match.state == "PAUSED":
                self.resume_match()
        elif key == pygame.K_r and match.state == "FULLTIME":
            if not self.active_league_fixture_id:
                match.start_new()
                self.visible_simulation.reset(match)
                self.roll_stadium_guests()
                self.reset_camera()
        elif key == pygame.K_t and match.state in ("FULLTIME", "PAUSED"):
            if self.active_league_fixture_id and match.state == "FULLTIME":
                self.return_to_league_screen()
            else:
                self.return_to_team_select()
        elif key == pygame.K_f and match.state in ("PLAYING", "PAUSED"):
            current = SPEED_OPTIONS.index(match.speed_multiplier)
            match.speed_multiplier = SPEED_OPTIONS[(current + 1) % len(SPEED_OPTIONS)]
        elif key in (pygame.K_p, pygame.K_TAB) and match.state in ("PLAYING", "PAUSED", "FULLTIME"):
            self.player_list_open = True

    def handle_click(self, pos: tuple[int, int]) -> None:
        if getattr(self, "settings_open", False):
            self.handle_settings_click(pos)
            return
        if self.other_matches_open:
            if self.other_matches_close_button.collidepoint(pos):
                self.other_matches_open = False
            elif self.other_matches_scroll_track.collidepoint(pos):
                maximum = other_match_max_scroll(self.other_matches_status_count())
                if maximum > 0:
                    travel = max(1, self.other_matches_scroll_track.height - self.other_matches_scroll_thumb.height)
                    thumb_center = pos[1] - self.other_matches_scroll_track.top - self.other_matches_scroll_thumb.height * 0.5
                    self.other_matches_scroll = round(max(0, min(travel, thumb_center)) / travel * maximum)
            return
        if self.player_list_open:
            if self.player_list_close_button.collidepoint(pos):
                self.player_list_open = False
            elif self.player_list_rank_button.collidepoint(pos):
                self.player_list_rank_mode = not self.player_list_rank_mode
            return
        if self.league_screen_open:
            # Buttons are appended in draw order. Check the newest entry first
            # so an overlay (such as the editor sidebar) receives the click.
            for rect, action in reversed(self.league_buttons):
                if rect.collidepoint(pos):
                    self.handle_league_action(action)
                    return
            if self.league_tab == "schedule" and self.league_schedule_scroll_track.collidepoint(pos):
                maximum = schedule_max_scroll(len(self.league_manager.next_fixtures()))
                if maximum > 0:
                    travel = max(1, self.league_schedule_scroll_track.height - self.league_schedule_scroll_thumb.height)
                    thumb_center = pos[1] - self.league_schedule_scroll_track.top - self.league_schedule_scroll_thumb.height * 0.5
                    self.league_schedule_scroll = round(max(0, min(travel, thumb_center)) / travel * maximum)
            return
        if self.settings_button.collidepoint(pos):
            self.open_settings()
            return
        if self.match.state == "MAIN_MENU":
            for rect, action in self.main_menu_buttons:
                if not rect.collidepoint(pos):
                    continue
                if action == "team_editor":
                    self.open_team_editor()
                elif action == "league_editor":
                    self.open_league_editor()
                elif action == "league_start":
                    self.open_league_screen()
                elif action == "match_test":
                    self.match.state = "TEAM_SELECT"
                return
            return
        if self.match.state in ("PLAYING", "PAUSED", "FULLTIME"):
            if self.active_league_fixture_id and self.other_matches_button.collidepoint(pos):
                self.other_matches_open = True
                self.other_matches_scroll = 0
                return
            for rect, step in self.zoom_buttons:
                if rect.collidepoint(pos):
                    self.change_camera_zoom(step)
                    return
        if self.match.state == "PAUSED":
            for rect, action in self.pause_menu_buttons:
                if not rect.collidepoint(pos):
                    continue
                if action == "resume":
                    self.resume_match()
                elif action == "abort":
                    self.abort_current_match()
                elif action == "skip":
                    self.start_match_skip()
                return
            return
        if self.match.state == "TEAM_SELECT":
            for rect, action in self.team_select_buttons:
                if not rect.collidepoint(pos):
                    continue
                if action == "home_prev":
                    self.cycle_team_choice("home", -1)
                elif action == "home_next":
                    self.cycle_team_choice("home", 1)
                elif action == "away_prev":
                    self.cycle_team_choice("away", -1)
                elif action == "away_next":
                    self.cycle_team_choice("away", 1)
                elif action.startswith("venue_"):
                    self.venue_mode_index = self.venue_modes.index(action.removeprefix("venue_").upper())
                elif action == "start":
                    self.start_selected_match()
                elif action == "editor":
                    self.open_team_editor()
                elif action == "league":
                    self.open_league_screen()
                elif action == "main_menu":
                    self.return_to_main_menu()
                return
            return
        if self.match.state == "TITLE":
            self.match.start_new()
            self.visible_simulation.reset(self.match)
            self.roll_stadium_guests()
            self.reset_camera()
            return
        if self.player_list_button.collidepoint(pos):
            self.player_list_open = True
            return
        if self.match.state == "FULLTIME":
            for rect, action in self.fulltime_buttons:
                if rect.collidepoint(pos):
                    if action == "rematch":
                        self.match.start_new()
                        self.visible_simulation.reset(self.match)
                        self.roll_stadium_guests()
                        self.reset_camera()
                    elif action == "team_select":
                        self.return_to_team_select()
                    elif action == "league_results":
                        self.return_to_league_screen()
                    return
            return
        for rect, speed in self.speed_buttons:
            if rect.collidepoint(pos):
                self.match.speed_multiplier = speed

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif getattr(self, "settings_open", False):
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self.close_settings()
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.handle_settings_click(self.logical_mouse_pos(event.pos))
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self.league_team_detail_id:
                        self.league_team_detail_id = ""
                    else:
                        self.open_settings()
                elif self.team_editor_open:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_F10:
                        self.cycle_window_size()
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                        self.toggle_fullscreen()
                    else:
                        mouse_pos = self.logical_mouse_pos(event.pos) if hasattr(event, "pos") else None
                        self.team_editor.handle_event(event, mouse_pos)
                elif event.type == pygame.TEXTINPUT and self.league_screen_open:
                    self.handle_league_text_input(event.text)
                elif event.type == pygame.TEXTEDITING and self.league_screen_open:
                    self.ime_composition = event.text
                elif event.type == pygame.KEYDOWN:
                    if self.league_screen_open and self.league_save_select_open:
                        self.handle_league_save_key(event)
                    elif (
                        self.league_screen_open
                        and self.league_tab == "structure"
                        and (self.league_editor_input_active or self.league_template_input_active)
                    ):
                        self.handle_league_editor_key(event)
                    else:
                        self.handle_key(event.key)
                elif event.type == pygame.MOUSEWHEEL:
                    if self.other_matches_open:
                        self.scroll_other_matches(-event.y)
                    elif self.player_list_open:
                        pass
                    elif self.league_screen_open and not self.league_save_select_open:
                        mouse_pos = self.logical_mouse_pos()
                        team_editor_scroll = (
                            self.league_tab == "structure"
                            and self.league_structure_kind == "league"
                            and self.league_editor_mode == "teams"
                            and self.league_team_scroll_rect.collidepoint(mouse_pos)
                        )
                        schedule_scroll = (
                            self.league_tab == "schedule"
                            and self.league_schedule_scroll_rect.collidepoint(mouse_pos)
                        )
                        if schedule_scroll:
                            self.scroll_league_schedule(-event.y)
                        elif team_editor_scroll:
                            self.league_team_scroll = max(0, self.league_team_scroll - event.y)
                        else:
                            total = len(self.league_manager.league_names) + len(self.league_manager.tournament_names)
                            self.league_competition_scroll = max(0, min(max(0, total - 7), self.league_competition_scroll - event.y))
                    elif self.match.state in ("PLAYING", "PAUSED", "FULLTIME"):
                        self.change_camera_zoom(1 if event.y > 0 else -1)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(self.logical_mouse_pos(event.pos))
            self.update_league_simulations()
            self.update_match_skip()
            if (
                self.league_skip_auto_return
                and self.match.state == "FULLTIME"
                and self.league_simulation_session is None
            ):
                self.league_skip_auto_return = False
                self.return_to_league_screen()
            self.update_league_auto_progress(dt)
            if self.team_editor_open:
                if not self.settings_open:
                    self.team_editor.update(dt)
                self.team_editor.draw()
                if self.settings_open:
                    self.draw_settings_modal()
                self.present()
                continue
            if self.match.state == "PLAYING" and not self.league_screen_open and not self.skip_match_in_progress:
                self.visible_simulation.advance(self.match, dt)
                self.finalize_league_match()
                self.update_camera(dt)
            self.draw()
        if self.gpu_presenter is not None:
            self.gpu_presenter.destroy()
        if self.league_simulation_session is not None:
            self.league_simulation_session.cancel()
        pygame.quit()
