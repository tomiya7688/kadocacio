class_name MatchOperation
extends RefCounted
## Detached validated host operation, not a player's AI action.

var error: String = ""
var kind: String = ""
var _payload: Dictionary = {}


static func read(payload: Variant) -> MatchOperation:
	var result: MatchOperation = MatchOperation.new()
	if not payload is Dictionary:
		result.error = "unknown match operation"
		return result
	var data: Dictionary = payload as Dictionary
	if not data.get("kind") is String or not (MatchProtocol.values()["operations"] as Array).has(data["kind"]):
		result.error = "unknown match operation"
		return result
	result.kind = data["kind"] as String
	var field: String = "dt" if result.kind == "STEP" else "value" if result.kind == "SET_SPEED" else ""
	if data.size() != (1 if field.is_empty() else 2) or (not field.is_empty() and not data.has(field)):
		result.error = "unexpected/missing operation fields"
		return result
	if result.kind == "STEP":
		var value: Variant = data["dt"]
		if not (value is int or value is float) or not is_finite(value as float) or (value as float) <= 0 or (value as float) > (MatchProtocol.values()["max_dt"] as float):
			result.error = "invalid STEP dt"
			return result
	if result.kind == "SET_SPEED" and (not MatchProtocol.is_integer(data["value"]) or not (MatchProtocol.values()["speeds"] as Array).has(data["value"] as float)):
		result.error = "unsupported speed"
		return result
	result._payload = data.duplicate(true)
	return result


func is_valid() -> bool:
	return error.is_empty() and not _payload.is_empty()


func to_payload() -> Dictionary:
	return _payload.duplicate(true)
