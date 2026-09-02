"""Plan and generate editable K1-K9 development league clubs."""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

from scripts.core.paths import PROJECT_ROOT, TEAMS_DIR, TEMPLATE_DIR
from scripts.core.stat_scale import (
    clamp_player_stat,
    current_to_legacy_player_stat,
)
from scripts.team.team_editor_data import STAT_FIELDS, validate_payload
from scripts.team.team_template_profile import generation_field_targets, profile_label
from scripts.tools.generate_original_league_teams import make_team


DEFAULT_CONFIG_PATH = TEMPLATE_DIR / "k_league_generation.json"
EDITOR_OPTIONS_PATH = TEMPLATE_DIR / "editor_options.json"
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "league_templates" / "K1-K9.json"


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_generation_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Kリーグ生成設定のルートはオブジェクトである必要があります")
    return payload


def configured_names(config: dict, names_path: Path | None = None) -> list[str]:
    if names_path is not None:
        payload = load_json(names_path)
        values = payload.get("チーム名", payload.get("names", [])) if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise ValueError("名前ファイルは配列、またはチーム名配列を持つJSONにしてください")
        return [str(value).strip() for value in values if str(value).strip()]
    regions = [str(value).strip() for value in config.get("地域名", []) if str(value).strip()]
    nicknames = [str(value).strip() for value in config.get("愛称", []) if str(value).strip()]
    return [f"{region}{nickname}" for region in regions for nickname in nicknames]


def source_team_paths(config: dict, league_number: int, teams_root: Path = TEAMS_DIR) -> list[Path]:
    folder = str(config.get("既存チーム参照", {}).get(str(league_number), "")).strip()
    if not folder:
        return []
    source = teams_root / folder
    return sorted(source.glob("*.json"), key=lambda path: path.name.casefold()) if source.is_dir() else []


def build_generation_plan(
    config: dict,
    *,
    league_count: int | None = None,
    teams_per_league: int | None = None,
    teams_root: Path = TEAMS_DIR,
    names_path: Path | None = None,
) -> list[dict]:
    league_total = max(1, min(999, int(league_count or config.get("リーグ数", 9))))
    team_total = max(2, int(teams_per_league or config.get("1リーグのチーム数", 20)))
    folder_prefix = str(config.get("フォルダ接頭辞", "KadokaOriginalK"))
    league_prefix = str(config.get("リーグ名接頭辞", "K"))
    targets = [int(value) for value in config.get("基準能力値", [])]
    colors = [str(value) for value in config.get("リーグ表示色", [])]
    tendencies = [str(value) for value in config.get("チーム傾向", ["balanced"])] or ["balanced"]
    names = configured_names(config, names_path)
    used_names: set[str] = set()
    generated_name_index = 0
    plan: list[dict] = []

    for league_index in range(league_total):
        league_number = league_index + 1
        target = targets[min(league_index, len(targets) - 1)] if targets else round(2750 - league_index * 250)
        league_name = f"{league_prefix}{league_number}リーグ"
        folder_name = f"{folder_prefix}{league_number}"
        sources = source_team_paths(config, league_number, teams_root)
        for team_index in range(team_total):
            source_path = sources[team_index] if team_index < len(sources) else None
            if source_path is not None:
                team_name = source_path.stem
                used_names.add(team_name)
            else:
                while generated_name_index < len(names) and names[generated_name_index] in used_names:
                    generated_name_index += 1
                if generated_name_index >= len(names):
                    raise ValueError("設定された名前候補では生成チーム数を満たせません")
                team_name = names[generated_name_index]
                generated_name_index += 1
                used_names.add(team_name)
            plan.append({
                "league_number": league_number,
                "league_name": league_name,
                "league_color": colors[league_index % len(colors)] if colors else "#718096",
                "upper_league": f"{league_prefix}{league_number - 1}リーグ" if league_number > 1 else "",
                "folder_name": folder_name,
                "team_index": team_index,
                "team_name": team_name,
                "target": round(clamp_player_stat(target)),
                "tendency": tendencies[(league_index * team_total + team_index) % len(tendencies)],
                "source_path": source_path,
            })
    return plan


def team_mean(payload: dict) -> float:
    values = [float(player[field]) for player in payload["選手一覧"] for field in STAT_FIELDS]
    return sum(values) / max(1, len(values))


def apply_team_tendency(payload: dict, target: int, tendency: str, editor_options: dict) -> None:
    profile_id = "balanced" if tendency == "ace" else tendency
    field_targets = generation_field_targets(target, profile_id, editor_options, STAT_FIELDS)
    for player in payload["選手一覧"]:
        for field in STAT_FIELDS:
            shifted = float(player[field]) + field_targets[field] - target
            player[field] = str(round(clamp_player_stat(shifted)))
    if tendency == "ace" and len(payload["選手一覧"]) > 1:
        players = payload["選手一覧"]
        ace = next((player for player in players if player.get("ポジション") == "FW"), players[0])
        compensation = 650.0 / (len(players) - 1)
        for field in STAT_FIELDS:
            ace[field] = str(round(clamp_player_stat(float(ace[field]) + 650)))
            for player in players:
                if player is not ace:
                    player[field] = str(round(clamp_player_stat(float(player[field]) - compensation)))


def make_generated_payload(entry: dict, editor_options: dict, *, seed: int) -> dict:
    current_target = int(entry["target"])
    legacy_target = round(current_to_legacy_player_stat(current_target))
    division = "A" if current_target >= 2400 else "B"
    color_rng = random.Random(seed + int(entry["league_number"]) * 1009 + int(entry["team_index"]) * 37)
    color = "#{:02X}{:02X}{:02X}".format(
        color_rng.randint(48, 210), color_rng.randint(48, 210), color_rng.randint(48, 210)
    )
    short_name = str(entry["team_name"])[:4]
    payload = make_team(
        division,
        int(entry["league_number"]) * 100 + int(entry["team_index"]),
        (str(entry["team_name"]), short_name, legacy_target, color),
    )
    apply_team_tendency(payload, current_target, str(entry["tendency"]), editor_options)
    players = payload["選手一覧"]
    for player_index, player in enumerate(players, start=1):
        player["選手ID"] = (
            f"K{int(entry['league_number']):03d}T{int(entry['team_index']) + 1:03d}P{player_index:02d}"
        )
    info = payload["チーム情報"]
    tendency_label = "エース型" if entry["tendency"] == "ace" else profile_label(
        editor_options, str(entry["tendency"])
    )
    info["チーム紹介"] = (
        f"{entry['team_name']}は{entry['league_name']}向けに生成された{tendency_label}のクラブです。"
        f"チーム平均{current_target}を目安にしつつ、選手の役割と個性が出る能力配分を持ちます。"
    )
    tuner = payload.get("チームチューナー", {}).get("基準値ステータス", {})
    for category in tuple(tuner):
        tuner[category] = str(current_target)
    issues = validate_payload(payload)
    if issues:
        messages = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        raise ValueError(f"{entry['team_name']}: {messages}")
    return payload


def league_template_payload(plan: list[dict]) -> dict:
    leagues = []
    for league_number in sorted({int(entry["league_number"]) for entry in plan}):
        entries = [entry for entry in plan if int(entry["league_number"]) == league_number]
        first = entries[0]
        leagues.append({
            "リーグ名": first["league_name"],
            "表示色": first["league_color"],
            "開幕日": 14,
            "最終節日": 330,
            "上位リーグ": first["upper_league"],
            "所属チーム": [
                f"json:{entry['folder_name']}/{entry['team_name']}.json" for entry in entries
            ],
        })
    return {"リーグ一覧": leagues, "トーナメント一覧": []}


def write_generation(
    plan: list[dict],
    *,
    output_root: Path,
    template_path: Path,
    editor_options: dict,
    seed: int,
    overwrite: bool,
) -> None:
    for entry in plan:
        destination = output_root / str(entry["folder_name"]) / f"{entry['team_name']}.json"
        if destination.exists() and not overwrite:
            raise FileExistsError(f"既存ファイルを保護しました: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_path = entry.get("source_path")
        if isinstance(source_path, Path):
            shutil.copy2(source_path, destination)
        else:
            payload = make_generated_payload(entry, editor_options, seed=seed)
            destination.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        json.dumps(league_template_payload(plan), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="K1～K9用の開発チームとリーグテンプレートを生成します")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--names-file", type=Path, help="Ollama等で作ったチーム名JSONを使用します")
    parser.add_argument("--leagues", type=int, help="生成リーグ数（1～999）")
    parser.add_argument("--teams", type=int, help="1リーグのチーム数")
    parser.add_argument("--seed", type=int, default=20260901)
    parser.add_argument("--output-root", type=Path, default=TEAMS_DIR)
    parser.add_argument("--template-path", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--write", action="store_true", help="省略時は生成計画だけを表示します")
    parser.add_argument("--overwrite", action="store_true", help="生成先の同名ファイルを上書きします")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_generation_config(args.config)
    plan = build_generation_plan(
        config,
        league_count=args.leagues,
        teams_per_league=args.teams,
        names_path=args.names_file,
    )
    counts = {
        league: len([entry for entry in plan if entry["league_name"] == league])
        for league in dict.fromkeys(entry["league_name"] for entry in plan)
    }
    print(f"生成計画: {len(counts)}リーグ / {len(plan)}チーム")
    print(" / ".join(f"{league} {amount}" for league, amount in counts.items()))
    if not args.write:
        print("プレビューのみです。書き出す場合は --write を指定してください。")
        return 0
    editor_options = load_json(EDITOR_OPTIONS_PATH)
    if not isinstance(editor_options, dict):
        raise ValueError("editor_options.jsonが不正です")
    write_generation(
        plan,
        output_root=args.output_root,
        template_path=args.template_path,
        editor_options=editor_options,
        seed=args.seed,
        overwrite=args.overwrite,
    )
    print(f"保存完了: {args.output_root} / {args.template_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
