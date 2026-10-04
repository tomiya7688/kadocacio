class_name BallSimulationSystem
extends RefCounted
## Flight -> keeper -> boundary -> touches. Unmigrated resolvers queue a barrier.

var _save_resolver: Callable
var _touch_resolver: Callable
var _resolver_owners: Array[RefCounted] = []


func connect_contacts(save_resolver: Callable, touch_resolver: Callable) -> bool:
	for resolver: Callable in [save_resolver, touch_resolver]:
		if not resolver.is_valid() or not resolver.get_object() is RefCounted:
			return false
	_save_resolver = save_resolver
	_touch_resolver = touch_resolver
	_resolver_owners.assign([save_resolver.get_object(), touch_resolver.get_object()])
	return true


func update(state: MatchState, dt: float, rng: ObservedMatchRandom) -> void:
	if state.ball.owner != null:
		return
	BallFlightSystem.update(state.ball, dt)
	var save: BallContactCandidate = BallContactQuery.save_candidate(state)
	if save != null:
		if not _save_resolver.is_valid():
			state.ball_contact = save
			return
		if _save_resolver.call(state, save, rng) as bool:
			return
	var outcome: String = state.ball.shot_outcome
	var event: BallBoundaryEvent = BallBoundarySystem.detect(state)
	if event != null:
		if event.kind == "POST":
			state.events.append((state.ball.last_touch.definition.name if state.ball.last_touch != null else "シュート") + "はポスト！", state.clock)
		else:
			state.ball_boundary = event
			if event.kind in ["GOAL_KICK", "CORNER_KICK"] and not state.ball.shot_miss_announced and outcome in ["WIDE", "OVER"]:
				state.ball.shot_miss_announced = true
				var shooter: String = state.ball.last_touch.definition.name if state.ball.last_touch != null else "シュート"
				state.events.append(shooter + ("のシュートはゴールの外" if outcome == "WIDE" else "のシュートはバーの上"), state.clock)
		return
	for candidate: BallContactCandidate in BallContactQuery.touches(state):
		if not _touch_resolver.is_valid():
			state.ball_contact = candidate
			return
		if _touch_resolver.call(state, candidate, rng) as bool:
			return
