class_name PlayerState
extends RefCounted
## Runtime player values, separate from saved definitions and rendering Nodes.

var definition: PlayerDefinition
var identity: String
var direction: int
var position: SimulationCoordinate = SimulationCoordinate.new()
var velocity: SimulationCoordinate = SimulationCoordinate.new()
var target: SimulationCoordinate = SimulationCoordinate.new()
var stamina: float
var stamina_max: float
var command: String = "HOLD_POSITION"
var sent_off: bool = false
var personal_tactic_timer: float
var skill: float
var roam_timer: float


func _init(player: PlayerDefinition, side: String, index: int, team_direction: int, rng: ObservedMatchRandom) -> void:
	definition = player
	identity = "%s:%d" % [side, index]
	direction = team_direction
	var rules: Dictionary = MatchProtocol.values()["kernel"] as Dictionary
	stamina_max = (rules["stamina_base"] as float) + (player.normalized_stats["MaxStamina"] as float) * (rules["stamina_span"] as float)
	stamina = stamina_max
	personal_tactic_timer = rng.uniform(1.5, 4.0)
	skill = rng.uniform(0.88, 1.12)
	roam_timer = rng.uniform(0.4, 1.8)
	reset_position(rng)


func reset_position(rng: ObservedMatchRandom) -> void:
	var field: Array = (MatchProtocol.values()["kernel"] as Dictionary)["field"] as Array
	var slot: Array = definition.slot as Array
	var home_x: float = slot[1] as float
	var world_x: float = home_x if direction == 1 else 1.0 - home_x
	position.set_values((field[0] as float) + world_x * (field[2] as float), (field[1] as float) + (slot[2] as float) * (field[3] as float))
	velocity.set_values(0, 0)
	target.set_values(position.x, position.y)
	command = "GUARD_GOAL" if slot[0] == "GK" else "HOLD_POSITION"
	roam_timer = rng.uniform(0.4, 1.8)
