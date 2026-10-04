extends SceneTree
## Isolated actual ball rules, not football AI, contact success or restart parity.

var _assertions: int = 0
var _failures: int = 0
var _entries: Array[Dictionary] = []


func _initialize() -> void:
	_run.call_deferred()


func _expect(condition: bool, label: String) -> void:
	_assertions += 1
	if not condition:
		_failures += 1
		push_error(label)


func _run() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size() != 4 or args[0] != "--fixture" or args[2] != "--output":
		quit(2)
		return
	var parsed: Dictionary = StrictJsonReader.read_file(args[1])
	_expect((parsed["error"] as String).is_empty(), "ball fixture")
	var fixture: Dictionary = parsed["data"] as Dictionary
	for item: Dictionary in fixture["cases"] as Array:
		_replay(fixture["input"] as Dictionary, item)
		if item["name"] in ["slow_roll", "fast_roll", "lofted", "curve", "knuckle"]:
			_check_pacing(fixture["input"] as Dictionary, item)
	_check_integration(fixture["input"] as Dictionary, (fixture["cases"] as Array)[0] as Dictionary)
	var trace: Dictionary = {"format": MatchProtocol.values()["trace_format"], "version": 1,
		"source": {"implementation": "godot-ball-rules", "execution": "simulation", "rng": "contact success intercepted; flight deterministic", "seed_text": "41"}, "entries": _entries}
	var report: Dictionary = MatchTraceComparison.compare(MatchTraceRecord.read(fixture["reference"]), MatchTraceRecord.read(trace))
	_expect(report["same_observations"] as bool, "ball trace: " + JSON.stringify(report["first_difference"]))
	_expect((report["kernel_parity"] as String) == "not_evaluated", "isolated ball rules are not whole football parity")
	var output: FileAccess = FileAccess.open(args[3], FileAccess.WRITE)
	_expect(output != null, "ball output")
	if output != null:
		output.store_string(JSON.stringify(trace))
		output.close()
	print("KADOCALCIO_BALL_TESTS: %d cases, %d assertions, %d failures; contact decisions/restarts NOT migrated" % [(fixture["cases"] as Array).size(), _assertions, _failures])
	quit(0 if _failures == 0 else 1)


func _configured(input: Dictionary, item: Dictionary) -> MatchKernel:
	var copied: Dictionary = input.duplicate(true)
	copied["repro_input"]["settings"]["max_steps"] = 20000
	var kernel: MatchKernel = MatchKernel.from_input(copied)
	_expect(kernel.error.is_empty() and kernel.apply({"kind": "START"}), "ball kernel start")
	kernel._state.clock.banner_timer = 0.0
	var players: Dictionary = {}
	for team: TeamState in [kernel._state.home, kernel._state.away]:
		for player: PlayerState in team.players:
			players[player.identity] = player
	for data: Dictionary in item["initial"]["players"] as Array:
		var player: PlayerState = players[data["id"]] as PlayerState
		var pos: Array = data["position"] as Array
		var vel: Array = data["velocity"] as Array
		player.position.set_values(pos[0] as float, pos[1] as float, pos[2] as float)
		player.velocity.set_values(vel[0] as float, vel[1] as float)
		player.sent_off = data["sent_off"] as bool
		player.contact_jump_accuracy = data["contact_jump_accuracy"] as float
	var initial: Dictionary = item["initial"]["ball"] as Dictionary
	var ball: BallState = kernel._state.ball
	for key: String in initial:
		if key in ["position", "velocity", "control_offset", "curve_vector", "intended_destination", "owner", "last_touch", "intended", "recovery_team"]:
			continue
		ball.set(key, initial[key])
	for key: String in ["position", "velocity", "curve_vector", "intended_destination"]:
		var target: SimulationCoordinate = ball.get(key) as SimulationCoordinate
		var values: Array = initial[key] as Array
		target.set_values(values[0] as float, values[1] as float, values[2] as float if values.size() == 3 else 0.0)
	ball.control_offset = initial["control_offset"][0] as float
	ball.control_offset_y = initial["control_offset"][1] as float
	for key: String in ["owner", "last_touch", "intended"]:
		ball.set(key, null if initial[key] == null else players[initial[key]])
	ball.recovery_team = null if initial["recovery_team"] == null else kernel._state.home if initial["recovery_team"] == "HOME" else kernel._state.away
	var operation: String = item.get("operation", "flight") as String
	if operation == "spill":
		BallPossessionSystem.release_knockback(kernel._state, players["HOME:1"] as PlayerState, 0.6, 0.8, kernel._state.away if item.get("recovery") == "AWAY" else null)
	elif operation.begins_with("claim"):
		var player: PlayerState = players["HOME:1"] as PlayerState
		BallPossessionSystem.claim(ball, player, 8 if operation == "claim" else player.direction * 10, -3 if operation == "claim" else 0)
	return kernel


func _replay(input: Dictionary, item: Dictionary) -> void:
	var kernel: MatchKernel = _configured(input, item)
	var system: BallSimulationSystem = BallSimulationSystem.new()
	var probe: BallRuleProbe = BallRuleProbe.new()
	# Keeper outcomes are intercepted identically in the Python oracle; touches
	# are observed at the first actual eligibility point before changing owner.
	_expect(system.connect_contacts(probe.save, probe.touch), "connect keeper seam")
	system._touch_resolver = Callable()
	for expected: Dictionary in item["frames"] as Array:
		system.update(kernel._state, 0.05, kernel.rng)
		var frame: Dictionary = {"step": expected["step"], "case_name": item["name"], "ball": BallObservation.capture(kernel._state.ball),
			"boundary": null if kernel._state.ball_boundary == null else kernel._state.ball_boundary.to_payload(),
			"contact": null if kernel._state.ball_contact == null else kernel._state.ball_contact.to_payload()}
		var difference: Variant = MatchTraceComparison.first_difference(expected, frame)
		_expect(difference == null, (item["name"] as String) + "/" + str(expected["step"]) + ": " + JSON.stringify(difference))
		_entries.append({"operation_index": _entries.size(), "snapshot": {"step": frame["step"], "case_name": frame["case_name"],
			"ball": frame["ball"], "boundary": frame["boundary"], "contact": frame["contact"], "paused": false, "simulation_elapsed": 0.0,
			"status": {"state": "PLAYING", "game_time": 0.0, "home_score": 0, "away_score": 0}, "home": {"players": []}, "away": {"players": []}, "restart": null}, "events": [], "result": null})


func _simulation(input: Dictionary, item: Dictionary) -> MatchKernel:
	var kernel: MatchKernel = _configured(input, item)
	var system: BallSimulationSystem = BallSimulationSystem.new()
	var probe: BallRuleProbe = BallRuleProbe.new()
	_expect(kernel.register_system("players", probe.players) and kernel.register_system("decisions", probe.decisions) and kernel.register_system("ball", system.update), "real ball stage")
	return kernel


func _check_pacing(input: Dictionary, item: Dictionary) -> void:
	var expected: MatchKernel = _simulation(input, item)
	for tick: int in 20:
		_expect(expected.apply({"kind": "STEP", "dt": 0.05}), "headless ball step")
	for frequency: int in [30, 60, 120]:
		for speed: int in [1, 2, 3, 5, 10, 100]:
			var kernel: MatchKernel = _simulation(input, item)
			_expect(kernel.apply({"kind": "SET_SPEED", "value": speed}), "ball speed")
			var driver: FixedStepDriver = FixedStepDriver.new(kernel)
			for frame: int in frequency:
				driver.advance(1.0 / frequency / speed)
				kernel.observe_ball()
			_expect(kernel._state.step == 20, "ball fixed ticks")
			_expect(MatchTraceComparison.first_difference(expected.observe_ball(), kernel.observe_ball()) == null, "ball frame/speed invariant")
			_expect(kernel.rng.word_count == expected.rng.word_count, "ball observations consume no RNG")


func _check_integration(input: Dictionary, item: Dictionary) -> void:
	var boundary: MatchKernel = _simulation(input, item)
	var field: Array = MatchProtocol.values()["kernel"]["field"] as Array
	boundary._state.ball.position.x = (field[0] as float) + (field[2] as float) + 1
	_expect(boundary.apply({"kind": "STEP", "dt": 0.05}) and boundary._state.ball_boundary != null, "goal queued")
	var before: Dictionary = boundary.observe()
	_expect(not boundary.apply({"kind": "STEP", "dt": 0.05}), "unmigrated goal/restart blocks clock")
	_expect(MatchTraceComparison.first_difference(before, boundary.observe()) == null, "no fake progress after goal")
	var contact: MatchKernel = _simulation(input, item)
	contact._state.home.players[1].position.set_values(contact._state.ball.position.x, contact._state.ball.position.y)
	contact._state.ball.velocity.set_values(0, 0)
	_expect(contact.apply({"kind": "STEP", "dt": 0.05}) and contact._state.ball_contact != null, "touch queued")
	before = contact.observe()
	_expect(not contact.apply({"kind": "STEP", "dt": 0.05}), "unmigrated contact blocks clock")
	_expect(MatchTraceComparison.first_difference(before, contact.observe()) == null, "no fake progress after touch")
	var snapshot: Dictionary = contact.observe_ball()
	snapshot["ball"]["position"][0] = -999
	_expect(contact._state.ball.position.x != -999, "flight observation detached")
	var system: BallSimulationSystem = BallSimulationSystem.new()
	_expect(not system.connect_contacts(Callable(), Callable()), "invalid callbacks")
	var keeper: PlayerState = null
	for player: PlayerState in contact._state.away.players:
		if (player.definition.slot as Array)[0] == "GK":
			keeper = player
			break
	contact._state.ball_contact = null
	contact._state.ball.position.set_values((field[0] as float) + (field[2] as float) - 10, (field[1] as float) + (field[3] as float) / 2, 10)
	contact._state.ball.velocity.set_values(200, 0)
	keeper.position.set_values(contact._state.ball.position.x, contact._state.ball.position.y)
	system.update(contact._state, 0.05, contact.rng)
	_expect(contact._state.ball_contact != null and contact._state.ball_contact.kind == "KEEPER_SAVE", "save resolution precedes goal detection")
	contact._state.ball_contact = null
	var probe: BallRuleProbe = BallRuleProbe.new()
	probe.save_result = true
	_expect(system.connect_contacts(probe.save, probe.touch), "valid callbacks")
	contact._state.ball.position.x = (field[0] as float) + (field[2] as float) - 10
	contact._state.ball.velocity.set_values(200, 0)
	system.update(contact._state, 0.05, contact.rng)
	_expect(probe.saves == 1 and contact._state.ball_boundary == null, "successful save stops boundary")
	var pending: MatchKernel = _configured(input, item)
	pending._state.ball.owner = pending._state.home.players[1]
	pending._state.pending_kick = {"player": pending._state.ball.owner.identity}
	BallPossessionSystem.release_knockback(pending._state, pending._state.ball.owner, 1, 0)
	_expect(pending._state.pending_kick.is_empty() and pending._state.ball.owner == null, "spill cancels owner's kick")
