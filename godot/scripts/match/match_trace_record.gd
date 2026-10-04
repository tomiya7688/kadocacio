class_name MatchTraceRecord
extends RefCounted
## Detached observation trace; UI consumers never receive mutable engine objects.

var error: String = ""
var _payload: Dictionary = {}


static func read(payload: Variant) -> MatchTraceRecord:
	var result: MatchTraceRecord = MatchTraceRecord.new()
	result.error = _validate(payload)
	if result.error.is_empty():
		result._payload = (payload as Dictionary).duplicate(true)
	return result


func is_valid() -> bool:
	return error.is_empty() and not _payload.is_empty()


func to_payload() -> Dictionary:
	return _payload.duplicate(true)


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


static func _nonnegative_number(value: Variant) -> bool:
	return (value is int or value is float) and (value as float) >= 0 and (value as float) < 9e15 and is_finite(value as float)


static func _nonnegative_integer(value: Variant) -> bool:
	return MatchProtocol.is_integer(value) and (value as float) >= 0


static func _vector(value: Variant, size: int) -> bool:
	if not value is Array or (value as Array).size() != size:
		return false
	for component: Variant in value as Array:
		if not (component is int or component is float) or absf(component as float) >= 9e15 or not is_finite(component as float):
			return false
	return true


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
		return is_finite(value as float)
	else:
		return value == null or value is String or value is bool or value is int
	return true
