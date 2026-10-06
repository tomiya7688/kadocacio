class_name BallBoundaryEvent
extends RefCounted
## One detected post/goal/exit, not a completed restart or scored match result.

var kind: String
var side: String
var spot: SimulationCoordinate


func _init(event_kind: String, team_side: String, x: float, y: float) -> void:
	kind = event_kind
	side = team_side
	spot = SimulationCoordinate.new()
	spot.set_values(x, y)


func to_payload() -> Dictionary:
	return {"kind": kind, "side": side, "spot": [spot.x, spot.y]}
