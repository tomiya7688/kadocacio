class_name UiContract
extends RefCounted
## Derived display/performance choices. Python is only needed when regenerating.

static var _values: Dictionary = {}


static func values() -> Dictionary:
	if _values.is_empty():
		_values = JSON.parse_string(FileAccess.get_file_as_string("res://data/ui_contract.json")) as Dictionary
	return _values
