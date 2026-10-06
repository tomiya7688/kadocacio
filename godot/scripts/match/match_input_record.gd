# {
#   責務: [MatchInputRecord: 再現条件と操作列を検証し独立した試合入力として保持する]
#   フィールド: [error: 不正入力の診断; _payload: 正常入力の独立コピー]
# }
class_name MatchInputRecord
extends RefCounted
## Versioned input reader. Does not start/replay a fabricated match.

var error: String = ""
var _payload: Dictionary = {}


# {
#   責務: [read: 外部入力を検証して読込結果を生成する]
#   処理: [1: 入力制約を検査; 2: 成功時だけ元値を深く複製]
#   引数: [payload: 外部JSON値]
#   戻り値: [MatchInputRecord: 入力またはerrorを保持する読込結果]
# }
static func read(payload: Variant) -> MatchInputRecord:
	var result: MatchInputRecord = MatchInputRecord.new()
	result.error = _validate(payload)
	if result.error.is_empty():
		result._payload = (payload as Dictionary).duplicate(true)
	return result


# {
#   責務: [is_valid: 演算入口へ渡せる読込済み入力か確認する]
#   処理: [1: 診断と保持値の有無を確認]
#   引数: []
#   戻り値: [bool: 正常読込済みならtrue]
# }
func is_valid() -> bool:
	return error.is_empty() and not _payload.is_empty()


# {
#   責務: [to_payload: 消費側に内部入力の可変参照を渡さない]
#   処理: [1: 保持入力を深く複製]
#   引数: []
#   戻り値: [Dictionary: 独立した契約入力]
# }
func to_payload() -> Dictionary:
	return _payload.duplicate(true)


# {
#   責務: [_validate: 再現入力と操作列を両実装で共通の制約へ制限する]
#   処理: [1: 形式・seed・予算・会場・判断頻度を検査; 2: チームを検査; 3: START順序とSTEP予算を検査]
#   引数: [payload: 外部入力候補]
#   戻り値: [String: 最初の診断。正常なら空文字]
# }
static func _validate(payload: Variant) -> String:
	if not payload is Dictionary:
		return "unsupported match contract input"
	var data: Dictionary = payload as Dictionary
	if data.get("format") != MatchProtocol.values()["input_format"] or not MatchProtocol.is_integer(data.get("version")) or data["version"] != MatchProtocol.values()["version"]:
		return "unsupported match contract input"
	if not data.get("repro_input") is Dictionary:
		return "missing reproduction input"
	var repro: Dictionary = data["repro_input"] as Dictionary
	if repro.get("format") != "kadocalcio.match-repro-input" or not MatchProtocol.is_integer(repro.get("version")) or repro["version"] != 1 or repro.get("commands") != []:
		return "unsupported reproduction input"
	if not repro.get("settings") is Dictionary or not repro.get("teams") is Dictionary:
		return "missing settings/teams"
	var settings: Dictionary = repro["settings"] as Dictionary
	if not MatchProtocol.is_seed_text(settings.get("seed")):
		return "seed must be canonical decimal text"
	if not MatchProtocol.is_integer(settings.get("max_steps")) or (settings["max_steps"] as float) < 1:
		return "invalid step budget"
	if settings.get("fixed_physics_dt") != MatchProtocol.values()["max_dt"] or not ["HOME", "AWAY", "NEUTRAL"].has(settings.get("venue_mode")):
		return "incompatible fixed step/venue"
	var multiplier: Variant = settings.get("ai_rethink_multiplier")
	if not (multiplier is int or multiplier is float) or not is_finite(multiplier as float) or (multiplier as float) < 0.5 or (multiplier as float) > 3:
		return "invalid AI frequency"
	for side: String in ["home", "away"]:
		var team_error: String = _validate_team((repro["teams"] as Dictionary).get(side))
		if not team_error.is_empty():
			return side + ": " + team_error
	if not data.get("operations") is Array or (data["operations"] as Array).is_empty():
		return "operations must start with START"
	var start_count: int = 0
	var steps: int = 0
	for item: Variant in data["operations"] as Array:
		var operation: MatchOperation = MatchOperation.read(item)
		if not operation.is_valid():
			return operation.error
		start_count += 1 if operation.kind == "START" else 0
		steps += 1 if operation.kind == "STEP" else 0
	var first: MatchOperation = MatchOperation.read((data["operations"] as Array)[0])
	if start_count != 1 or first.kind != "START":
		return "exactly one leading START required"
	return "physics step budget exceeded" if steps > (settings["max_steps"] as int) else ""


# {
#   責務: [_validate_team: 境界で必要なチーム識別・先発・色の形式を確認する]
#   処理: [1: ID・名称・先発配列を確認; 2: 必要なRGB成分の整数範囲を確認]
#   引数: [payload: 一チームの選択値。能力内容の意味検証は別の読込責務]
#   戻り値: [String: 不正項目の診断。正常なら空文字]
# }
static func _validate_team(payload: Variant) -> String:
	if not payload is Dictionary:
		return "missing team"
	var team: Dictionary = payload as Dictionary
	for key: String in ["id", "name", "short"]:
		if not team.get(key) is String or (team[key] as String).is_empty():
			return "missing identity"
	if not team.get("starters") is Array or (team["starters"] as Array).is_empty():
		return "missing starters"
	for key: String in ["primary", "secondary"]:
		if key == "secondary" and not team.has(key):
			continue
		if not team.get(key) is Array or (team[key] as Array).size() != 3:
			return "invalid RGB color"
		for channel: Variant in team[key] as Array:
			if not MatchProtocol.is_integer(channel) or (channel as float) < 0 or (channel as float) > 255:
				return "invalid RGB color"
	return ""
