"""Pickle-safe worker functions for complete league matches."""

from __future__ import annotations

import hashlib
import time
from statistics import mean

from scripts.core.cpu_usage_limiter import CpuUsageLimiter
from scripts.core.match_telemetry import MatchTelemetry
from scripts.core.simulation_runtime import MAX_FULL_MATCH_STEPS, advance_match_fixed
from scripts.match.match_engine import Match


SYNCED_LIVE_STEP_BUDGET = 20
SYNCED_FAST_FINISH_STEP_BUDGET = 240
SYNCED_LIVE_REPORT_INTERVAL = 5.0
SYNCED_FAST_FINISH_REPORT_INTERVAL = 60.0


def _run_headless_league_match(job: dict) -> dict:
    """Play a complete real Match in a worker process without rendering."""
    fixture = job["fixture"]
    match = Match(
        job["home_choice"], job["away_choice"], "HOME",
        ai_rethink_multiplier=float(job.get("ai_rethink_multiplier", 1.0)),
    )
    seed_text = f"{fixture.get('id')}:{job['home_choice'].get('name')}:{job['away_choice'].get('name')}"
    seed = int.from_bytes(hashlib.sha256(seed_text.encode("utf-8")).digest()[:8], "big")
    match.rng.seed(seed)
    match.start_new()
    collect_telemetry = bool(job.get("collect_telemetry", False))
    telemetry = MatchTelemetry(match) if collect_telemetry else None
    sample_every_steps = max(1, int(job.get("sample_every_steps", 18)))
    started_at = time.perf_counter()
    steps = 0
    progress_queue = job.get("progress_queue")
    cpu_limiter = CpuUsageLimiter(job.get("cpu_duty_cycle", 1.0))
    next_report = 0.0
    maximum_steps = max(1, int(job.get("max_match_steps", MAX_FULL_MATCH_STEPS)))
    while match.state != "FULLTIME" and steps < maximum_steps:
        advance_match_fixed(match)
        steps += 1
        if telemetry is not None:
            telemetry.observe_control()
            if steps % sample_every_steps == 0:
                telemetry.sample()
        cpu_limiter.throttle()
        if progress_queue is not None and match.game_time >= next_report:
            progress_queue.put({
                "fixture_id": fixture["id"],
                "minute": min(90, int(match.game_time // 60)),
                "home_score": match.home.score,
                "away_score": match.away.score,
                "state": match.state,
            })
            next_report += 60.0
    if progress_queue is not None:
        progress_queue.put({
            "fixture_id": fixture["id"],
            "game_time": min(5400.0, match.game_time),
            "minute": min(90, int(match.game_time // 60)),
            "home_score": match.home.score, "away_score": match.away.score,
            "state": match.state,
        })
    result = {
        "fixture_id": fixture["id"],
        "home_score": match.home.score,
        "away_score": match.away.score,
        "home_shots": match.home.shots,
        "away_shots": match.away.shots,
        "home_possession": match.home.possession,
        "away_possession": match.away.possession,
        "goal_scorers": list(match.goal_scorers),
        "engine_steps": steps,
        "simulation_mode": str(job.get("simulation_mode", "PRECISE")),
        "fulltime": match.state == "FULLTIME",
        "finish_reason": "fulltime" if match.state == "FULLTIME" else "step_limit",
        "game_time": match.game_time,
        "simulation_elapsed": match.simulation_elapsed,
        "restart_type": match.restart_type,
        "restart_elapsed": match.restart_elapsed,
        "restart_counts": dict(match.restart_counts),
        "wall_seconds": time.perf_counter() - started_at,
    }
    if telemetry is not None:
        result["home_telemetry"] = telemetry.team_metrics(match.home)
        result["away_telemetry"] = telemetry.team_metrics(match.away)
        result["home_remaining_stamina"] = mean(player.stamina_ratio for player in match.home.players)
        result["away_remaining_stamina"] = mean(player.stamina_ratio for player in match.away.players)
    return result


def _run_synchronized_match_batch(jobs: list[dict], sync_clock, progress_queue, cancel_event) -> list[dict]:
    """Advance games at the watched simulation pace, with independent clocks."""
    contexts: list[dict] = []
    cpu_limiter = CpuUsageLimiter(jobs[0].get("cpu_duty_cycle", 1.0) if jobs else 1.0)
    for job in jobs:
        fixture = job["fixture"]
        match = Match(
            job["home_choice"], job["away_choice"], "HOME",
            ai_rethink_multiplier=float(job.get("ai_rethink_multiplier", 1.0)),
        )
        seed_text = f"{fixture.get('id')}:{job['home_choice'].get('name')}:{job['away_choice'].get('name')}"
        seed = int.from_bytes(hashlib.sha256(seed_text.encode("utf-8")).digest()[:8], "big")
        match.rng.seed(seed)
        match.start_new()
        contexts.append({
            "fixture": fixture,
            "match": match,
            "steps": 0,
            "maximum_steps": max(1, int(job.get("max_match_steps", MAX_FULL_MATCH_STEPS))),
            "next_report": 0.0,
            "simulation_mode": str(job.get("simulation_mode", "PRECISE")),
        })

    while not cancel_event.is_set() and any(
        context["match"].state != "FULLTIME" and context["steps"] < context["maximum_steps"]
        for context in contexts
    ):
        requested_elapsed = float(sync_clock.value)
        finish_without_pacing = requested_elapsed < 0.0
        target_elapsed = float("inf") if finish_without_pacing else max(0.0, requested_elapsed)
        progressed = False
        for context in contexts:
            match = context["match"]
            if match.state == "FULLTIME" or context["steps"] >= context["maximum_steps"]:
                continue
            # Every match receives the same amount of physics time. Its playing
            # clock may legitimately differ because restarts pause independently.
            # Once the watched game is over there is no frame clock to follow.
            # Larger chunks improve cache locality and avoid repeatedly reading
            # the manager-backed clock for every twenty fixed physics steps.
            # The Match engine still receives the exact same 0.05 second steps.
            step_budget = (
                SYNCED_FAST_FINISH_STEP_BUDGET
                if finish_without_pacing
                else SYNCED_LIVE_STEP_BUDGET
            )
            while (
                match.simulation_elapsed + 0.001 < target_elapsed
                and step_budget > 0
                and match.state != "FULLTIME"
                and context["steps"] < context["maximum_steps"]
            ):
                advance_match_fixed(match)
                context["steps"] += 1
                step_budget -= 1
                progressed = True
                cpu_limiter.throttle()
            if match.game_time >= context["next_report"] or match.state == "FULLTIME":
                progress_queue.put({
                    "fixture_id": context["fixture"]["id"],
                    "game_time": min(5400.0, match.game_time),
                    "minute": min(90, int(match.game_time // 60)),
                    "home_score": match.home.score,
                    "away_score": match.away.score,
                    "state": match.state,
                })
                # Sending two Manager queue messages per real-time second is
                # useful during a watched game, but it can flood the IPC queue
                # when dozens of lagging games are released to full speed.
                report_interval = (
                    SYNCED_FAST_FINISH_REPORT_INTERVAL
                    if finish_without_pacing
                    else SYNCED_LIVE_REPORT_INTERVAL
                )
                context["next_report"] = match.game_time + report_interval
        if not progressed:
            time.sleep(0.002)

    if cancel_event.is_set():
        return []
    results = []
    for context in contexts:
        fixture = context["fixture"]
        match = context["match"]
        progress_queue.put({
            "fixture_id": fixture["id"],
            "game_time": min(5400.0, match.game_time),
            "minute": min(90, int(match.game_time // 60)),
            "home_score": match.home.score,
            "away_score": match.away.score,
            "state": match.state,
        })
        results.append({
            "fixture_id": fixture["id"], "home_score": match.home.score, "away_score": match.away.score,
            "home_shots": match.home.shots, "away_shots": match.away.shots,
            "home_possession": match.home.possession, "away_possession": match.away.possession,
            "goal_scorers": list(match.goal_scorers), "engine_steps": context["steps"],
            "simulation_mode": str(context.get("simulation_mode", "PRECISE")),
            "fulltime": match.state == "FULLTIME",
            "finish_reason": "fulltime" if match.state == "FULLTIME" else "step_limit",
            "game_time": match.game_time,
            "simulation_elapsed": match.simulation_elapsed,
            "restart_type": str(getattr(match, "restart_type", "")),
            "restart_elapsed": float(getattr(match, "restart_elapsed", 0.0)),
        })
    return results


__all__ = ("_run_headless_league_match", "_run_synchronized_match_batch")
