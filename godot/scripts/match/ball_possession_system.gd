class_name BallPossessionSystem
extends RefCounted
## Ball-only claim/reset/spill effects. Decision timing/skills stay with later units.


static func reset_flight(ball: BallState, x: float, y: float) -> void:
	ball.intended = null
	ball.pickup_lock = 0.0
	ball.velocity.set_values(0, 0)
	ball.curve_acceleration = 0.0
	ball.curve_vector.set_values(0, 0)
	ball.knuckle_amplitude = 0.0
	ball.flight_type = ""
	ball.shot_deception = 0.0
	ball.shot_outcome = ""
	ball.shot_miss_announced = false
	ball.pass_outcome = ""
	ball.pass_brake = 0.0
	ball.intended_destination.set_values(x, y)
	ball.eye_contact_bonus = 0.0
	ball.catch_forbidden = false
	ball.last_keeper_response = ""
	ball.recovery_team = null
	ball.recovery_timer = 0.0


static func claim(ball: BallState, player: PlayerState, offset_x: float, offset_y: float = 0.0) -> void:
	var lock: float = ball.pickup_lock
	reset_flight(ball, player.position.x, player.position.y)
	ball.pickup_lock = lock
	ball.owner = player
	ball.last_touch = player
	ball.position.z = 5.0
	ball.control_offset = offset_x
	ball.control_offset_y = offset_y


static func release_knockback(state: MatchState, player: PlayerState, direction_x: float, direction_y: float, recovery: TeamState = null) -> void:
	var ball: BallState = state.ball
	if ball.owner != player:
		return
	if state.pending_kick.get("player") == player.identity:
		state.pending_kick.clear()
	ball.owner = null
	ball.last_touch = player
	ball.intended = null
	ball.eye_contact_bonus = 0.0
	ball.catch_forbidden = false
	ball.last_keeper_response = ""
	ball.pickup_lock = 0.16 if recovery != null else 0.34
	var offset: float = -6.0 if recovery != null else 12.0
	var power: float = 46.0 if recovery != null else 82.0
	ball.position.set_values(player.position.x + direction_x * offset, player.position.y + direction_y * offset, 6.0)
	ball.velocity.set_values(player.velocity.x * 0.16 + direction_x * power, player.velocity.y * 0.16 + direction_y * power, 18.0)
	ball.curve_acceleration = 0.0
	ball.curve_vector.set_values(0, 0)
	ball.knuckle_amplitude = 0.0
	ball.flight_type = "フィジカルこぼれ球"
	ball.recovery_team = recovery
	ball.recovery_timer = 1.25 if recovery != null else 0.0
