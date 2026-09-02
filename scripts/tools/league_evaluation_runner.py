"""Unattended, checkpointed evaluation of complete league seasons."""

from __future__ import annotations

import os
import platform
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from copy import deepcopy
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path

from scripts.core.performance_settings import (
    league_simulation_profile,
    limited_worker_count,
    normalize_cpu_limit,
    worker_duty_cycle,
)
from scripts.core.simulation_runtime import MAX_FULL_MATCH_STEPS
from scripts.league.league_manager import LeagueManager, recommended_worker_count
from scripts.league.league_simulation_workers import _run_headless_league_match
from scripts.team.team_data import discover_team_choices
from scripts.tools.league_evaluation_report import (
    append_jsonl,
    build_summary,
    read_jsonl,
    write_csv_reports,
    write_json_atomic,
)


class LeagueEvaluationRunner:
    """Run real league matches unattended and persist reproducible diagnostics."""

    def __init__(self, config: dict, output_dir: Path, *, checkpoint: dict | None = None) -> None:
        self.config = deepcopy(config)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.matches_path = self.output_dir / "matches.jsonl"
        self.seasons_path = self.output_dir / "seasons.jsonl"
        self.events_path = self.output_dir / "events.jsonl"
        self.errors_path = self.output_dir / "errors.jsonl"
        self.checkpoint_path = self.output_dir / "checkpoint.json"
        self.summary_path = self.output_dir / "summary.json"
        self.started_at = time.perf_counter()
        self.previous_elapsed_seconds = float((checkpoint or {}).get("elapsed_seconds", 0.0))
        self.matches_completed = int((checkpoint or {}).get("matches_completed", 0))
        if self.matches_completed <= 0 and self.matches_path.exists():
            self.matches_completed = len(read_jsonl(self.matches_path))
        self.matchdays_completed = int((checkpoint or {}).get("matchdays_completed", 0))
        self.seasons_completed = int((checkpoint or {}).get("seasons_completed", 0))
        self._interrupted = False

        choices = discover_team_choices()
        self.manager = LeagueManager(
            choices,
            template_id=str(self.config.get("template_id", "default")),
            load_state=False,
        )
        if checkpoint and isinstance(checkpoint.get("manager_state"), dict):
            self.manager._apply_state(checkpoint["manager_state"])
            self.manager.refresh_teams(choices)
        else:
            self._select_competitions()
        self.manager.save_path = None
        self.manager.save = lambda: None
        self.worker_count, self.worker_duty_cycle = self._worker_budget()

    def _select_competitions(self) -> None:
        requested = [str(value) for value in self.config.get("leagues", [])]
        playable = [name for name in self.manager.league_names if len(self.manager.teams_in_league(name)) >= 2]
        if not requested or requested == ["all"]:
            selected = playable
        else:
            unknown = [name for name in requested if name not in self.manager.league_names]
            if unknown:
                raise ValueError("リーグが見つかりません: " + ", ".join(unknown))
            selected = [name for name in requested if name in playable]
        if not selected:
            raise ValueError("2チーム以上所属する評価対象リーグがありません")
        self.manager.selected_leagues = set(selected)
        self.manager.selected_tournaments = set()

    def _worker_budget(self) -> tuple[int, float]:
        cpu_limit = normalize_cpu_limit(self.config.get("cpu_limit", 100))
        safe_workers = recommended_worker_count(
            999,
            reserve_for_ui=False,
            cpu_limit_percent=100,
        )
        requested = self.config.get("processes", "auto")
        if str(requested).casefold() == "auto":
            full_budget = min(safe_workers, int(self.config.get("max_processes", 8)))
        else:
            full_budget = min(safe_workers, max(1, int(requested)), int(self.config.get("max_processes", 8)))
        workers = limited_worker_count(full_budget, cpu_limit)
        return workers, worker_duty_cycle(full_budget, cpu_limit, workers)

    def _job(self, fixture: dict) -> dict:
        profile = league_simulation_profile(self.config.get("quality", "PRECISE"))
        return {
            "fixture": deepcopy(fixture),
            "home_choice": self.manager.choices_by_id[str(fixture["home_id"])],
            "away_choice": self.manager.choices_by_id[str(fixture["away_id"])],
            "simulation_mode": str(self.config.get("quality", "PRECISE")),
            "ai_rethink_multiplier": float(profile["ai_rethink_multiplier"]),
            "cpu_duty_cycle": self.worker_duty_cycle,
            "collect_telemetry": True,
            "sample_every_steps": int(self.config.get("sample_every_steps", 18)),
        }

    @staticmethod
    def _enrich_result(fixture: dict, result: dict) -> dict:
        return {
            **result,
            "year": int(fixture.get("year", 0)),
            "day": int(fixture.get("day", 0)),
            "round": int(fixture.get("round", 0)),
            "league": str(fixture.get("league", "")),
            "tournament": str(fixture.get("tournament", "")),
            "fixture_type": str(fixture.get("fixture_type", "REGULAR")),
            "competition_label": str(fixture.get("competition_label", "")),
            "home_id": str(fixture.get("home_id", "")),
            "away_id": str(fixture.get("away_id", "")),
            "home_name": str(fixture.get("home_name", "")),
            "away_name": str(fixture.get("away_name", "")),
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _failed_result(self, fixture: dict, error: Exception) -> dict:
        failure = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "fixture_id": fixture.get("id", ""),
            "error_type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        append_jsonl(self.errors_path, failure)
        if bool(self.config.get("stop_on_error", False)):
            raise RuntimeError(f"試合評価に失敗しました: {fixture.get('id')}") from error
        return self._enrich_result(fixture, {
            "fixture_id": fixture.get("id", ""),
            "home_score": 0,
            "away_score": 0,
            "home_shots": 0,
            "away_shots": 0,
            "home_possession": 0.0,
            "away_possession": 0.0,
            "goal_scorers": [],
            "engine_steps": 0,
            "wall_seconds": 0.0,
            "fulltime": False,
            "evaluation_failed": True,
            "simulation_mode": str(self.config.get("quality", "PRECISE")),
        })

    def _run_batch(self, fixtures: list[dict], executor: ProcessPoolExecutor | None) -> list[dict]:
        results: dict[str, dict] = {}
        if executor is None:
            for fixture in fixtures:
                try:
                    raw = _run_headless_league_match(self._job(fixture))
                    results[str(fixture["id"])] = self._enrich_result(fixture, raw)
                except Exception as error:
                    results[str(fixture["id"])] = self._failed_result(fixture, error)
        else:
            futures = {executor.submit(_run_headless_league_match, self._job(fixture)): fixture for fixture in fixtures}
            for future in as_completed(futures):
                fixture = futures[future]
                try:
                    results[str(fixture["id"])] = self._enrich_result(fixture, future.result())
                except Exception as error:
                    if isinstance(error, BrokenProcessPool):
                        raise
                    results[str(fixture["id"])] = self._failed_result(fixture, error)
        ordered_results = [results[str(fixture["id"])] for fixture in fixtures]
        return self._retry_incomplete_results(fixtures, ordered_results, executor)

    def _retry_incomplete_results(
        self,
        fixtures: list[dict],
        results: list[dict],
        executor: ProcessPoolExecutor | None,
    ) -> list[dict]:
        """Retry step-limited matches once without accepting a partial score."""
        fixtures_by_id = {str(fixture["id"]): fixture for fixture in fixtures}
        retry_fixtures = [
            fixtures_by_id[str(result.get("fixture_id", ""))]
            for result in results
            if result.get("fulltime", True) is not True
            and not result.get("evaluation_failed", False)
            and str(result.get("fixture_id", "")) in fixtures_by_id
        ]
        if not retry_fixtures:
            return results

        replacements: dict[str, dict] = {}
        retry_jobs = {}
        for fixture in retry_fixtures:
            job = self._job(fixture)
            job["max_match_steps"] = MAX_FULL_MATCH_STEPS * 2
            retry_jobs[str(fixture["id"])] = job

        if executor is None:
            for fixture in retry_fixtures:
                try:
                    raw = _run_headless_league_match(retry_jobs[str(fixture["id"])])
                    replacements[str(fixture["id"])] = self._enrich_result(fixture, raw)
                except Exception as error:
                    replacements[str(fixture["id"])] = self._failed_result(fixture, error)
        else:
            futures = {
                executor.submit(_run_headless_league_match, retry_jobs[str(fixture["id"])]): fixture
                for fixture in retry_fixtures
            }
            for future in as_completed(futures):
                fixture = futures[future]
                try:
                    replacements[str(fixture["id"])] = self._enrich_result(fixture, future.result())
                except Exception as error:
                    if isinstance(error, BrokenProcessPool):
                        raise
                    replacements[str(fixture["id"])] = self._failed_result(fixture, error)

        return [replacements.get(str(result.get("fixture_id", "")), result) for result in results]

    def _record_batch(self, fixtures: list[dict], results: list[dict]) -> None:
        incomplete = [result for result in results if result.get("fulltime", True) is not True]
        if incomplete:
            for result in incomplete:
                append_jsonl(self.errors_path, {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "event": "match_incomplete_after_retry",
                    "fixture_id": result.get("fixture_id", ""),
                    "finish_reason": result.get("finish_reason", "unknown"),
                    "engine_steps": int(result.get("engine_steps", 0)),
                    "game_time": float(result.get("game_time", 0.0)),
                    "restart_type": str(result.get("restart_type", "")),
                    "restart_elapsed": float(result.get("restart_elapsed", 0.0)),
                })
            raise RuntimeError(
                f"再試行後も未完走の試合が{len(incomplete)}件あります。順位表には反映しません"
            )
        for result in results:
            append_jsonl(self.matches_path, result)
        self.manager.apply_headless_results(results)
        event = {
            "event": "matchday_completed",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "year": self.manager.year,
            "day": self.manager.day,
            "matches": len(fixtures),
            "total_matches": self.matches_completed + len(results),
        }
        append_jsonl(self.events_path, event)
        self.matches_completed = int(event["total_matches"])
        self.matchdays_completed += 1
        print(
            f"year{self.manager.year} {self.manager.day}日目: {len(fixtures)}試合完了 "
            f"(累計{event['total_matches']}試合)",
            flush=True,
        )

    def _complete_season(self) -> None:
        year = self.manager.year
        season = {
            "year": year,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "leagues": {
                league: self.manager.standings(league)
                for league in sorted(self.manager.selected_leagues)
            },
            "promotion_events": deepcopy(self.manager.promotion_events),
        }
        append_jsonl(self.seasons_path, season)
        self.manager._start_next_year()
        self.seasons_completed += 1
        print(f"year{year} 完了", flush=True)

    def _checkpoint(self, status: str) -> None:
        payload = {
            "format_version": 1,
            "status": status,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "config": self.config,
            "matchdays_completed": self.matchdays_completed,
            "seasons_completed": self.seasons_completed,
            "matches_completed": self.matches_completed,
            "elapsed_seconds": self.previous_elapsed_seconds + time.perf_counter() - self.started_at,
            "manager_state": self.manager._state_payload(),
        }
        write_json_atomic(self.checkpoint_path, payload)

    def _should_stop(self) -> str:
        max_hours = max(0.0, float(self.config.get("hours", 0.0)))
        max_seasons = max(0, int(self.config.get("seasons", 0)))
        max_matchdays = max(0, int(self.config.get("max_matchdays", 0)))
        if max_hours and time.perf_counter() - self.started_at >= max_hours * 3600.0:
            return "time_limit"
        if max_seasons and self.seasons_completed >= max_seasons:
            return "season_limit"
        if max_matchdays and self.matchdays_completed >= max_matchdays:
            return "matchday_limit"
        return ""

    def _write_summary(self, status: str) -> dict:
        match_rows = read_jsonl(self.matches_path)
        season_rows = read_jsonl(self.seasons_path)
        summary = build_summary(
            match_rows,
            season_rows,
            status=status,
            elapsed_seconds=self.previous_elapsed_seconds + time.perf_counter() - self.started_at,
        )
        summary.update({
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "output_directory": str(self.output_dir),
            "worker_count": self.worker_count,
            "worker_duty_cycle": self.worker_duty_cycle,
            "cpu_count": os.cpu_count() or 1,
            "platform": platform.platform(),
            "config": self.config,
        })
        write_json_atomic(self.summary_path, summary)
        write_csv_reports(self.output_dir, match_rows)
        return summary

    def run(self) -> dict:
        write_json_atomic(self.output_dir / "config.json", self.config)
        append_jsonl(self.events_path, {
            "event": "started",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "year": self.manager.year,
            "day": self.manager.day,
            "worker_count": self.worker_count,
        })
        executor = (
            ProcessPoolExecutor(max_workers=self.worker_count, mp_context=get_context("spawn"))
            if self.worker_count > 1 else None
        )
        status = "completed"
        try:
            while not (status := self._should_stop()):
                due = self.manager.fixtures_on_day(self.manager.day, unplayed_only=True)
                if not due:
                    next_day = self.manager.next_matchday()
                    if next_day is None:
                        self._complete_season()
                        self._checkpoint("running")
                        continue
                    self.manager.day = next_day
                    due = self.manager.fixtures_on_day(next_day, unplayed_only=True)
                append_jsonl(self.events_path, {
                    "event": "matchday_started",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "year": self.manager.year,
                    "day": self.manager.day,
                    "matches": len(due),
                })
                results = self._run_batch(due, executor)
                self._record_batch(due, results)
                self._checkpoint("running")
        except KeyboardInterrupt:
            self._interrupted = True
            status = "interrupted"
        except Exception as error:
            status = "error"
            append_jsonl(self.errors_path, {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "error_type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            })
        finally:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=self._interrupted)
            self._checkpoint(status)
        return self._write_summary(status)


__all__ = ("LeagueEvaluationRunner",)
