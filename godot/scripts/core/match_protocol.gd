class_name MatchProtocol
extends RefCounted
## Generated boundary policy; this is not a football engine or RNG implementation.

static var _values: Dictionary = {}


static func values() -> Dictionary:
	if _values.is_empty():
		_values = JSON.parse_string(FileAccess.get_file_as_string("res://data/match_contract.json")) as Dictionary
	return _values


static func is_integer(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(value as float) and floorf(value as float) == (value as float) and absf(value as float) < 9.0e15


static func is_seed_text(value: Variant) -> bool:
	if not value is String or value == "-0" or (value as String).trim_prefix("-").length() > 4096:
		return false
	var pattern: RegEx = RegEx.new()
	pattern.compile("^-?(0|[1-9][0-9]*)$")
	return pattern.search(value as String) != null
