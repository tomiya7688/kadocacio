class_name MatchSnapshot
extends RefCounted
## Detached v1 observations. Does not advance time, RNG, physics or UI.


static func capture(state: MatchState, after_sequence: int = 0) -> Dictionary:
	return {"snapshot": {"step": state.step, "paused": state.paused,
		"status": {"home_short_name": state.home.choice["short"], "away_short_name": state.away.choice["short"],
			"home_score": state.home.score, "away_score": state.away.score, "game_time": state.clock.game_time,
			"state": state.clock.state, "banner": state.clock.banner, "banner_timer": state.clock.banner_timer, "speed_multiplier": state.speed_multiplier},
		"simulation_elapsed": state.clock.simulation_elapsed, "home": _team(state.home), "away": _team(state.away),
		"ball": {"position": state.ball.position.to_array(), "velocity": state.ball.velocity.to_array(), "owner": null if state.ball.owner == null else state.ball.owner.identity},
		"restart": null if state.restart.is_empty() else state.restart.duplicate(true),
		"throw_in": null if state.throw_in.is_empty() else state.throw_in.duplicate(true),
		"pending_kick": null if state.pending_kick.is_empty() else state.pending_kick.duplicate(true),
		"foul_count": state.foul_count, "card_count": state.card_count, "restart_counts": state.restart_counts.duplicate()},
		"events": state.events.after(after_sequence), "result": null}


static func _team(team: TeamState) -> Dictionary:
	var players: Array[Dictionary] = []
	for player: PlayerState in team.players:
		players.append({"id": player.identity, "number": player.definition.number, "name": player.definition.name,
			"role": (player.definition.slot as Array)[0], "position": player.position.to_array(),
			"target": [player.target.x, player.target.y], "stamina": player.stamina, "command": player.command, "sent_off": player.sent_off})
	return {"score": team.score, "shots": team.shots, "possession": team.possession, "tactic": team.tactic,
		"direction": team.direction, "players": players}
