from __future__ import annotations

import json
import os
import statistics
import sys
import time
from datetime import datetime

import pygame

from scripts.app.game_app import Game
from scripts.core.paths import PERFORMANCE_LOG_DIR


MATCH_COUNT = max(2, int(os.environ.get("KADOKA_STRESS_MATCHES", "90")))
VISIBLE_SPEED = max(1, int(os.environ.get("KADOKA_STRESS_SPEED", "1")))
AUTO_CLOSE_DELAY = 5.0
WALL_TIME_LIMIT = max(5.0, float(os.environ.get("KADOKA_STRESS_SECONDS", "30")))
USE_LEGACY_VISIBLE_UPDATE = os.environ.get("KADOKA_STRESS_LEGACY", "0") == "1"
LOG_DIR = PERFORMANCE_LOG_DIR


def build_fixtures(game: Game) -> list[dict]:
    choices = list(game.team_choices)
    if len(choices) < 2:
        raise RuntimeError("90試合テストには有効なチームが2つ以上必要です")

    fixtures: list[dict] = []
    for index in range(MATCH_COUNT):
        home = choices[(index * 2) % len(choices)]
        away = choices[(index * 2 + 1) % len(choices)]
        if str(home["id"]) == str(away["id"]):
            away = choices[(index * 2 + 2) % len(choices)]
        fixtures.append(
            {
                "id": f"stress90:{index + 1:03d}",
                "year": game.league_manager.year,
                "league": "Aリーグ",
                "round": 1,
                "day": game.league_manager.day,
                "home_id": str(home["id"]),
                "away_id": str(away["id"]),
                "home_name": str(home["name"]),
                "away_name": str(away["name"]),
                "fixture_type": "REGULAR",
                "competition_label": "90試合同時実行テスト",
                "played": False,
                "home_score": None,
                "away_score": None,
                "watched": False,
            }
        )
    return fixtures


class NinetyMatchStressGame(Game):
    def __init__(self) -> None:
        super().__init__()
        pygame.display.set_caption("カドカルチョ - 90試合同時実行テスト")

        # This run must not alter the user's league save.  The normal league
        # fixture/session code is used, but persistence is disabled in memory.
        self.league_manager.save = lambda: None
        self.league_manager.selected_leagues = {"Aリーグ"}
        self.league_manager.last_results = []
        self.league_manager.fixtures = build_fixtures(self)
        self.league_manager.watch_fixture_id = self.league_manager.fixtures[0]["id"]

        self._stress_started = time.perf_counter()
        self._last_report = self._stress_started
        self._completed_at: float | None = None
        self._session_errors: list[str] = []
        self._session_result_count = 0
        self._summary_written = False
        self._last_frame_started_at = time.perf_counter()
        self._playing_frame_intervals: list[float] = []
        self._postmatch_frame_intervals: list[float] = []
        self._draw_times: list[float] = []
        self._match_update_times: list[float] = []
        self._league_poll_times: list[float] = []

        self.start_league_fixture(self.league_manager.fixtures[0])
        self.match.speed_multiplier = VISIBLE_SPEED
        if USE_LEGACY_VISIBLE_UPDATE:
            self.visible_simulation.advance = lambda match, dt: (match.update(dt) or 0)
        self._original_visible_advance = self.visible_simulation.advance
        self.visible_simulation.advance = self._timed_visible_advance
        session = self.league_simulation_session
        workers = session.worker_count if session is not None else 0
        waves = session.estimated_waves if session is not None else 0
        memory_gb = session.available_memory_gb if session is not None else 0.0
        print(
            "STRESS90_START "
            + json.dumps(
                {
                    "total_matches": MATCH_COUNT,
                    "rendered_matches": 1,
                    "headless_matches": MATCH_COUNT - 1,
                    "visible_speed": VISIBLE_SPEED,
                    "workers": workers,
                    "estimated_waves": waves,
                    "available_memory_gb": round(memory_gb, 2),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    def update_league_simulations(self) -> None:
        poll_started = time.perf_counter()
        previous_session = self.league_simulation_session
        super().update_league_simulations()
        self._league_poll_times.append(time.perf_counter() - poll_started)
        if previous_session is not None and self.league_simulation_session is None:
            self._session_errors.extend(previous_session.errors)
            self._session_result_count += len(previous_session.results)

        now = time.perf_counter()
        if now - self._last_report >= 5.0:
            self._last_report = now
            session = self.league_simulation_session
            statuses = list(session.live_status.values()) if session is not None else []
            minutes = [int(status.get("minute", 0)) for status in statuses]
            print(
                "STRESS90_PROGRESS "
                + json.dumps(
                    {
                        "elapsed_seconds": round(now - self._stress_started, 1),
                        "visible_minute": min(90, int(self.match.game_time // 60)),
                        "headless_minute_min": min(minutes) if minutes else 90,
                        "headless_minute_max": max(minutes) if minutes else 90,
                        "headless_batches_completed": session.completed if session is not None else MATCH_COUNT - 1,
                        "headless_matches_completed": session.display_completed if session is not None else MATCH_COUNT - 1,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        all_done = (
            self.match.state == "FULLTIME"
            and self.league_match_finalized
            and self.league_simulation_session is None
        )
        if all_done and self._completed_at is None:
            self._completed_at = now
            self._write_summary(timed_out=False)
        if self._completed_at is not None and now - self._completed_at >= AUTO_CLOSE_DELAY:
            self.running = False
        elif now - self._stress_started >= WALL_TIME_LIMIT:
            self._write_summary(timed_out=True)
            if self.league_simulation_session is not None:
                self.league_simulation_session.cancel()
                self.league_simulation_session = None
            self.running = False

    def _timed_visible_advance(self, match, dt: float) -> int:
        started = time.perf_counter()
        result = self._original_visible_advance(match, dt)
        self._match_update_times.append(time.perf_counter() - started)
        return result

    def draw(self) -> None:
        frame_started = time.perf_counter()
        interval = frame_started - self._last_frame_started_at
        self._last_frame_started_at = frame_started
        state_before_draw = self.match.state
        started = time.perf_counter()
        super().draw()
        self._draw_times.append(time.perf_counter() - started)
        if state_before_draw == "PLAYING":
            self._playing_frame_intervals.append(interval)
        else:
            self._postmatch_frame_intervals.append(interval)

    @staticmethod
    def _timing_summary(samples: list[float]) -> dict[str, float | int]:
        if not samples:
            return {"samples": 0, "average_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0, "over_33ms": 0, "over_50ms": 0}
        ordered = sorted(samples)
        percentile = lambda ratio: ordered[min(len(ordered) - 1, int((len(ordered) - 1) * ratio))]
        return {
            "samples": len(samples),
            "average_ms": round(statistics.fmean(samples) * 1000.0, 3),
            "p95_ms": round(percentile(0.95) * 1000.0, 3),
            "p99_ms": round(percentile(0.99) * 1000.0, 3),
            "max_ms": round(max(samples) * 1000.0, 3),
            "over_33ms": sum(value > 0.033334 for value in samples),
            "over_50ms": sum(value > 0.050 for value in samples),
        }
    def _write_summary(self, *, timed_out: bool) -> None:
        if self._summary_written:
            return
        self._summary_written = True
        played = [fixture for fixture in self.league_manager.fixtures if fixture.get("played")]
        watched = [fixture for fixture in played if fixture.get("watched")]
        headless = [fixture for fixture in played if not fixture.get("watched")]
        summary = {
            "measurement_limit_reached": timed_out,
            "configured_matches": MATCH_COUNT,
            "configured_speed": VISIBLE_SPEED,
            "legacy_visible_update": USE_LEGACY_VISIBLE_UPDATE,
            "elapsed_seconds": round(time.perf_counter() - self._stress_started, 3),
            "played_matches": len(played),
            "rendered_matches": len(watched),
            "headless_matches": len(headless),
            "unplayed_matches": MATCH_COUNT - len(played),
            "worker_results": self._session_result_count,
            "errors": self._session_errors,
            "rendered_score": (
                f"{watched[0]['home_name']} {watched[0]['home_score']}-{watched[0]['away_score']} {watched[0]['away_name']}"
                if watched
                else "not completed"
            ),
            "playing_frame_interval": self._timing_summary(self._playing_frame_intervals),
            "postmatch_frame_interval": self._timing_summary(self._postmatch_frame_intervals),
            "draw_time": self._timing_summary(self._draw_times),
            "match_update_time": self._timing_summary(self._match_update_times),
            "league_poll_time": self._timing_summary(self._league_poll_times),
        }
        print("STRESS90_RESULT " + json.dumps(summary, ensure_ascii=False), flush=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = LOG_DIR / f"league_stress_{MATCH_COUNT}_{stamp}.json"
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"STRESS90_LOG {output}", flush=True)


def main() -> None:
    game = NinetyMatchStressGame()
    try:
        game.run()
    finally:
        if not game._summary_written:
            game._write_summary(timed_out=True)


if __name__ == "__main__":
    main()
