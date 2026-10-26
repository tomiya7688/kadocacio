"""Versioned, lossless input records for the developer match parity checker."""

from __future__ import annotations

import json

from scripts.core.simulation_runtime import FIXED_PHYSICS_DT


INPUT_FORMAT = "kadocalcio.match-repro-input"
INPUT_VERSION = 1


# {
#   責務: [create_input_record: 正規化済みチームと試合条件から独立した再現入力v1を作る]
#   処理: [1: 固定ステップと外部操作なしの入力を組み立てる; 2: 非有限値を拒否するJSON往復で元データから分離する; 3: 復元検証を通してから記録を返す]
#   引数: [home・away: 正規化済み両チーム辞書; settings: seed・max_steps・venue_mode・ai_rethink_multiplier等の試合条件]
#   戻り値: [dict: 元データを参照しない記録。不正形式・設定はValueError、JSON非対応値はTypeErrorとなる]
# }
def create_input_record(home: dict, away: dict, **settings) -> dict:
    """Detach normalized inputs without rounding player or manager values."""
    # 小数を丸めずに保存し、tuple等はJSONで扱える配列へ揃える。
    record = json.loads(
        json.dumps(
            {
                "format": INPUT_FORMAT,
                "version": INPUT_VERSION,
                "settings": {"fixed_physics_dt": FIXED_PHYSICS_DT, **settings},
                "teams": {"home": home, "away": away},
                "commands": [],
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    # 記録できても再実行できない条件を返さないよう、公開復元経路で検証する。
    restore_input_record(record)
    return record


# {
#   責務: [_validate_settings: 再現入力の設定型・固定ステップ・会場・判断倍率を検証する]
#   処理: [1: 辞書と整数seed・正の更新上限を確認する; 2: 固定ステップと会場の互換性を確認する; 3: boolを除く数値で倍率が閉区間0.5〜3.0にあるか確認する]
#   引数: [settings: 外部JSONから読んだ設定値]
#   戻り値: [None: 正常時は変更しない。不正型・非有限・範囲外はValueError]
# }
def _validate_settings(settings: object) -> None:
    # boolはintの派生型なので、seedや更新回数へ暗黙に受け入れない。
    if not isinstance(settings, dict):
        raise ValueError("input settings must be an object")
    for key in ("seed", "max_steps"):
        if type(settings.get(key)) is not int:
            raise ValueError(f"input {key} must be an integer")
    if settings["max_steps"] < 1:
        raise ValueError("input max_steps must be positive")
    # 異なる物理幅や未知の会場を、近い値や既定値へ黙って置き換えない。
    if settings.get("fixed_physics_dt") != FIXED_PHYSICS_DT:
        raise ValueError("input fixed_physics_dt is incompatible with this engine")
    if settings.get("venue_mode") not in ("HOME", "AWAY", "NEUTRAL"):
        raise ValueError("input venue_mode must be HOME, AWAY or NEUTRAL")
    multiplier = settings.get("ai_rethink_multiplier")
    # 範囲比較だけでNaN・無限大も拒否し、巨大整数をfloatへ変換して例外を漏らさない。
    if type(multiplier) not in (int, float) or not 0.5 <= multiplier <= 3.0:
        raise ValueError("input ai_rethink_multiplier must be finite and in 0.5..3.0")


# {
#   責務: [_restore_team: 記録のチーム識別・先発・色形式を確認し色を演算用tupleへ戻す]
#   処理: [1: 辞書と必須識別子・空でない先発配列を検証する; 2: 必須色と存在する副色をRGB範囲で検証する; 3: 色をtupleへ置き換える]
#   引数: [team: 呼出し元が複製したチーム値; side: エラー文の対象名]
#   戻り値: [dict: 渡された辞書の色を復元した同じ辞書。不正形式はValueError。全選手能力の網羅検証ではない]
# }
def _restore_team(team: object, side: str) -> dict:
    # 外部チームファイルの探索はせず、記録内の必要な形を検証する。
    if not isinstance(team, dict):
        raise ValueError(f"input {side} team must be an object")
    for key in ("id", "name", "short"):
        if not isinstance(team.get(key), str) or not team[key]:
            raise ValueError(f"input {side} team requires {key}")
    if not isinstance(team.get("starters"), list) or not team["starters"]:
        raise ValueError(f"input {side} team requires starters")
    # 副色の省略は既存入力と互換にし、指定された色はboolも含め厳密に確認する。
    for key in ("primary", "secondary"):
        if key == "secondary" and key not in team:
            continue
        color = team.get(key)
        if not isinstance(color, list) or len(color) != 3:
            raise ValueError(f"input {side} team requires an RGB {key}")
        if any(type(channel) is not int or not 0 <= channel <= 255 for channel in color):
            raise ValueError(f"input {side} team has invalid RGB {key}")
        # Match compares kit colours with tuple constants when resolving clashes.
        team[key] = tuple(color)
    return team


# {
#   責務: [restore_input_record: 再現入力v1を検証し元記録から独立したMatch引数へ復元する]
#   処理: [1: 形式・厳密な版番号・外部操作なしを検証する; 2: 設定を検証しJSONで深く複製する; 3: 両チームと色を復元する; 4: 許可する試合設定だけを抽出する]
#   引数: [record: 外部から読んだ再現入力。通常のチームJSONや比較レポート全体とは別形式]
#   戻り値: [tuple: home・away・settingsの順。不正な入力はValueError、JSON非対応値はTypeError。元記録を変更しない]
# }
def restore_input_record(record: object) -> tuple[dict, dict, dict]:
    """Validate a record and return independent Match inputs without discovery."""
    if not isinstance(record, dict) or record.get("format") != INPUT_FORMAT:
        raise ValueError("not a match reproduction input record")
    if type(record.get("version")) is not int or record["version"] != INPUT_VERSION:
        raise ValueError("unsupported match reproduction input version")
    # Never silently replay a future record while discarding its commands.
    if record.get("commands") != []:
        raise ValueError("this input version supports autonomous matches with no external commands only")
    # 読込後のtuple変換が元記録へ書き戻されないよう、検証後に分離する。
    _validate_settings(record.get("settings"))
    copy = json.loads(json.dumps(record, ensure_ascii=False, allow_nan=False))
    teams = copy.get("teams")
    if not isinstance(teams, dict):
        raise ValueError("input teams must be an object")
    home = _restore_team(teams.get("home"), "home")
    away = _restore_team(teams.get("away"), "away")
    # 固定ステップや未知の追加キーをMatchの任意キーワードへ流さない。
    settings = copy["settings"]
    return (
        home,
        away,
        {
            key: settings[key]
            for key in (
                "seed",
                "max_steps",
                "venue_mode",
                "ai_rethink_multiplier",
            )
        },
    )
