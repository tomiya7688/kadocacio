from __future__ import annotations

import math

import pygame

from scripts.core.performance_settings import LEAGUE_SIMULATION_MODES
from scripts.match.entities import Player
from scripts.league.league_rendering import LeagueRendererMixin
from scripts.league.league_live_view import (
    OTHER_MATCH_COLUMNS,
    OTHER_MATCH_VISIBLE_ROWS,
    clamp_other_match_scroll,
    other_match_max_scroll,
    visible_other_matches,
)
from scripts.match.match_engine import Match
from scripts.match.player_commands import PlayerCommand
from scripts.team.team_rating import compact_entity_grade_text
from scripts.core.stat_scale import denormalize_player_stat
from scripts.core.settings import (
    AWAY_BLUE, CENTER_CIRCLE_RADIUS, CREAM, FIELD, GOAL_AREA_DEPTH, GOAL_AREA_WIDTH,
    GOAL_DEPTH, GOAL_HALF_HEIGHT, GOAL_HEIGHT, GOLD, HEIGHT, HOME_DARK, HOME_RED, INK,
    LINE, MUTED, PANEL, PAPER, PENALTY_AREA_DEPTH, PENALTY_AREA_WIDTH,
    PENALTY_SPOT_DISTANCE, PITCH_1, PITCH_2, PLAYER_VISUAL_SCALE, SPEED_OPTIONS,
    TACTICS, TEAMS_DIR, WIDTH, clamp, darken_color,
)


class RendererMixin(LeagueRendererMixin):
    """Pygame projection and drawing methods used by Game."""

    def font(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont("Yu Gothic UI,Meiryo,MS Gothic,Arial", size, bold=bold)
        return self.fonts[key]

    def text(
        self,
        value: str,
        size: int,
        color: tuple[int, int, int],
        pos: tuple[int, int],
        *,
        bold: bool = False,
        center: bool = False,
        right: bool = False,
    ) -> pygame.Rect:
        key = (value, size, color, bold)
        surface = self.text_surface_cache.get(key)
        if surface is None:
            surface = self.font(size, bold).render(value, True, color)
            if len(self.text_surface_cache) >= 4096:
                self.text_surface_cache.clear()
            self.text_surface_cache[key] = surface
        rect = surface.get_rect()
        if center:
            rect.center = pos
        elif right:
            rect.topright = pos
        else:
            rect.topleft = pos
        self.screen.blit(surface, rect)
        return rect

    def draw_window_size_button(self, rect: pygame.Rect) -> None:
        gap = 5
        window_rect = pygame.Rect(rect.left, rect.top, max(112, rect.width - 94), rect.height)
        fullscreen_rect = pygame.Rect(window_rect.right + gap, rect.top, rect.right - window_rect.right - gap, rect.height)
        self.window_size_button = window_rect
        self.fullscreen_button = fullscreen_rect
        mouse = self.logical_mouse_pos()
        width, height = self.current_window_size
        for button, label, active in (
            (window_rect, f"F10 {width}×{height}", False),
            (fullscreen_rect, "F11 全画面", self.fullscreen),
        ):
            hover = button.collidepoint(mouse)
            color = GOLD if active or hover else (230, 226, 211)
            pygame.draw.rect(self.screen, color, button, border_radius=7)
            pygame.draw.rect(self.screen, (183, 180, 168), button, 2, border_radius=7)
            self.text(label, 10, INK, button.center, bold=True, center=True)

    def draw_settings_button(self, rect: pygame.Rect) -> None:
        self.settings_button = rect
        hover = rect.collidepoint(self.logical_mouse_pos())
        color = (37, 49, 62) if not hover else (48, 65, 80)
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        pygame.draw.rect(self.screen, (91, 112, 128), rect, 1, border_radius=8)
        self.text("ESC　設定", 11, (236, 240, 242), rect.center, bold=True, center=True)

    def draw_settings_modal(self) -> None:
        """Modern modal shared by title, match, league and team editor screens."""
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((5, 10, 17, 208))
        self.screen.blit(shade, (0, 0))

        card = pygame.Rect(WIDTH // 2 - 400, 40, 800, 640)
        shadow = pygame.Surface((card.width + 28, card.height + 28), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 95), shadow.get_rect(), border_radius=25)
        self.screen.blit(shadow, (card.left - 8, card.top + 7))
        pygame.draw.rect(self.screen, (18, 25, 34), card, border_radius=20)
        pygame.draw.rect(self.screen, (64, 79, 94), card, 1, border_radius=20)
        pygame.draw.rect(self.screen, (77, 198, 178), (card.left, card.top, card.width, 4), border_radius=2)

        self.settings_buttons = []
        mouse = self.logical_mouse_pos()

        def button(
            rect: pygame.Rect,
            label: str,
            action: str,
            *,
            active: bool = False,
            danger: bool = False,
            subtitle: str = "",
        ) -> None:
            hover = rect.collidepoint(mouse)
            if danger:
                fill = (166, 59, 69) if hover else (126, 45, 55)
                border = (225, 105, 112)
            elif active:
                fill = (31, 101, 94) if not hover else (38, 121, 111)
                border = (77, 198, 178)
            else:
                fill = (31, 41, 53) if not hover else (43, 57, 71)
                border = (69, 85, 100)
            pygame.draw.rect(self.screen, fill, rect, border_radius=10)
            pygame.draw.rect(self.screen, border, rect, 1, border_radius=10)
            label_y = rect.centery - (8 if subtitle else 0)
            self.text(label, 12, (244, 247, 248), (rect.centerx, label_y), bold=True, center=True)
            if subtitle:
                self.text(subtitle, 9, (166, 180, 191), (rect.centerx, rect.centery + 14), center=True)
            self.settings_buttons.append((rect, action))

        self.text("SETTINGS", 10, (77, 198, 178), (card.left + 32, card.top + 24), bold=True)
        self.text("ゲーム設定", 28, (244, 247, 248), (card.left + 32, card.top + 43), bold=True)
        self.text("Escでも閉じて元の画面へ戻れます", 11, (151, 166, 178), (card.left + 32, card.top + 81))
        close_rect = pygame.Rect(card.right - 66, card.top + 24, 38, 38)
        button(close_rect, "×", "close")

        panel_color = (23, 32, 43)
        panel_border = (48, 62, 76)
        cpu_panel = pygame.Rect(card.left + 28, card.top + 112, card.width - 56, 104)
        pygame.draw.rect(self.screen, panel_color, cpu_panel, border_radius=13)
        pygame.draw.rect(self.screen, panel_border, cpu_panel, 1, border_radius=13)
        self.text("CPU演算枠", 14, (230, 235, 238), (cpu_panel.left + 18, cpu_panel.top + 13), bold=True)
        self.text("同時試合数とフレーム内の計算量を制限", 10, (143, 157, 169), (cpu_panel.left + 128, cpu_panel.top + 17))
        cpu_values = (10, 25, 50, 75, 100)
        gap = 8
        chip_width = (cpu_panel.width - 36 - gap * 4) // 5
        for index, value in enumerate(cpu_values):
            rect = pygame.Rect(cpu_panel.left + 18 + index * (chip_width + gap), cpu_panel.top + 51, chip_width, 36)
            button(rect, f"{value}%", f"cpu:{value}", active=value == int(getattr(self, "cpu_limit_percent", 100)))

        league_panel = pygame.Rect(card.left + 28, card.top + 228, card.width - 56, 188)
        pygame.draw.rect(self.screen, panel_color, league_panel, border_radius=13)
        pygame.draw.rect(self.screen, panel_border, league_panel, 1, border_radius=13)
        self.text("リーグ戦の裏試合", 14, (230, 235, 238), (league_panel.left + 18, league_panel.top + 13), bold=True)
        self.text("ボール・衝突・時計は全モード共通。戦術AIの再判断頻度を変更", 10, (143, 157, 169), (league_panel.left + 162, league_panel.top + 17))
        mode = str(getattr(self, "league_simulation_mode", "PRECISE"))
        mode_descriptions = {
            "ULTRA_PRECISE": "高頻度更新 / 最高負荷",
            "PRECISE": "現在と同じ / 標準",
            "NORMAL": "更新を少し抑制",
            "LIGHT": "更新を大きく抑制",
        }
        mode_gap = 9
        mode_width = (league_panel.width - 36 - mode_gap * 3) // 4
        for index, (key, profile) in enumerate(LEAGUE_SIMULATION_MODES.items()):
            rect = pygame.Rect(league_panel.left + 18 + index * (mode_width + mode_gap), league_panel.top + 51, mode_width, 91)
            button(
                rect,
                str(profile["label"]),
                f"league_mode:{key}",
                active=key == mode,
                subtitle=mode_descriptions[key],
            )
        self.text("設定変更は次に開始する裏試合から反映されます", 9, (126, 143, 156), (league_panel.left + 18, league_panel.bottom - 27))

        display_panel = pygame.Rect(card.left + 28, card.top + 428, card.width - 56, 100)
        pygame.draw.rect(self.screen, panel_color, display_panel, border_radius=13)
        pygame.draw.rect(self.screen, panel_border, display_panel, 1, border_radius=13)
        self.text("画面・バックエンド", 14, (230, 235, 238), (display_panel.left + 18, display_panel.top + 13), bold=True)
        width, height = self.current_window_size
        gpu_enabled = bool(getattr(getattr(self, "performance_settings", None), "gpu_rendering", True))
        display_specs = (
            (f"{width} × {height}", "window_size", False, "ウィンドウサイズ"),
            ("全画面 ON" if self.fullscreen else "全画面 OFF", "fullscreen", self.fullscreen, "表示モード"),
            ("GPU描画 ON" if gpu_enabled else "GPU描画 OFF", "gpu_rendering", gpu_enabled, "次回起動から反映"),
        )
        display_gap = 9
        display_width = (display_panel.width - 36 - display_gap * 2) // 3
        for index, (label, action, active, subtitle) in enumerate(display_specs):
            rect = pygame.Rect(display_panel.left + 18 + index * (display_width + display_gap), display_panel.top + 48, display_width, 38)
            button(rect, label, action, active=active, subtitle=subtitle)

        backend = f"演算 {getattr(self, 'compute_backend_name', 'CPU')} / 描画 {getattr(self, 'render_backend_name', 'CPU (Surface)')}"
        self.text(backend, 10, (132, 149, 162), (card.left + 32, card.top + 545))
        previous_state = str(getattr(self, "settings_previous_match_state", ""))
        auto_running = bool(getattr(self, "league_auto_running", False))
        footer_y = card.bottom - 61
        if previous_state in ("PLAYING", "PAUSED"):
            if auto_running:
                button(pygame.Rect(card.left + 28, footer_y, 170, 40), "オート停止", "auto_stop", danger=True)
                button(pygame.Rect(card.left + 208, footer_y, 170, 40), "試合を中断", "abort", danger=True)
                button(pygame.Rect(card.left + 388, footer_y, 170, 40), "残りをスキップ", "skip")
                button(pygame.Rect(card.left + 568, footer_y, 184, 40), "閉じる", "close", active=True)
            else:
                button(pygame.Rect(card.left + 28, footer_y, 184, 40), "試合を中断", "abort", danger=True)
                button(pygame.Rect(card.left + 222, footer_y, 184, 40), "残りをスキップ", "skip")
                button(pygame.Rect(card.right - 212, footer_y, 184, 40), "閉じる", "close", active=True)
        elif auto_running:
            button(pygame.Rect(card.left + 28, footer_y, 184, 40), "オート停止", "auto_stop", danger=True)
            button(pygame.Rect(card.right - 212, footer_y, 184, 40), "閉じる", "close", active=True)
        else:
            button(pygame.Rect(card.right - 212, footer_y, 184, 40), "閉じる", "close", active=True)

    def project(self, x: float, y: float, z: float = 0.0) -> tuple[pygame.Vector2, float]:
        relative = pygame.Vector3(x, y, z) - self.camera
        depth = max(1.0, relative.dot(self.camera_forward))
        screen_x = self.view_center.x + self.focal_length * relative.dot(self.camera_right) / depth
        screen_y = self.view_center.y - self.focal_length * relative.dot(self.camera_up) / depth
        return pygame.Vector2(screen_x, screen_y), depth

    def world_line(
        self,
        color: tuple[int, int, int],
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        width: int = 2,
    ) -> None:
        point_a, _ = self.project(*start)
        point_b, _ = self.project(*end)
        pygame.draw.line(self.screen, color, point_a, point_b, width)

    def world_polygon(self, color: tuple[int, int, int], points: list[tuple[float, float, float]]) -> None:
        projected = [self.project(*point)[0] for point in points]
        pygame.draw.polygon(self.screen, color, projected)

    def world_circle(
        self,
        color: tuple[int, int, int],
        center_x: float,
        center_y: float,
        radius: float,
        width: int = 2,
    ) -> None:
        points = [
            self.project(
                center_x + math.cos(index / 36 * math.tau) * radius,
                center_y + math.sin(index / 36 * math.tau) * radius,
                0.7,
            )[0]
            for index in range(37)
        ]
        pygame.draw.lines(self.screen, color, True, points, width)

    def project_player_point(
        self,
        player: Player,
        x: float,
        y: float,
        z: float,
    ) -> tuple[pygame.Vector2, float]:
        """Project a body part around the player's feet at the visual scale.

        The player's world position and jump height stay unchanged; only the
        chibi model itself becomes smaller relative to the pitch.
        """
        scale = PLAYER_VISUAL_SCALE
        return self.project(
            player.pos.x + (x - player.pos.x) * scale,
            player.pos.y + (y - player.pos.y) * scale,
            player.z + (z - player.z) * scale,
        )

    def draw_stadium(self) -> None:
        # Layered sky, roof and terraces give the pixel grandstand a cleaner
        # modern silhouette while spectators still occupy the one-person grid.
        for band in range(8):
            color = (119 + band * 5, 170 + band * 5, 200 + band * 4)
            pygame.draw.rect(self.screen, color, (0, band * 14, PANEL.left, 15))
        pygame.draw.rect(self.screen, (24, 31, 41), (0, 45, PANEL.left, 28))
        pygame.draw.rect(self.screen, (52, 63, 75), (0, 72, PANEL.left, 9))
        for x in range(30, PANEL.left, 112):
            pygame.draw.polygon(self.screen, (58, 69, 80), [(x, 70), (x + 7, 70), (x + 25, 226), (x + 15, 226)])
        if self.stadium_seats is not None:
            self.screen.blit(self.stadium_seats, (0, 69))
        else:
            pygame.draw.rect(self.screen, (65, 74, 88), (0, 92, PANEL.left, 144))
            pygame.draw.polygon(
                self.screen,
                (43, 49, 60),
                [(0, 128), (PANEL.left, 100), (PANEL.left, 232), (0, 232)],
            )
        # Tier fascia and aisle markers stay visible over either the generated
        # seat asset or the no-asset fallback.
        pygame.draw.rect(self.screen, (42, 52, 63), (0, 119, PANEL.left, 7))
        pygame.draw.rect(self.screen, (47, 58, 69), (0, 166, PANEL.left, 7))
        pygame.draw.rect(self.screen, (54, 66, 76), (0, 214, PANEL.left, 8))
        for x in range(0, PANEL.left, 160):
            pygame.draw.polygon(self.screen, (122, 128, 126), [(x + 67, 84), (x + 78, 84), (x + 102, 218), (x + 88, 218)])
        guest_seats = {(x, y) for _, x, y, _ in self.special_spectators}
        crowd_phase = float(getattr(self.match, "simulation_elapsed", 0.0)) * 2.4
        for x, y, color in self.crowd:
            if (x, y) in guest_seats:
                continue
            # Block-built spectators sit over the generated empty seats. Rear
            # rows are smaller to retain the grandstand's depth.
            size = 1 if y < 132 else 2
            cheer = size == 2 and (x * 3 + y) % 53 == 0
            bounce = -1 if cheer and math.sin(crowd_phase + x * 0.07) > 0.45 else 0
            pygame.draw.rect(
                self.screen,
                (226, 190, 151),
                (x - size, y - size * 3 + bounce, size * 2, size * 2),
            )
            pygame.draw.rect(self.screen, color, (x - size, y - size + bounce, size * 2, size * 3))
            if size == 2:
                highlight = tuple(min(255, channel + 34) for channel in color)
                pygame.draw.line(self.screen, highlight, (x - 1, y + bounce), (x - 1, y + 2 + bounce), 1)
                if cheer:
                    pygame.draw.line(self.screen, color, (x - 2, y + bounce), (x - 5, y - 4 + bounce), 1)
                    pygame.draw.line(self.screen, color, (x + 2, y + bounce), (x + 5, y - 4 + bounce), 1)
        for kind, x, y, size in self.special_spectators:
            sprite = self.special_spectator_sprites.get(kind)
            if sprite is None:
                continue
            aspect = sprite.get_width() / max(1, sprite.get_height())
            guest = pygame.transform.scale(sprite, (max(1, round(size * aspect)), size))
            self.screen.blit(guest, guest.get_rect(midbottom=(x, y + 4)))
        pygame.draw.line(self.screen, (227, 189, 83), (0, 226), (PANEL.left, 226), 4)
        pygame.draw.rect(self.screen, (90, 96, 96), (0, 230, PANEL.left, 17))
        pygame.draw.line(self.screen, (195, 201, 196), (0, 230), (PANEL.left, 230), 2)

    def draw_goal(self, goal_x: float, outward: float) -> None:
        front_top = (goal_x, FIELD.centery - GOAL_HALF_HEIGHT, GOAL_HEIGHT)
        front_bottom = (goal_x, FIELD.centery + GOAL_HALF_HEIGHT, GOAL_HEIGHT)
        left_ground = (goal_x, FIELD.centery - GOAL_HALF_HEIGHT, 0)
        right_ground = (goal_x, FIELD.centery + GOAL_HALF_HEIGHT, 0)
        back_x = goal_x + outward
        frame = (239, 242, 233)
        net = (176, 197, 193)
        self.world_line(frame, left_ground, front_top, 4)
        self.world_line(frame, right_ground, front_bottom, 4)
        self.world_line(frame, front_top, front_bottom, 4)
        self.world_line(net, front_top, (back_x, FIELD.centery - GOAL_HALF_HEIGHT, GOAL_HEIGHT), 2)
        self.world_line(net, front_bottom, (back_x, FIELD.centery + GOAL_HALF_HEIGHT, GOAL_HEIGHT), 2)
        self.world_line(net, (back_x, FIELD.centery - GOAL_HALF_HEIGHT, GOAL_HEIGHT), (back_x, FIELD.centery - GOAL_HALF_HEIGHT, 0), 2)
        self.world_line(net, (back_x, FIELD.centery + GOAL_HALF_HEIGHT, GOAL_HEIGHT), (back_x, FIELD.centery + GOAL_HALF_HEIGHT, 0), 2)
        for step in range(1, 6):
            y = FIELD.centery - GOAL_HALF_HEIGHT + step * GOAL_HALF_HEIGHT * 2 / 6
            self.world_line(net, (goal_x, y, 0), (back_x, y, 0), 1)
            self.world_line(net, (back_x, y, 0), (back_x, y, GOAL_HEIGHT), 1)
        for step in range(1, 4):
            z = step * GOAL_HEIGHT / 4
            self.world_line(net, (goal_x, FIELD.centery - GOAL_HALF_HEIGHT, z), (back_x, FIELD.centery - GOAL_HALF_HEIGHT, z), 1)
            self.world_line(net, (goal_x, FIELD.centery + GOAL_HALF_HEIGHT, z), (back_x, FIELD.centery + GOAL_HALF_HEIGHT, z), 1)

    def draw_pitch(self) -> None:
        self.draw_stadium()
        border = 16
        self.world_polygon(
            (43, 91, 60),
            [
                (FIELD.left - border, FIELD.top - border, -1),
                (FIELD.right + border, FIELD.top - border, -1),
                (FIELD.right + border, FIELD.bottom + border, -1),
                (FIELD.left - border, FIELD.bottom + border, -1),
            ],
        )
        stripe_width = FIELD.width / 10
        for index in range(10):
            x1 = FIELD.left + index * stripe_width
            x2 = x1 + stripe_width + 0.5
            self.world_polygon(
                PITCH_1 if index % 2 == 0 else PITCH_2,
                [(x1, FIELD.top, 0), (x2, FIELD.top, 0), (x2, FIELD.bottom, 0), (x1, FIELD.bottom, 0)],
            )

        z = 0.8
        self.world_line(LINE, (FIELD.left, FIELD.top, z), (FIELD.right, FIELD.top, z), 3)
        self.world_line(LINE, (FIELD.right, FIELD.top, z), (FIELD.right, FIELD.bottom, z), 3)
        self.world_line(LINE, (FIELD.right, FIELD.bottom, z), (FIELD.left, FIELD.bottom, z), 3)
        self.world_line(LINE, (FIELD.left, FIELD.bottom, z), (FIELD.left, FIELD.top, z), 3)
        self.world_line(LINE, (FIELD.centerx, FIELD.top, z), (FIELD.centerx, FIELD.bottom, z), 3)
        self.world_circle(LINE, FIELD.centerx, FIELD.centery, CENTER_CIRCLE_RADIUS, 3)

        center_spot, center_depth = self.project(FIELD.centerx, FIELD.centery, 1)
        pygame.draw.circle(self.screen, LINE, center_spot, max(2, round(4 * self.focal_length / center_depth)))
        penalty_w, penalty_h = PENALTY_AREA_DEPTH, PENALTY_AREA_WIDTH
        for x1, x2 in ((FIELD.left, FIELD.left + penalty_w), (FIELD.right, FIELD.right - penalty_w)):
            top = FIELD.centery - penalty_h / 2
            bottom = FIELD.centery + penalty_h / 2
            self.world_line(LINE, (x1, top, z), (x2, top, z), 3)
            self.world_line(LINE, (x2, top, z), (x2, bottom, z), 3)
            self.world_line(LINE, (x2, bottom, z), (x1, bottom, z), 3)
        small_w, small_h = GOAL_AREA_DEPTH, GOAL_AREA_WIDTH
        for x1, x2 in ((FIELD.left, FIELD.left + small_w), (FIELD.right, FIELD.right - small_w)):
            top = FIELD.centery - small_h / 2
            bottom = FIELD.centery + small_h / 2
            self.world_line(LINE, (x1, top, z), (x2, top, z), 2)
            self.world_line(LINE, (x2, top, z), (x2, bottom, z), 2)
            self.world_line(LINE, (x2, bottom, z), (x1, bottom, z), 2)
        for x in (FIELD.left + PENALTY_SPOT_DISTANCE, FIELD.right - PENALTY_SPOT_DISTANCE):
            spot, depth = self.project(x, FIELD.centery, 1)
            pygame.draw.circle(self.screen, LINE, spot, max(2, round(3.5 * self.focal_length / depth)))
        self.draw_goal(FIELD.left, -GOAL_DEPTH)
        self.draw_goal(FIELD.right, GOAL_DEPTH)

    def draw_player_label(self, player: Player, base_z: float) -> None:
        if self.match.ball.owner is not player:
            return
        label_pos, _ = self.project(player.pos.x, player.pos.y, player.z + 63 * PLAYER_VISUAL_SCALE)
        action_label = player.action_command.value
        if player.skill_command is not PlayerCommand.IDLE:
            action_label = player.skill_command.value
        if player.technique_command is PlayerCommand.TRAP and player.last_trap_style:
            action_label = player.last_trap_style
        label_text = f"{player.name}｜{action_label}"
        label = self.font(13, True).render(label_text, True, CREAM)
        label_shadow = self.font(13, True).render(label_text, True, INK)
        self.screen.blit(label_shadow, label_shadow.get_rect(center=(label_pos.x + 1, label_pos.y + 1)))
        self.screen.blit(label, label.get_rect(center=label_pos))
        stamina_bar = pygame.Rect(round(label_pos.x - 24), round(label_pos.y + 10), 48, 5)
        pygame.draw.rect(self.screen, INK, stamina_bar, border_radius=2)
        stamina_ratio = player.stamina_ratio
        stamina_color = (73, 190, 103) if stamina_ratio > 0.5 else GOLD if stamina_ratio > 0.25 else HOME_RED
        stamina_fill = stamina_bar.copy()
        stamina_fill.width = round(stamina_bar.width * stamina_ratio)
        if stamina_fill.width > 0:
            pygame.draw.rect(self.screen, stamina_color, stamina_fill, border_radius=2)

    def draw_block_limb(
        self,
        start: pygame.Vector2,
        end: pygame.Vector2,
        width: int,
        color: tuple[int, int, int],
    ) -> None:
        """Draw a square-ended limb so players read as block figures."""
        start = pygame.Vector2(start)
        end = pygame.Vector2(end)
        delta = end - start
        if delta.length_squared() < 0.01:
            rect = pygame.Rect(0, 0, width, width)
            rect.center = start
            pygame.draw.rect(self.screen, color, rect)
            pygame.draw.rect(self.screen, INK, rect, 1)
            return
        normal = pygame.Vector2(-delta.y, delta.x).normalize() * width * 0.5
        block = [start + normal, end + normal, end - normal, start - normal]
        pygame.draw.polygon(self.screen, color, block)
        pygame.draw.lines(self.screen, INK, True, block, 1)
        if width >= 3:
            highlight = tuple(min(255, channel + 34) for channel in color)
            pygame.draw.line(self.screen, highlight, start + normal * 0.35, end + normal * 0.35, 1)

    def draw_square_head(self, center: pygame.Vector2, size: int) -> None:
        head = pygame.Rect(0, 0, size, size)
        head.center = center
        shadow = head.move(max(1, size // 9), max(1, size // 10))
        pygame.draw.rect(self.screen, (70, 49, 40), shadow, border_radius=max(1, size // 7))
        pygame.draw.rect(self.screen, (239, 188, 143), head)
        pygame.draw.rect(self.screen, INK, head, 1)
        if size >= 7:
            pygame.draw.rect(self.screen, (91, 58, 42), (head.left + 1, head.top + 1, head.width - 2, max(2, size // 5)))
            pygame.draw.line(self.screen, (252, 211, 169), (head.left + 2, head.top + max(2, size // 4)), (head.right - 2, head.top + max(2, size // 4)), 1)
        eye_height = max(2, size // 3)
        eye_y = head.centery - eye_height // 2
        eye_offset = max(2, size // 5)
        eye_width = max(1, size // 10)
        pygame.draw.line(self.screen, INK, (head.centerx - eye_offset, eye_y), (head.centerx - eye_offset, eye_y + eye_height), eye_width)
        pygame.draw.line(self.screen, INK, (head.centerx + eye_offset, eye_y), (head.centerx + eye_offset, eye_y + eye_height), eye_width)

    def draw_horizontal_player(self, player: Player, scale: float) -> None:
        diving_pose = player.diving_header_active or player.heading_motion == "FALLEN"
        direction = pygame.Vector2(player.heading_direction if diving_pose else player.slide_direction)
        if direction.length_squared() < 0.0001:
            direction.update(player.team.direction, 0)
        else:
            direction = direction.normalize()
        side = pygame.Vector2(-direction.y, direction.x)
        body_z = player.z + (5 if diving_pose else 2)
        if diving_pose:
            head_world = player.pos + direction * 25
            shoulder_center = player.pos + direction * 11
            hip_center = player.pos - direction * 7
            foot_center = player.pos - direction * 27
        else:
            head_world = player.pos - direction * 25
            shoulder_center = player.pos - direction * 11
            hip_center = player.pos + direction * 6
            foot_center = player.pos + direction * 27

        hip_left, _ = self.project_player_point(player, *(hip_center + side * 7), body_z + 5)
        hip_right, _ = self.project_player_point(player, *(hip_center - side * 7), body_z + 5)
        shoulder_left, _ = self.project_player_point(player, *(shoulder_center + side * 10), body_z + 9)
        shoulder_right, _ = self.project_player_point(player, *(shoulder_center - side * 10), body_z + 9)
        torso = [hip_left, hip_right, shoulder_right, shoulder_left]
        pygame.draw.polygon(self.screen, player.team.primary, torso)
        pygame.draw.lines(self.screen, CREAM, True, torso, 1)

        kick_lift = math.sin(player.kick_motion_progress * math.pi) * 12 if player.kick_motion_progress > 0 else 0
        foot_left_world = foot_center + side * 7
        foot_right_world = foot_center - side * 7
        if player.kick_motion_progress > 0:
            foot_right_world += direction * (player.kick_motion_progress * 17)
        foot_left, _ = self.project_player_point(player, *foot_left_world, body_z + 1)
        foot_right, _ = self.project_player_point(player, *foot_right_world, body_z + 1 + kick_lift)
        self.draw_block_limb(hip_left, foot_left, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)), player.team.secondary)
        self.draw_block_limb(hip_right, foot_right, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)), player.team.secondary)

        arm_left_world = shoulder_center + side * 19 + direction * (5 if diving_pose else 0)
        arm_right_world = shoulder_center - side * 19 + direction * (5 if diving_pose else 0)
        arm_left, _ = self.project_player_point(player, *arm_left_world, body_z + 5)
        arm_right, _ = self.project_player_point(player, *arm_right_world, body_z + 5)
        self.draw_block_limb(shoulder_left, arm_left, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)), player.team.primary)
        self.draw_block_limb(shoulder_right, arm_right, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)), player.team.primary)

        head, head_depth = self.project_player_point(player, *head_world, body_z + 10)
        head_size = max(5, round(14 * PLAYER_VISUAL_SCALE * self.focal_length / head_depth))
        self.draw_square_head(head, head_size)
        chest = (shoulder_left + shoulder_right + hip_left + hip_right) / 4
        number = self.font(max(6, min(10, round(10 * scale * PLAYER_VISUAL_SCALE))), True).render(str(player.number), True, CREAM)
        self.screen.blit(number, number.get_rect(center=chest))
        self.draw_player_label(player, body_z + 6)

    def draw_player(self, player: Player) -> None:
        ground, ground_depth = self.project(player.pos.x, player.pos.y, 0)
        scale = self.focal_length / ground_depth
        horizontal_pose = player.ground_motion_active or player.diving_header_active
        shadow_width = max(5, round((48 if horizontal_pose else 21) * scale * PLAYER_VISUAL_SCALE))
        shadow_height = max(2, round((13 if horizontal_pose else 8) * scale * PLAYER_VISUAL_SCALE))
        shadow_alpha = max(65, 145 - round(player.z * 1.5))
        shadow = pygame.Surface((shadow_width + 4, shadow_height + 4), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (20, 45, 29, shadow_alpha), shadow.get_rect())
        self.screen.blit(shadow, shadow.get_rect(center=ground))

        if horizontal_pose:
            self.draw_horizontal_player(player, scale)
            return

        velocity = pygame.Vector2(player.motion_velocity)
        speed = velocity.length()
        moving = speed > 4.0 and player.z < 2.0
        forward = velocity.normalize() if moving else pygame.Vector2(player.team.direction, 0)
        side = pygame.Vector2(-forward.y, forward.x)
        motion_time = float(getattr(self.match, "simulation_elapsed", 0.0))
        gait_phase = math.sin(motion_time * (7.0 + min(7.0, speed / 85.0)) + player.number * 0.83)
        stride = gait_phase * min(10.0, 2.5 + speed / 42.0) if moving else 0.0
        base_z = player.z + (abs(gait_phase) * 1.8 if moving else 0.0)
        kick_phase = player.kick_motion_progress
        kick_shift = 0.0
        kick_lift = 0.0
        body_lean = 0.0
        header_shift = pygame.Vector2()
        if kick_phase > 0.0:
            if kick_phase < 0.35:
                kick_shift = -12 * (kick_phase / 0.35)
            else:
                swing = (kick_phase - 0.35) / 0.65
                kick_shift = -12 + 38 * swing
            kick_lift = math.sin(kick_phase * math.pi) * 11
            body_lean = math.sin(kick_phase * math.pi) * 4
        if player.heading_motion == "STANDING" and player.heading_motion_timer > 0.0:
            header_phase = 1.0 - player.heading_motion_timer / 0.48
            header_shift = player.heading_direction * (math.sin(clamp(header_phase, 0.0, 1.0) * math.pi) * 10)
        if player.knockback_timer > 0.0 and player.knockback_velocity.length_squared() > 0.01:
            stumble = clamp(player.knockback_timer / 0.42, 0.0, 1.0)
            header_shift -= player.knockback_velocity.normalize() * (8 + stumble * 6)
        left_foot_world = pygame.Vector2(player.pos) - side * 5 + forward * stride
        right_foot_world = pygame.Vector2(player.pos) + side * 5 - forward * stride
        left_foot_z = right_foot_z = base_z + 1
        if player.number % 2 == 0:
            left_foot_world += forward * kick_shift
            left_foot_z += kick_lift
        else:
            right_foot_world += forward * kick_shift
            right_foot_z += kick_lift
        left_hip_world = pygame.Vector2(player.pos) - side * 5
        right_hip_world = pygame.Vector2(player.pos) + side * 5
        left_foot, _ = self.project_player_point(player, *left_foot_world, left_foot_z)
        right_foot, _ = self.project_player_point(player, *right_foot_world, right_foot_z)
        left_hip, _ = self.project_player_point(player, *left_hip_world, base_z + 17)
        right_hip, _ = self.project_player_point(player, *right_hip_world, base_z + 17)
        self.draw_block_limb(left_foot, left_hip, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)), player.team.secondary)
        self.draw_block_limb(right_foot, right_hip, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)), player.team.secondary)

        body_center = pygame.Vector2(player.pos) + forward * body_lean + header_shift
        lower_left = pygame.Vector2(player.pos) - side * 9
        lower_right = pygame.Vector2(player.pos) + side * 9
        upper_left = body_center - side * 11
        upper_right = body_center + side * 11
        torso = [
            self.project_player_point(player, *lower_left, base_z + 16)[0],
            self.project_player_point(player, *lower_right, base_z + 16)[0],
            self.project_player_point(player, *upper_right, base_z + 36)[0],
            self.project_player_point(player, *upper_left, base_z + 36)[0],
        ]
        pygame.draw.polygon(self.screen, player.team.primary, torso)
        pygame.draw.lines(self.screen, INK, True, torso, 1)
        jersey_highlight = tuple(min(255, channel + 48) for channel in player.team.primary)
        pygame.draw.line(self.screen, jersey_highlight, torso[3], torso[2], 1)
        arm_swing = forward * (-stride * 0.7)
        arm_left_world = body_center - side * 17 + arm_swing
        arm_right_world = body_center + side * 17 - arm_swing
        arm_left, _ = self.project_player_point(player, *arm_left_world, base_z + 23)
        arm_right, _ = self.project_player_point(player, *arm_right_world, base_z + 23)
        shoulder_left, _ = self.project_player_point(player, *upper_left, base_z + 32)
        shoulder_right, _ = self.project_player_point(player, *upper_right, base_z + 32)
        self.draw_block_limb(shoulder_left, arm_left, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)), player.team.primary)
        self.draw_block_limb(shoulder_right, arm_right, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)), player.team.primary)

        head_world = pygame.Vector2(player.pos) + forward * body_lean * 1.2 + header_shift * 1.35
        head, head_depth = self.project_player_point(player, *head_world, base_z + 45)
        head_size = max(5, round(14 * PLAYER_VISUAL_SCALE * self.focal_length / head_depth))
        self.draw_square_head(head, head_size)
        chest, _ = self.project_player_point(player, *body_center, base_z + 27)
        number_size = max(6, min(10, round(10 * scale * PLAYER_VISUAL_SCALE)))
        number_color = INK if sum(player.team.primary) > 570 else CREAM
        number = self.font(number_size, True).render(str(player.number), True, number_color)
        self.screen.blit(number, number.get_rect(center=chest))

        if moving and speed > 150 and player.z < 1.0:
            trail_start, _ = self.project_player_point(player, *(pygame.Vector2(player.pos) - forward * 18 - side * 7), 9)
            trail_end, _ = self.project_player_point(player, *(pygame.Vector2(player.pos) - forward * 36 - side * 7), 9)
            pygame.draw.line(self.screen, (*player.team.secondary, 150), trail_start, trail_end, max(1, round(scale)))

        self.draw_player_label(player, base_z)

    def draw_ball(self) -> None:
        ball = self.match.ball
        ground, ground_depth = self.project(ball.pos.x, ball.pos.y, 0)
        ball_point, ball_depth = self.project(ball.pos.x, ball.pos.y, ball.z)
        shadow_scale = self.focal_length / ground_depth
        pygame.draw.ellipse(
            self.screen,
            (31, 68, 43),
            (
                round(ground.x - 7 * shadow_scale),
                round(ground.y - 2 * shadow_scale),
                max(4, round(14 * shadow_scale)),
                max(2, round(5 * shadow_scale)),
            ),
        )
        radius = max(3, round(6 * self.focal_length / ball_depth))
        pygame.draw.circle(self.screen, CREAM, ball_point, radius)
        pygame.draw.circle(self.screen, INK, ball_point, radius, 1)
        pygame.draw.circle(self.screen, INK, (round(ball_point.x + 1), round(ball_point.y - 1)), max(1, radius // 3))

    def draw_referee(self) -> None:
        referee = self.match.referee_pos
        ground, depth = self.project(referee.x, referee.y, 0)
        scale = self.focal_length / depth
        pygame.draw.ellipse(
            self.screen,
            (31, 57, 39),
            (ground.x - 11 * scale, ground.y - 3 * scale, 22 * scale, 7 * scale),
        )
        hip, _ = self.project(referee.x, referee.y, 19)
        shoulder, _ = self.project(referee.x, referee.y, 39)
        head, head_depth = self.project(referee.x, referee.y, 49)
        leg_width = max(2, round(4 * scale))
        pygame.draw.line(self.screen, INK, hip, (ground.x - 6 * scale, ground.y), leg_width)
        pygame.draw.line(self.screen, INK, hip, (ground.x + 6 * scale, ground.y), leg_width)
        torso = pygame.Rect(0, 0, max(7, round(20 * scale)), max(10, round(23 * scale)))
        torso.center = ((hip.x + shoulder.x) / 2, (hip.y + shoulder.y) / 2)
        pygame.draw.rect(self.screen, (210, 229, 67), torso, border_radius=max(2, round(3 * scale)))
        pygame.draw.rect(self.screen, INK, torso, 1, border_radius=max(2, round(3 * scale)))
        radius = max(4, round(7 * self.focal_length / head_depth))
        pygame.draw.circle(self.screen, (221, 168, 124), head, radius)
        pygame.draw.circle(self.screen, INK, head, radius, 1)
        if self.match.referee_active and self.match.referee_card:
            card_point, _ = self.project(referee.x, referee.y, 70)
            card_color = HOME_RED if self.match.referee_card == "RED" else GOLD
            card = pygame.Rect(round(card_point.x - 4), round(card_point.y - 7), 8, 14)
            pygame.draw.rect(self.screen, card_color, card, border_radius=1)
            pygame.draw.rect(self.screen, INK, card, 1, border_radius=1)

    def draw_scoreboard(self) -> None:
        pitch_screen_center = PANEL.left // 2
        board = pygame.Rect(pitch_screen_center - 190, 17, 380, 46)
        pygame.draw.rect(self.screen, INK, board, border_radius=8)
        self.text(self.match.home.short_name, 17, CREAM, (board.left + 18, board.top + 12), bold=True, center=False)
        self.text(self.match.away.short_name, 17, CREAM, (board.right - 18, board.top + 12), bold=True, right=True)
        score = f"{self.match.home.score}  -  {self.match.away.score}"
        self.text(score, 25, GOLD, (board.centerx, board.centery), bold=True, center=True)
        minute = min(90, int(self.match.game_time // 60))
        second = 0 if minute >= 90 else int(self.match.game_time % 60)
        time_label = "HT" if self.match.banner == "HALF TIME" and self.match.banner_timer > 0 else f"{minute}:{second:02d}"
        self.text(time_label, 16, INK, (20, 28), bold=True)
        self.text(f"SPEED ×{self.match.speed_multiplier}", 13, MUTED, (PANEL.left - 20, 31), bold=True, right=True)

    def draw_panel(self) -> None:
        pygame.draw.rect(self.screen, PAPER, PANEL, border_radius=12)
        pygame.draw.rect(self.screen, (217, 211, 192), PANEL, 2, border_radius=12)
        x = PANEL.left + 18
        team_title = self.match.home.name.replace("_", " ")
        self.text(team_title, 18, INK, (x, PANEL.top + 18), bold=True)
        manager_label = f"{self.match.home.short_name}　監督 {self.match.home.manager}" if self.match.home.manager else self.match.home.short_name
        self.text(manager_label, 12, MUTED, (x, PANEL.top + 48))
        self.text(self.match.venue_name, 10, MUTED, (PANEL.right - 18, PANEL.top + 50), right=True)
        speed_label_y = PANEL.top + 82
        speed_button_y = PANEL.top + 108
        divider_y = PANEL.top + 174
        self.text("試合速度", 16, INK, (x, speed_label_y), bold=True)
        self.text("Fで順送り", 11, MUTED, (PANEL.right - 18, speed_label_y + 5), right=True)
        self.speed_buttons.clear()
        for index, speed in enumerate(SPEED_OPTIONS):
            rect = pygame.Rect(x + index * 45, speed_button_y, 41, 38)
            self.speed_buttons.append((rect, speed))
            active = self.match.speed_multiplier == speed
            hover = rect.collidepoint(self.logical_mouse_pos())
            color = GOLD if active else (239, 234, 214) if hover else (230, 226, 211)
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            pygame.draw.rect(self.screen, INK if active else (190, 188, 176), rect, 2, border_radius=6)
            self.text(f"×{speed}", 12, INK, rect.center, bold=True, center=True)

        pygame.draw.line(self.screen, (211, 207, 192), (x, divider_y), (PANEL.right - 18, divider_y), 2)
        self.text("MATCH DATA", 15, INK, (x, divider_y + 17), bold=True)
        self.text("シュート", 13, MUTED, (x, divider_y + 48))
        self.text(str(self.match.home.shots), 18, self.match.home.primary, (x + 104, divider_y + 43), bold=True, center=True)
        self.text(str(self.match.away.shots), 18, self.match.away.primary, (x + 205, divider_y + 43), bold=True, center=True)
        self.text(self.match.home.short_name, 11, MUTED, (x + 104, divider_y + 68), center=True)
        self.text(self.match.away.short_name, 11, MUTED, (x + 205, divider_y + 68), center=True)

        possession_total = self.match.home.possession + self.match.away.possession
        home_share = self.match.home.possession / possession_total if possession_total else 0.5
        bar = pygame.Rect(x, divider_y + 92, PANEL.width - 36, 15)
        pygame.draw.rect(self.screen, self.match.away.primary, bar, border_radius=6)
        if home_share > 0:
            home_bar = pygame.Rect(bar.x, bar.y, round(bar.width * home_share), bar.height)
            pygame.draw.rect(self.screen, self.match.home.primary, home_bar, border_radius=6)
        self.text(f"支配率  {round(home_share * 100)}%", 12, INK, (x, divider_y + 115), bold=True)
        self.text(f"{round((1-home_share) * 100)}%", 12, INK, (PANEL.right - 18, divider_y + 115), bold=True, right=True)

        log_y = divider_y + 148
        self.text("MATCH LOG", 15, INK, (x, log_y), bold=True)
        for index, (minute, event) in enumerate(self.match.events):
            y = log_y + 27 + index * 25
            if y > PANEL.bottom - 144:
                break
            pygame.draw.circle(self.screen, GOLD if index == 0 else (200, 196, 182), (x + 4, y + 8), 3)
            self.text(f"{minute:02d}'", 12, MUTED, (x + 14, y + 1), bold=True)
            self.text(event, 12, INK, (x + 50, y + 1))

        zoom_y = PANEL.bottom - 120
        if self.active_league_fixture_id:
            self.other_matches_button = pygame.Rect(x, zoom_y - 39, PANEL.width - 36, 31)
            hover = self.other_matches_button.collidepoint(self.logical_mouse_pos())
            pygame.draw.rect(self.screen, GOLD if hover else (230, 226, 211), self.other_matches_button, border_radius=6)
            pygame.draw.rect(self.screen, (183, 180, 168), self.other_matches_button, 2, border_radius=6)
            self.text("O　他の試合（リアルタイム）", 11, INK, self.other_matches_button.center, bold=True, center=True)
        self.text(f"カメラズーム　{round(self.camera_zoom * 100)}%", 12, INK, (x, zoom_y + 7), bold=True)
        self.zoom_buttons.clear()
        for rect, step, label in (
            (pygame.Rect(PANEL.right - 104, zoom_y, 38, 30), -1, "−"),
            (pygame.Rect(PANEL.right - 60, zoom_y, 38, 30), 1, "＋"),
        ):
            self.zoom_buttons.append((rect, step))
            hover = rect.collidepoint(self.logical_mouse_pos())
            pygame.draw.rect(self.screen, GOLD if hover else (230, 226, 211), rect, border_radius=6)
            pygame.draw.rect(self.screen, (183, 180, 168), rect, 2, border_radius=6)
            self.text(label, 18, INK, rect.center, bold=True, center=True)

        self.draw_settings_button(pygame.Rect(x, PANEL.bottom - 84, PANEL.width - 36, 30))
        self.player_list_button = pygame.Rect(x, PANEL.bottom - 48, PANEL.width - 36, 34)
        hover = self.player_list_button.collidepoint(self.logical_mouse_pos())
        button_color = GOLD if hover else (230, 226, 211)
        pygame.draw.rect(self.screen, button_color, self.player_list_button, border_radius=7)
        pygame.draw.rect(self.screen, (183, 180, 168), self.player_list_button, 2, border_radius=7)
        self.text("P / TAB　選手一覧・状態", 13, INK, self.player_list_button.center, bold=True, center=True)

    def draw_player_list(self) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((18, 22, 29, 205))
        self.screen.blit(shade, (0, 0))
        modal = pygame.Rect(58, 38, WIDTH - 116, HEIGHT - 76)
        pygame.draw.rect(self.screen, PAPER, modal, border_radius=12)
        pygame.draw.rect(self.screen, (202, 196, 179), modal, 3, border_radius=12)
        self.text("選手一覧・試合中パラメーター", 23, INK, (modal.left + 28, modal.top + 19), bold=True)
        subtitle = (
            "キ:キック　速:スピード　ス:スタミナ　技:テクニック　跳:ジャンプ　メ:メンタル　知:知性　守/攻:裏能力"
            if self.player_list_rank_mode else "試合を進行しながら現在値をリアルタイム表示中"
        )
        self.text(subtitle, 10 if self.player_list_rank_mode else 12, MUTED, (modal.left + 30, modal.top + 53))
        self.player_list_close_button = pygame.Rect(modal.right - 142, modal.top + 18, 112, 34)
        pygame.draw.rect(self.screen, (230, 226, 211), self.player_list_close_button, border_radius=7)
        pygame.draw.rect(self.screen, (183, 180, 168), self.player_list_close_button, 2, border_radius=7)
        self.text("P / TAB　閉じる", 12, INK, self.player_list_close_button.center, bold=True, center=True)
        self.player_list_rank_button = pygame.Rect(modal.right - 320, modal.top + 18, 166, 34)
        pygame.draw.rect(self.screen, GOLD if self.player_list_rank_mode else (230, 226, 211), self.player_list_rank_button, border_radius=7)
        pygame.draw.rect(self.screen, (183, 180, 168), self.player_list_rank_button, 2, border_radius=7)
        mode_label = "表示：能力ランク" if self.player_list_rank_mode else "表示：試合中状態"
        self.text(mode_label, 11, INK, self.player_list_rank_button.center, bold=True, center=True)

        column_gap = 28
        column_width = (modal.width - 56 - column_gap) // 2
        for team_index, team in enumerate(self.match.teams):
            column_x = modal.left + 28 + team_index * (column_width + column_gap)
            header_y = modal.top + 82
            pygame.draw.rect(self.screen, team.primary, (column_x, header_y, column_width, 34), border_radius=6)
            self.text(team.name.replace("_", " "), 15, CREAM, (column_x + 12, header_y + 7), bold=True)
            tactic_label = TACTICS.get(team.tactic, TACTICS["BALANCE"])["label"]
            self.text(
                f"{tactic_label}　交代{team.substitutions_used}/3",
                11, CREAM, (column_x + column_width - 12, header_y + 9), bold=True, right=True,
            )
            for index, player in enumerate(team.players):
                row_y = header_y + 42 + index * 45
                row = pygame.Rect(column_x, row_y, column_width, 39)
                row_color = (237, 233, 218) if index % 2 == 0 else (244, 240, 226)
                pygame.draw.rect(self.screen, row_color, row, border_radius=4)
                if self.match.ball.owner is player:
                    pygame.draw.circle(self.screen, GOLD, (row.left + 9, row.top + 11), 4)
                self.text(f"{player.number:>2}  {player.role}", 11, MUTED, (row.left + 17, row.top + 4), bold=True)
                if player.sent_off:
                    player_label = f"{player.name}　退場"
                elif player.yellow_cards:
                    player_label = f"{player.name}　黄{player.yellow_cards}"
                else:
                    player_label = player.name
                name_color = HOME_RED if player.sent_off else GOLD if player.yellow_cards else INK
                self.text(player_label, 13, name_color, (row.left + 82, row.top + 3), bold=True)
                self.text(player.player_type, 10, MUTED, (row.left + 250, row.top + 6))
                stamina_text = f"{player.stamina:.0f}/{player.stamina_max:.0f}  {player.stamina_ratio * 100:.0f}%"
                self.text(stamina_text, 11, INK, (row.right - 8, row.top + 4), bold=True, right=True)
                most_alert = max(player.alertness.items(), key=lambda item: item[1], default=(None, 0.0))
                alert_number = most_alert[0].number if most_alert[0] is not None else "-"
                if self.player_list_rank_mode:
                    dynamic_text = compact_entity_grade_text(player)
                    self.text(dynamic_text, 8, INK, (row.left + 17, row.top + 23), bold=True)
                else:
                    dynamic_text = (
                        f"忠{player.tactical_loyalty * 100:.0f}  自{player.confidence * 100:.0f}  "
                        f"Z{player.zone_awareness * 100:.0f}  P{player.position_awareness * 100:.0f}  "
                        f"積{player.aggressiveness * 100:.0f}  警#{alert_number}"
                    )
                    self.text(dynamic_text, 9, MUTED, (row.left + 17, row.top + 23))
                bar = pygame.Rect(row.right - 146, row.top + 26, 134, 7)
                pygame.draw.rect(self.screen, (191, 190, 180), bar, border_radius=3)
                ratio = player.stamina_ratio
                color = (73, 190, 103) if ratio > 0.5 else GOLD if ratio > 0.25 else HOME_RED
                fill = bar.copy()
                fill.width = round(bar.width * ratio)
                if fill.width > 0:
                    pygame.draw.rect(self.screen, color, fill, border_radius=3)

    def draw_other_matches(self) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((18, 22, 29, 205))
        self.screen.blit(shade, (0, 0))
        modal = pygame.Rect(32, 42, WIDTH - 64, HEIGHT - 84)
        pygame.draw.rect(self.screen, PAPER, modal, border_radius=14)
        pygame.draw.rect(self.screen, GOLD, modal, 3, border_radius=14)
        self.text("他の試合　リアルタイム速報", 23, INK, (modal.left + 28, modal.top + 22), bold=True)
        session = self.league_simulation_session
        worker_text = f" / 自動割当 {session.worker_count}コア" if session is not None else ""
        self.text("観戦試合と同じ試合時計で、別CPUコアのAI試合を進行中" + worker_text, 11, MUTED, (modal.left + 30, modal.top + 58))
        self.other_matches_close_button = pygame.Rect(modal.right - 142, modal.top + 20, 112, 34)
        pygame.draw.rect(self.screen, (230, 226, 211), self.other_matches_close_button, border_radius=7)
        pygame.draw.rect(self.screen, (183, 180, 168), self.other_matches_close_button, 2, border_radius=7)
        self.text("O / ESC 閉じる", 11, INK, self.other_matches_close_button.center, bold=True, center=True)

        statuses = [dict(item) for item in session.live_status.values()] if session is not None else list(self.league_live_last_status)
        result_by_id = {str(item.get("fixture_id")): item for item in self.league_manager.last_results}
        for status in statuses:
            result = result_by_id.get(str(status.get("fixture_id")))
            if result:
                status.update({"home_score": result.get("home_score", 0), "away_score": result.get("away_score", 0), "minute": 90, "state": "FULLTIME"})
        if not statuses:
            self.text("同時開催の他の試合はありません", 16, MUTED, modal.center, center=True)
            self.other_matches_scroll = 0
            self.other_matches_scroll_track = pygame.Rect(0, 0, 0, 0)
            self.other_matches_scroll_thumb = pygame.Rect(0, 0, 0, 0)
            return

        self.other_matches_scroll = clamp_other_match_scroll(self.other_matches_scroll, len(statuses))
        visible, first_index, last_index = visible_other_matches(statuses, self.other_matches_scroll)
        self.text(
            f"全{len(statuses)}試合　表示 {first_index + 1}～{last_index}",
            11, INK, (modal.right - 176, modal.top + 64), right=True, bold=True,
        )
        self.text(
            "マウスホイール / ↑↓ / PageUp・PageDown / Home・End",
            10, MUTED, (modal.left + 30, modal.top + 81),
        )

        grid = pygame.Rect(modal.left + 24, modal.top + 108, modal.width - 76, 480)
        column_gap = 8
        row_gap = 6
        row_height = 48
        column_width = (grid.width - column_gap * (OTHER_MATCH_COLUMNS - 1)) // OTHER_MATCH_COLUMNS
        for visible_index, status in enumerate(visible):
            column = visible_index % OTHER_MATCH_COLUMNS
            grid_row = visible_index // OTHER_MATCH_COLUMNS
            row = pygame.Rect(
                grid.left + column * (column_width + column_gap),
                grid.top + grid_row * (row_height + row_gap),
                column_width,
                row_height,
            )
            source_index = first_index + visible_index
            pygame.draw.rect(self.screen, (236, 233, 220) if source_index % 2 == 0 else (228, 226, 214), row, border_radius=6)
            pygame.draw.rect(self.screen, (205, 201, 188), row, 1, border_radius=6)
            game_time = float(status.get("game_time", float(status.get("minute", 0)) * 60.0))
            minute = "終了" if status.get("state") == "FULLTIME" else f"{int(game_time // 60):02d}:{int(game_time % 60):02d}"
            league_label = str(status.get("league", ""))
            self.text(league_label[:18], 9, MUTED, (row.left + 8, row.top + 5), bold=True)
            self.text(minute, 10, INK, (row.right - 8, row.top + 5), right=True, bold=True)
            home_name = str(status.get("home_name", ""))
            away_name = str(status.get("away_name", ""))
            if len(home_name) > 14:
                home_name = home_name[:13] + "…"
            if len(away_name) > 14:
                away_name = away_name[:13] + "…"
            self.text(home_name, 10, INK, (row.centerx - 34, row.top + 27), right=True, bold=True)
            self.text(f"{status.get('home_score', 0)}-{status.get('away_score', 0)}", 14, HOME_RED, (row.centerx, row.top + 27), center=True, bold=True)
            self.text(away_name, 10, INK, (row.centerx + 34, row.top + 27), bold=True)

        maximum = other_match_max_scroll(len(statuses))
        track = pygame.Rect(modal.right - 24, grid.top, 9, grid.height)
        self.other_matches_scroll_track = track
        pygame.draw.rect(self.screen, (211, 208, 196), track, border_radius=4)
        if maximum > 0:
            total_rows = maximum + OTHER_MATCH_VISIBLE_ROWS
            thumb_height = max(34, round(track.height * OTHER_MATCH_VISIBLE_ROWS / total_rows))
            thumb_y = track.top + round((track.height - thumb_height) * self.other_matches_scroll / maximum)
            thumb = pygame.Rect(track.left, thumb_y, track.width, thumb_height)
            pygame.draw.rect(self.screen, HOME_RED, thumb, border_radius=4)
        else:
            thumb = track.copy()
            pygame.draw.rect(self.screen, (166, 163, 153), thumb, border_radius=4)
        self.other_matches_scroll_thumb = thumb

    def draw_overlay(self) -> None:
        match = self.match
        if match.banner_timer > 0:
            banner = pygame.Rect(FIELD.left + 200, FIELD.centery - 45, FIELD.width - 400, 90)
            shade = pygame.Surface(banner.size, pygame.SRCALPHA)
            shade.fill((28, 33, 43, 225))
            self.screen.blit(shade, banner)
            self.text(match.banner, 34, GOLD, banner.center, bold=True, center=True)

        kickoff_prediction = (
            match.state == "PLAYING"
            and match.banner == "KICK OFF"
            and match.banner_timer > 0.0
            and match.game_time <= 0.0001
        )
        if kickoff_prediction:
            prediction_box = pygame.Rect(64, 78, PANEL.left - 128, 42)
            pygame.draw.rect(self.screen, (28, 33, 43), prediction_box, border_radius=8)
            pygame.draw.rect(self.screen, GOLD, prediction_box, 2, border_radius=8)
            self.text(match.predicted_result_text(), 16, GOLD, prediction_box.center, bold=True, center=True)

        if self.skip_match_in_progress:
            match_view = pygame.Rect(0, 0, PANEL.left, HEIGHT)
            shade = pygame.Surface(match_view.size, pygame.SRCALPHA)
            shade.fill((20, 24, 32, 218))
            self.screen.blit(shade, match_view.topleft)
            center_x = match_view.centerx
            self.text("試合を高速処理中", 34, GOLD, (center_x, 250), bold=True, center=True)
            self.text(
                f"{int(match.game_time // 60):02d}:{int(match.game_time % 60):02d} / 90:00",
                22, CREAM, (center_x, 305), bold=True, center=True,
            )
            if self.active_league_fixture_id:
                self.text("観戦試合の後、同日開催の全試合も完了させます", 15, CREAM, (center_x, 350), center=True)
            else:
                self.text("通常試合と同じAI・物理演算で残り時間を進めています", 15, CREAM, (center_x, 350), center=True)
            self.pause_menu_buttons.clear()
        elif match.state == "PAUSED":
            match_view = pygame.Rect(0, 0, PANEL.left, HEIGHT)
            shade = pygame.Surface(match_view.size, pygame.SRCALPHA)
            shade.fill((20, 24, 32, 205))
            self.screen.blit(shade, match_view.topleft)
            center_x = match_view.centerx
            self.text("ポーズ", 38, GOLD, (center_x, 168), bold=True, center=True)
            self.pause_menu_buttons.clear()
            button_specs = (
                ("試合に戻る", "resume"),
                ("試合を中断", "abort"),
                ("残りをスキップ", "skip"),
            )
            for index, (label, action) in enumerate(button_specs):
                rect = pygame.Rect(center_x - 145, 235 + index * 72, 290, 52)
                hover = rect.collidepoint(self.logical_mouse_pos())
                pygame.draw.rect(self.screen, GOLD if hover else (242, 184, 72), rect, border_radius=8)
                pygame.draw.rect(self.screen, CREAM, rect, 2, border_radius=8)
                self.text(label, 17, INK, rect.center, bold=True, center=True)
                self.pause_menu_buttons.append((rect, action))
            league_note = "中断すると未確定のままリーグ画面へ戻ります" if self.active_league_fixture_id else "中断するとチーム選択へ戻ります"
            self.text(league_note, 14, CREAM, (center_x, 478), center=True)
            self.text("Esc / Space：試合に戻る", 14, GOLD, (center_x, 514), center=True)
        elif match.state == "FULLTIME":
            # FIELD is expressed in world coordinates and is much larger than the
            # logical screen.  Full-time controls must use screen coordinates so
            # they remain visible and clickable at every camera zoom.
            match_view = pygame.Rect(0, 0, PANEL.left, HEIGHT)
            shade = pygame.Surface(match_view.size, pygame.SRCALPHA)
            shade.fill((20, 24, 32, 205))
            self.screen.blit(shade, match_view.topleft)
            center_x = match_view.centerx
            self.text("FULL TIME", 25, GOLD, (center_x, 82), bold=True, center=True)
            result = f"{match.home.short_name}  {match.home.score}  -  {match.away.score}  {match.away.short_name}"
            self.text(result, 42, CREAM, (center_x, 137), bold=True, center=True)
            league_match = bool(self.active_league_fixture_id)
            if match.home.score > match.away.score:
                message = "ホームチーム勝利"
            elif match.home.score < match.away.score:
                message = "アウェーチーム勝利" if league_match else "惜しくも敗戦"
            else:
                message = "DRAW"
            self.text(message, 21, CREAM, (center_x, 188), bold=True, center=True)
            scorer_box = pygame.Rect(center_x - 280, 226, 560, 190)
            scorer_title = "得点者一覧" if match.goal_scorers else "得点者一覧（まだなし）"
            pygame.draw.rect(self.screen, (30, 35, 44), scorer_box, border_radius=10)
            pygame.draw.rect(self.screen, GOLD, scorer_box, 2, border_radius=10)
            self.text(scorer_title, 15, GOLD, (scorer_box.centerx, scorer_box.top + 12), bold=True, center=True)
            if match.goal_scorers:
                visible_scorers = match.goal_scorers[:7]
                for index, (minute, scorer_name) in enumerate(visible_scorers):
                    y = scorer_box.top + 40 + index * 18
                    self.text(f"{minute}'  {scorer_name}", 14, CREAM, (scorer_box.left + 24, y))
                if len(match.goal_scorers) > len(visible_scorers):
                    self.text(
                        f"ほか {len(match.goal_scorers) - len(visible_scorers)}得点",
                        12, MUTED, (scorer_box.right - 24, scorer_box.bottom - 24), right=True,
                    )
            self.fulltime_buttons.clear()
            if league_match:
                if self.league_simulation_session is not None:
                    session = self.league_simulation_session
                    heading = f"同日試合の残りを高速完走中　{session.completed}/{session.total}"
                else:
                    heading = "同日開催の試合結果"
                self.text(heading, 15, GOLD, (center_x, 438), bold=True, center=True)
                for index, other_result in enumerate(self.league_manager.last_results[:5]):
                    y = 465 + index * 24
                    result_text = (
                        f"{other_result['league']}　{other_result['home_name']}  "
                        f"{other_result['home_score']}-{other_result['away_score']}  {other_result['away_name']}"
                    )
                    if other_result.get("home_penalties") is not None:
                        result_text += f"　PK {other_result['home_penalties']}-{other_result['away_penalties']}"
                    self.text(result_text, 11, CREAM, (center_x, y), bold=bool(other_result.get("watched")), center=True)
                league_rect = pygame.Rect(center_x - 145, 600, 290, 48)
                hover = league_rect.collidepoint(self.logical_mouse_pos())
                results_ready = self.league_simulation_session is None
                button_color = GOLD if results_ready and hover else (242, 184, 72) if results_ready else (115, 112, 104)
                pygame.draw.rect(self.screen, button_color, league_rect, border_radius=8)
                pygame.draw.rect(self.screen, CREAM, league_rect, 2, border_radius=8)
                button_label = "リーグ結果・成績へ" if results_ready else "他会場の試合を計算中"
                self.text(button_label, 16, INK, league_rect.center, bold=True, center=True)
                if results_ready:
                    self.fulltime_buttons.append((league_rect, "league_results"))
                    self.text("T / Enter / Space：リーグ画面へ", 14, GOLD, (center_x, 670), center=True)
                else:
                    self.text("全試合の完了後に移動できます", 14, GOLD, (center_x, 670), center=True)
            else:
                rematch_rect = pygame.Rect(center_x - 206, 455, 176, 50)
                select_rect = pygame.Rect(center_x + 30, 455, 236, 50)
                for rect, label, action in ((rematch_rect, "再戦", "rematch"), (select_rect, "チーム選択へ戻る", "team_select")):
                    hover = rect.collidepoint(self.logical_mouse_pos())
                    pygame.draw.rect(self.screen, GOLD if hover else (242, 184, 72), rect, border_radius=8)
                    pygame.draw.rect(self.screen, CREAM, rect, 2, border_radius=8)
                    self.text(label, 16, INK, rect.center, bold=True, center=True)
                    self.fulltime_buttons.append((rect, action))
                self.text("R：再戦　　T / Enter / Space：チーム選択へ戻る", 16, GOLD, (center_x, 535), center=True)

    def draw_choice_formation(self, choice: dict, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, (54, 124, 73), rect, border_radius=8)
        pygame.draw.rect(self.screen, LINE, rect, 2, border_radius=8)
        pygame.draw.line(self.screen, LINE, (rect.left, rect.centery), (rect.right, rect.centery), 1)
        pygame.draw.circle(self.screen, LINE, rect.center, 25, 1)
        primary = choice["primary"]
        secondary = choice.get("secondary", darken_color(primary))
        records = choice["starters"]
        points = []
        for record in records:
            if record["position_y"] == 11:
                normalized_x = 0.5
                normalized_y = 0.94
            else:
                normalized_x = (record["position_x"] - 0.5) / 15.0
                normalized_y = 0.08 + (record["position_y"] - 1) / 9.0 * 0.75
            points.append((record["number"], normalized_x, normalized_y))
        for number, normalized_x, normalized_y in points:
            px = round(rect.left + normalized_x * rect.width)
            py = round(rect.top + normalized_y * rect.height)
            pygame.draw.circle(self.screen, secondary, (px + 1, py + 2), 8)
            pygame.draw.circle(self.screen, primary, (px, py), 8)
            jersey = self.font(9, True).render(str(number), True, CREAM)
            self.screen.blit(jersey, jersey.get_rect(center=(px, py)))

    def draw_team_card(self, rect: pygame.Rect, choice: dict, side: str) -> None:
        pygame.draw.rect(self.screen, PAPER, rect, border_radius=14)
        pygame.draw.rect(self.screen, choice["primary"], rect, 4, border_radius=14)
        side_label = "HOME / 操作チーム" if side == "home" else "AWAY / 相手チーム"
        self.text(side_label, 14, MUTED, (rect.centerx, rect.top + 24), bold=True, center=True)
        self.text(choice["name"].replace("_", " "), 25, INK, (rect.centerx, rect.top + 68), bold=True, center=True)
        badge = pygame.Rect(rect.right - 92, rect.top + 18, 72, 24)
        pygame.draw.rect(self.screen, GOLD, badge, border_radius=5)
        self.text(choice["kind"], 10, INK, badge.center, bold=True, center=True)

        manager = choice.get("manager") or "—"
        manager_intelligence = round(denormalize_player_stat(choice.get("manager_intelligence", 0.542)))
        tactic_aggression = round(denormalize_player_stat(choice.get("manager_tactic_aggression", 0.375)))
        substitution_aggression = round(denormalize_player_stat(choice.get("manager_substitution_aggression", 0.375)))
        manager_detail = (
            f"監督 {manager}　知{manager_intelligence} 戦{tactic_aggression} 交{substitution_aggression}"
            if choice.get("manager")
            else "監督 —"
        )
        self.text(
            f"{manager_detail}　略称 {choice['short']}",
            10, MUTED, (rect.centerx, rect.top + 101), center=True,
        )
        formation_rect = pygame.Rect(rect.left + 65, rect.top + 125, rect.width - 130, 185)
        self.draw_choice_formation(choice, formation_rect)
        player_count = len(choice["starters"])
        bench_count = len(choice.get("bench", []))
        formation_label = "15×10 JSON配置"
        self.text(formation_label, 13, INK, (rect.left + 30, rect.top + 330), bold=True)
        self.text(f"先発 {player_count}人　控え {bench_count}人", 12, MUTED, (rect.right - 30, rect.top + 332), right=True)
        tactic_label = choice.get("tactic_label", "バランス")
        zone_label = f"ゾーン {choice.get('zone_near', 3)}–{choice.get('zone_far', 7)}"
        discipline = round(choice.get("tactical_discipline", 0.5) * 100)
        self.text(
            f"戦術 {tactic_label}　/　{zone_label}　/　チーム忠実さ {discipline}",
            12, INK, (rect.centerx, rect.top + 360), bold=True, center=True,
        )
        self.text(
            f"所属：{choice.get('league') or '未所属'}　/　ホームコート：{choice.get('home_court', '—')}",
            10, MUTED, (rect.centerx, rect.top + 384), center=True,
        )

        prev_rect = pygame.Rect(rect.left + 18, rect.top + 184, 38, 58)
        next_rect = pygame.Rect(rect.right - 56, rect.top + 184, 38, 58)
        for button, label in ((prev_rect, "‹"), (next_rect, "›")):
            hover = button.collidepoint(self.logical_mouse_pos())
            pygame.draw.rect(self.screen, GOLD if hover else (224, 220, 205), button, border_radius=7)
            pygame.draw.rect(self.screen, INK, button, 2, border_radius=7)
            self.text(label, 30, INK, button.center, bold=True, center=True)
        self.team_select_buttons.append((prev_rect, f"{side}_prev"))
        self.team_select_buttons.append((next_rect, f"{side}_next"))

    def draw_team_select(self) -> None:
        self.screen.fill(INK)
        for index in range(12):
            color = (35, 82, 55) if index % 2 == 0 else (40, 91, 61)
            pygame.draw.polygon(
                self.screen,
                color,
                [(0, index * 72), (WIDTH, index * 72 - 180), (WIDTH, index * 72 - 105), (0, index * 72 + 75)],
            )
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((19, 25, 32, 145))
        self.screen.blit(shade, (0, 0))
        self.text("DEBUG TEAM SELECT", 16, GOLD, (WIDTH // 2, 27), bold=True, center=True)
        self.text("対戦チームを選択", 34, CREAM, (WIDTH // 2, 67), bold=True, center=True)

        self.team_select_buttons.clear()
        home_rect = pygame.Rect(72, 108, 520, 410)
        away_rect = pygame.Rect(688, 108, 520, 410)
        home_choice = self.team_choices[self.home_choice_index]
        away_choice = self.team_choices[self.away_choice_index]
        self.draw_team_card(home_rect, home_choice, "home")
        self.draw_team_card(away_rect, away_choice, "away")
        self.text("VS", 31, GOLD, (WIDTH // 2, 302), bold=True, center=True)

        if home_choice["id"] == away_choice["id"]:
            self.text("同チーム対戦：AWAY側は青ユニフォームになります", 11, CREAM, (WIDTH // 2, 520), center=True)
        venue_labels = (("HOME", "HOMEのホーム"), ("NEUTRAL", "中立地"), ("AWAY", "AWAYのホーム"))
        for index, (mode, label) in enumerate(venue_labels):
            rect = pygame.Rect(WIDTH // 2 - 261 + index * 174, 531, 166, 34)
            active = self.venue_modes[self.venue_mode_index] == mode
            hover = rect.collidepoint(self.logical_mouse_pos())
            color = GOLD if active else (238, 233, 216) if hover else (211, 210, 199)
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            pygame.draw.rect(self.screen, INK, rect, 2, border_radius=6)
            self.text(label, 12, INK, rect.center, bold=True, center=True)
            self.team_select_buttons.append((rect, f"venue_{mode.lower()}"))
        start_rect = pygame.Rect(WIDTH // 2 - 175, 578, 350, 58)
        hover = start_rect.collidepoint(self.logical_mouse_pos())
        pygame.draw.rect(self.screen, (239, 89, 76) if hover else HOME_RED, start_rect, border_radius=10)
        pygame.draw.rect(self.screen, GOLD, start_rect, 3, border_radius=10)
        self.text("この対戦で試合開始", 20, CREAM, start_rect.center, bold=True, center=True)
        self.team_select_buttons.append((start_rect, "start"))

        self.text("HOME: Q / E　AWAY: A / D　会場: V　Enter / Space: 開始", 13, CREAM, (WIDTH // 2, 648), center=True)
        editor_rect = pygame.Rect(20, 674, 218, 30)
        editor_hover = editor_rect.collidepoint(self.logical_mouse_pos())
        pygame.draw.rect(self.screen, GOLD if editor_hover else (230, 226, 211), editor_rect, border_radius=7)
        pygame.draw.rect(self.screen, (183, 180, 168), editor_rect, 2, border_radius=7)
        self.text("チームエディタ", 11, INK, editor_rect.center, bold=True, center=True)
        self.team_select_buttons.append((editor_rect, "editor"))
        league_rect = pygame.Rect(250, 674, 218, 30)
        league_hover = league_rect.collidepoint(self.logical_mouse_pos())
        pygame.draw.rect(self.screen, GOLD if league_hover else (230, 226, 211), league_rect, border_radius=7)
        pygame.draw.rect(self.screen, (183, 180, 168), league_rect, 2, border_radius=7)
        self.text("リーグ戦", 11, INK, league_rect.center, bold=True, center=True)
        self.team_select_buttons.append((league_rect, "league"))
        menu_rect = pygame.Rect(480, 674, 218, 30)
        menu_hover = menu_rect.collidepoint(self.logical_mouse_pos())
        pygame.draw.rect(self.screen, GOLD if menu_hover else (230, 226, 211), menu_rect, border_radius=7)
        pygame.draw.rect(self.screen, (183, 180, 168), menu_rect, 2, border_radius=7)
        self.text("メインメニューへ", 11, INK, menu_rect.center, bold=True, center=True)
        self.team_select_buttons.append((menu_rect, "main_menu"))
        self.draw_settings_button(pygame.Rect(WIDTH - 238, 674, 218, 30))
        empty_count = sum(1 for path in TEAMS_DIR.glob("*.json") if path.stat().st_size == 0) if TEAMS_DIR.exists() else 0
        info = f"選択可能 {len(self.team_choices)}チーム"
        if empty_count:
            info += f"　空のJSON {empty_count}件は除外"
        self.text(info, 11, (192, 200, 199), (WIDTH // 2, 664), center=True)

    def draw_title(self) -> None:
        self.screen.fill((10, 17, 25))
        # A restrained stadium/pitch motif gives the hub depth without making
        # the navigation cards compete with an animated match.
        for y in range(0, HEIGHT, 48):
            tone = 23 + min(18, y // 48)
            pygame.draw.rect(self.screen, (tone, tone + 9, tone + 15), (0, y, WIDTH, 48))
        pygame.draw.polygon(self.screen, (24, 83, 57), [(0, 305), (WIDTH, 236), (WIDTH, HEIGHT), (0, HEIGHT)])
        for index in range(9):
            x = index * 190 - 120
            pygame.draw.polygon(self.screen, (29, 101, 67) if index % 2 else (27, 94, 63), [(x, 274), (x + 150, 266), (x + 360, HEIGHT), (x + 145, HEIGHT)])
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((7, 12, 18, 118))
        self.screen.blit(veil, (0, 0))

        self.main_menu_buttons.clear()
        self.text("KADOCALCIO", 13, (77, 198, 178), (64, 38), bold=True)
        self.text("カドカルチョ", 44, CREAM, (64, 58), bold=True)
        self.text("FOOTBALL CLUB SIMULATOR", 12, (154, 171, 181), (67, 112), bold=True)
        self.text("クラブ作成、リーグ構築、シーズン進行、単体試合テストをここから開始します。", 14, (204, 214, 218), (66, 150))

        cards = (
            ("TEAM", "チームエディタ", "選手・能力・色・フォーメーションを編集", "team_editor", (77, 198, 178)),
            ("LEAGUE", "リーグ戦エディタ", "リーグ・大会・参加チーム・日程を編集", "league_editor", (100, 151, 235)),
            ("SEASON", "リーグ戦を開始", "新規セーブを作成、または途中データを再開", "league_start", (232, 174, 72)),
            ("MATCH", "試合テスト", "任意の2チームと会場で単体試合を実行", "match_test", (224, 94, 88)),
        )
        mouse = self.logical_mouse_pos()
        for index, (eyebrow, title, detail, action, accent) in enumerate(cards):
            column, row = index % 2, index // 2
            rect = pygame.Rect(64 + column * 588, 205 + row * 190, 552, 158)
            hover = rect.collidepoint(mouse)
            shadow = pygame.Surface((rect.width + 14, rect.height + 14), pygame.SRCALPHA)
            pygame.draw.rect(shadow, (0, 0, 0, 90), shadow.get_rect(), border_radius=17)
            self.screen.blit(shadow, (rect.left - 3, rect.top + 6))
            pygame.draw.rect(self.screen, (29, 40, 52) if not hover else (38, 52, 66), rect, border_radius=14)
            pygame.draw.rect(self.screen, accent, (rect.left, rect.top, 5, rect.height), border_radius=3)
            pygame.draw.rect(self.screen, (66, 82, 96) if not hover else accent, rect, 1, border_radius=14)
            icon = pygame.Rect(rect.left + 24, rect.top + 28, 74, 74)
            pygame.draw.rect(self.screen, (*accent, 255), icon, border_radius=13)
            self.text(str(index + 1), 30, (12, 23, 31), icon.center, bold=True, center=True)
            self.text(eyebrow, 9, accent, (rect.left + 122, rect.top + 25), bold=True)
            self.text(title, 22, (245, 248, 249), (rect.left + 122, rect.top + 45), bold=True)
            self.text(detail, 11, (157, 173, 183), (rect.left + 122, rect.top + 82))
            self.text("開く  ›", 11, accent, (rect.right - 24, rect.bottom - 28), right=True, bold=True)
            self.main_menu_buttons.append((rect, action))
        self.text("1–4 キーでも選択できます", 11, (142, 158, 168), (64, HEIGHT - 31))
        self.draw_settings_button(pygame.Rect(WIDTH - 238, HEIGHT - 46, 218, 30))

    def draw(self) -> None:
        if self.league_screen_open:
            self.draw_league_screen()
            if getattr(self, "settings_open", False):
                self.draw_settings_modal()
            self.present()
            return
        if self.match.state == "MAIN_MENU":
            self.draw_title()
            if getattr(self, "settings_open", False):
                self.draw_settings_modal()
            self.present()
            return
        if self.match.state == "TEAM_SELECT":
            self.draw_team_select()
            if getattr(self, "settings_open", False):
                self.draw_settings_modal()
            self.present()
            return
        if self.match.state == "TITLE":
            self.draw_title()
            if getattr(self, "settings_open", False):
                self.draw_settings_modal()
            self.present()
            return
        self.screen.fill((228, 222, 204))
        self.draw_pitch()
        renderables: list[tuple[float, str, object]] = [
            (player.pos.y, "player", player)
            for team in self.match.teams
            for player in team.players
            if not player.sent_off
        ]
        renderables.append((self.match.referee_pos.y, "referee", None))
        renderables.append((self.match.ball.pos.y, "ball", self.match.ball))
        for _, kind, item in sorted(renderables, key=lambda entry: entry[0]):
            if kind == "player":
                self.draw_player(item)
            elif kind == "referee":
                self.draw_referee()
            else:
                self.draw_ball()
        self.draw_scoreboard()
        self.draw_panel()
        self.draw_overlay()
        if self.player_list_open:
            self.draw_player_list()
        if self.other_matches_open:
            self.draw_other_matches()
        if getattr(self, "settings_open", False):
            self.draw_settings_modal()
        self.present()
