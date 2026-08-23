"""Geometry boundary between the portable match core and the Pygame frontend.

The simulation imports ``Vec2``/``Rect`` from this module instead of importing
Pygame directly.  A future GDScript port therefore has one explicit geometry
adapter to replace, while rendering and window management remain in the Pygame
frontend.
"""

from __future__ import annotations

from pygame import Rect, Vector2


Vec2 = Vector2


__all__ = ("Rect", "Vec2")
