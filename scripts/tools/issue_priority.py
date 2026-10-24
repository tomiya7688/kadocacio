"""Resolve one Issue's P0..P4 rank without selecting work or mutating GitHub."""

from __future__ import annotations

import re


PRIORITY_ORDER = ("P0", "P1", "P2", "P3", "P4")
DEFAULT_PRIORITY = "P2"


def issue_priority(issue: dict) -> int:
    labels = {str(label.get("name", "")).strip().upper() for label in issue.get("labels", [])}
    # Labels override old titles. Multiple labels resolve to the most urgent.
    for rank, priority in enumerate(PRIORITY_ORDER):
        if priority in labels:
            return rank
    searchable = str(issue.get("title", "")).upper()
    for rank, priority in enumerate(PRIORITY_ORDER):
        if re.search(rf"(?:^|[^A-Z0-9]){priority}(?:[^A-Z0-9]|$)", searchable):
            return rank
    return PRIORITY_ORDER.index(DEFAULT_PRIORITY)
