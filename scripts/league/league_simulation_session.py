"""Lifecycle of a non-blocking multicore league simulation batch."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from queue import Empty

from scripts.core.performance_settings import (
    league_simulation_profile,
    limited_worker_count,
    normalize_cpu_limit,
    normalize_league_simulation_mode,
    worker_duty_cycle,
)
from scripts.league.league_simulation_workers import (
    _run_headless_league_match,
    _run_synchronized_match_batch,
)
from scripts.league.league_worker_budget import available_memory_bytes, recommended_worker_count

class LeagueSimulationSession:
    """Non-blocking multicore batch of complete headless Match simulations."""

    def __init__(
        self,
        fixtures: list[dict],
        choices_by_id: dict[str, dict],
        max_workers: int | None = None,
        *,
        live_updates: bool = False,
        cpu_limit_percent: int = 100,
        simulation_mode: str = "PRECISE",
    ) -> None:
        self.total = len(fixtures)
        self.completed = 0
        self.results: list[dict] = []
        self.errors: list[str] = []
        self.finished = self.total == 0
        self.executor: ProcessPoolExecutor | None = None
        self.pending: dict = {}
        self.live_status: dict[str, dict] = {
            str(fixture["id"]): {
                "fixture_id": str(fixture["id"]),
                "league": str(fixture.get("league", "")),
                "home_name": str(fixture.get("home_name", "")),
                "away_name": str(fixture.get("away_name", "")),
                "game_time": 0.0, "minute": 0,
                "home_score": 0, "away_score": 0, "state": "PLAYING",
            }
            for fixture in fixtures
        }
        self.process_manager = None
        self.progress_queue = None
        self.sync_clock = None
        self.cancel_event = None
        self.live_updates = bool(live_updates)
        self.cpu_limit_percent = normalize_cpu_limit(cpu_limit_percent)
        self.simulation_mode = normalize_league_simulation_mode(simulation_mode)
        simulation_profile = league_simulation_profile(self.simulation_mode)
        self.ai_rethink_multiplier = float(simulation_profile["ai_rethink_multiplier"])
        self.worker_count = 0
        self.worker_duty_cycle = 1.0
        self.estimated_waves = 0
        self.detected_cpu_count = os.cpu_count() or 2
        self.available_memory_gb = available_memory_bytes() / 1024**3
        if self.finished:
            return
        if live_updates:
            self.process_manager = get_context("spawn").Manager()
            self.progress_queue = self.process_manager.Queue()
            self.sync_clock = self.process_manager.Value("d", 0.0)
            self.cancel_event = self.process_manager.Event()
        # A watched match needs one estimated physical core for pygame and
        # rendering.  An unattended result screen can devote all estimated
        # physical cores to league workers while remaining process-bounded.
        full_worker_budget = recommended_worker_count(self.total, reserve_for_ui=live_updates)
        if max_workers is not None:
            full_worker_budget = max(1, min(int(max_workers), full_worker_budget))
        workers = limited_worker_count(full_worker_budget, self.cpu_limit_percent)
        self.worker_count = workers
        self.worker_duty_cycle = worker_duty_cycle(full_worker_budget, self.cpu_limit_percent, workers)
        self.estimated_waves = (self.total + workers - 1) // workers
        self.executor = ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))
        valid_jobs: list[dict] = []
        for fixture in fixtures:
            home_choice = choices_by_id.get(str(fixture.get("home_id")))
            away_choice = choices_by_id.get(str(fixture.get("away_id")))
            if home_choice is None or away_choice is None:
                self.completed += 1
                self.errors.append(str(fixture.get("id", "missing team")))
                continue
            job = {
                "fixture": fixture,
                "home_choice": home_choice,
                "away_choice": away_choice,
                "progress_queue": self.progress_queue,
                "cpu_duty_cycle": self.worker_duty_cycle,
                "simulation_mode": self.simulation_mode,
                "ai_rethink_multiplier": self.ai_rethink_multiplier,
            }
            valid_jobs.append(job)
        if live_updates and valid_jobs:
            batches: list[list[dict]] = [[] for _ in range(min(workers, len(valid_jobs)))]
            for index, job in enumerate(valid_jobs):
                batches[index % len(batches)].append(job)
            for batch in batches:
                future = self.executor.submit(
                    _run_synchronized_match_batch,
                    batch, self.sync_clock, self.progress_queue, self.cancel_event,
                )
                self.pending[future] = {"label": ",".join(str(job["fixture"]["id"]) for job in batch), "count": len(batch)}
        else:
            for job in valid_jobs:
                future = self.executor.submit(_run_headless_league_match, job)
                self.pending[future] = {"label": str(job["fixture"]["id"]), "count": 1}
        if not self.pending:
            self.finished = True
            self._shutdown()

    @property
    def display_completed(self) -> int:
        """Return per-fixture progress even when several games share a future."""
        reported = sum(
            1 for status in self.live_status.values()
            if status.get("state") == "FULLTIME"
        )
        return min(self.total, max(self.completed, reported))

    @property
    def display_average_minute(self) -> int:
        """Expose moving progress while a large synchronized batch is unfinished."""
        if not self.live_status:
            return 90 if self.finished else 0
        minutes = [
            min(90, int(float(status.get("game_time", float(status.get("minute", 0)) * 60.0)) // 60))
            for status in self.live_status.values()
        ]
        return round(sum(minutes) / len(minutes))

    @property
    def progress(self) -> float:
        return self.display_completed / max(1, self.total)

    def set_target_simulation_time(self, simulation_elapsed: float) -> None:
        if self.sync_clock is not None:
            if float(self.sync_clock.value) >= 0.0:
                self.sync_clock.value = max(0.0, float(simulation_elapsed))

    def finish_remaining_as_fast_as_possible(self) -> None:
        """Release live pacing after the watched match reaches full time."""
        if self.sync_clock is not None:
            self.sync_clock.value = -1.0

    def poll(self) -> bool:
        self._drain_progress()
        if self.finished:
            return True
        for future in [future for future in self.pending if future.done()]:
            pending_info = self.pending.pop(future)
            try:
                result = future.result()
                if isinstance(result, list):
                    self.results.extend(result)
                else:
                    self.results.append(result)
            except Exception as error:
                self.errors.append(f"{pending_info['label']}: {error}")
            self.completed += int(pending_info["count"])
        if self.completed >= self.total:
            self._drain_progress()
            self.finished = True
            self._shutdown()
        return self.finished

    def _drain_progress(self) -> None:
        if self.progress_queue is None:
            return
        while True:
            try:
                update = self.progress_queue.get_nowait()
            except Empty:
                break
            status = self.live_status.get(str(update.get("fixture_id")))
            if status is not None:
                status.update(update)

    def _shutdown(self) -> None:
        if self.executor is not None:
            # All tracked futures are complete before normal shutdown reaches
            # this path. Reap the pool before stopping the Manager server so a
            # worker cannot retain a Queue/Value proxy while its owner exits.
            executor = self.executor
            self.executor = None
            executor.shutdown(wait=True, cancel_futures=False)
        # Pool shutdown can flush the last progress messages.
        self._drain_progress()
        if self.process_manager is not None:
            process_manager = self.process_manager
            self.process_manager = None
            process_manager.shutdown()
        self.progress_queue = None
        self.sync_clock = None
        self.cancel_event = None

    def cancel(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
        for future in self.pending:
            future.cancel()
        self.pending.clear()
        if self.executor is not None:
            self.executor.shutdown(wait=bool(self.cancel_event), cancel_futures=True)
            self.executor = None
        if self.process_manager is not None:
            self.process_manager.shutdown()
            self.process_manager = None
        self.finished = True


__all__ = ("LeagueSimulationSession",)
