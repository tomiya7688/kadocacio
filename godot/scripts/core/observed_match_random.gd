class_name ObservedMatchRandom
extends PythonRandomStream
## Opt-in primitive draw audit. Observation/rendering never consumes this stream.

var enabled: bool = false
var purpose: String = "construct"
var step: int = 0
var _events: Array[Dictionary] = []


func random() -> float:
	var before: int = word_count
	var value: float = super.random()
	_record("random", [], value, before)
	return value


func getrandbits(bits: int) -> int:
	var before: int = word_count
	var value: int = super.getrandbits(bits)
	_record("getrandbits", [bits], value, before)
	return value


func _record(method: String, arguments: Array, value: Variant, before: int) -> void:
	if enabled:
		_events.append({"sequence": _events.size() + 1, "step": step, "purpose": purpose,
			"method": method, "arguments": arguments, "value": value,
			"word_before": before, "word_after": word_count})
		if method == "getrandbits":
			_events[-1]["bit_value"] = value


func history() -> Array[Dictionary]:
	return _events.duplicate(true)
