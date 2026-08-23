"""Migrate editable team ability values while preserving normalized strength."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.core.paths import PROJECT_ROOT
from scripts.core.stat_scale import (
    PLAYER_STAT_MAX,
    PLAYER_STAT_MIN,
    current_scale_metadata,
    payload_stat_bounds,
    remap_player_stat,
)
from scripts.team.team_data import PLAYER_STAT_CANONICAL_KEYS
from scripts.team.team_editor_data import STAT_FIELDS


MANAGER_STAT_FIELDS = ("戦術変更への積極性", "選手交代への積極性", "インテリジェンス")


def _mapped_text(value: object, source_min: float, source_max: float) -> str:
    return str(round(remap_player_stat(value, source_min, source_max)))


def migrate_payload(payload: dict) -> tuple[dict, bool]:
    source_min, source_max = payload_stat_bounds(payload)
    already_current = source_min == PLAYER_STAT_MIN and source_max == PLAYER_STAT_MAX
    changed = not already_current

    if not already_current:
        for player in payload.get("選手一覧", []):
            if not isinstance(player, dict):
                continue
            for field in (*STAT_FIELDS, *PLAYER_STAT_CANONICAL_KEYS):
                if field in player:
                    player[field] = _mapped_text(player[field], source_min, source_max)

        team_info = payload.get("チーム情報", {})
        if isinstance(team_info, dict):
            for field in MANAGER_STAT_FIELDS:
                if field in team_info:
                    team_info[field] = _mapped_text(team_info[field], source_min, source_max)

        tuner = payload.get("チームチューナー", {})
        targets = tuner.get("基準値ステータス", {}) if isinstance(tuner, dict) else {}
        if isinstance(targets, dict):
            for field, value in tuple(targets.items()):
                targets[field] = _mapped_text(value, source_min, source_max)

    metadata = current_scale_metadata()
    if payload.get("能力値スケール") != metadata:
        payload["能力値スケール"] = metadata
        changed = True
    return payload, changed


def migrate_directory(root: Path, *, dry_run: bool = False) -> tuple[int, int]:
    examined = 0
    changed_count = 0
    for path in sorted(root.rglob("*.json"), key=lambda item: item.as_posix().casefold()):
        examined += 1
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            continue
        payload, changed = migrate_payload(payload)
        if not changed:
            continue
        changed_count += 1
        if not dry_run:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return examined, changed_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="チームJSONの能力値スケールを現在設定へ変換します")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "teams", help="変換対象フォルダ")
    parser.add_argument("--dry-run", action="store_true", help="ファイルを書き換えず対象数だけ確認")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    examined, changed = migrate_directory(args.root.resolve(), dry_run=args.dry_run)
    mode = "確認" if args.dry_run else "変換"
    print(f"{mode}完了: {examined}ファイル中 {changed}ファイル")


if __name__ == "__main__":
    main()
