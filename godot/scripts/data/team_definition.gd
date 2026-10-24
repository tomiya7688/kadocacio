class_name TeamDefinition
extends RefCounted
## Node-free editable definition; original payload preserves unknown/custom metadata.

var team_id: String
var legacy_ids: PackedStringArray = []
var source: String
var name: String
var short_name: String
var description: String
var manager: ManagerDefinition
var primary: Array[int] = []
var uniform_data: Dictionary = {}
var tactic: String
var tactic_label: String
var zone_near: int
var zone_far: int
var tactical_discipline: float
var home_court: String
var starters: Array[PlayerDefinition] = []
var bench: Array[PlayerDefinition] = []
var original_payload: Dictionary = {}


func to_choice() -> Dictionary:
	var starting_records: Array[Dictionary] = []
	var bench_records: Array[Dictionary] = []
	for player: PlayerDefinition in starters:
		starting_records.append(player.to_record())
	for player: PlayerDefinition in bench:
		bench_records.append(player.to_record())
	return {"id": team_id, "legacy_ids": Array(legacy_ids), "source": source,
		"name": name, "short": short_name, "description": description, "manager": manager.name,
		"manager_tactic_aggression": manager.tactic_aggression,
		"manager_substitution_aggression": manager.substitution_aggression,
		"manager_intelligence": manager.intelligence, "primary": primary.duplicate(),
		"uniform_data": uniform_data.duplicate(true), "tactic": tactic, "tactic_label": tactic_label,
		"zone_near": zone_near, "zone_far": zone_far, "tactical_discipline": tactical_discipline,
		"home_court": home_court, "starters": starting_records, "bench": bench_records}
