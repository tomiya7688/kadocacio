class_name TeamContract
extends RefCounted
## Shared generated contract; never reads Python or imports UI at game runtime.

static var _data: Dictionary = {}


static func values() -> Dictionary:
	if _data.is_empty():
		var parser: JSON = JSON.new()
		var status: Error = parser.parse(FileAccess.get_file_as_string("res://data/team_contract.json"))
		if status != OK or not parser.data is Dictionary:
			push_error("Godot team contract is missing or invalid")
			return {}
		_data = parser.data as Dictionary
	return _data
