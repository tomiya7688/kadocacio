class_name BallFlightSystem
extends RefCounted
## Deterministic free flight from Match.update_loose_ball; no player AI or rules.


static func update(ball: BallState, dt: float) -> void:
	if ball.owner != null:
		return
	ball.pickup_lock = maxf(0.0, ball.pickup_lock - dt)
	ball.recovery_timer = maxf(0.0, ball.recovery_timer - dt)
	if ball.recovery_timer <= 0.0:
		ball.recovery_team = null
	ball.velocity.y += ball.curve_acceleration * dt
	ball.velocity.x += ball.curve_vector.x * dt
	ball.velocity.y += ball.curve_vector.y * dt
	ball.curve_vector.x *= pow(0.68, dt)
	ball.curve_vector.y *= pow(0.68, dt)
	var speed: float = sqrt(ball.velocity.x * ball.velocity.x + ball.velocity.y * ball.velocity.y)
	if ball.knuckle_amplitude > 0.1 and speed * speed > 0.01:
		ball.knuckle_phase += dt * (17.0 + speed / 72.0)
		var wave: float = sin(ball.knuckle_phase) * ball.knuckle_amplitude * dt
		var lateral_x: float = -ball.velocity.y / speed
		var lateral_y: float = ball.velocity.x / speed
		ball.velocity.x += lateral_x * wave
		ball.velocity.y += lateral_y * wave
		ball.knuckle_amplitude *= pow(0.72, dt)
	ball.curve_acceleration *= pow(0.70, dt)
	ball.position.x += ball.velocity.x * dt
	ball.position.y += ball.velocity.y * dt
	ball.position.z += ball.velocity.z * dt
	ball.velocity.z -= (MatchProtocol.values()["ball_rules"]["gravity"] as float) * dt
	if ball.position.z <= 0.0:
		ball.position.z = 0.0
		if ball.velocity.z < -48:
			ball.velocity.z = -ball.velocity.z * 0.38
			ball.velocity.x *= 0.90
			ball.velocity.y *= 0.90
		else:
			ball.velocity.z = 0.0
	speed = sqrt(ball.velocity.x * ball.velocity.x + ball.velocity.y * ball.velocity.y)
	var brake: float = clampf(ball.pass_brake, 0.0, 1.0)
	var drag: float
	if ball.position.z <= 0.5:
		drag = (0.72 if speed > 120 else 0.80) - brake * 0.14
	else:
		drag = (0.958 if speed > 90 else 0.972) - brake * 0.014
	ball.velocity.x *= pow(drag, dt)
	ball.velocity.y *= pow(drag, dt)
	if ball.position.z <= 0.5 and sqrt(ball.velocity.x * ball.velocity.x + ball.velocity.y * ball.velocity.y) < 7.0:
		ball.velocity.x = 0.0
		ball.velocity.y = 0.0
