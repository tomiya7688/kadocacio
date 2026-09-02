"""Projected pixel-pattern drawing for block-built player uniforms."""

from __future__ import annotations

import pygame


Color = tuple[int, int, int]
Grid = tuple[tuple[Color, ...], ...]


def _solid_color(grid: Grid) -> Color | None:
    if not grid or not grid[0]:
        return None
    first = grid[0][0]
    return first if all(color == first for row in grid for color in row) else None


def _mix(left: pygame.Vector2, right: pygame.Vector2, ratio: float) -> pygame.Vector2:
    return left + (right - left) * ratio


def draw_uniform_polygon(
    surface: pygame.Surface,
    points: list[pygame.Vector2],
    grid: Grid,
    outline: Color,
) -> None:
    if len(points) != 4 or not grid or not grid[0]:
        return
    solid = _solid_color(grid)
    if solid is not None:
        pygame.draw.polygon(surface, solid, points)
        pygame.draw.lines(surface, outline, True, points, 1)
        return
    bottom_left, bottom_right, top_right, top_left = (pygame.Vector2(point) for point in points)
    height, width = len(grid), len(grid[0])
    for y, row in enumerate(grid):
        top_ratio, bottom_ratio = y / height, (y + 1) / height
        row_top_left = _mix(top_left, bottom_left, top_ratio)
        row_top_right = _mix(top_right, bottom_right, top_ratio)
        row_bottom_left = _mix(top_left, bottom_left, bottom_ratio)
        row_bottom_right = _mix(top_right, bottom_right, bottom_ratio)
        for x, color in enumerate(row):
            left_ratio, right_ratio = x / width, (x + 1) / width
            cell = [
                _mix(row_top_left, row_top_right, left_ratio),
                _mix(row_top_left, row_top_right, right_ratio),
                _mix(row_bottom_left, row_bottom_right, right_ratio),
                _mix(row_bottom_left, row_bottom_right, left_ratio),
            ]
            pygame.draw.polygon(surface, color, cell)
    pygame.draw.lines(surface, outline, True, points, 1)


def draw_uniform_limb(
    surface: pygame.Surface,
    start: pygame.Vector2,
    end: pygame.Vector2,
    width: int,
    grid: Grid,
    outline: Color,
) -> None:
    start = pygame.Vector2(start)
    end = pygame.Vector2(end)
    delta = end - start
    if delta.length_squared() < 0.01:
        color = _solid_color(grid) or (grid[0][0] if grid and grid[0] else outline)
        rect = pygame.Rect(0, 0, width, width)
        rect.center = start
        pygame.draw.rect(surface, color, rect)
        pygame.draw.rect(surface, outline, rect, 1)
        return
    normal = pygame.Vector2(-delta.y, delta.x).normalize() * width * 0.5
    points = [end + normal, end - normal, start - normal, start + normal]
    draw_uniform_polygon(surface, points, grid, outline)


__all__ = ("draw_uniform_limb", "draw_uniform_polygon")
