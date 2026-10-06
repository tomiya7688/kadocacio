"""Portable first-divergence comparison; matching samples are not engine parity."""

import math

from scripts.core.match_protocol import EXACT_NUMBERS, REPORT_FORMAT, TRACE_FORMAT, TOLERANCES, VERSION, is_json_integer


# {
#   責務: [validate_trace: 比較前に観測列の形式・時系列・数値の交換可能性を検証する]
#   処理: [1: 出自と操作順を検証; 2: 状態・イベント・終了結果の整合を検証; 3: 全階層のJSON値を検証]
#   引数: [trace: 外部の観測列]
#   戻り値: [None: 正常なら終了。不正な境界値はValueError]
# }
def validate_trace(trace: object) -> None:
    if not isinstance(trace, dict) or trace.get("format") != TRACE_FORMAT or not is_json_integer(trace.get("version")) or trace["version"] != VERSION:
        raise ValueError("unsupported match trace")
    source = trace.get("source")
    if not isinstance(source, dict) or source.get("execution") not in ("simulation", "contract_roundtrip"):
        raise ValueError("trace must declare execution scope")
    if any(not isinstance(source.get(key), str) or not source[key] for key in ("implementation", "rng", "seed_text")):
        raise ValueError("missing source provenance")
    entries = trace.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("trace must contain observations")
    sequence = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not is_json_integer(entry.get("operation_index")) or entry["operation_index"] != index:
            raise ValueError("invalid operation index")
        _validate_snapshot(entry.get("snapshot"))
        events = entry.get("events")
        if not isinstance(events, list) or "result" not in entry or (entry["result"] is not None and not isinstance(entry["result"], dict)):
            raise ValueError("missing events/result boundary")
        if (entry["snapshot"]["status"]["state"] == "FULLTIME") != (entry["result"] is not None):
            raise ValueError("result must be present exactly at FULLTIME")
        for event in events:
            if not isinstance(event, dict) or not is_json_integer(event.get("sequence")) or event["sequence"] <= sequence or not _nonnegative_number(event.get("game_time")) or not _nonnegative_number(event.get("simulation_elapsed")) or not isinstance(event.get("text"), str):
                raise ValueError("invalid chronological event")
            sequence = event["sequence"]
        if entry["result"] is not None:
            result = entry["result"]
            if any(not _nonnegative_integer(result.get(key)) for key in ("home_score", "away_score", "home_shots", "away_shots")) or not _nonnegative_number(result.get("game_time")):
                raise ValueError("invalid result values")
    _validate_json(trace)


# {
#   責務: [_nonnegative_number: 時刻等に使える有限な非負数か判定する]
#   処理: [1: boolを除く数値型と交換範囲を確認; 2: 有限性を確認]
#   引数: [value: 検査値]
#   戻り値: [bool: 許容範囲ならTrue]
# }
def _nonnegative_number(value: object) -> bool:
    return type(value) in (int, float) and 0 <= value < 9e15 and math.isfinite(value)


# {
#   責務: [_nonnegative_integer: カウンタに使える交換可能な非負整数か判定する]
#   処理: [1: 共通整数制約と符号を確認する]
#   引数: [value: 検査値]
#   戻り値: [bool: 許容整数ならTrue]
# }
def _nonnegative_integer(value: object) -> bool:
    return is_json_integer(value) and value >= 0


# {
#   責務: [_vector: 座標を規定の成分数と有限数値範囲に制限する]
#   処理: [1: 配列長を確認; 2: 全成分の型・範囲・有限性を確認]
#   引数: [value: 座標候補; size: 必要な次元数]
#   戻り値: [bool: 全成分が有効ならTrue]
# }
def _vector(value: object, size: int) -> bool:
    return isinstance(value, list) and len(value) == size and all(type(component) in (int, float) and abs(component) < 9e15 and math.isfinite(component) for component in value)


# {
#   責務: [_validate_snapshot: 状態観測の必須項目と選手判断を検証する]
#   処理: [1: 更新番号・時計・得点を検査; 2: ボールと再開状態を検査; 3: 両チームの選手値を検査]
#   引数: [snapshot: 一操作後の状態観測]
#   戻り値: [None: 不正値はValueErrorで拒否する]
# }
def _validate_snapshot(snapshot: object) -> None:
    if not isinstance(snapshot, dict) or not _nonnegative_integer(snapshot.get("step")):
        raise ValueError("invalid snapshot step")
    for key in ("status", "ball", "home", "away"):
        if not isinstance(snapshot.get(key), dict):
            raise ValueError("missing observation: " + key)
    status, ball = snapshot["status"], snapshot["ball"]
    if not isinstance(status.get("state"), str) or not status["state"] or not _nonnegative_number(status.get("game_time")) or any(not _nonnegative_integer(status.get(key)) for key in ("home_score", "away_score")):
        raise ValueError("invalid clock/score observation")
    if type(snapshot.get("paused")) is not bool or not _nonnegative_number(snapshot.get("simulation_elapsed")):
        raise ValueError("invalid simulation clock/pause observation")
    if "owner" not in ball or (ball["owner"] is not None and (not isinstance(ball["owner"], str) or not ball["owner"])) or not _vector(ball.get("position"), 3) or not _vector(ball.get("velocity"), 3):
        raise ValueError("invalid ball observation")
    if "restart" not in snapshot or (snapshot["restart"] is not None and not isinstance(snapshot["restart"], dict)):
        raise ValueError("invalid restart observation")
    for side in ("home", "away"):
        players = snapshot[side].get("players")
        if not isinstance(players, list):
            raise ValueError("missing player decisions")
        for player in players:
            if not isinstance(player, dict) or any(not isinstance(player.get(key), str) or not player[key] for key in ("id", "command")) or not _vector(player.get("position"), 3) or not _vector(player.get("target"), 2) or not _nonnegative_number(player.get("stamina")):
                raise ValueError("invalid player decision")


# {
#   責務: [_validate_json: 追加項目を含む全階層から交換不能なJSON値を排除する]
#   処理: [1: 文字列キーの辞書と配列を再帰検査; 2: 整数範囲・浮動小数の有限性・型を確認]
#   引数: [value: 観測値またはその子要素]
#   戻り値: [None: 異常時は比較演算の前にValueError]
# }
def _validate_json(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON keys must be strings")
            _validate_json(child)
    elif isinstance(value, list):
        for child in value:
            _validate_json(child)
    elif type(value) is int and not is_json_integer(value):
        raise ValueError("observation integer is outside portable range")
    elif isinstance(value, float) and (not math.isfinite(value) or abs(value) >= 9e15):
        raise ValueError("nonfinite or out-of-range observation")
    elif value is not None and type(value) not in (str, bool, int, float):
        raise ValueError("observation must contain only JSON values")


# {
#   責務: [first_difference: 検証済みJSON値の最初の差を項目別許容差で特定する]
#   処理: [1: 辞書・配列を安定順で再帰比較; 2: 数値は厳密項目と許容差を区別; 3: 差のパスと値を返す]
#   引数: [expected: 基準値; actual: 比較値; path: 現在のJSONパス]
#   戻り値: [dictまたはNone: 最初の相違情報。一致ならNone]
# }
def first_difference(expected: object, actual: object, path: str = "$") -> dict | None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(expected.keys() | actual.keys()):
            child_path = f"{path}.{key}"
            if key not in expected or key not in actual:
                return {"path": child_path, "reason": "missing_key", "expected": expected.get(key), "actual": actual.get(key)}
            difference = first_difference(expected[key], actual[key], child_path)
            if difference:
                return difference
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return {"path": path, "reason": "length", "expected": len(expected), "actual": len(actual)}
        for index, (left, right) in enumerate(zip(expected, actual)):
            difference = first_difference(left, right, f"{path}[{index}]")
            if difference:
                return difference
        return None
    if type(expected) in (int, float) and type(actual) in (int, float):
        fields = path.replace("[", ".").replace("]", "").split(".")
        tolerance = 0.0 if any(field in EXACT_NUMBERS for field in fields) else next((TOLERANCES[field] for field in reversed(fields) if field in TOLERANCES), TOLERANCES["default"])
        relative = 0.0 if tolerance == 0 else TOLERANCES["relative"] * max(abs(expected), abs(actual))
        equal = abs(expected - actual) <= tolerance + relative
    else:
        equal = type(expected) is type(actual) and expected == actual
    return None if equal else {"path": path, "reason": "value", "expected": expected, "actual": actual}


# {
#   責務: [compare_traces: 状態・イベント・結果の差を互換認定と区別した報告へまとめる]
#   処理: [1: 両観測列を検証; 2: seedと各観測カテゴリを比較; 3: 最初の相違と評価範囲を記録]
#   引数: [expected: 基準観測列; actual: 比較する観測列]
#   戻り値: [report: 観測一致の報告。試合核互換は常に未評価]
# }
def compare_traces(expected: dict, actual: dict) -> dict:
    validate_trace(expected)
    validate_trace(actual)
    report = {"format": REPORT_FORMAT, "version": VERSION, "same_observations": True,
              "kernel_parity": "not_evaluated", "scope": "contract_roundtrip" if actual["source"]["execution"] == "contract_roundtrip" or expected["source"]["execution"] == "contract_roundtrip" else "simulation_observations",
              "sources": {"expected": expected["source"], "actual": actual["source"]},
              "first_difference": None, "first_state_difference": None,
              "first_event_difference": None, "first_result_difference": None}
    left, right = expected["entries"], actual["entries"]
    if expected["source"]["seed_text"] != actual["source"]["seed_text"]:
        report["first_difference"] = {"path": "$.source.seed_text", "reason": "different_input_seed", "expected": expected["source"]["seed_text"], "actual": actual["source"]["seed_text"], "entry_index": None, "operation_index": None, "step": None, "category": "input"}
    for index in range(max(len(left), len(right))):
        if index >= min(len(left), len(right)):
            difference = {"path": f"$.entries[{index}]", "reason": "missing_entry", "expected": index < len(left), "actual": index < len(right), "entry_index": index, "step": None, "operation_index": index, "category": "trace"}
            report["first_difference"] = report["first_difference"] or difference
            break
        for field, category in (("snapshot", "state"), ("events", "event"), ("result", "result")):
            difference = first_difference(left[index][field], right[index][field], f"$.entries[{index}].{field}")
            if difference:
                difference.update(entry_index=index, operation_index=index, step=left[index]["snapshot"]["step"], category=category)
                key = f"first_{category}_difference"
                report[key] = report[key] or difference
                report["first_difference"] = report["first_difference"] or difference
    report["same_observations"] = report["first_difference"] is None
    return report
