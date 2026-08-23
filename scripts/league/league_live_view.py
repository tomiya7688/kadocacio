from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar


OTHER_MATCH_COLUMNS = 3
OTHER_MATCH_VISIBLE_ROWS = 9

_Status = TypeVar("_Status")


def other_match_max_scroll(
    status_count: int,
    *,
    columns: int = OTHER_MATCH_COLUMNS,
    visible_rows: int = OTHER_MATCH_VISIBLE_ROWS,
) -> int:
    """Return the maximum row offset for the live-match grid."""
    count = max(0, int(status_count))
    column_count = max(1, int(columns))
    row_count = (count + column_count - 1) // column_count
    return max(0, row_count - max(1, int(visible_rows)))


def clamp_other_match_scroll(scroll_row: int, status_count: int) -> int:
    return max(0, min(int(scroll_row), other_match_max_scroll(status_count)))


def visible_other_matches(
    statuses: Sequence[_Status],
    scroll_row: int,
) -> tuple[list[_Status], int, int]:
    """Return the visible grid items and their zero-based source bounds."""
    scroll = clamp_other_match_scroll(scroll_row, len(statuses))
    start = scroll * OTHER_MATCH_COLUMNS
    capacity = OTHER_MATCH_COLUMNS * OTHER_MATCH_VISIBLE_ROWS
    end = min(len(statuses), start + capacity)
    return list(statuses[start:end]), start, end
