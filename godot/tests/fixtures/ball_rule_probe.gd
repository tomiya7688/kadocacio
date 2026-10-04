class_name BallRuleProbe
extends RefCounted
## Test seam only: no AI/movement, and explicitly selected keeper/touch outcomes.

var save_result: bool = false
var touch_result: bool = false
var saves: int = 0
var touches: int = 0


func players(_state: MatchState, _dt: float, _rng: ObservedMatchRandom) -> void:
	pass


func decisions(_state: MatchState, _dt: float, _rng: ObservedMatchRandom) -> void:
	pass


func save(_state: MatchState, _candidate: BallContactCandidate, _rng: ObservedMatchRandom) -> bool:
	saves += 1
	return save_result


func touch(_state: MatchState, _candidate: BallContactCandidate, _rng: ObservedMatchRandom) -> bool:
	touches += 1
	return touch_result
