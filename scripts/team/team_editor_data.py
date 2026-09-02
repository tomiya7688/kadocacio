from __future__ import annotations

import json
import math
import random
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from scripts.match.player_style_system import PLAYER_TYPES
from scripts.core.settings import TACTIC_NAMES, TEAMS_DIR
from scripts.match.skill_system import ALL_SKILLS, normalize_skill_name
from scripts.core.stat_scale import (
    MANAGER_ACTIVITY_DEFAULT,
    MANAGER_INTELLIGENCE_DEFAULT,
    PLAYER_STAT_DEFAULT,
    PLAYER_STAT_INITIAL,
    PLAYER_STAT_MAX,
    PLAYER_STAT_MIN,
    STAT_SCALE_METADATA_KEY,
    current_scale_metadata,
    legacy_player_stat_delta,
    payload_stat_bounds,
    remap_player_stat,
)
from scripts.team.team_data import PLAYER_KEY_ALIASES
from scripts.team.team_editor_config import load_editor_options
from scripts.team.team_template_profile import generation_field_targets, profile_label
from scripts.team.uniform_data import default_uniform, normalize_uniform, validate_uniform


TEAM_DEFAULTS = {
    "チーム名": "新規チーム",
    "チームの略称": "NEW",
    "チーム紹介": "",
    "監督名": "",
    "戦術変更への積極性": str(MANAGER_ACTIVITY_DEFAULT),
    "選手交代への積極性": str(MANAGER_ACTIVITY_DEFAULT),
    "インテリジェンス": str(MANAGER_INTELLIGENCE_DEFAULT),
    "チームカラー": "#D84442",
    "戦術": "バランス",
    "ゾーン手前": "3",
    "ゾーン奥": "7",
    "戦術への忠実さ": "50",
    "ホームコート": "新規チームホーム",
}

# A description is intentionally optional so old/custom teams remain valid.
# New templates and automatic repair still add the canonical Japanese key.
TEAM_FIELDS = tuple(key for key in TEAM_DEFAULTS if key != "チーム紹介")

IDENTITY_FIELDS = (
    "選手ID",
    "名前",
    "背番号",
    "性別",
    "年齢",
    "プレイヤータイプ",
    "戦術への忠実さ",
)

STAT_GROUPS = {
    "キック・速度": (
        "シュート力", "シュート精度", "パス精度", "パス力",
        "ダッシュ時のスピード", "ウォーク時のスピード",
        "ドリブル時のスピード", "キックモーションのスピード",
    ),
    "スタミナ・技術": (
        "スタミナ最大値", "スタミナ回復速度", "スタミナ管理", "疲労耐性",
        "ミスの少なさ", "ドリブルの上手さ", "トラップの上手さ",
        "パスカットの上手さ", "ゴールストップ力", "シュートの上手さ",
        "パスの上手さ", "スティールの上手さ",
    ),
    "ジャンプ・身体": (
        "ジャンプの高さ", "ジャンプの正確さ", "ジャンプの速さ", "ジャンプの判断力",
        "ヘディングの強さ", "ヘディングの正確さ", "ヘディングの判断力",
        "衝突時のフィジカル", "ドリブル時のフィジカル", "フィジカルプレイの質",
    ),
    "判断・セットプレー": (
        "メンタル", "インテリジェンス", "自信", "安全なプレー",
        "フリーキック", "ペナルティキック", "ゴールキック",
        "スローイン", "コーナーキック",
    ),
    "守備行動": (
        "ゾーンマーキング", "マンツーマン", "プレッシング",
        "シュートカット", "インターセプト",
    ),
    "攻撃行動": (
        "サポート", "トライアングル", "マークを外す", "オーバーラップ",
        "ダイアゴナルラン", "スペースに走り込む", "ゴール前待機",
    ),
}

_EDITOR_OPTIONS = load_editor_options()
TEAM_DEFAULTS.update({
    str(key): str(value) for key, value in _EDITOR_OPTIONS.get("team_defaults", {}).items()
})
loaded_stat_groups = _EDITOR_OPTIONS.get("stat_groups")
if isinstance(loaded_stat_groups, dict) and loaded_stat_groups:
    STAT_GROUPS = {
        str(group): tuple(str(field) for field in fields)
        for group, fields in loaded_stat_groups.items() if isinstance(fields, list)
    }

STAT_FIELDS = tuple(field for fields in STAT_GROUPS.values() for field in fields)

PLAYER_REQUIRED_FIELDS = (
    "選手ID", "名前", "ポジション", "背番号", "プレイヤータイプ",
    "ポジションX", "ポジションY", "性別", "年齢", "スキル",
    *STAT_FIELDS,
    "戦術への忠実さ",
)

FORMATION_TEMPLATES: dict[str, tuple[tuple[int, int], ...]] = {
    "3-5-2": (
        (5, 2), (11, 2),
        (2, 5), (5, 5), (8, 5), (11, 5), (14, 5),
        (4, 8), (8, 8), (12, 8),
    ),
    "4-4-2": (
        (5, 2), (11, 2),
        (2, 5), (6, 5), (10, 5), (14, 5),
        (2, 8), (6, 8), (10, 8), (14, 8),
    ),
    "4-3-3": (
        (3, 2), (8, 2), (13, 2),
        (4, 5), (8, 5), (12, 5),
        (2, 8), (6, 8), (10, 8), (14, 8),
    ),
    "4-5-1": (
        (8, 2),
        (2, 5), (5, 5), (8, 5), (11, 5), (14, 5),
        (2, 8), (6, 8), (10, 8), (14, 8),
    ),
    "5-4-1": (
        (8, 2),
        (2, 5), (6, 5), (10, 5), (14, 5),
        (2, 8), (5, 8), (8, 8), (11, 8), (14, 8),
    ),
    "4-2-3-1": (
        (8, 2),
        (3, 4), (8, 4), (13, 4),
        (6, 6), (10, 6),
        (2, 8), (6, 8), (10, 8), (14, 8),
    ),
}

loaded_formations = _EDITOR_OPTIONS.get("formation_templates")
if isinstance(loaded_formations, dict) and loaded_formations:
    FORMATION_TEMPLATES = {
        str(name): tuple((int(point[0]), int(point[1])) for point in points)
        for name, points in loaded_formations.items() if isinstance(points, list)
    }


@dataclass(frozen=True)
class EditorIssue:
    path: str
    message: str
    fixable: bool = True

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def role_for_position_y(position_y: int) -> str:
    if position_y == 11:
        return "GK"
    if 1 <= position_y <= 3:
        return "FW"
    if 4 <= position_y <= 7:
        return "MF"
    if 8 <= position_y <= 10:
        return "DF"
    return "控え"


def _number(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _canonicalize_player(raw: object) -> dict:
    if not isinstance(raw, dict):
        return {}
    player = deepcopy(raw)
    for canonical, aliases in PLAYER_KEY_ALIASES.items():
        japanese = aliases[0]
        if japanese in player:
            continue
        if canonical in player:
            player[japanese] = deepcopy(player[canonical])
            continue
        for alias in aliases[1:]:
            if alias in player:
                player[japanese] = deepcopy(player[alias])
                break
    return player


def normalize_editor_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {"選手一覧": [], "チーム情報": {}}
    source_stat_min, source_stat_max = payload_stat_bounds(payload)
    normalized = deepcopy(payload)
    info = normalized.get("チーム情報")
    normalized["チーム情報"] = info if isinstance(info, dict) else {}
    info = normalized["チーム情報"]
    if "ユニフォーム" in info:
        info["ユニフォーム"] = normalize_uniform(info.get("ユニフォーム"))
    if "チーム紹介" not in info:
        for alias in ("チーム説明", "description", "teamDescription"):
            if alias in info:
                info["チーム紹介"] = str(info.get(alias, ""))
                break
    players = normalized.get("選手一覧")
    normalized["選手一覧"] = [
        _canonicalize_player(player) for player in players
    ] if isinstance(players, list) else []
    for player in normalized["選手一覧"]:
        skills = player.get("スキル")
        if isinstance(skills, list):
            player["スキル"] = list(dict.fromkeys(normalize_skill_name(skill) for skill in skills))
        for field in STAT_FIELDS:
            if field in player:
                player[field] = str(round(remap_player_stat(
                    player[field], source_stat_min, source_stat_max,
                )))
    info = normalized["チーム情報"]
    for key, default in (
        ("戦術変更への積極性", MANAGER_ACTIVITY_DEFAULT),
        ("選手交代への積極性", MANAGER_ACTIVITY_DEFAULT),
        ("インテリジェンス", MANAGER_INTELLIGENCE_DEFAULT),
    ):
        if key in info:
            info[key] = str(round(remap_player_stat(
                info[key], source_stat_min, source_stat_max, default=default,
            )))
    tuner = normalized.get("チームチューナー")
    if isinstance(tuner, dict):
        targets = tuner.get("基準値ステータス")
        if isinstance(targets, dict):
            for key, value in tuple(targets.items()):
                targets[key] = str(round(remap_player_stat(
                    value, source_stat_min, source_stat_max,
                    default=PLAYER_STAT_DEFAULT,
                )))
    normalized[STAT_SCALE_METADATA_KEY] = current_scale_metadata()
    return normalized


def load_editor_payload(path: Path) -> tuple[dict, list[EditorIssue]]:
    try:
        with path.open("r", encoding="utf-8-sig") as file:
            raw = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        return normalize_editor_payload({}), [EditorIssue("JSON", f"読み込み失敗: {error}")]
    payload = normalize_editor_payload(raw)
    return payload, validate_payload(payload)


def _valid_hex_color(value: object) -> bool:
    return bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", str(value or "")))


def validate_payload(payload: object) -> list[EditorIssue]:
    issues: list[EditorIssue] = []
    if not isinstance(payload, dict):
        return [EditorIssue("JSON", "最上位がオブジェクトではありません")]

    info = payload.get("チーム情報")
    if not isinstance(info, dict):
        issues.append(EditorIssue("チーム情報", "オブジェクトが必要です"))
        info = {}
    for key in TEAM_FIELDS:
        if key not in info:
            issues.append(EditorIssue(f"チーム情報.{key}", "必要なキーがありません"))
    if "チーム名" in info and not str(info.get("チーム名", "")).strip():
        issues.append(EditorIssue("チーム情報.チーム名", "空欄にはできません"))
    if "戦術" in info and str(info.get("戦術", "")) not in TACTIC_NAMES:
        issues.append(EditorIssue("チーム情報.戦術", "7種類の戦術から選んでください"))
    if "チームカラー" in info and not _valid_hex_color(info.get("チームカラー")):
        issues.append(EditorIssue("チーム情報.チームカラー", "#RRGGBB形式が必要です"))
    if "ユニフォーム" in info:
        issues.extend(
            EditorIssue(f"チーム情報.ユニフォーム.{message.split('は', 1)[0]}", message)
            for message in validate_uniform(info.get("ユニフォーム"))
        )
    near = _number(info.get("ゾーン手前"))
    far = _number(info.get("ゾーン奥"))
    if "ゾーン手前" in info and (near is None or not 1 <= near <= 10):
        issues.append(EditorIssue("チーム情報.ゾーン手前", "1〜10で指定してください"))
    if "ゾーン奥" in info and (far is None or not 1 <= far <= 10):
        issues.append(EditorIssue("チーム情報.ゾーン奥", "1〜10で指定してください"))
    if near is not None and far is not None and near > far:
        issues.append(EditorIssue("チーム情報.ゾーン", "手前は奥以下にしてください"))
    team_discipline = _number(info.get("戦術への忠実さ"))
    if "戦術への忠実さ" in info and (team_discipline is None or not 0 <= team_discipline <= 100):
        issues.append(EditorIssue("チーム情報.戦術への忠実さ", "0〜100で指定してください"))
    for key in ("戦術変更への積極性", "選手交代への積極性", "インテリジェンス"):
        value = _number(info.get(key))
        if key in info and (value is None or not PLAYER_STAT_MIN <= value <= PLAYER_STAT_MAX):
            issues.append(EditorIssue(f"チーム情報.{key}", f"{int(PLAYER_STAT_MIN)}〜{int(PLAYER_STAT_MAX)}で指定してください"))

    players = payload.get("選手一覧")
    if not isinstance(players, list):
        issues.append(EditorIssue("選手一覧", "配列が必要です"))
        return issues
    ids: set[str] = set()
    numbers: set[int] = set()
    active_cells: set[tuple[int, int]] = set()
    starters = 0
    keepers = 0
    for index, player in enumerate(players):
        prefix = f"選手{index + 1}"
        if not isinstance(player, dict):
            issues.append(EditorIssue(prefix, "オブジェクトが必要です"))
            continue
        for key in PLAYER_REQUIRED_FIELDS:
            if key not in player:
                issues.append(EditorIssue(f"{prefix}.{key}", "必要なキーがありません"))
        player_id = str(player.get("選手ID", "")).strip()
        if "選手ID" in player:
            if not player_id:
                issues.append(EditorIssue(f"{prefix}.選手ID", "空欄にはできません"))
            elif player_id in ids:
                issues.append(EditorIssue(f"{prefix}.選手ID", "重複しています"))
            ids.add(player_id)
        if "名前" in player and not str(player.get("名前", "")).strip():
            issues.append(EditorIssue(f"{prefix}.名前", "空欄にはできません"))
        jersey_value = _number(player.get("背番号"))
        if "背番号" in player:
            if jersey_value is None or not 1 <= jersey_value <= 999 or int(jersey_value) != jersey_value:
                issues.append(EditorIssue(f"{prefix}.背番号", "1〜999の整数が必要です"))
            elif int(jersey_value) in numbers:
                issues.append(EditorIssue(f"{prefix}.背番号", "重複しています"))
            else:
                numbers.add(int(jersey_value))
        if "プレイヤータイプ" in player and player.get("プレイヤータイプ") not in PLAYER_TYPES:
            issues.append(EditorIssue(f"{prefix}.プレイヤータイプ", "一覧から選んでください"))
        for key in STAT_FIELDS:
            if key not in player:
                continue
            value = _number(player.get(key))
            if value is None or not PLAYER_STAT_MIN <= value <= PLAYER_STAT_MAX:
                issues.append(EditorIssue(f"{prefix}.{key}", f"{int(PLAYER_STAT_MIN)}〜{int(PLAYER_STAT_MAX)}で指定してください"))
        discipline = _number(player.get("戦術への忠実さ"))
        if "戦術への忠実さ" in player and (discipline is None or not 0 <= discipline <= 100):
            issues.append(EditorIssue(f"{prefix}.戦術への忠実さ", "0〜100で指定してください"))
        x = _number(player.get("ポジションX"))
        y = _number(player.get("ポジションY"))
        has_x = "ポジションX" in player
        has_y = "ポジションY" in player
        valid_x = has_x and x is not None and int(x) == x and 0 <= x <= 15
        valid_y = has_y and y is not None and int(y) == y and 0 <= y <= 11
        if has_x and not valid_x:
            issues.append(EditorIssue(f"{prefix}.ポジションX", "0〜15の整数が必要です"))
        if has_y and not valid_y:
            issues.append(EditorIssue(f"{prefix}.ポジションY", "0〜11の整数が必要です"))
        if valid_y and int(y) != 0:
            starters += 1
            if int(y) == 11:
                keepers += 1
            elif valid_x and not 1 <= int(x) <= 15:
                issues.append(EditorIssue(f"{prefix}.ポジションX", "先発は1〜15が必要です"))
            if valid_x:
                cell = (int(x), int(y))
                if int(y) != 11 and cell in active_cells:
                    issues.append(EditorIssue(f"{prefix}.配置", "同じマスに別の選手がいます"))
                active_cells.add(cell)
        skills = player.get("スキル")
        if "スキル" in player and not isinstance(skills, list):
            issues.append(EditorIssue(f"{prefix}.スキル", "配列が必要です"))
        elif isinstance(skills, list):
            unknown = [str(skill) for skill in skills if skill not in ALL_SKILLS]
            if unknown:
                issues.append(EditorIssue(f"{prefix}.スキル", f"未登録: {', '.join(unknown[:3])}"))

    if not 7 <= starters <= 11:
        issues.append(EditorIssue("フォーメーション", f"先発は7〜11人必要です（現在{starters}人）"))
    if keepers < 1:
        issues.append(EditorIssue("フォーメーション", "GKは1人以上必要です"))
    return issues


def _random_stat(rng: random.Random, target: int | None, spread: str) -> int:
    if target is None:
        return rng.randint(round(PLAYER_STAT_MIN), round(PLAYER_STAT_MAX))
    sigma = {
        "小": legacy_player_stat_delta(45),
        "中": legacy_player_stat_delta(145),
        "大": legacy_player_stat_delta(300),
    }.get(spread, legacy_player_stat_delta(145))
    return round(max(PLAYER_STAT_MIN, min(PLAYER_STAT_MAX, rng.gauss(target, sigma))))


def _default_player(
    index: int,
    rng: random.Random,
    *,
    mode: str = "initial",
    target: int = round(PLAYER_STAT_DEFAULT),
    spread: str = "中",
    player_types: tuple[str, ...] = PLAYER_TYPES,
    field_targets: dict[str, int] | None = None,
) -> dict:
    def stat_value(key: str) -> int:
        if mode == "initial":
            return PLAYER_STAT_INITIAL
        if mode == "target":
            return _random_stat(rng, (field_targets or {}).get(key, target), spread)
        return _random_stat(rng, None, spread)
    player = {
        "選手ID": str(index),
        "名前": f"選手{index}",
        "ポジション": "控え",
        "背番号": str(index),
        "プレイヤータイプ": rng.choice(player_types) if mode != "initial" else "オールラウンド",
        "ポジションX": "0",
        "ポジションY": "0",
        "性別": rng.choice(("男", "女")) if mode != "initial" else "未設定",
        "年齢": str(rng.randint(15, 38) if mode != "initial" else 18),
        "スキル": [],
        "戦術への忠実さ": str(rng.randint(0, 100) if mode == "random" else 50),
    }
    for key in STAT_FIELDS:
        player[key] = str(stat_value(key))
    return player


def create_team_template(
    mode: str,
    *,
    target: int = round(PLAYER_STAT_DEFAULT),
    spread: str = "中",
    rng: random.Random | None = None,
    options: dict | None = None,
    profile_id: str = "balanced",
) -> dict:
    rng = rng or random.Random()
    options = options or _EDITOR_OPTIONS
    player_types = tuple(
        value for value in options.get("player_types", PLAYER_TYPES) if value in PLAYER_TYPES
    ) or PLAYER_TYPES
    team_defaults = deepcopy(options.get("team_defaults", TEAM_DEFAULTS))
    formations = options.get("formation_templates", FORMATION_TEMPLATES)
    target = round(max(PLAYER_STAT_MIN, min(PLAYER_STAT_MAX, int(target))))
    field_targets = generation_field_targets(target, profile_id, options, STAT_FIELDS)
    payload = {
        "選手一覧": [
            _default_player(
                index, rng, mode=mode, target=target, spread=spread,
                player_types=player_types, field_targets=field_targets,
            )
            for index in range(1, 12)
        ],
        "チーム情報": team_defaults,
        STAT_SCALE_METADATA_KEY: current_scale_metadata(),
    }
    payload["チーム情報"]["ユニフォーム"] = default_uniform()
    if mode == "target":
        # Clamping near the configured bounds would otherwise bias the average away from the
        # requested value.  Shift the generated population back toward the goal
        # while preserving as much of the chosen spread as the bounds allow.
        for _ in range(64):
            values = [int(player[key]) for player in payload["選手一覧"] for key in STAT_FIELDS]
            offset = target - sum(values) / len(values)
            if abs(offset) < 0.6:
                break
            for player in payload["選手一覧"]:
                for key in STAT_FIELDS:
                    player[key] = str(round(max(
                        PLAYER_STAT_MIN,
                        min(PLAYER_STAT_MAX, int(player[key]) + offset),
                    )))
    if mode == "random":
        payload["チーム情報"]["チーム名"] = "ランダムチーム"
        payload["チーム情報"]["チームの略称"] = "RND"
        payload["チーム情報"]["チームカラー"] = "#{:06X}".format(rng.randrange(0x1000000))
        tactics = tuple(value for value in options.get("tactics", TACTIC_NAMES) if value in TACTIC_NAMES)
        payload["チーム情報"]["戦術"] = rng.choice(tactics or tuple(TACTIC_NAMES))
        payload["チーム情報"]["戦術への忠実さ"] = str(rng.randint(0, 100))
        payload["チーム情報"]["戦術変更への積極性"] = str(rng.randint(round(PLAYER_STAT_MIN), round(PLAYER_STAT_MAX)))
        payload["チーム情報"]["選手交代への積極性"] = str(rng.randint(round(PLAYER_STAT_MIN), round(PLAYER_STAT_MAX)))
        payload["チーム情報"]["インテリジェンス"] = str(rng.randint(round(PLAYER_STAT_MIN), round(PLAYER_STAT_MAX)))
    elif mode == "target":
        payload["チーム情報"]["チーム名"] = f"基準{target}{profile_label(options, profile_id)}チーム"
        payload["チーム情報"]["チームの略称"] = "BASE"
    apply_formation(payload, "4-4-2", formations)
    return payload


def add_default_player(payload: dict, rng: random.Random | None = None) -> int:
    rng = rng or random.Random()
    players = payload.setdefault("選手一覧", [])
    existing_ids = {str(player.get("選手ID", "")) for player in players if isinstance(player, dict)}
    index = 1
    while str(index) in existing_ids:
        index += 1
    player = _default_player(index, rng, mode="initial")
    used_numbers = {
        int(value) for player_data in players if isinstance(player_data, dict)
        if (value := _number(player_data.get("背番号"))) is not None and int(value) == value
    }
    number = 1
    while number in used_numbers:
        number += 1
    player["背番号"] = str(number)
    players.append(player)
    return len(players) - 1


def _position_distance(player: dict, target: tuple[int, int]) -> float:
    x = _number(player.get("ポジションX"))
    y = _number(player.get("ポジションY"))
    if x is None or y is None or int(y) == 0:
        return 1000.0
    return (float(x) - target[0]) ** 2 + (float(y) - target[1]) ** 2 * 2.2


def apply_formation(payload: dict, formation: str, templates: dict | None = None) -> None:
    templates = templates or FORMATION_TEMPLATES
    fallback = templates.get("4-4-2") or next(iter(templates.values()), ())
    targets = [tuple(point) for point in templates.get(formation, fallback)]
    players = [player for player in payload.setdefault("選手一覧", []) if isinstance(player, dict)]
    if not players:
        return
    keeper = next((player for player in players if str(player.get("ポジションY")) == "11"), None)
    if keeper is None:
        keeper = next((player for player in players if str(player.get("ポジション")) == "GK"), players[-1])
    keeper["ポジションX"] = "8"
    keeper["ポジションY"] = "11"
    keeper["ポジション"] = "GK"

    available = [player for player in players if player is not keeper]
    assigned: dict[int, tuple[int, int]] = {}
    remaining_targets = list(targets)
    remaining_players = list(available)
    while remaining_targets and remaining_players:
        player, target = min(
            ((candidate, target) for candidate in remaining_players for target in remaining_targets),
            key=lambda pair: _position_distance(pair[0], pair[1]),
        )
        assigned[id(player)] = target
        remaining_players.remove(player)
        remaining_targets.remove(target)
    for player in available:
        target = assigned.get(id(player))
        if target is None:
            player["ポジションX"] = "0"
            player["ポジションY"] = "0"
            player["ポジション"] = "控え"
        else:
            player["ポジションX"] = str(target[0])
            player["ポジションY"] = str(target[1])
            player["ポジション"] = role_for_position_y(target[1])


def repair_payload(payload: object, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    repaired = normalize_editor_payload(payload)
    info = repaired["チーム情報"]
    for key, default in TEAM_DEFAULTS.items():
        if key not in info or (key == "チーム名" and not str(info.get(key, "")).strip()):
            info[key] = default
    info["ユニフォーム"] = normalize_uniform(info.get("ユニフォーム"))
    if str(info.get("戦術")) not in TACTIC_NAMES:
        info["戦術"] = rng.choice(tuple(TACTIC_NAMES))
    if not _valid_hex_color(info.get("チームカラー")):
        info["チームカラー"] = "#{:06X}".format(rng.randrange(0x1000000))
    for key in ("ゾーン手前", "ゾーン奥"):
        value = _number(info.get(key))
        if value is None or not 1 <= value <= 10:
            info[key] = str(rng.randint(1, 10))
    near = int(float(info["ゾーン手前"]))
    far = int(float(info["ゾーン奥"]))
    if near > far:
        near, far = far, near
    info["ゾーン手前"], info["ゾーン奥"] = str(near), str(far)
    discipline = _number(info.get("戦術への忠実さ"))
    if discipline is None or not 0 <= discipline <= 100:
        info["戦術への忠実さ"] = str(rng.randint(0, 100))
    for key in ("戦術変更への積極性", "選手交代への積極性", "インテリジェンス"):
        value = _number(info.get(key))
        if value is None or not PLAYER_STAT_MIN <= value <= PLAYER_STAT_MAX:
            info[key] = str(rng.randint(round(PLAYER_STAT_MIN), round(PLAYER_STAT_MAX)))

    players = repaired["選手一覧"]
    while len(players) < 11:
        add_default_player(repaired, rng)
    used_ids: set[str] = set()
    used_numbers: set[int] = set()
    for index, player in enumerate(players, 1):
        if not isinstance(player, dict):
            player = _default_player(index, rng, mode="random")
            players[index - 1] = player
        player_id = str(player.get("選手ID", "")).strip()
        if not player_id or player_id in used_ids:
            player_id = str(index)
            while player_id in used_ids:
                player_id = str(rng.randint(1, 999999))
            player["選手ID"] = player_id
        used_ids.add(player_id)
        if not str(player.get("名前", "")).strip():
            player["名前"] = f"選手{index}"
        number_value = _number(player.get("背番号"))
        number = int(number_value) if number_value is not None and int(number_value) == number_value else index
        if not 1 <= number <= 999 or number in used_numbers:
            number = 1
            while number in used_numbers:
                number += 1
        player["背番号"] = str(number)
        used_numbers.add(number)
        player.setdefault("性別", rng.choice(("男", "女", "未設定")))
        player.setdefault("年齢", str(rng.randint(15, 38)))
        if player.get("プレイヤータイプ") not in PLAYER_TYPES:
            player["プレイヤータイプ"] = rng.choice(PLAYER_TYPES)
        for key in STAT_FIELDS:
            value = _number(player.get(key))
            if value is None or not PLAYER_STAT_MIN <= value <= PLAYER_STAT_MAX:
                player[key] = str(rng.randint(round(PLAYER_STAT_MIN), round(PLAYER_STAT_MAX)))
        player_discipline = _number(player.get("戦術への忠実さ"))
        if player_discipline is None or not 0 <= player_discipline <= 100:
            player["戦術への忠実さ"] = str(rng.randint(0, 100))
        skills = player.get("スキル")
        player["スキル"] = list(dict.fromkeys(
            skill for skill in skills if skill in ALL_SKILLS
        )) if isinstance(skills, list) else []
        player.setdefault("ポジションX", "0")
        player.setdefault("ポジションY", "0")
        player.setdefault("ポジション", "控え")
    formation_issues = validate_payload(repaired)
    if any(
        issue.path == "フォーメーション"
        or ".ポジションX" in issue.path
        or ".ポジションY" in issue.path
        or issue.path.endswith(".配置")
        for issue in formation_issues
    ):
        apply_formation(repaired, "4-4-2")
    else:
        for player in players:
            player["ポジション"] = role_for_position_y(int(float(player["ポジションY"])))
    return repaired


def safe_team_filename(team_name: object) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(team_name or "新規チーム")).strip(" .")
    return (name or "新規チーム") + ".json"


def safe_team_folder(folder_name: object) -> Path:
    raw = str(folder_name or "").replace("\\", "/").strip().strip("/")
    if not raw:
        return Path()
    parts = []
    for value in raw.split("/"):
        if value in ("", ".", ".."):
            raise ValueError("フォルダ名に . や .. は使用できません")
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
        if not cleaned:
            raise ValueError("フォルダ名が空です")
        parts.append(cleaned[:48])
    return Path(*parts)


def team_relative_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(TEAMS_DIR.resolve())
    except ValueError as error:
        raise ValueError("teamsフォルダ外は操作できません") from error
    if resolved.suffix.lower() != ".json":
        raise ValueError("JSONファイルだけを操作できます")
    return relative


def team_id_for_path(path: Path) -> str:
    return f"json:{team_relative_path(path).as_posix()}"


def _replace_json_identifier(value, old_id: str, new_id: str):
    if isinstance(value, dict):
        return {
            (new_id if str(key) == old_id else key): _replace_json_identifier(item, old_id, new_id)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_json_identifier(item, old_id, new_id) for item in value]
    return new_id if value == old_id else value


def update_team_file_references(old_id: str, new_id: str) -> None:
    if not old_id or old_id == new_id:
        return
    root = TEAMS_DIR.parent
    targets = [root / "leagues.json", root / "league_state.json"]
    template_dir = root / "league_templates"
    if template_dir.exists():
        targets.extend(template_dir.glob("*.json"))
    save_dir = root / "league_save"
    if save_dir.exists():
        targets.extend(save_dir.glob("*.json"))
    for target in targets:
        if not target.exists():
            continue
        try:
            with target.open("r", encoding="utf-8-sig") as file:
                payload = json.load(file)
            replaced = _replace_json_identifier(payload, old_id, new_id)
            if replaced == payload:
                continue
            temporary = target.with_suffix(target.suffix + ".tmp")
            with temporary.open("w", encoding="utf-8", newline="\n") as file:
                json.dump(replaced, file, ensure_ascii=False, indent=2)
                file.write("\n")
            temporary.replace(target)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue


def save_editor_payload(payload: dict, source_path: Path | None = None, folder_name: object | None = None) -> Path:
    TEAMS_DIR.mkdir(parents=True, exist_ok=True)
    # League membership belongs exclusively to leagues.json.
    payload.get("チーム情報", {}).pop("所属リーグ", None)
    old_path = source_path.resolve() if source_path is not None else None
    if old_path is not None:
        team_relative_path(old_path)
    folder = safe_team_folder(folder_name) if folder_name is not None else (team_relative_path(old_path).parent if old_path else Path())
    target_dir = (TEAMS_DIR / folder).resolve()
    try:
        target_dir.relative_to(TEAMS_DIR.resolve())
    except ValueError as error:
        raise ValueError("teamsフォルダ外へは保存できません") from error
    target_dir.mkdir(parents=True, exist_ok=True)
    base = target_dir / safe_team_filename(payload.get("チーム情報", {}).get("チーム名"))
    path = base
    counter = 2
    while path.exists() and (old_path is None or path.resolve() != old_path):
        path = base.with_name(f"{base.stem} ({counter}).json")
        counter += 1
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(path)
    if old_path is not None and old_path != path.resolve():
        old_id = team_id_for_path(old_path)
        new_id = team_id_for_path(path)
        old_path.unlink()
        update_team_file_references(old_id, new_id)
    return path


def delete_team_file(path: Path) -> None:
    resolved = path.resolve()
    team_relative_path(resolved)
    resolved.unlink()


def scan_team_files() -> list[tuple[Path, dict, list[EditorIssue]]]:
    entries = []
    if not TEAMS_DIR.exists():
        return entries
    for file_path in sorted(TEAMS_DIR.rglob("*.json"), key=lambda item: item.relative_to(TEAMS_DIR).as_posix().casefold()):
        payload, issues = load_editor_payload(file_path)
        entries.append((file_path, payload, issues))
    return entries


def scan_team_directory(
    relative_folder: str | Path = "",
) -> tuple[list[Path], list[tuple[Path, dict, list[EditorIssue]]]]:
    """Return immediate subfolders and JSON teams for the editor browser."""
    root = TEAMS_DIR.resolve()
    folder = (TEAMS_DIR / Path(relative_folder)).resolve()
    try:
        folder.relative_to(root)
    except ValueError as error:
        raise ValueError("teamsフォルダ外は表示できません") from error
    if not folder.exists() or not folder.is_dir():
        return [], []
    directories = sorted(
        (path for path in folder.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    )
    entries: list[tuple[Path, dict, list[EditorIssue]]] = []
    for file_path in sorted(folder.glob("*.json"), key=lambda path: path.name.casefold()):
        payload, issues = load_editor_payload(file_path)
        entries.append((file_path, payload, issues))
    return directories, entries
