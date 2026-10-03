"""Build ignored Python-reference fixtures for Godot team-data parity tests."""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from scripts.core.paths import PROJECT_ROOT, USER_LOG_DIR
from scripts.core.settings import grid_role, player_stat
from scripts.core.stat_scale import current_scale_metadata, denormalize_player_stat
from scripts.match.player_style_system import normalize_player_type, type_preference
from scripts.match.skill_system import normalized_skills
from scripts.team.team_data import percentage_value, team_choice_from_payload
from scripts.team.team_identity import legacy_team_id, normalize_team_id, team_id_aliases
from scripts.tools.godot_team_contract import build_contract, check_contract


def public_team_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "teams"], cwd=PROJECT_ROOT,
        capture_output=True, check=True, encoding="utf-8",
    )
    return sorted(
        PROJECT_ROOT / name for name in result.stdout.split("\0")
        if name.endswith(".json") and "カルチョビット" not in Path(name).parts
    )


def reference_case(payload: object, source: str) -> dict:
    result = {"source": source, "payload": deepcopy(payload)}
    try:
        choice = team_choice_from_payload(deepcopy(payload), source)
        team_id = normalize_team_id(payload.get("チームID", "")) or legacy_team_id(source)
        aliases = team_id_aliases(payload)
        path_id = legacy_team_id(source)
        if path_id != team_id and path_id not in aliases:
            aliases.append(path_id)
        choice.update(id=team_id, legacy_ids=aliases)
    except (ValueError, TypeError, AttributeError):
        return {**result, "valid": False}
    contract = build_contract()
    parameters = []
    for record in choice["starters"] + choice["bench"]:
        raw = record["raw"]
        player_type = normalize_player_type(raw.get("PlayerType"), grid_role(record["position_y"]))
        style_defaults = {
            field: denormalize_player_stat(type_preference(player_type, behavior))
            for behavior, field in contract["style_fields"].items()
        }
        stats = {
            key: player_stat(raw, key, default=style_defaults.get(key, contract["scale"]["player_default"]), legacy_key=contract["stat_fallbacks"][key])
            for key in contract["stat_keys"]
        }
        parameters.append({
            "stats": stats, "player_type": player_type,
            "skills": sorted(normalized_skills(raw.get("Skills"))),
            "tactical_discipline": percentage_value(raw.get("TacticalDiscipline"), choice["tactical_discipline"] * 100.0),
        })
    return {**result, "valid": True, "choice": choice, "parameters": parameters}


def synthetic_cases(seed: dict) -> list[dict]:
    contract = build_contract()
    base = {
        "能力値スケール": current_scale_metadata(),
        "チーム情報": {"チーム名": "互換テスト", "戦術への忠実さ": 30},
        "選手一覧": [{"Name": f"選手{index}", "PositionX": index + 1, "PositionY": 11 if index == 0 else 8} for index in range(11)],
    }
    cases = [reference_case(base, "synthetic/defaults.json")]
    for bounds in (None, current_scale_metadata(), {"最小": -25.125, "最大": 1500.625}, {"最小": "bad", "最大": 100}, {"最小": 2, "最大": 2}, {}):
        for value in (0, 50, 100, 200, 500, 650, 1250, 5500, -10, 6000, "bad", None, True, "nan"):
            payload = deepcopy(base)
            if bounds is None:
                payload.pop("能力値スケール")
            else:
                payload["能力値スケール"] = bounds
            raw = payload["選手一覧"][1]
            for key in contract["stat_keys"]:
                raw[key] = value
            payload["チーム情報"].update({"戦術変更への積極性": value, "インテリジェンス": value})
            cases.append(reference_case(payload, f"synthetic/scale-{len(cases)}.json"))
    payload = deepcopy(seed)
    payload["チーム情報"].update({"チーム紹介": "長文\n🙂" * 3000, "チーム説明": "not selected", "戦術への忠実さ": 80, "ユニフォーム": {"ユニフォーム": {"パーツ": {"胸": [["p", "s", "#abcdef", "bad", None]]}}}})
    raw = payload["選手一覧"][0]
    raw.update({"Name": "English ignored", "名前": "日本語優先", "ダッシュ速度": 2000, "ダッシュ時のスピード": 4000, "スキル": list(contract["skill_aliases"]) + list(contract["skills"]) + ["unknown"], "プレイヤータイプ": "プレイメーカー", "戦術への忠実さ": 30, "拡張": {"保管": [None, False, "🙂"]}})
    payload["カスタム情報"] = {"never_drop": "保持"}
    cases.append(reference_case(payload, "synthetic/japanese-precedence.json"))
    for starters, keepers in ((7, 1), (7, 2), (7, 7), (11, 1), (6, 1), (12, 1), (7, 0)):
        payload = deepcopy(base)
        payload["選手一覧"] = [{"PositionX": 0 if i < keepers else (i % 15 + 1), "PositionY": 11 if i < keepers else 8} for i in range(starters)] + [{"PositionY": 0, "PositionX": 0}]
        cases.append(reference_case(payload, f"synthetic/formation-{starters}-{keepers}.json"))
    for key, value in (("選手一覧", {}), ("選手一覧", [None]), ("チーム情報", None), ("チームID", "bad")):
        payload = deepcopy(base)
        payload[key] = value
        cases.append(reference_case(payload, f"synthetic/invalid-{len(cases)}.json"))
    for key, value in (("戦術", "unknown"), ("ゾーン手前", "1.0"), ("ゾーン手前", 10), ("ゾーン奥", 11)):
        payload = deepcopy(base)
        payload["チーム情報"][key] = value
        cases.append(reference_case(payload, f"synthetic/invalid-{len(cases)}.json"))
    for key, value in (("PositionX", 16), ("PositionY", 12), ("PositionY", "1.0"), ("JerseyNumber", "1.0")):
        payload = deepcopy(base)
        payload["選手一覧"][1][key] = value
        cases.append(reference_case(payload, f"synthetic/invalid-{len(cases)}.json"))
    for root_value in ([], None):
        cases.append(reference_case(root_value, "synthetic/root.json"))
    return cases


def file_fingerprints(paths: list[Path]) -> dict[str, str]:
    return {str(path): sha256(path.read_bytes()).hexdigest() for path in paths}


def write_oracle() -> tuple[Path, dict[str, str]]:
    if not check_contract():
        raise ValueError("Godot contract is stale; regenerate explicitly with godot_team_contract --write")
    paths = public_team_paths()
    if not paths:
        raise ValueError("No tracked public teams available for Godot parity")
    before = file_fingerprints(paths)
    cases = []
    files = []
    for path in paths:
        source = path.relative_to(PROJECT_ROOT / "teams").as_posix()
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        case = reference_case(payload, source)
        cases.append(case)
        files.append({"path": str(path), "root": str(PROJECT_ROOT / "teams"), "source": source})
    seed = next((case["payload"] for case in cases if case["valid"]), None)
    if seed is None:
        raise ValueError("No valid tracked public team available for Godot parity")
    cases.extend(synthetic_cases(seed))
    output = USER_LOG_DIR / "godot" / "team_parity"
    output.mkdir(parents=True, exist_ok=True)
    fixture_root = output / "teams"
    (fixture_root / "nested").mkdir(parents=True, exist_ok=True)
    fixture_payload = deepcopy(seed)
    fixture_payload["チームID"] = "team:fixture"
    fixture_payload["チームID別名"] = ["json:old.json", "json:old.json", None]
    (fixture_root / "nested" / "good.json").write_text("\ufeff" + json.dumps(fixture_payload, ensure_ascii=False), encoding="utf-8")
    (fixture_root / "invalid.json").write_text('{"選手一覧": [}', encoding="utf-8")
    (fixture_root / "duplicate.json").write_text(json.dumps(fixture_payload, ensure_ascii=False), encoding="utf-8")
    path = output / "oracle.json"
    path.write_text(json.dumps({"cases": cases, "files": files, "catalog_root": str(fixture_root)}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path, before


def assert_sources_unchanged(before: dict[str, str]) -> None:
    after = file_fingerprints([Path(path) for path in before])
    if before != after:
        raise ValueError("Godot parity test modified a source team file")
