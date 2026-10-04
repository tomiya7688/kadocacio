class_name BallState
extends RefCounted
## Node-free flight/possession metadata. Rules live in dedicated ball systems.

var position: SimulationCoordinate = SimulationCoordinate.new()
var velocity: SimulationCoordinate = SimulationCoordinate.new()
var owner: PlayerState = null
var last_touch: PlayerState = null
var control_offset: float = 10.0
var control_offset_y: float = 0.0
var intended: PlayerState = null
var intended_destination: SimulationCoordinate = SimulationCoordinate.new()
var pickup_lock: float = 0.0
var curve_acceleration: float = 0.0
var curve_vector: SimulationCoordinate = SimulationCoordinate.new()
var knuckle_amplitude: float = 0.0
var knuckle_phase: float = 0.0
var flight_type: String = ""
var flight_serial: int = 0
var shot_serial: int = 0
var shot_deception: float = 0.0
var shot_outcome: String = ""
var shot_miss_announced: bool = false
var pass_outcome: String = ""
var pass_brake: float = 0.0
var eye_contact_bonus: float = 0.0
var catch_forbidden: bool = false
var last_keeper_response: String = ""
var recovery_team: TeamState = null
var recovery_timer: float = 0.0
