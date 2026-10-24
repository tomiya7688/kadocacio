class_name TeamState
extends RefCounted
## One match-local roster and totals; team files/definitions are never mutated.

var choice: Dictionary
var side: String
var direction: int
var players: Array[PlayerState] = []
var bench: Array = []
var definitions: Array[PlayerDefinition] = []
var score: int = 0
var shots: int = 0
var possession: float = 0.0
var tactic: String
var manager_next_review: float = 0.0


func _init(source: Dictionary, team_side: String, team_direction: int, rng: ObservedMatchRandom) -> void:
	choice = source.duplicate(true)
	side = team_side
	direction = team_direction
	tactic = choice.get("tactic", "BALANCE") as String
	for record: Dictionary in choice["starters"] as Array:
		definitions.append(TeamPayloadDecoder.decode_record(record, choice.get("tactical_discipline", 0.5) as float))
	reset_roster(rng)


func reset_roster(rng: ObservedMatchRandom) -> void:
	players.clear()
	bench = (choice.get("bench", []) as Array).duplicate(true)
	for index: int in definitions.size():
		players.append(PlayerState.new(definitions[index], side, index, direction, rng))
