class_name KernelStepProbe
extends RefCounted
## Test-only prescribed kinematics, never a football approximation or game system.

var player_updates: int = 0
var decision_updates: int = 0
var ball_updates: int = 0
var randomize: bool = false
var last_dt: float = 0.0


func players(state: MatchState, dt: float, _rng: ObservedMatchRandom) -> void:
	player_updates += 1
	last_dt = dt
	for team: TeamState in [state.home, state.away]:
		for player: PlayerState in team.players:
			player.position.x += player.velocity.x * dt
			player.position.y += player.velocity.y * dt


func decisions(state: MatchState, _dt: float, rng: ObservedMatchRandom) -> void:
	decision_updates += 1
	if randomize:
		rng.purpose = "probe.decisions"
		state.home.players[0].command = "HOLD_POSITION" if rng.random() < 0.5 else "FOLLOW_BALL"


func ball(state: MatchState, dt: float, _rng: ObservedMatchRandom) -> void:
	ball_updates += 1
	state.ball.position.x += state.ball.velocity.x * dt
	state.ball.position.y += state.ball.velocity.y * dt
	state.ball.position.z += state.ball.velocity.z * dt
