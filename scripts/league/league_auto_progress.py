from __future__ import annotations

from dataclasses import dataclass
from random import Random

from scripts.core.settings import SPEED_OPTIONS


WATCH_RANDOM = "RANDOM"
WATCH_NONE = "NONE"
WATCH_FOCUS = "FOCUS"
WATCH_MODES = (WATCH_RANDOM, WATCH_NONE, WATCH_FOCUS)
WATCH_MODE_LABELS = {
    WATCH_RANDOM: "ランダム観戦",
    WATCH_NONE: "観戦なし",
    WATCH_FOCUS: "指定チームだけ",
}


@dataclass
class LeagueAutoProgressConfig:
    """Ephemeral debug settings; intentionally not part of league save data."""

    watch_mode: str = WATCH_RANDOM
    speed_multiplier: int = 1
    focus_team_id: str = ""

    def normalize(self) -> None:
        if self.watch_mode not in WATCH_MODES:
            self.watch_mode = WATCH_RANDOM
        if self.speed_multiplier not in SPEED_OPTIONS:
            self.speed_multiplier = 1
        self.focus_team_id = str(self.focus_team_id)


def choose_auto_watch_fixture(
    fixtures: list[dict],
    config: LeagueAutoProgressConfig,
    rng: Random,
) -> dict | None:
    """Choose only the displayed fixture; all other fixtures remain real headless matches."""
    config.normalize()
    available = [fixture for fixture in fixtures if not fixture.get("played")]
    if not available or config.watch_mode == WATCH_NONE:
        return None
    if config.watch_mode == WATCH_FOCUS:
        focus_id = config.focus_team_id
        available = [
            fixture for fixture in available
            if focus_id in (str(fixture.get("home_id", "")), str(fixture.get("away_id", "")))
        ]
        if not available:
            return None
    return rng.choice(available)
