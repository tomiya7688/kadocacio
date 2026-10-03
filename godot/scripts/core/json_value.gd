class_name JsonValue
extends RefCounted
## Shared Python-compatible scalar conversion, including strict integer strings.


static func number(value: Variant, fallback: float) -> float:
	if value is bool:
		return 1.0 if (value as bool) else 0.0
	if value is int or value is float:
		return value as float
	if value is String:
		var text: String = (value as String).strip_edges()
		match text.to_lower():
			"nan", "+nan", "-nan": return NAN
			"inf", "+inf", "infinity", "+infinity": return INF
			"-inf", "-infinity": return -INF
		if text.is_valid_float():
			return text.to_float()
	return fallback


static func integer_valid(value: Variant) -> bool:
	if value is bool or value is int:
		return true
	if value is float:
		return is_finite(value as float) and absf(value as float) < 9.0e18
	return value is String and (value as String).strip_edges().is_valid_int()


static func integer(value: Variant) -> int:
	if value is bool:
		return 1 if (value as bool) else 0
	if value is String:
		return (value as String).strip_edges().to_int()
	return value as int


static func text(value: Variant) -> String:
	if value == null:
		return "None"
	if value is bool:
		return "True" if (value as bool) else "False"
	return str(value)


static func python_clamp(value: float, minimum: float, maximum: float) -> float:
	# Python min(maximum, nan) chooses the first operand. Preserve reference behavior.
	return maximum if is_nan(value) else clampf(value, minimum, maximum)


static func round_even(value: float) -> int:
	var base: float = floorf(value)
	if value - base == 0.5:
		return int(base) if int(base) % 2 == 0 else int(base) + 1
	return int(roundf(value))
