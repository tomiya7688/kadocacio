class_name PlayerDefinition
extends RefCounted
## Save-local raw parameters plus derived normalized values; no runtime motion/state.

var name: String
var number: int
var position_x: int
var position_y: int
var slot: Variant = null
var raw: Dictionary = {}
var normalized_stats: Dictionary = {}
var player_type: String
var skills: PackedStringArray = []
var tactical_discipline: float


func to_record() -> Dictionary:
	var exported_slot: Variant = (slot as Array).duplicate() if slot is Array else slot
	return {"name": name, "number": number, "position_x": position_x,
		"position_y": position_y, "slot": exported_slot, "raw": raw.duplicate(true)}


func to_parameters() -> Dictionary:
	return {"stats": normalized_stats.duplicate(), "player_type": player_type,
		"skills": Array(skills), "tactical_discipline": tactical_discipline}
