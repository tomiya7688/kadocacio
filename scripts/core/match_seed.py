"""Stable seed rules shared by watched and headless league fixtures."""

from __future__ import annotations

import hashlib


def league_fixture_seed(fixture_id: object, home_name: object, away_name: object) -> int:
    """Preserve the existing league seed formula across execution paths."""
    seed_text = f"{fixture_id}:{home_name}:{away_name}"
    return int.from_bytes(hashlib.sha256(seed_text.encode("utf-8")).digest()[:8], "big")
