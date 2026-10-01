"""Shared presentation tokens and bounded text for entry screens."""
from __future__ import annotations

import pygame

BACKGROUND = (12, 22, 29)
SURFACE = (23, 38, 47)
TEXT = (238, 244, 240)
MUTED = (169, 188, 190)
ACCENT = (126, 229, 187)
BORDER = (56, 78, 85)


def fit_label(font: pygame.font.Font, value: str, width: int) -> str:
    """Fit a single-line label without shrinking it below readable sizes."""
    value = " ".join(str(value).split())
    if font.size(value)[0] <= width:
        return value
    suffix = "…"
    if font.size(suffix)[0] > width:
        return ""
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if font.size(value[:middle] + suffix)[0] <= width:
            low = middle
        else:
            high = middle - 1
    return value[:low] + suffix
