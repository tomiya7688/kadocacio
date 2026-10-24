class_name MatchEventLog
extends RefCounted
## Existing observable message contract, not yet all structured domain events.

var _events: Array[Dictionary] = []


func append(text: String, clock: MatchClock) -> void:
	_events.append({"sequence": _events.size() + 1, "game_time": clock.game_time,
		"simulation_elapsed": clock.simulation_elapsed, "text": text})


func after(sequence: int) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for item: Dictionary in _events:
		if (item["sequence"] as int) > sequence:
			result.append(item.duplicate(true))
	return result
