"""Portable observation/operation contract, not a second football engine."""

import math

from scripts.core.settings import SPEED_OPTIONS
from scripts.core.simulation_runtime import FIXED_PHYSICS_DT

INPUT_FORMAT = "kadocalcio.match-contract-input"
TRACE_FORMAT = "kadocalcio.match-contract-trace"
REPORT_FORMAT = "kadocalcio.match-contract-diff"
VERSION = 1
OPERATION_KINDS = ("START", "STEP", "SET_SPEED", "PAUSE", "RESUME")
EXACT_NUMBERS = ("step", "operation_index", "sequence", "number", "direction",
                 "score", "shots", "home_score", "away_score", "home_shots", "away_shots",
                 "speed_multiplier", "foul_count", "card_count")
TOLERANCES = {"position": 1e-3, "velocity": 1e-3, "target": 1e-3, "spot": 1e-3,
              "target_point": 1e-3, "stamina": 1e-6, "default": 1e-8, "relative": 1e-9}


# {
#   責務: [is_json_integer: PythonとGodotで整数として交換できる値か確認する]
#   処理: [1: boolを除く数値型と安全範囲を検査; 2: 有限性と小数部の不在を確認]
#   引数: [value: JSON数値候補]
#   戻り値: [bool: 両実装で丸めなく交換できる整数ならTrue]
# }
def is_json_integer(value: object) -> bool:
    return type(value) in (int, float) and abs(value) < 9e15 and math.isfinite(value) and int(value) == value


# {
#   責務: [protocol_definition: Pythonの操作・固定更新・許容差を移植先の定義へ集約する]
#   処理: [1: 正本の定数を独立した辞書と配列へ構成する]
#   引数: []
#   戻り値: [dict: バージョン付きの交換規約]
# }
def protocol_definition() -> dict:
    return {"input_format": INPUT_FORMAT, "trace_format": TRACE_FORMAT,
            "report_format": REPORT_FORMAT, "version": VERSION,
            "operations": list(OPERATION_KINDS), "max_dt": FIXED_PHYSICS_DT,
            "speeds": list(SPEED_OPTIONS), "exact_numbers": list(EXACT_NUMBERS),
            "tolerances": dict(TOLERANCES)}
