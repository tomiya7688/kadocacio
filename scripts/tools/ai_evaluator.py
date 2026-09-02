from __future__ import annotations

import argparse
import csv
import json
import os
import random
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path
from statistics import mean

from scripts.core.paths import AI_EVALUATION_DIR
from scripts.core.performance_settings import (
    limited_worker_count,
    load_performance_settings,
    normalize_cpu_limit,
    worker_duty_cycle,
)
from scripts.match.match_engine import Match
from scripts.core.settings import MATCH_SECONDS
from scripts.core.match_telemetry import MatchTelemetry
from scripts.core.simulation_limits import SimulationLimits
from scripts.core.simulation_runtime import run_headless_match
from scripts.core.stat_scale import PLAYER_STAT_MAX, PLAYER_STAT_MIN
from scripts.team.team_data import PLAYER_KEY_ALIASES, discover_team_choices


OUTPUT_DIR = AI_EVALUATION_DIR


def _find_team(choices: list[dict], text: str, fallback_index: int) -> dict:
    query = text.strip().casefold()
    if query:
        exact = next((choice for choice in choices if choice["name"].casefold() == query), None)
        if exact:
            return exact
        partial = next((choice for choice in choices if query in choice["name"].casefold()), None)
        if partial:
            return partial
        raise ValueError(f"チームが見つかりません: {text}")
    return choices[min(fallback_index, len(choices) - 1)]


def _canonical_parameter(name: str) -> str:
    query = name.strip()
    for canonical, aliases in PLAYER_KEY_ALIASES.items():
        if query == canonical or query in aliases:
            return canonical
    raise ValueError(f"選手パラメータが見つかりません: {name}")


def _with_parameter(choice: dict, parameter: str, value: int) -> dict:
    changed = deepcopy(choice)
    for record in tuple(changed.get("starters", ())) + tuple(changed.get("bench", ())):
        record["raw"][parameter] = str(round(max(PLAYER_STAT_MIN, min(PLAYER_STAT_MAX, int(value)))))
    changed["name"] = f"{choice['name']} [{parameter}={value}]"
    return changed


def _run_evaluation_job(job: dict) -> dict:
    random.seed(int(job["seed"]))
    if job["target_is_home"]:
        match = Match(job["target"], job["opponent"], "NEUTRAL")
        target = match.home
        opponent = match.away
    else:
        match = Match(job["opponent"], job["target"], "NEUTRAL")
        target = match.away
        opponent = match.home
    match.rng.seed(int(job["seed"]))
    match.state = "PLAYING"
    telemetry = MatchTelemetry(match)
    result = run_headless_match(
        match,
        SimulationLimits(
            wall_time_limit=job["wall_time_limit"],
            target_game_time=job["target_game_time"],
            sample_every_steps=18,
            cpu_duty_cycle=job.get("cpu_duty_cycle", 1.0),
        ),
        telemetry,
    )
    possession_total = target.possession + opponent.possession
    metrics = telemetry.team_metrics(target)
    metrics.update({
        "goals_for": float(target.score),
        "goals_against": float(opponent.score),
        "shots_for": float(target.shots),
        "shots_against": float(opponent.shots),
        "possession_share": target.possession / possession_total if possession_total else 0.5,
        "remaining_stamina": mean(player.stamina_ratio for player in target.players),
    })
    return {
        "value": job["value"],
        "seed": job["seed"],
        "target_is_home": job["target_is_home"],
        "simulation": {
            "reason": result.reason,
            "steps": result.steps,
            "elapsed_seconds": result.elapsed_seconds,
            "game_time": result.game_time,
            "fulltime": result.fulltime,
        },
        "metrics": metrics,
    }


def _aggregate(rows: list[dict]) -> dict:
    numeric_keys = (
        "goals_for", "goals_against", "shots_for", "shots_against", "possession_share",
        "remaining_stamina", "action_diversity", "active_ratio",
        "average_nearest_teammate_distance", "crowded_player_ratio", "average_team_width",
        "average_distance_to_ball", "takeaways", "turnovers",
    )
    aggregated = {key: mean(float(row["metrics"].get(key, 0.0)) for row in rows) for key in numeric_keys}
    aggregated["completed_matches"] = sum(bool(row["simulation"]["fulltime"]) for row in rows)
    aggregated["evaluated_matches"] = len(rows)
    aggregated["average_runtime_seconds"] = mean(float(row["simulation"]["elapsed_seconds"]) for row in rows)
    commands: dict[str, float] = {}
    names = {name for row in rows for name in row["metrics"].get("command_counts", {})}
    for name in names:
        commands[name] = mean(float(row["metrics"].get("command_counts", {}).get(name, 0)) for row in rows)
    aggregated["average_command_counts"] = dict(sorted(commands.items(), key=lambda item: item[1], reverse=True))
    return aggregated


def evaluate(args: argparse.Namespace) -> tuple[dict, Path, Path]:
    choices = discover_team_choices()
    target = _find_team(choices, args.team, 0)
    opponent = _find_team(choices, args.opponent, 1)
    parameter = _canonical_parameter(args.parameter)
    values = [round(max(PLAYER_STAT_MIN, min(PLAYER_STAT_MAX, int(part)))) for part in args.values.split(",") if part.strip()]
    if not values:
        raise ValueError("比較する値を1つ以上指定してください")
    seeds = [args.seed + index for index in range(max(1, args.matches))]
    target_game_time = None if args.full_match else min(MATCH_SECONDS, max(60.0, args.game_minutes * 60.0))
    jobs = []
    for value in values:
        variant = _with_parameter(target, parameter, value)
        for index, seed in enumerate(seeds):
            jobs.append({
                "target": variant, "opponent": opponent, "value": value, "seed": seed,
                "target_is_home": index % 2 == 0,
                "wall_time_limit": None if args.wall_seconds <= 0 else args.wall_seconds,
                "target_game_time": target_game_time,
            })
    cpu_count = os.cpu_count() or 1
    configured_limit = load_performance_settings().cpu_limit_percent
    cpu_limit_percent = normalize_cpu_limit(args.cpu_limit if args.cpu_limit is not None else configured_limit)
    if args.processes == "auto":
        full_process_count = max(1, min(cpu_count - 1 or 1, args.max_processes, len(jobs)))
    else:
        full_process_count = max(1, min(int(args.processes), args.max_processes, len(jobs)))
    process_count = limited_worker_count(full_process_count, cpu_limit_percent)
    duty_cycle = worker_duty_cycle(full_process_count, cpu_limit_percent, process_count)
    for job in jobs:
        job["cpu_duty_cycle"] = duty_cycle
    if process_count == 1:
        rows = [_run_evaluation_job(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=process_count, mp_context=get_context("spawn")) as executor:
            rows = list(executor.map(_run_evaluation_job, jobs))
    grouped = {str(value): _aggregate([row for row in rows if row["value"] == value]) for value in values}
    report = {
        "format_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target_team": target["name"],
        "opponent_team": opponent["name"],
        "parameter": args.parameter,
        "canonical_parameter": parameter,
        "values": values,
        "matches_per_value": len(seeds),
        "full_match": bool(args.full_match),
        "target_game_minutes": 90 if args.full_match else args.game_minutes,
        "wall_time_limit_per_match": None if args.wall_seconds <= 0 else args.wall_seconds,
        "cpu_count": cpu_count,
        "process_count": process_count,
        "cpu_limit_percent": cpu_limit_percent,
        "worker_duty_cycle": duty_cycle,
        "fixed_physics_dt": 0.05,
        "summary": grouped,
        "matches": rows,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("ai_evaluation_%Y%m%d_%H%M%S")
    json_path = OUTPUT_DIR / f"{stem}.json"
    csv_path = OUTPUT_DIR / f"{stem}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = ["parameter_value"] + [key for key in next(iter(grouped.values())) if key != "average_command_counts"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for value, metrics in grouped.items():
            writer.writerow({"parameter_value": value, **{key: metrics[key] for key in fieldnames[1:]}})
    return report, json_path, csv_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="描画なしで選手パラメータの差を比較します")
    parser.add_argument("--team", default="", help="評価するチーム名（空欄なら一覧の先頭）")
    parser.add_argument("--opponent", default="", help="対戦相手名（空欄なら一覧の2番目）")
    parser.add_argument("--parameter", default="インテリジェンス", help="評価する選手パラメータ")
    parser.add_argument("--values", default="0,2750,5500", help="比較値（0～5500）。カンマ区切り")
    parser.add_argument("--matches", type=int, default=2, help="値ごとの試合数")
    parser.add_argument("--game-minutes", type=float, default=15.0, help="短時間評価の試合内分数")
    parser.add_argument("--full-match", action="store_true", help="90分終了まで評価")
    parser.add_argument("--wall-seconds", type=float, default=30.0, help="1試合の実時間上限。0で無制限")
    parser.add_argument("--processes", default="1", help="同時プロセス数。autoも指定可能")
    parser.add_argument("--max-processes", type=int, default=8, help="同時プロセスの安全上限")
    parser.add_argument("--cpu-limit", type=int, default=None, help="CPU演算枠の上限（10～100。省略時は共通設定）")
    parser.add_argument("--seed", type=int, default=72401, help="比較に共通使用する乱数シード")
    return parser


def main() -> None:
    report, json_path, csv_path = evaluate(build_parser().parse_args())
    print(f"評価完了: {report['target_team']} / {report['parameter']}")
    for value, metrics in report["summary"].items():
        print(
            f"  {value}: 支配率={metrics['possession_share'] * 100:.1f}% "
            f"シュート={metrics['shots_for']:.2f} 密集率={metrics['crowded_player_ratio'] * 100:.1f}% "
            f"完走={metrics['completed_matches']}/{metrics['evaluated_matches']}"
        )
    print(f"JSON: {json_path}")
    print(f"CSV : {csv_path}")


if __name__ == "__main__":
    main()
