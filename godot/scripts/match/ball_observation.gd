class_name BallObservation
extends RefCounted
## Detached flight/possession values, separate from the unchanged v1 HUD subset.


static func capture(ball: BallState) -> Dictionary:
	return {"position": ball.position.to_array(), "velocity": ball.velocity.to_array(),
		"owner": null if ball.owner == null else ball.owner.identity,
		"last_touch": null if ball.last_touch == null else ball.last_touch.identity,
		"intended": null if ball.intended == null else ball.intended.identity,
		"control_offset": [ball.control_offset, ball.control_offset_y],
		"pickup_lock": ball.pickup_lock, "curve_acceleration": ball.curve_acceleration,
		"curve_vector": [ball.curve_vector.x, ball.curve_vector.y], "knuckle_amplitude": ball.knuckle_amplitude,
		"knuckle_phase": ball.knuckle_phase, "flight_type": ball.flight_type,
		"flight_serial": ball.flight_serial, "shot_serial": ball.shot_serial,
		"shot_deception": ball.shot_deception, "shot_outcome": ball.shot_outcome,
		"shot_miss_announced": ball.shot_miss_announced, "pass_outcome": ball.pass_outcome,
		"pass_brake": ball.pass_brake, "intended_destination": [ball.intended_destination.x, ball.intended_destination.y],
		"eye_contact_bonus": ball.eye_contact_bonus, "catch_forbidden": ball.catch_forbidden,
		"last_keeper_response": ball.last_keeper_response,
		"recovery_team": null if ball.recovery_team == null else ball.recovery_team.side, "recovery_timer": ball.recovery_timer}
