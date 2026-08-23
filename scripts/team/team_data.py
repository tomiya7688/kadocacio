from __future__ import annotations

import json
from pathlib import Path

from scripts.match.manager_system import manager_stat
from scripts.core.settings import HOME_RED, TACTIC_NAMES, TEAMS_DIR, clamp, grid_role, grid_slot, parse_hex_color
from scripts.core.stat_scale import (
    MANAGER_ACTIVITY_DEFAULT,
    MANAGER_INTELLIGENCE_DEFAULT,
    PLAYER_STAT_MAX,
    PLAYER_STAT_MIN,
    payload_stat_bounds,
    remap_player_stat,
)


PLAYER_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "ID": ("選手ID",),
    "Name": ("名前", "選手名"),
    "Position": ("ポジション",),
    "JerseyNumber": ("背番号",),
    "ShotPower": ("シュート力",),
    "ShotAccuracy": ("シュート精度",),
    "PassAccuracy": ("パス精度",),
    "PassPower": ("パス力",),
    "DashSpeed": ("ダッシュ時のスピード", "ダッシュ速度"),
    "WalkSpeed": ("ウォーク時のスピード", "ウォーク速度"),
    "DribbleSpeed": ("ドリブル時のスピード", "ドリブル速度"),
    "KickMotionSpeed": ("キックモーションのスピード", "キックモーション速度"),
    "MaxStamina": ("スタミナ最大値",),
    "StaminaRecovery": ("スタミナ回復速度",),
    "StaminaManagement": ("スタミナ管理",),
    "FatigueResistance": ("疲労耐性",),
    "MistakeAvoidance": ("ミスの少なさ",),
    "DribbleTechnique": ("ドリブルの上手さ",),
    "TrapTechnique": ("トラップの上手さ",),
    "PassInterception": ("パスカットの上手さ",),
    "GoalStopping": ("ゴールストップ力",),
    "ShootingTechnique": ("シュートの上手さ",),
    "PassingTechnique": ("パスの上手さ",),
    "StealTechnique": ("スティールの上手さ",),
    "CollisionPhysical": ("衝突時のフィジカル",),
    "DribblePhysical": ("ドリブル時のフィジカル",),
    "PhysicalPlayQuality": ("フィジカルプレイの質",),
    "JumpHeight": ("ジャンプの高さ",),
    "JumpAccuracy": ("ジャンプの正確さ",),
    "JumpSpeed": ("ジャンプの速さ",),
    "JumpJudgment": ("ジャンプの判断力",),
    "HeadingPower": ("ヘディングの強さ",),
    "HeadingAccuracy": ("ヘディングの正確さ",),
    "HeadingJudgment": ("ヘディングの判断力",),
    "Mental": ("メンタル",),
    "Intelligence": ("インテリジェンス",),
    "Skills": ("スキル",),
    "SafePlay": ("安全なプレー",),
    "FreeKickSkill": ("フリーキック",),
    "PenaltyKickSkill": ("ペナルティキック",),
    "GoalKickSkill": ("ゴールキック",),
    "ThrowInSkill": ("スローイン",),
    "CornerKickSkill": ("コーナーキック",),
    "PlayerType": ("プレイヤータイプ",),
    "PositionX": ("ポジションX",),
    "PositionY": ("ポジションY",),
    "gender": ("性別",),
    "age": ("年齢",),
    "ZoneMarking": ("ゾーンマーキング",),
    "ManMarking": ("マンツーマン",),
    "Pressing": ("プレッシング",),
    "ShotBlocking": ("シュートカット",),
    "Interception": ("インターセプト",),
    "Support": ("サポート",),
    "Triangle": ("トライアングル",),
    "LoseMark": ("マークを外す",),
    "Overlap": ("オーバーラップ",),
    "DiagonalRun": ("ダイアゴナルラン",),
    "RunIntoSpace": ("スペースに走り込む",),
    "GoalPoaching": ("ゴール前待機",),
    "Confidence": ("自信",),
    "TacticalDiscipline": ("戦術への忠実さ",),
    # Old aggregate parameters are still accepted for older custom teams.
    "Kick": ("キック",),
    "Speed": ("スピード",),
    "Stamina": ("スタミナ",),
    "Technique": ("テクニック",),
    "Jump": ("ジャンプ",),
    "Physical": ("フィジカル",),
}

_PLAYER_NON_STAT_KEYS = {
    "ID", "Name", "Position", "JerseyNumber", "Skills", "PlayerType",
    "PositionX", "PositionY", "gender", "age", "TacticalDiscipline",
}
PLAYER_STAT_CANONICAL_KEYS = tuple(
    key for key in PLAYER_KEY_ALIASES if key not in _PLAYER_NON_STAT_KEYS
)


def normalize_player_keys(raw: dict) -> dict:
    """Return canonical internal keys from Japanese or legacy English JSON.

    Japanese aliases take precedence when both forms are present so that an
    editor can override an old English field without first deleting it.
    """
    normalized = dict(raw)
    for canonical, aliases in PLAYER_KEY_ALIASES.items():
        for alias in aliases:
            if alias in raw:
                normalized[canonical] = raw[alias]
                break
    return normalized


def percentage_value(value: object, default: float = 50.0) -> float:
    """Normalize an editable 0..100 JSON value to the internal 0..1 range."""
    try:
        return clamp(float(value), 0.0, 100.0) / 100.0
    except (TypeError, ValueError):
        return clamp(default, 0.0, 100.0) / 100.0


def team_choice_from_payload(payload: dict, source_name: str = "<memory>") -> dict:
    """Build the normal Match choice directly from an editor payload."""
    try:
        source_stat_min, source_stat_max = payload_stat_bounds(payload)
        needs_stat_remap = (
            source_stat_min != PLAYER_STAT_MIN or source_stat_max != PLAYER_STAT_MAX
        )
        players = payload.get("選手一覧", [])
        starters = []
        bench = []
        for source_raw in players:
            raw = normalize_player_keys(source_raw)
            if needs_stat_remap:
                for key in PLAYER_STAT_CANONICAL_KEYS:
                    if key in raw:
                        raw[key] = round(remap_player_stat(raw[key], source_stat_min, source_stat_max))
            position_x = int(raw.get("PositionX", 0))
            position_y = int(raw.get("PositionY", 0))
            record = {
                "name": str(raw.get("Name", "PLAYER")),
                "number": int(raw.get("JerseyNumber", len(starters) + len(bench) + 1)),
                "position_x": position_x,
                "position_y": position_y,
                "slot": None if position_y == 0 else grid_slot(position_x, position_y),
                "raw": raw,
            }
            if position_y == 0:
                bench.append(record)
            else:
                starters.append(record)
        if not 7 <= len(starters) <= 11:
            raise ValueError(f"The team must have 7 to 11 starters; found {len(starters)}")
        if sum(record["position_y"] == 11 for record in starters) < 1:
            raise ValueError("The team must have at least one goalkeeper at PositionY=11")
        info = payload.get("チーム情報", {})
        tactic_label = str(info.get("戦術", "バランス")).strip()
        tactic = TACTIC_NAMES.get(tactic_label)
        if tactic is None:
            raise ValueError(f"Unknown team tactic: {tactic_label}")
        zone_near = int(info.get("ゾーン手前", 3))
        zone_far = int(info.get("ゾーン奥", 7))
        if not (1 <= zone_near <= zone_far <= 10):
            raise ValueError(f"Zones must satisfy 1 <= ゾーン手前 <= ゾーン奥 <= 10: {zone_near}, {zone_far}")
        def manager_value(key: str, default: float) -> float:
            if key not in info:
                return default
            return remap_player_stat(info[key], source_stat_min, source_stat_max)

        return {
            "name": str(info.get("チーム名", Path(source_name).stem)),
            "short": str(info.get("チームの略称", "")).strip(),
            "manager": str(info.get("監督名", "")),
            "manager_tactic_aggression": manager_stat(
                manager_value("戦術変更への積極性", MANAGER_ACTIVITY_DEFAULT),
                MANAGER_ACTIVITY_DEFAULT,
            ),
            "manager_substitution_aggression": manager_stat(
                manager_value("選手交代への積極性", MANAGER_ACTIVITY_DEFAULT),
                MANAGER_ACTIVITY_DEFAULT,
            ),
            "manager_intelligence": manager_stat(
                manager_value("インテリジェンス", MANAGER_INTELLIGENCE_DEFAULT),
                MANAGER_INTELLIGENCE_DEFAULT,
            ),
            "primary": parse_hex_color(info.get("チームカラー", ""), HOME_RED),
            "tactic": tactic,
            "tactic_label": tactic_label,
            "zone_near": zone_near,
            "zone_far": zone_far,
            "tactical_discipline": percentage_value(info.get("戦術への忠実さ", 50.0)),
            "home_court": str(info.get("ホームコート", f"{info.get('チーム名', Path(source_name).stem)}ホーム")).strip(),
            "starters": starters,
            "bench": bench,
            "source": source_name,
        }
    except (ValueError, TypeError) as error:
        raise ValueError(f"Team payload could not be converted ({source_name}): {error}") from error


def load_team_config(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)
        source_name = path.relative_to(TEAMS_DIR).as_posix()
        return team_choice_from_payload(payload, source_name)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"Team file could not be loaded ({path.name}): {error}")
        return None


def discover_team_choices() -> list[dict]:
    choices = []
    if TEAMS_DIR.exists():
        for path in sorted(TEAMS_DIR.rglob("*.json"), key=lambda item: item.relative_to(TEAMS_DIR).as_posix().casefold()):
            try:
                if path.stat().st_size == 0:
                    continue
            except OSError:
                continue
            config = load_team_config(path)
            if config:
                config.update(
                    {
                        "id": f"json:{path.relative_to(TEAMS_DIR).as_posix()}",
                        "kind": "JSON",
                        "short": config["short"] or ("KAD" if "kadoka" in config["name"].casefold() else config["name"][:3]),
                    }
                )
                choices.append(config)

    if not choices:
        raise RuntimeError(f"No valid team JSON files were found in {TEAMS_DIR}")
    return choices
