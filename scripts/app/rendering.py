from __future__ import annotations

import math

import pygame

from scripts.app.ui_theme import SURFACE, TEXT, ACCENT, BORDER
from scripts.app.uniform_rendering import draw_uniform_limb, draw_uniform_polygon

from scripts.match.player import Player
from scripts.league.league_rendering import LeagueRendererMixin
from scripts.match.match_engine import Match
from scripts.match.player_commands import PlayerCommand
from scripts.core.settings import (
    AWAY_BLUE, CENTER_CIRCLE_RADIUS, CREAM, FIELD, GOAL_AREA_DEPTH, GOAL_AREA_WIDTH,
    GOAL_DEPTH, GOAL_HALF_HEIGHT, GOAL_HEIGHT, GOLD, HEIGHT, HOME_DARK, HOME_RED, INK,
    LINE, MUTED, PANEL, PAPER, PENALTY_AREA_DEPTH, PENALTY_AREA_WIDTH,
    PENALTY_SPOT_DISTANCE, PITCH_1, PITCH_2, PLAYER_VISUAL_SCALE,
    WIDTH, clamp,
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
        color = SURFACE if not hover else (29, 49, 57)
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT if hover else BORDER, rect, 1, border_radius=8)
        self.text("ESC　設定", 14, TEXT, rect.center, bold=True, center=True)

    def draw_settings_modal(self) -> None:
        self.settings_view.draw(self)

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
        pattern: tuple | None = None,
    ) -> None:
        """Draw a square-ended limb so players read as block figures."""
        if pattern:
            draw_uniform_limb(self.screen, start, end, width, pattern, INK)
            return
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
        draw_uniform_polygon(self.screen, torso, player.team.uniform["胸"], CREAM)

        kick_lift = math.sin(player.kick_motion_progress * math.pi) * 12 if player.kick_motion_progress > 0 else 0
        foot_left_world = foot_center + side * 7
        foot_right_world = foot_center - side * 7
        if player.kick_motion_progress > 0:
            foot_right_world += direction * (player.kick_motion_progress * 17)
        foot_left, _ = self.project_player_point(player, *foot_left_world, body_z + 1)
        foot_right, _ = self.project_player_point(player, *foot_right_world, body_z + 1 + kick_lift)
        self.draw_block_limb(
            hip_left, foot_left, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)),
            player.team.secondary, player.team.uniform["左脚"],
        )
        self.draw_block_limb(
            hip_right, foot_right, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)),
            player.team.secondary, player.team.uniform["右脚"],
        )

        arm_left_world = shoulder_center + side * 19 + direction * (5 if diving_pose else 0)
        arm_right_world = shoulder_center - side * 19 + direction * (5 if diving_pose else 0)
        arm_left, _ = self.project_player_point(player, *arm_left_world, body_z + 5)
        arm_right, _ = self.project_player_point(player, *arm_right_world, body_z + 5)
        self.draw_block_limb(
            shoulder_left, arm_left, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)),
            player.team.primary, player.team.uniform["左腕"],
        )
        self.draw_block_limb(
            shoulder_right, arm_right, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)),
            player.team.primary, player.team.uniform["右腕"],
        )

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
        self.draw_block_limb(
            left_hip, left_foot, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)),
            player.team.secondary, player.team.uniform["左脚"],
        )
        self.draw_block_limb(
            right_hip, right_foot, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)),
            player.team.secondary, player.team.uniform["右脚"],
        )

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
        draw_uniform_polygon(self.screen, torso, player.team.uniform["胸"], INK)
        arm_swing = forward * (-stride * 0.7)
        arm_left_world = body_center - side * 17 + arm_swing
        arm_right_world = body_center + side * 17 - arm_swing
        arm_left, _ = self.project_player_point(player, *arm_left_world, base_z + 23)
        arm_right, _ = self.project_player_point(player, *arm_right_world, base_z + 23)
        shoulder_left, _ = self.project_player_point(player, *upper_left, base_z + 32)
        shoulder_right, _ = self.project_player_point(player, *upper_right, base_z + 32)
        self.draw_block_limb(
            shoulder_left, arm_left, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)),
            player.team.primary, player.team.uniform["左腕"],
        )
        self.draw_block_limb(
            shoulder_right, arm_right, max(1, round(5 * scale * PLAYER_VISUAL_SCALE)),
            player.team.primary, player.team.uniform["右腕"],
        )

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
        self.match_hud_view.draw_scoreboard(self)

    def draw_panel(self) -> None:
        self.match_hud_view.draw_panel(self)

    def draw_player_list(self) -> None:
        self.player_status_view.draw(self)

    def draw_other_matches(self) -> None:
        self.other_matches_view.draw(self)

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
            self.match_hud_view.draw_prediction(self)

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
            self.fulltime_view.draw(self)

    def draw_choice_formation(self, choice: dict, rect: pygame.Rect) -> None:
        self.team_select_view.draw_formation(self, choice, rect)

    def draw_team_card(self, rect: pygame.Rect, choice: dict, side: str) -> None:
        index = self.home_choice_index if side == "home" else self.away_choice_index
        self.team_select_view.draw_card(self, rect, choice, side, index)

    def draw_team_select(self) -> None:
        self.team_select_view.draw(self)

    def draw_title(self) -> None:
        self.main_menu_view.draw(self)

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
        if self.match.state == "FULLTIME":
            self.fulltime_view.draw(self)
            if self.player_list_open:
                self.draw_player_list()
            if self.other_matches_open:
                self.draw_other_matches()
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
