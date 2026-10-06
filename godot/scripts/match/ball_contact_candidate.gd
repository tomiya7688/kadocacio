class_name BallContactCandidate
extends RefCounted
## Geometric contact eligibility, not a successful trap/header/save probability.

var player: PlayerState
var kind: String = "TOUCH"
var radius: float
var distance_squared: float
var hands_legal: bool
var priority: int
var ordinal: int


func to_payload() -> Dictionary:
	return {"kind": kind, "player": player.identity, "hands_legal": hands_legal}
