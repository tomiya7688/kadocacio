class_name BallContactQuery
extends RefCounted
## Reference spatial/height/lock/recovery gates. Skill/control decisions follow #128.


static func hands_legal(state: MatchState, player: PlayerState) -> bool:
	if (player.definition.slot as Array)[0] != "GK":
		return false
	var field: Array = MatchProtocol.values()["kernel"]["field"] as Array
	var rules: Dictionary = MatchProtocol.values()["ball_rules"] as Dictionary
	var center_y: float = (field[1] as float) + (field[3] as float) / 2
	var goal_x: float = (field[0] as float) + ((field[2] as float) if player.direction == -1 else 0.0)
	var depth: float = (state.ball.position.x - goal_x) * player.direction
	if depth < 0 or depth > (rules["penalty_depth"] as float) or absf(state.ball.position.y - center_y) > (rules["penalty_width"] as float) / 2:
		return false
	var last: PlayerState = state.ball.last_touch
	if last == null or last == player or not last.identity.begins_with(player.identity.get_slice(":", 0) + ":"):
		return true
	if state.ball.intended == player:
		return false
	for token: String in ["パス", "スローイン", "ゴールキック", "コーナーキック"]:
		if token in state.ball.flight_type:
			return false
	return true


static func save_candidate(state: MatchState) -> BallContactCandidate:
	var ball: BallState = state.ball
	if ball.owner != null or ball.velocity.x * ball.velocity.x + ball.velocity.y * ball.velocity.y < 170 * 170:
		return null
	var team: TeamState = state.home if ball.velocity.x < 0 else state.away
	var keeper: PlayerState = null
	for player: PlayerState in team.players:
		if (player.definition.slot as Array)[0] == "GK":
			keeper = player
			break
	if keeper == null or not hands_legal(state, keeper):
		return null
	var scale: float = MatchProtocol.values()["ball_rules"]["visual_scale"] as float
	var distance: float = pow(keeper.position.x - ball.position.x, 2) + pow(keeper.position.y - ball.position.y, 2)
	# Conservative gate includes guardian activation range; the actual save/skill
	# resolver, not this geometry query, must determine the final hand radius.
	if distance >= pow(50 * scale, 2) or ball.position.z > keeper.position.z + 88 * scale:
		return null
	var candidate: BallContactCandidate = BallContactCandidate.new()
	candidate.player = keeper
	candidate.kind = "KEEPER_SAVE"
	candidate.hands_legal = true
	candidate.radius = 50 * scale
	candidate.distance_squared = distance
	return candidate


static func touches(state: MatchState) -> Array[BallContactCandidate]:
	var ball: BallState = state.ball
	if ball.owner != null:
		return []
	var rules: Dictionary = MatchProtocol.values()["ball_rules"] as Dictionary
	var scale: float = rules["visual_scale"] as float
	var results: Array[BallContactCandidate] = []
	var ordinal: int = 0
	for team: TeamState in [state.home, state.away]:
		for player: PlayerState in team.players:
			ordinal += 1
			if player.sent_off or (ball.pickup_lock > 0 and player == ball.last_touch):
				continue
			var legal: bool = hands_legal(state, player)
			var airborne: bool = player.position.z > 0.5
			var radius: float = (rules["keeper_reach"] as float) if legal else (11 + player.contact_jump_accuracy * 9) * scale if airborne else (rules["outfield_reach"] as float)
			var recovery: bool = ball.recovery_timer > 0 and ball.recovery_team == team
			if recovery:
				radius += 5 * scale
			var distance: float = pow(player.position.x - ball.position.x, 2) + pow(player.position.y - ball.position.y, 2)
			var reach: float = player.position.z + (72 if airborne else 55) * scale if legal else player.position.z + 54 * scale if airborne else 24 * scale
			if sqrt(distance) > radius or ball.position.z > reach:
				continue
			if legal and "シュート" in ball.flight_type and ball.velocity.x * ball.velocity.x + ball.velocity.y * ball.velocity.y >= 170 * 170:
				continue
			var candidate: BallContactCandidate = BallContactCandidate.new()
			candidate.player = player
			candidate.radius = radius
			candidate.distance_squared = distance
			candidate.hands_legal = legal
			candidate.priority = 0 if recovery else 1
			candidate.ordinal = ordinal
			results.append(candidate)
	results.sort_custom(_nearer)
	return results


static func _nearer(first: BallContactCandidate, second: BallContactCandidate) -> bool:
	if first.priority != second.priority:
		return first.priority < second.priority
	if first.distance_squared != second.distance_squared:
		return first.distance_squared < second.distance_squared
	return first.ordinal < second.ordinal
