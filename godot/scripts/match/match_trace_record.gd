# {
#   責務: [MatchTraceRecord: 状態・イベント・終了結果の観測列を検証し独立保持する]
#   フィールド: [error: 検証失敗理由; _payload: 検証済み観測列の複製]
# }
class_name MatchTraceRecord
extends RefCounted
## Detached observation trace; UI consumers never receive mutable engine objects.

var error: String = ""
var _payload: Dictionary = {}


# {
#   責務: [read: 外部観測列を検証して読込結果を作る]
#   処理: [1: 観測制約を検査; 2: 正常入力だけを深く複製]
#   引数: [payload: 外部JSON値]
#   戻り値: [MatchTraceRecord: 正常観測またはerrorを保持する結果]
# }
static func read(payload: Variant) -> MatchTraceRecord:
	var result: MatchTraceRecord = MatchTraceRecord.new()
	result.error = _validate(payload)
	if result.error.is_empty():
		result._payload = (payload as Dictionary).duplicate(true)
	return result


# {
#   責務: [is_valid: 比較可能な観測列を保持しているか確認する]
#   処理: [1: 診断と保持値の有無を確認]
#   引数: []
#   戻り値: [bool: 正常読込済みならtrue]
# }
func is_valid() -> bool:
	return error.is_empty() and not _payload.is_empty()


# {
#   責務: [to_payload: 観測消費側が内部の保持値を変更できないようにする]
#   処理: [1: 観測辞書を深く複製]
#   引数: []
#   戻り値: [Dictionary: 独立した観測列]
# }
func to_payload() -> Dictionary:
	return _payload.duplicate(true)


# {
#   責務: [_validate: 観測列の出自・順序・結果と状態の整合性を保証する]
#   処理: [1: 形式と出自を検査; 2: 操作順・状態・イベント・結果を検査; 3: 全階層のJSON値を確認]
#   引数: [payload: 外部観測候補]
#   戻り値: [String: 最初の失敗理由。正常なら空文字]
# }
static func _validate(payload: Variant) -> String:
	if not payload is Dictionary:
		return "unsupported match trace"
	var data: Dictionary = payload as Dictionary
	if data.get("format") != MatchProtocol.values()["trace_format"] or not MatchProtocol.is_integer(data.get("version")) or data["version"] != MatchProtocol.values()["version"]:
		return "unsupported match trace"
	if not data.get("source") is Dictionary or not ["simulation", "contract_roundtrip"].has((data["source"] as Dictionary).get("execution")):
		return "trace must declare execution scope"
	for key: String in ["implementation", "rng", "seed_text"]:
		var source: Dictionary = data["source"] as Dictionary
		if not source.get(key) is String or (source[key] as String).is_empty():
			return "missing source provenance"
	if not data.get("entries") is Array or (data["entries"] as Array).is_empty():
		return "missing observations"
	var sequence: int = 0
	var entries: Array = data["entries"] as Array
	for index: int in entries.size():
		if not entries[index] is Dictionary:
			return "invalid entry"
		var entry: Dictionary = entries[index] as Dictionary
		if not MatchProtocol.is_integer(entry.get("operation_index")) or (entry["operation_index"] as int) != index:
			return "invalid operation index"
		var observation_error: String = _validate_snapshot(entry.get("snapshot"))
		if not observation_error.is_empty():
			return observation_error
		if not entry.get("events") is Array or not entry.has("result") or (entry["result"] != null and not entry["result"] is Dictionary):
			return "missing events/result boundary"
		if ((entry["snapshot"] as Dictionary)["status"]["state"] == "FULLTIME") != (entry["result"] != null):
			return "result must be present exactly at FULLTIME"
		for item: Variant in entry["events"] as Array:
			if not item is Dictionary:
				return "invalid event"
			var event: Dictionary = item as Dictionary
			if not MatchProtocol.is_integer(event.get("sequence")) or (event["sequence"] as int) <= sequence or not _nonnegative_number(event.get("game_time")) or not _nonnegative_number(event.get("simulation_elapsed")) or not event.get("text") is String:
				return "invalid chronological event"
			sequence = event["sequence"] as int
		if entry["result"] != null:
			var final_result: Dictionary = entry["result"] as Dictionary
			for key: String in ["home_score", "away_score", "home_shots", "away_shots"]:
				if not _nonnegative_integer(final_result.get(key)):
					return "invalid result values"
			if not _nonnegative_number(final_result.get("game_time")):
				return "invalid result clock"
	return "" if _finite_json(data) else "observation must contain finite JSON values"


# {
#   責務: [_validate_snapshot: 状態観測の必須値と選手判断の形式を確認する]
#   処理: [1: 更新番号と時計・得点を検査; 2: ボールと再開状態を検査; 3: 両チームの選手値を検査]
#   引数: [payload: 一操作後の状態]
#   戻り値: [String: 不正項目の診断。正常なら空文字]
# }
static func _validate_snapshot(payload: Variant) -> String:
	if not payload is Dictionary:
		return "missing snapshot"
	var snapshot: Dictionary = payload as Dictionary
	if not _nonnegative_integer(snapshot.get("step")):
		return "invalid snapshot step"
	for key: String in ["status", "ball", "home", "away"]:
		if not snapshot.get(key) is Dictionary:
			return "missing observation: " + key
	var status: Dictionary = snapshot["status"] as Dictionary
	var ball: Dictionary = snapshot["ball"] as Dictionary
	if not status.get("state") is String or (status["state"] as String).is_empty() or not _nonnegative_number(status.get("game_time")) or not _nonnegative_integer(status.get("home_score")) or not _nonnegative_integer(status.get("away_score")):
		return "invalid clock/score observation"
	if not snapshot.get("paused") is bool or not _nonnegative_number(snapshot.get("simulation_elapsed")):
		return "invalid simulation clock/pause observation"
	if not ball.has("owner") or (ball["owner"] != null and (not ball["owner"] is String or (ball["owner"] as String).is_empty())) or not _vector(ball.get("position"), 3) or not _vector(ball.get("velocity"), 3):
		return "invalid ball observation"
	if not snapshot.has("restart") or (snapshot["restart"] != null and not snapshot["restart"] is Dictionary):
		return "invalid restart observation"
	for side: String in ["home", "away"]:
		var team: Dictionary = snapshot[side] as Dictionary
		if not team.get("players") is Array:
			return "missing player decisions"
		for player: Variant in team["players"] as Array:
			if not player is Dictionary:
				return "invalid player decision"
			var decision: Dictionary = player as Dictionary
			for key: String in ["id", "command"]:
				if not decision.get(key) is String or (decision[key] as String).is_empty():
					return "invalid player identity/command"
			if not _vector(decision.get("position"), 3) or not _vector(decision.get("target"), 2) or not _nonnegative_number(decision.get("stamina")):
				return "invalid player decision values"
	return ""


# {
#   責務: [_nonnegative_number: 時計等の有限な非負数か判定する]
#   処理: [1: 型・符号・交換範囲・有限性を確認]
#   引数: [value: 数値候補]
#   戻り値: [bool: 共通制約を満たすならtrue]
# }
static func _nonnegative_number(value: Variant) -> bool:
	return (value is int or value is float) and (value as float) >= 0 and (value as float) < 9e15 and is_finite(value as float)


# {
#   責務: [_nonnegative_integer: カウンタに使える非負整数か判定する]
#   処理: [1: 規約の整数制約と符号を確認]
#   引数: [value: カウンタ候補]
#   戻り値: [bool: 共通制約を満たすならtrue]
# }
static func _nonnegative_integer(value: Variant) -> bool:
	return MatchProtocol.is_integer(value) and (value as float) >= 0


# {
#   責務: [_vector: 座標を指定次元と有限な交換範囲に制限する]
#   処理: [1: 配列長を確認; 2: 全成分の型と範囲・有限性を確認]
#   引数: [value: 座標候補; size: 必要な成分数]
#   戻り値: [bool: 有効な座標ならtrue]
# }
static func _vector(value: Variant, size: int) -> bool:
	if not value is Array or (value as Array).size() != size:
		return false
	for component: Variant in value as Array:
		if not (component is int or component is float) or absf(component as float) >= 9e15 or not is_finite(component as float):
			return false
	return true


# {
#   責務: [_finite_json: 追加項目を含む全階層の交換不能値を検出する]
#   処理: [1: 辞書キーと子要素を再帰検査; 2: 配列を再帰検査; 3: 数値範囲・有限性とJSON型を確認]
#   引数: [value: 観測またはその子要素]
#   戻り値: [bool: 全階層が交換可能ならtrue]
# }
static func _finite_json(value: Variant) -> bool:
	if value is Dictionary:
		var dictionary: Dictionary = value as Dictionary
		for key: Variant in dictionary:
			if not key is String or not _finite_json(dictionary[key]):
				return false
	elif value is Array:
		for item: Variant in value as Array:
			if not _finite_json(item):
				return false
	elif value is float:
		return is_finite(value as float) and absf(value as float) < 9e15
	elif value is int:
		return MatchProtocol.is_integer(value)
	else:
		return value == null or value is String or value is bool
	return true
