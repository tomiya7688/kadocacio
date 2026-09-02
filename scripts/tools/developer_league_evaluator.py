"""CLI entry point for unattended full-league evaluation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from scripts.core.paths import DEVELOPMENT_EVALUATION_DIR
from scripts.core.performance_settings import (
    LEAGUE_SIMULATION_MODES,
    load_performance_settings,
    normalize_cpu_limit,
    normalize_league_simulation_mode,
)
from scripts.league.league_manager import LeagueManager
from scripts.tools.league_evaluation_runner import LeagueEvaluationRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="実際のMatchエンジンでリーグを放置運転し、AI・順位・性能ログを保存します",
    )
    parser.add_argument("--template", default=None, help="リーグテンプレートID。省略時はdefault")
    parser.add_argument("--leagues", default=None, help="対象リーグ名のカンマ区切り。allで全リーグ")
    parser.add_argument("--hours", type=float, default=None, help="今回の実時間上限。0で無制限（新規既定8時間）")
    parser.add_argument("--seasons", type=int, default=None, help="完走年度数。0で時間上限まで継続")
    parser.add_argument(
        "--quality", default=None, choices=tuple(LEAGUE_SIMULATION_MODES),
        help="ULTRA_PRECISE / PRECISE / NORMAL / LIGHT",
    )
    parser.add_argument("--cpu-limit", type=int, default=None, help="CPU演算枠の上限（10～100）")
    parser.add_argument("--processes", default=None, help="同時ワーカー数またはauto")
    parser.add_argument("--max-processes", type=int, default=None, help="auto時を含む同時ワーカー安全上限")
    parser.add_argument("--sample-every-steps", type=int, default=None, help="AI統計のサンプル間隔。既定18固定ステップ")
    parser.add_argument("--max-matchdays", type=int, default=None, help="開発用の試合日上限。0で無制限")
    parser.add_argument("--stop-on-error", action=argparse.BooleanOptionalAction, default=None, help="1試合の失敗で全評価を止める")
    parser.add_argument("--output-name", default=None, help="新規ログフォルダ名")
    parser.add_argument("--resume", type=Path, default=None, help="checkpoint.jsonまたはその親フォルダから再開")
    parser.add_argument("--list-templates", action="store_true", help="テンプレート一覧を表示して終了")
    return parser


def _new_config(args: argparse.Namespace) -> dict:
    settings = load_performance_settings()
    template_id = args.template or "default"
    known_template_ids = {str(entry["id"]) for entry in LeagueManager.template_entries()}
    if template_id not in known_template_ids:
        raise ValueError(f"リーグテンプレートが見つかりません: {template_id}")
    return {
        "template_id": template_id,
        "leagues": [part.strip() for part in (args.leagues or "all").split(",") if part.strip()],
        "hours": 8.0 if args.hours is None else max(0.0, args.hours),
        "seasons": 0 if args.seasons is None else max(0, args.seasons),
        "quality": normalize_league_simulation_mode(args.quality or settings.league_simulation_mode),
        "cpu_limit": normalize_cpu_limit(args.cpu_limit if args.cpu_limit is not None else settings.cpu_limit_percent),
        "processes": args.processes or "auto",
        "max_processes": max(1, args.max_processes or 8),
        "sample_every_steps": max(1, args.sample_every_steps or 18),
        "max_matchdays": max(0, args.max_matchdays or 0),
        "stop_on_error": bool(args.stop_on_error) if args.stop_on_error is not None else False,
    }


def _resume_payload(path: Path) -> tuple[Path, dict]:
    checkpoint_path = path if path.name.casefold() == "checkpoint.json" else path / "checkpoint.json"
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not isinstance(payload.get("config"), dict):
        raise ValueError("有効な評価チェックポイントではありません")
    return checkpoint_path.parent, payload


def _resume_config(saved: dict, args: argparse.Namespace) -> dict:
    config = dict(saved)
    if args.hours is not None:
        config["hours"] = max(0.0, args.hours)
    if args.seasons is not None:
        config["seasons"] = max(0, args.seasons)
    if args.quality is not None:
        config["quality"] = normalize_league_simulation_mode(args.quality)
    if args.cpu_limit is not None:
        config["cpu_limit"] = normalize_cpu_limit(args.cpu_limit)
    if args.processes is not None:
        config["processes"] = args.processes
    if args.max_processes is not None:
        config["max_processes"] = max(1, args.max_processes)
    if args.sample_every_steps is not None:
        config["sample_every_steps"] = max(1, args.sample_every_steps)
    if args.max_matchdays is not None:
        config["max_matchdays"] = max(0, args.max_matchdays)
    if args.stop_on_error is not None:
        config["stop_on_error"] = bool(args.stop_on_error)
    return config


def _new_output_dir(name: str | None) -> Path:
    stem = (name or datetime.now().strftime("league_eval_%Y%m%d_%H%M%S")).strip()
    safe = "".join("_" if character in '<>:"/\\|?*' else character for character in stem).strip(" .")
    output = DEVELOPMENT_EVALUATION_DIR / (safe or datetime.now().strftime("league_eval_%Y%m%d_%H%M%S"))
    suffix = 2
    candidate = output
    while candidate.exists():
        candidate = output.with_name(f"{output.name}_{suffix}")
        suffix += 1
    return candidate


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_templates:
        for entry in LeagueManager.template_entries():
            print(f"{entry['id']}\t{entry['name']}")
        return 0
    if args.resume is not None:
        output_dir, checkpoint = _resume_payload(args.resume)
        config = _resume_config(checkpoint["config"], args)
    else:
        output_dir = _new_output_dir(args.output_name)
        checkpoint = None
        config = _new_config(args)
    print(f"評価ログ: {output_dir}", flush=True)
    print(
        f"設定: template={config['template_id']} leagues={','.join(config['leagues'])} "
        f"hours={config['hours']} seasons={config['seasons']} quality={config['quality']} "
        f"cpu={config['cpu_limit']}% processes={config['processes']}",
        flush=True,
    )
    runner = LeagueEvaluationRunner(config, output_dir, checkpoint=checkpoint)
    summary = runner.run()
    print(
        f"終了: {summary['status']} / {summary['completed_matches']}試合 / "
        f"{summary['completed_seasons']}年度 / 失敗{summary['failed_matches']}試合",
        flush=True,
    )
    print(f"集計: {runner.summary_path}", flush=True)
    return 1 if summary["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
