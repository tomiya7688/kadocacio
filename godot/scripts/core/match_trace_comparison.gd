# {
#   責務: [MatchTraceComparison: 検証済み観測の最初の差を評価範囲付きで報告する]
#   フィールド: []
# }
class_name MatchTraceComparison
extends RefCounted
## First observed difference. Never reports unimplemented kernel parity as success.


# {
#   責務: [compare: 出自・状態・イベント・結果をカテゴリ別に比較する]
#   処理: [1: 読込の有効性を確認; 2: seedと操作順の観測を比較; 3: 最初の差と未評価の互換範囲を報告]
#   引数: [expected: 基準観測; actual: 比較対象観測]
#   戻り値: [Dictionary: 一致と相違情報。不正観測は一致扱いにしない]
# }
static func compare(expected: MatchTraceRecord, actual: MatchTraceRecord) -> Dictionary:
	if not expected.is_valid() or not actual.is_valid():
		return {"error": "invalid trace", "same_observations": false, "kernel_parity": "not_evaluated"}
	var left: Dictionary = expected.to_payload()
	var right: Dictionary = actual.to_payload()
	var left_source: Dictionary = left["source"] as Dictionary
	var right_source: Dictionary = right["source"] as Dictionary
	var report: Dictionary = {"format": MatchProtocol.values()["report_format"], "version": MatchProtocol.values()["version"], "same_observations": true, "kernel_parity": "not_evaluated",
		"scope": "contract_roundtrip" if left_source["execution"] == "contract_roundtrip" or right_source["execution"] == "contract_roundtrip" else "simulation_observations",
		"sources": {"expected": left_source, "actual": right_source}, "first_difference": null,
		"first_state_difference": null, "first_event_difference": null, "first_result_difference": null}
	var left_entries: Array = left["entries"] as Array
	var right_entries: Array = right["entries"] as Array
	if left_source["seed_text"] != right_source["seed_text"]:
		report["first_difference"] = {"path": "$.source.seed_text", "reason": "different_input_seed", "expected": left_source["seed_text"], "actual": right_source["seed_text"], "entry_index": null, "operation_index": null, "step": null, "category": "input"}
	for index: int in maxi(left_entries.size(), right_entries.size()):
		if index >= mini(left_entries.size(), right_entries.size()):
			if report["first_difference"] == null:
				report["first_difference"] = {"path": "$.entries[%d]" % index, "reason": "missing_entry", "expected": index < left_entries.size(), "actual": index < right_entries.size(), "entry_index": index, "step": null, "operation_index": index, "category": "trace"}
			break
		var left_entry: Dictionary = left_entries[index] as Dictionary
		var right_entry: Dictionary = right_entries[index] as Dictionary
		for pair: Array in [["snapshot", "state"], ["events", "event"], ["result", "result"]]:
			var field: String = pair[0] as String
			var category: String = pair[1] as String
			var difference: Variant = first_difference(left_entry[field], right_entry[field], "$.entries[%d].%s" % [index, field])
			if difference != null:
				var detail: Dictionary = difference as Dictionary
				detail.merge({"entry_index": index, "operation_index": index, "step": (left_entry["snapshot"] as Dictionary)["step"], "category": category})
				var key: String = "first_" + category + "_difference"
				if report[key] == null:
					report[key] = detail
				if report["first_difference"] == null:
					report["first_difference"] = detail
	report["same_observations"] = report["first_difference"] == null
	return report


# {
#   責務: [first_difference: JSON値を安定順と項目別許容差で比較する]
#   処理: [1: 辞書・配列を再帰比較; 2: 数値の厳密性と許容差を適用; 3: 最初の差を返す]
#   引数: [expected: 基準値; actual: 比較値; path: 現在のJSONパス]
#   戻り値: [Variant: 差分辞書。一致ならnull]
# }
static func first_difference(expected: Variant, actual: Variant, path: String = "$") -> Variant:
	if expected is Dictionary and actual is Dictionary:
		var left: Dictionary = expected as Dictionary
		var right: Dictionary = actual as Dictionary
		var keys: Array = left.keys()
		for key: Variant in right:
			if not keys.has(key):
				keys.append(key)
		keys.sort()
		for key: String in keys:
			var child: String = path + "." + key
			if not left.has(key) or not right.has(key):
				return {"path": child, "reason": "missing_key", "expected": left.get(key), "actual": right.get(key)}
			var difference: Variant = first_difference(left[key], right[key], child)
			if difference != null:
				return difference
		return null
	if expected is Array and actual is Array:
		var left: Array = expected as Array
		var right: Array = actual as Array
		if left.size() != right.size():
			return {"path": path, "reason": "length", "expected": left.size(), "actual": right.size()}
		for index: int in left.size():
			var difference: Variant = first_difference(left[index], right[index], "%s[%d]" % [path, index])
			if difference != null:
				return difference
		return null
	var equal: bool = false
	if (expected is int or expected is float) and (actual is int or actual is float):
		var tolerance: float = _tolerance(path)
		var relative: float = 0.0 if tolerance == 0 else (MatchProtocol.values()["tolerances"] as Dictionary)["relative"] as float
		equal = absf((expected as float) - (actual as float)) <= tolerance + relative * maxf(absf(expected as float), absf(actual as float))
	else:
		equal = typeof(expected) == typeof(actual) and expected == actual
	return null if equal else {"path": path, "reason": "value", "expected": expected, "actual": actual}


# {
#   責務: [_tolerance: 観測パスから厳密一致または許容差を選ぶ]
#   処理: [1: パス要素に厳密項目があればゼロ; 2: 末端に近い規約値または既定値を選択]
#   引数: [path: 比較中のJSONパス]
#   戻り値: [float: 絶対許容差]
# }
static func _tolerance(path: String) -> float:
	var fields: PackedStringArray = path.replace("[", ".").replace("]", "").split(".")
	for field: String in fields:
		if (MatchProtocol.values()["exact_numbers"] as Array).has(field):
			return 0.0
	var tolerances: Dictionary = MatchProtocol.values()["tolerances"] as Dictionary
	fields.reverse()
	for field: String in fields:
		if tolerances.has(field):
			return tolerances[field] as float
	return tolerances["default"] as float
