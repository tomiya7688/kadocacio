class_name BallState
extends RefCounted
## Node-free ball position/velocity/ownership; football flight rules follow in #125.

var position: SimulationCoordinate = SimulationCoordinate.new()
var velocity: SimulationCoordinate = SimulationCoordinate.new()
var owner: PlayerState = null
var last_touch: PlayerState = null
var control_offset: float = 10.0
