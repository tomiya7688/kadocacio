"""Generate the bundled Kadocalcio A/B original clubs deterministically."""

from __future__ import annotations

import json
import random
from pathlib import Path

from scripts.core.paths import PROJECT_ROOT
from scripts.match.skill_system import ALL_SKILLS
from scripts.core.stat_scale import current_scale_metadata, legacy_player_stat
from scripts.team.team_editor_data import FORMATION_TEMPLATES, STAT_FIELDS, STAT_GROUPS, validate_payload


ROOT = PROJECT_ROOT
TEAMS_ROOT = ROOT / "teams"
A_DIR = TEAMS_ROOT / "kadoka_original_A"
B_DIR = TEAMS_ROOT / "kadoka_original_B"

A_TEAMS = (
    ("北海スノーフォックス", "KSF", 820, "#70B9E8"),
    ("仙台フォレスト", "SDF", 790, "#2E9B63"),
    ("越後スワンズ", "EGS", 770, "#F2F3F5"),
    ("浦和レッドギア", "URG", 830, "#D9323E"),
    ("千葉マリナーズ", "CBM", 740, "#F1C33B"),
    ("東京メトロスター", "TMS", 810, "#334F9A"),
    ("川崎ブルーギア", "KBG", 840, "#39A8DC"),
    ("横浜ベイウイング", "YBW", 800, "#245DA8"),
    ("甲府グレープス", "KFG", 700, "#704A9E"),
    ("信州アルプス", "SAS", 690, "#68A9D3"),
    ("金沢ゴールドリーフ", "KGL", 720, "#C8A13A"),
    ("名古屋シャチホコ", "NSH", 780, "#E58A2C"),
    ("京都パープルズ", "KYP", 760, "#71439A"),
    ("神戸ハーバーズ", "KBH", 790, "#8C3154"),
    ("広島レッドアロー", "HRA", 750, "#B8323F"),
)

B_TEAMS = (
    ("札幌ノースゲート", "SNG", 610, "#3B6AB3"),
    ("盛岡グラナイト", "MGN", 500, "#6B7887"),
    ("秋田ライスフィールド", "ARF", 490, "#D8D1A8"),
    ("山形チェリーズ", "YGC", 530, "#D95D78"),
    ("福島ピーチブロッサム", "FPB", 520, "#F08AA4"),
    ("水戸レイクサイド", "MLS", 560, "#386FB7"),
    ("栃木サンダーズ", "TST", 550, "#E7C13C"),
    ("群馬ホットスプリング", "GHS", 540, "#4C9278"),
    ("大宮オレンジライン", "OOL", 640, "#E98631"),
    ("多摩グリーンズ", "TMG", 570, "#3C9B56"),
    ("相模原スターズ", "SGS", 510, "#5A789E"),
    ("湘南シーブリーズ", "SSB", 620, "#55AFD3"),
    ("富山マウンテンズ", "TYM", 520, "#5579A5"),
    ("岐阜リバーバンク", "GRB", 500, "#4A856A"),
    ("静岡ティーリーフ", "STL", 600, "#65A848"),
    ("奈良ディアーズ", "NRD", 550, "#8A6349"),
    ("岡山ピーチボーイズ", "OPB", 590, "#E17D94"),
    ("徳島ブルータイド", "TBT", 560, "#315F9D"),
    ("熊本ファイアーズ", "KMF", 580, "#D84D36"),
    ("琉球サンゴ", "RSC", 540, "#E06F65"),
)

SURNAMES = (
    "サトウ", "スズキ", "タカハシ", "タナカ", "イトウ", "ワタナベ", "ヤマモト", "ナカムラ",
    "コバヤシ", "カトウ", "ヨシダ", "ヤマダ", "ササキ", "ヤマグチ", "マツモト", "イノウエ",
    "キムラ", "ハヤシ", "シミズ", "ヤマザキ", "モリ", "アベ", "イケダ", "ハシモト",
    "イシカワ", "ヤマシタ", "オガワ", "ゴトウ", "オカダ", "ハセガワ", "ムラカミ", "コンドウ",
    "イシイ", "サイトウ", "サカモト", "エンドウ", "アオキ", "フジタ", "ニシムラ", "フクダ",
    "オオタ", "ミウラ", "フジイ", "オカモト", "マツダ", "ナカガワ", "ナカノ", "ハラダ",
)
GIVEN_NAMES = (
    "ハル", "レン", "ソウタ", "ユウト", "アオイ", "ミナト", "リク", "カイト", "ヒナタ", "ナオ",
    "ユイ", "リン", "メイ", "サクラ", "アカリ", "ミオ", "ナナ", "レイ", "ツバサ", "マコト",
    "シン", "ケイ", "ジュン", "カナ", "ノゾミ", "ユウ", "ヒカル", "チアキ", "コウ", "ナギ",
)

FORMATIONS = ("4-4-2", "4-3-3", "4-5-1", "5-4-1", "4-2-3-1", "3-5-2")
TACTICS = ("攻撃的", "バランス", "防御的", "バランス", "指示なし")
BENCH_ROLES = ("FW", "MF", "MF", "DF", "GK")

ROLE_TYPES = {
    "FW": ("ストライカー", "アタッカー", "チャンスメーカー"),
    "MF": ("ダイナモ", "レジスタ", "オールラウンド", "チャンスメーカー"),
    "DF": ("ストッパー", "マンマーカー", "スイーパー", "リベロ", "バックアップ"),
    "GK": ("バックアップ", "スイーパー"),
}

ROLE_BIASES = {
    "FW": {
        "シュート力": 115, "シュート精度": 105, "シュートの上手さ": 110,
        "ドリブルの上手さ": 65, "マークを外す": 80, "スペースに走り込む": 90,
        "ゴール前待機": 120, "ゴールストップ力": -180, "ゾーンマーキング": -65,
        "マンツーマン": -65, "シュートカット": -70,
    },
    "MF": {
        "パス精度": 90, "パス力": 55, "パスの上手さ": 100, "トラップの上手さ": 65,
        "スタミナ最大値": 55, "サポート": 95, "トライアングル": 95,
        "ダイアゴナルラン": 55, "ゴールストップ力": -110,
    },
    "DF": {
        "ゾーンマーキング": 105, "マンツーマン": 105, "プレッシング": 70,
        "シュートカット": 110, "インターセプト": 105, "パスカットの上手さ": 85,
        "スティールの上手さ": 90, "衝突時のフィジカル": 65, "シュート精度": -65,
        "ドリブルの上手さ": -45, "ゴールストップ力": -80,
    },
    "GK": {
        "ゴールストップ力": 230, "ジャンプの高さ": 100, "ジャンプの正確さ": 125,
        "ジャンプの速さ": 115, "ジャンプの判断力": 145, "ゴールキック": 125,
        "パスの上手さ": 45, "インテリジェンス": 70, "シュート力": -130,
        "シュート精度": -150, "ドリブルの上手さ": -120, "ゴール前待機": -160,
    },
}

ROLE_SKILLS = {
    "FW": ("エアリアルヘッド", "スライドフィニッシュ", "決定機センサー", "背後の狩人",
           "キャリーショット", "オーバーヘッドボレー", "ダイレクトボレー", "セット＆シュート"),
    "MF": ("アークカーブ", "魔術師のプレースキック", "ワンタッチリレー", "オーバーロード",
           "奪取カウンター", "スピンターン", "ブラインドフィード", "サイン連携"),
    "DF": ("城塞ブロック", "密着封鎖", "空白カバー", "リカバリーチェイス",
           "不動の体幹", "パワースライド", "片道封鎖", "猛追プレス"),
    "GK": ("セービングオーラ", "先読みセーブ", "スイーパーキーパー"),
}


def clamp_stat(value: float) -> int:
    """Clamp values in the generator's legacy balancing domain."""
    return max(50, min(1250, round(value)))


def role_for_position_y(position_y: int) -> str:
    if position_y == 11:
        return "GK"
    if position_y <= 3:
        return "FW"
    if position_y <= 7:
        return "MF"
    return "DF"


def team_strength(payload: dict) -> float:
    player_means = []
    for fields in STAT_GROUPS.values():
        values = [int(player[field]) for player in payload["選手一覧"] for field in fields]
        player_means.append(sum(values) / len(values))
    return sum(player_means) / len(player_means)


def choose_skills(rng: random.Random, role: str, target: int, squad_rank: int) -> list[str]:
    chance = 0.18 + max(0, target - 450) / 900 * 0.42
    count = 0
    if rng.random() < chance:
        count += 1
    if squad_rank < 3 and rng.random() < chance * 0.9:
        count += 1
    if target >= 780 and squad_rank == 0 and rng.random() < 0.65:
        count += 1
    pool = [skill for skill in ROLE_SKILLS[role] if skill in ALL_SKILLS]
    return rng.sample(pool, min(count, len(pool)))


def make_player(
    rng: random.Random,
    division: str,
    team_index: int,
    player_index: int,
    target: int,
    role: str,
    position: tuple[int, int] | None,
) -> dict:
    squad_offsets = (95, 70, 50, 35, 25, 15, 5, -5, -15, -25, -35, -45, -55, -65, -75, -85)
    base = target + squad_offsets[player_index]
    surname = SURNAMES[(team_index * 13 + player_index * 5) % len(SURNAMES)]
    given = GIVEN_NAMES[(team_index * 7 + player_index * 11) % len(GIVEN_NAMES)]
    player = {
        "選手ID": f"K{division}{team_index + 1:02d}P{player_index + 1:02d}",
        "名前": f"{surname} {given}",
        "ポジション": role,
        "背番号": str(player_index + 1),
    }
    for field in STAT_FIELDS:
        bias = ROLE_BIASES[role].get(field, 0)
        player[field] = str(clamp_stat(rng.gauss(base + bias, 48 if division == "A" else 58)))
    position_x, position_y = position if position is not None else (0, 0)
    player.update({
        "スキル": choose_skills(rng, role, target, player_index),
        "プレイヤータイプ": rng.choice(ROLE_TYPES[role]),
        "ポジションX": str(position_x),
        "ポジションY": str(position_y),
        "性別": "女性" if (team_index + player_index) % 5 == 0 else "男性",
        "年齢": str(18 + (team_index * 3 + player_index * 2) % 17),
        "戦術への忠実さ": str(35 + (team_index * 7 + player_index * 3) % 46),
    })
    return player


def make_team(division: str, team_index: int, spec: tuple[str, str, int, str]) -> dict:
    name, short, target, color = spec
    rng = random.Random(20260819 + (0 if division == "A" else 10000) + team_index * 101)
    formation_name = FORMATIONS[team_index % len(FORMATIONS)]
    formation = list(FORMATION_TEMPLATES[formation_name]) + [(8, 11)]
    starter_roles = [role_for_position_y(y) for _, y in formation]
    roles = starter_roles + list(BENCH_ROLES)
    players = [
        make_player(
            rng, division, team_index, index, target, role,
            formation[index] if index < len(formation) else None,
        )
        for index, role in enumerate(roles)
    ]
    tactic = TACTICS[team_index % len(TACTICS)]
    payload = {
        "選手一覧": players,
        "チーム情報": {
            "チーム名": name,
            "チームの略称": short,
            "監督名": f"{SURNAMES[(team_index * 9 + (0 if division == 'A' else 17)) % len(SURNAMES)]}監督",
            "戦術変更への積極性": str(380 + (team_index * 53) % 360),
            "選手交代への積極性": str(420 + (team_index * 47) % 380),
            "インテリジェンス": str(clamp_stat(target + (30 if division == "A" else 0))),
            "チームカラー": color,
            "戦術": tactic,
            "ゾーン手前": str(2 + team_index % 3),
            "ゾーン奥": str(7 + team_index % 3),
            "戦術への忠実さ": str(38 + team_index * 5 % 42),
            "ホームコート": f"{name}ホーム",
        },
        "チームチューナー": {
            "基準値ステータス": {
                key: str(target) for key in (
                    "kick", "speed", "stamina", "technique", "jump", "mental",
                    "intelligence", "defense", "offense", "physical",
                )
            },
            "裏パラメータ自動調整": True,
            "時間上限秒": "200",
            "終了条件": "収束まで",
            "評価モード": "精度重視",
        },
    }
    # Preserve positional specialisation while centring the ten category means
    # on the intended division strength.
    shift = target - team_strength(payload)
    for player in players:
        for field in STAT_FIELDS:
            player[field] = str(clamp_stat(int(player[field]) + shift))
    # Generation continues to use the original balancing values above so its
    # deterministic club strengths do not change. Store the result on the
    # current editable scale only after balancing is complete.
    for player in players:
        for field in STAT_FIELDS:
            player[field] = str(round(legacy_player_stat(float(player[field]))))
    team_info = payload["チーム情報"]
    for field in ("戦術変更への積極性", "選手交代への積極性", "インテリジェンス"):
        team_info[field] = str(round(legacy_player_stat(float(team_info[field]))))
    tuner_targets = payload["チームチューナー"]["基準値ステータス"]
    for field, value in tuple(tuner_targets.items()):
        tuner_targets[field] = str(round(legacy_player_stat(float(value))))
    payload["能力値スケール"] = current_scale_metadata()
    issues = validate_payload(payload)
    if issues:
        raise ValueError(f"{name}: " + "; ".join(f"{issue.path}: {issue.message}" for issue in issues))
    return payload


def write_team(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_leagues() -> None:
    path = ROOT / "leagues.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    definitions = payload.setdefault("リーグ一覧", [])
    by_name = {str(entry.get("リーグ名")): entry for entry in definitions}
    for league_name, upper, color in (("Aリーグ", "", "#E35D5B"), ("Bリーグ", "Aリーグ", "#4C83D1")):
        if league_name not in by_name:
            entry = {"リーグ名": league_name, "表示色": color, "開幕日": 14, "最終節日": 330,
                     "上位リーグ": upper, "所属チーム": []}
            definitions.append(entry)
            by_name[league_name] = entry
        by_name[league_name]["上位リーグ"] = upper
    by_name["Aリーグ"]["所属チーム"] = [
        f"json:kadoka_original_A/{path.name}" for path in sorted(A_DIR.glob("*.json"), key=lambda item: item.name.casefold())
    ]
    by_name["Bリーグ"]["所属チーム"] = [
        f"json:kadoka_original_B/{path.name}" for path in sorted(B_DIR.glob("*.json"), key=lambda item: item.name.casefold())
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    A_DIR.mkdir(parents=True, exist_ok=True)
    B_DIR.mkdir(parents=True, exist_ok=True)
    for index, spec in enumerate(A_TEAMS):
        write_team(A_DIR / f"{spec[0]}.json", make_team("A", index, spec))
    for index, spec in enumerate(B_TEAMS):
        write_team(B_DIR / f"{spec[0]}.json", make_team("B", index, spec))
    update_leagues()
    print(f"A: {len(list(A_DIR.glob('*.json')))} teams / B: {len(list(B_DIR.glob('*.json')))} teams")


if __name__ == "__main__":
    main()
