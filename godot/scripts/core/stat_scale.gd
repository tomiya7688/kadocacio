class_name StatScale
extends RefCounted
## Node-free scale math; editable bounds/defaults/grades come only from Python export.


static func bounds(payload: Dictionary) -> Array[float]:
	var scale: Dictionary = TeamContract.values()["scale"] as Dictionary
	var legacy: Array[float] = [scale["legacy_min"] as float, scale["legacy_max"] as float]
	var metadata: Variant = payload.get(scale["metadata_key"])
	if not metadata is Dictionary:
		return legacy
	var current: Dictionary = scale["current"] as Dictionary
	var low: float = JsonValue.number((metadata as Dictionary).get("最小", current["最小"]), NAN)
	var high: float = JsonValue.number((metadata as Dictionary).get("最大", current["最大"]), NAN)
	if not is_finite(low) or not is_finite(high) or high <= low:
		return legacy
	return [low, high]


static func current_bounds() -> Array[float]:
	var current: Dictionary = (TeamContract.values()["scale"] as Dictionary)["current"] as Dictionary
	return [current["最小"] as float, current["最大"] as float]


static func normalize(value: Variant, fallback: float) -> float:
	var limits: Array[float] = current_bounds()
	var numeric: float = JsonValue.python_clamp(JsonValue.number(value, fallback), limits[0], limits[1])
	return (numeric - limits[0]) / maxf(1.0, limits[1] - limits[0])


static func remap(value: Variant, source: Array[float]) -> int:
	var numeric: float = JsonValue.number(value, source[0])
	if not is_finite(numeric):
		numeric = source[0]
	var unit: float = (clampf(numeric, source[0], source[1]) - source[0]) / maxf(1.0, source[1] - source[0])
	var current: Array[float] = current_bounds()
	return JsonValue.round_even(current[0] + clampf(unit, 0.0, 1.0) * (current[1] - current[0]))


static func percentage(value: Variant, fallback: float = 50.0) -> float:
	return JsonValue.python_clamp(JsonValue.number(value, fallback), 0.0, 100.0) / 100.0


static func grade(value: float) -> String:
	var rows: Array = (TeamContract.values()["scale"] as Dictionary)["grades"] as Array
	for item: Variant in rows:
		var row: Dictionary = item as Dictionary
		if value >= (row["minimum"] as float):
			return row["rank"] as String
	return "E-"
