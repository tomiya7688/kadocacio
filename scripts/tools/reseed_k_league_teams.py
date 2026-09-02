"""Rearrange generated K-league team files from an evaluation checkpoint."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from scripts.core.paths import PROJECT_ROOT, TEAMS_DIR


DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "league_templates" / "K1-K9.json"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "development_reseed_backup"
K_LEAGUE_PATTERN = re.compile(r"^K([1-9][0-9]{0,2})リーグ$")
JSON_TEAM_PREFIX = "json:"


def load_json_object(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSONのルートがオブジェクトではありません: {path}")
    return payload


def league_entries(payload: dict) -> list[dict]:
    entries = payload.get("リーグ一覧", [])
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def checkpoint_competition_template(checkpoint: dict) -> dict:
    manager_state = checkpoint.get("manager_state")
    if not isinstance(manager_state, dict):
        raise ValueError("評価チェックポイントにmanager_stateがありません")
    template = manager_state.get("competition_template")
    if not isinstance(template, dict):
        raise ValueError("評価チェックポイントにcompetition_templateがありません")
    if int(checkpoint.get("seasons_completed", 0)) < 1:
        raise ValueError("少なくとも1年度を完走した評価チェックポイントが必要です")
    return template


def k_league_memberships(payload: dict) -> dict[str, list[str]]:
    memberships: dict[str, list[str]] = {}
    for entry in league_entries(payload):
        name = str(entry.get("リーグ名", ""))
        if K_LEAGUE_PATTERN.fullmatch(name) is None:
            continue
        raw_teams = entry.get("所属チーム", [])
        if not isinstance(raw_teams, list):
            raise ValueError(f"{name}の所属チームが配列ではありません")
        memberships[name] = [str(team_id) for team_id in raw_teams]
    if not memberships:
        raise ValueError("K1～K999リーグの所属情報が見つかりません")
    return memberships


def membership_team_ids(memberships: dict[str, list[str]]) -> set[str]:
    all_ids = [team_id for team_ids in memberships.values() for team_id in team_ids]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("同じチームが複数のKリーグに所属しています")
    return set(all_ids)


def team_path_from_id(team_id: str, teams_root: Path) -> Path:
    if not team_id.startswith(JSON_TEAM_PREFIX):
        raise ValueError(f"JSONチーム以外は再配置できません: {team_id}")
    relative = Path(team_id[len(JSON_TEAM_PREFIX):])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"不正なチームパスです: {team_id}")
    return teams_root / relative


def build_reseed_plan(checkpoint: dict, template: dict, *, teams_root: Path = TEAMS_DIR) -> list[dict]:
    evaluated = k_league_memberships(checkpoint_competition_template(checkpoint))
    configured = k_league_memberships(template)
    evaluated_ids = membership_team_ids(evaluated)
    configured_ids = membership_team_ids(configured)
    if evaluated_ids != configured_ids:
        missing = sorted(configured_ids - evaluated_ids)
        unknown = sorted(evaluated_ids - configured_ids)
        raise ValueError(
            "評価対象とリーグテンプレートのチーム集合が一致しません"
            f"（評価に不足{len(missing)}件 / 未登録{len(unknown)}件）"
        )

    plan: list[dict] = []
    destinations: set[Path] = set()
    for league_name in sorted(evaluated, key=lambda name: int(K_LEAGUE_PATTERN.fullmatch(name).group(1))):
        league_number = int(K_LEAGUE_PATTERN.fullmatch(league_name).group(1))
        for team_id in evaluated[league_name]:
            source = team_path_from_id(team_id, teams_root)
            destination = teams_root / f"KadokaOriginalK{league_number}" / source.name
            if destination in destinations:
                raise ValueError(f"再配置先が重複しています: {destination}")
            destinations.add(destination)
            plan.append({
                "team_id": team_id,
                "team_name": source.stem,
                "league_name": league_name,
                "source": source,
                "destination": destination,
                "new_team_id": f"json:KadokaOriginalK{league_number}/{source.name}",
                "move_required": source != destination,
            })
    return plan


def validate_reseed_files(plan: list[dict]) -> None:
    for entry in plan:
        source = entry["source"]
        destination = entry["destination"]
        if not source.is_file():
            raise FileNotFoundError(f"チームファイルが見つかりません: {source}")
        if destination.exists() and destination != source:
            raise FileExistsError(f"再配置先に別ファイルがあります: {destination}")


def updated_template(template: dict, plan: list[dict]) -> dict:
    replacements = {entry["team_id"]: entry["new_team_id"] for entry in plan}
    desired = {}
    for entry in plan:
        desired.setdefault(entry["league_name"], []).append(entry["new_team_id"])
    result = json.loads(json.dumps(template, ensure_ascii=False))
    for league in league_entries(result):
        name = str(league.get("リーグ名", ""))
        if name in desired:
            league["所属チーム"] = desired[name]
        elif K_LEAGUE_PATTERN.fullmatch(name):
            league["所属チーム"] = [
                replacements.get(str(team_id), str(team_id))
                for team_id in league.get("所属チーム", [])
            ]
    return result


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def backup_reseed_sources(plan: list[dict], backup_directory: Path, teams_root: Path) -> None:
    for entry in plan:
        source = entry["source"]
        relative = source.relative_to(teams_root)
        backup_path = backup_directory / "teams" / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup_path)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "moves": [
            {
                "team_name": entry["team_name"],
                "from": str(entry["source"].relative_to(teams_root).as_posix()),
                "to": str(entry["destination"].relative_to(teams_root).as_posix()),
            }
            for entry in plan if entry["move_required"]
        ],
    }
    write_json_atomic(backup_directory / "manifest.json", manifest)


def apply_reseed_plan(
    plan: list[dict],
    template: dict,
    *,
    template_path: Path,
    teams_root: Path = TEAMS_DIR,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
) -> Path:
    validate_reseed_files(plan)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_directory = backup_root / f"k_reseed_{stamp}"
    backup_reseed_sources(plan, backup_directory, teams_root)
    template_backup = backup_directory / "league_template.json"
    if template_path.exists():
        shutil.copy2(template_path, template_backup)

    created_destinations: list[Path] = []
    try:
        for entry in plan:
            if not entry["move_required"]:
                continue
            destination = entry["destination"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry["source"], destination)
            created_destinations.append(destination)
        write_json_atomic(template_path, updated_template(template, plan))
        for entry in plan:
            if entry["move_required"]:
                entry["source"].unlink()
    except Exception:
        for destination in created_destinations:
            if destination.exists():
                destination.unlink()
        for entry in plan:
            backup = backup_directory / "teams" / entry["source"].relative_to(teams_root)
            if backup.exists() and not entry["source"].exists():
                entry["source"].parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, entry["source"])
        if template_backup.exists():
            shutil.copy2(template_backup, template_path)
        raise
    return backup_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="実試合評価後の所属に合わせてKリーグチームを再配置します")
    parser.add_argument("checkpoint", type=Path, help="development_evaluation内のcheckpoint.json")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--teams-root", type=Path, default=TEAMS_DIR)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--apply", action="store_true", help="省略時は移動計画だけを表示します")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checkpoint = load_json_object(args.checkpoint)
    template = load_json_object(args.template)
    plan = build_reseed_plan(checkpoint, template, teams_root=args.teams_root)
    validate_reseed_files(plan)
    moves = [entry for entry in plan if entry["move_required"]]
    print(f"評価所属を確認: {len(plan)}チーム / フォルダ移動 {len(moves)}チーム")
    for entry in moves:
        print(f"{entry['team_name']}: {entry['source'].parent.name} -> {entry['destination'].parent.name}")
    if not args.apply:
        print("プレビューのみです。適用する場合は --apply を指定してください。")
        return 0
    backup = apply_reseed_plan(
        plan,
        template,
        template_path=args.template,
        teams_root=args.teams_root,
        backup_root=args.backup_root,
    )
    print(f"再配置完了。復旧用バックアップ: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
