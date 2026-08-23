from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar


SCHEDULE_COLUMNS = 2
SCHEDULE_VISIBLE_ROWS = 8

_Fixture = TypeVar("_Fixture")


def schedule_max_scroll(fixture_count: int) -> int:
    count = max(0, int(fixture_count))
    total_rows = (count + SCHEDULE_COLUMNS - 1) // SCHEDULE_COLUMNS
    return max(0, total_rows - SCHEDULE_VISIBLE_ROWS)


def clamp_schedule_scroll(scroll_row: int, fixture_count: int) -> int:
    return max(0, min(int(scroll_row), schedule_max_scroll(fixture_count)))


def visible_schedule_fixtures(
    fixtures: Sequence[_Fixture],
    scroll_row: int,
) -> tuple[list[_Fixture], int, int]:
    scroll = clamp_schedule_scroll(scroll_row, len(fixtures))
    start = scroll * SCHEDULE_COLUMNS
    capacity = SCHEDULE_COLUMNS * SCHEDULE_VISIBLE_ROWS
    end = min(len(fixtures), start + capacity)
    return list(fixtures[start:end]), start, end
