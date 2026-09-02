"""Incremental files and final summaries for unattended league evaluation."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * ratio))]


def _team_aggregate(rows: list[dict]) -> list[dict]:
    teams: dict[str, dict] = defaultdict(lambda: {
        "team_id": "", "team_name": "", "matches": 0,
        "won": 0, "drawn": 0, "lost": 0, "goals_for": 0, "goals_against": 0,
        "shots_for": 0, "shots_against": 0, "possession": [], "remaining_stamina": [],
        "crowded_ratio": [], "team_width": [], "takeaways": 0, "turnovers": 0,
    })
    for row in rows:
        for side, other in (("home", "away"), ("away", "home")):
            team_id = str(row.get(f"{side}_id", ""))
            if not team_id:
                continue
            item = teams[team_id]
            item["team_id"] = team_id
            item["team_name"] = str(row.get(f"{side}_name", team_id))
            item["matches"] += 1
            goals_for = int(row.get(f"{side}_score", 0))
            goals_against = int(row.get(f"{other}_score", 0))
            item["goals_for"] += goals_for
            item["goals_against"] += goals_against
            item["shots_for"] += int(row.get(f"{side}_shots", 0))
            item["shots_against"] += int(row.get(f"{other}_shots", 0))
            if goals_for > goals_against:
                item["won"] += 1
            elif goals_for < goals_against:
                item["lost"] += 1
            else:
                item["drawn"] += 1
            possession_total = float(row.get("home_possession", 0.0)) + float(row.get("away_possession", 0.0))
            if possession_total > 0:
                item["possession"].append(float(row.get(f"{side}_possession", 0.0)) / possession_total)
            stamina = row.get(f"{side}_remaining_stamina")
            if stamina is not None:
                item["remaining_stamina"].append(float(stamina))
            telemetry = row.get(f"{side}_telemetry", {})
            if isinstance(telemetry, dict):
                item["crowded_ratio"].append(float(telemetry.get("crowded_player_ratio", 0.0)))
                item["team_width"].append(float(telemetry.get("average_team_width", 0.0)))
                item["takeaways"] += int(telemetry.get("takeaways", 0))
                item["turnovers"] += int(telemetry.get("turnovers", 0))
    output = []
    for item in teams.values():
        output.append({
            key: value for key, value in item.items()
            if key not in {"possession", "remaining_stamina", "crowded_ratio", "team_width"}
        } | {
            "goal_difference": item["goals_for"] - item["goals_against"],
            "average_possession_share": mean(item["possession"]) if item["possession"] else 0.0,
            "average_remaining_stamina": mean(item["remaining_stamina"]) if item["remaining_stamina"] else 0.0,
            "average_crowded_ratio": mean(item["crowded_ratio"]) if item["crowded_ratio"] else 0.0,
            "average_team_width": mean(item["team_width"]) if item["team_width"] else 0.0,
        })
    return sorted(output, key=lambda item: (-item["won"], -item["goal_difference"], item["team_name"]))


def _command_aggregate(rows: list[dict]) -> list[dict]:
    commands: dict[str, Counter[str]] = defaultdict(Counter)
    names: dict[str, str] = {}
    for row in rows:
        for side in ("home", "away"):
            team_id = str(row.get(f"{side}_id", ""))
            names[team_id] = str(row.get(f"{side}_name", team_id))
            telemetry = row.get(f"{side}_telemetry", {})
            if isinstance(telemetry, dict):
                commands[team_id].update(telemetry.get("command_counts", {}))
    return [
        {"team_id": team_id, "team_name": names.get(team_id, team_id), "command": command, "samples": count}
        for team_id, counts in commands.items()
        for command, count in counts.most_common()
    ]


def build_summary(rows: list[dict], season_rows: list[dict], *, status: str, elapsed_seconds: float) -> dict:
    runtimes = [float(row.get("wall_seconds", 0.0)) for row in rows]
    steps = [int(row.get("engine_steps", 0)) for row in rows]
    failures = [row for row in rows if row.get("evaluation_failed") or not row.get("fulltime", True)]
    return {
        "format_version": 1,
        "status": status,
        "elapsed_seconds": elapsed_seconds,
        "completed_matches": len(rows),
        "completed_seasons": len(season_rows),
        "failed_matches": len(failures),
        "average_match_wall_seconds": mean(runtimes) if runtimes else 0.0,
        "p95_match_wall_seconds": _percentile(runtimes, 0.95),
        "maximum_match_wall_seconds": max(runtimes, default=0.0),
        "average_engine_steps": mean(steps) if steps else 0.0,
        "teams": _team_aggregate(rows),
    }


def write_csv_reports(output_dir: Path, rows: list[dict]) -> None:
    team_rows = _team_aggregate(rows)
    command_rows = _command_aggregate(rows)
    performance_rows = [
        {
            "fixture_id": row.get("fixture_id", ""),
            "year": row.get("year", 0),
            "day": row.get("day", 0),
            "league": row.get("league", ""),
            "home_name": row.get("home_name", ""),
            "away_name": row.get("away_name", ""),
            "wall_seconds": row.get("wall_seconds", 0.0),
            "engine_steps": row.get("engine_steps", 0),
            "fulltime": row.get("fulltime", False),
            "evaluation_failed": row.get("evaluation_failed", False),
        }
        for row in rows
    ]
    for name, records in (("team_summary.csv", team_rows), ("commands.csv", command_rows), ("performance.csv", performance_rows)):
        path = output_dir / name
        if not records:
            path.write_text("", encoding="utf-8-sig")
            continue
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)


__all__ = (
    "append_jsonl",
    "build_summary",
    "read_jsonl",
    "write_csv_reports",
    "write_json_atomic",
)
