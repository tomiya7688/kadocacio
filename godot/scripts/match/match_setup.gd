class_name MatchSetup
extends RefCounted
## Match-local initial rosters/formation/kickoff, preserving reference draw order.


static func create(input: Dictionary, rng: ObservedMatchRandom) -> MatchState:
	var source: Dictionary = input["repro_input"] as Dictionary
	var teams: Dictionary = source["teams"] as Dictionary
	var settings: Dictionary = source["settings"] as Dictionary
	var state: MatchState = MatchState.new()
	state.max_steps = settings["max_steps"] as int
	state.venue_mode = settings["venue_mode"] as String
	state.ai_rethink_multiplier = settings["ai_rethink_multiplier"] as float
	state.home = TeamState.new(teams["home"] as Dictionary, "HOME", 1, rng)
	state.away = TeamState.new(teams["away"] as Dictionary, "AWAY", -1, rng)
	reset_positions(state, state.home, rng)
	return state


static func start(state: MatchState, rng: ObservedMatchRandom) -> void:
	for team: TeamState in [state.home, state.away]:
		team.reset_roster(rng)
		team.manager_next_review = 150.0 + rng.uniform(0.0, 90.0)
		for player: PlayerState in team.players:
			player.personal_tactic_timer = rng.uniform(1.5, 4.0)
	state.clock.state = "PLAYING"
	state.clock.banner = "KICK OFF"
	state.clock.banner_timer = 2.8
	state.events.append("キックオフ！", state.clock)
	reset_positions(state, state.home, rng)


static func reset_positions(state: MatchState, kickoff_team: TeamState, rng: ObservedMatchRandom) -> void:
	state.restart.clear()
	state.throw_in.clear()
	state.pending_kick.clear()
	state.ball_boundary = null
	state.ball_contact = null
	for team: TeamState in [state.home, state.away]:
		for player: PlayerState in team.players:
			player.reset_position(rng)
	var field: Array = (MatchProtocol.values()["kernel"] as Dictionary)["field"] as Array
	var center_x: float = (field[0] as float) + (field[2] as float) / 2.0
	var center_y: float = (field[1] as float) + (field[3] as float) / 2.0
	var candidates: Array[PlayerState] = []
	for player: PlayerState in kickoff_team.players:
		if (player.definition.slot as Array)[0] == "FW":
			candidates.append(player)
	if candidates.is_empty():
		for player: PlayerState in kickoff_team.players:
			if (player.definition.slot as Array)[0] != "GK":
				candidates.append(player)
	if candidates.is_empty():
		candidates = kickoff_team.players.duplicate()
	var owner: PlayerState = candidates[0]
	var nearest: float = INF
	for player: PlayerState in candidates:
		var distance: float = pow(player.position.x - center_x, 2) + pow(player.position.y - center_y, 2)
		if distance < nearest:
			nearest = distance
			owner = player
	owner.position.set_values(center_x - kickoff_team.direction * 12, center_y)
	owner.command = "KEEP_BALL"
	state.ball.position.set_values(center_x, center_y, 4.0)
	state.ball.velocity.set_values(0, 0)
	BallPossessionSystem.reset_flight(state.ball, center_x, center_y)
	state.ball.owner = owner
	state.ball.last_touch = owner
	state.ball.control_offset = kickoff_team.direction * 10.0
	state.ball.control_offset_y = 0.0
