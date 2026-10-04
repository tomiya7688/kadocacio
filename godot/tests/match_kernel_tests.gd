extends SceneTree
## Actual foundation/RNG execution; football AI/physics systems are NOT migrated.

var _assertions: int = 0
var _failures: int = 0


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
		push_error("Pass --fixture and --output")
		quit(2)
		return
	var parsed: Dictionary = StrictJsonReader.read_file(args[1])
	_expect((parsed["error"] as String).is_empty(), "read kernel fixture")
	var fixture: Dictionary = parsed["data"] as Dictionary
	_check_rng(fixture["rng_cases"] as Array)
	_check_clocks(fixture["clock_cases"] as Array)
	var trace: Dictionary = _replay(fixture["input"] as Dictionary)
	var difference: Dictionary = MatchTraceComparison.compare(MatchTraceRecord.read(fixture["reference"]), MatchTraceRecord.read(trace))
	_expect(difference["same_observations"] as bool, "kickoff execution difference: " + JSON.stringify(difference["first_difference"]))
	_expect((difference["scope"] as String) == "simulation_observations", "foundation executes, not observation roundtrip")
	_expect((difference["kernel_parity"] as String) == "not_evaluated", "sample is not whole football parity")
	_check_steps(fixture["input"] as Dictionary)
	var output: FileAccess = FileAccess.open(args[3], FileAccess.WRITE)
	_expect(output != null, "native kernel output")
	if output != null:
		output.store_string(JSON.stringify(trace))
		output.close()
	print("KADOCALCIO_MATCH_KERNEL_TESTS: %d assertions, %d failures; football systems NOT migrated" % [_assertions, _failures])
	quit(0 if _failures == 0 else 1)


func _check_rng(cases: Array) -> void:
	for item: Dictionary in cases:
		var rng: ObservedMatchRandom = ObservedMatchRandom.new(item["seed_text"] as String)
		rng.enabled = true
		var index: int = 0
		for row: Dictionary in item["outputs"] as Array:
			var kind: String = row["kind"] as String
			rng.purpose = "draw.sequence" if kind == "random" else "draw.bits" if kind == "getrandbits" else "draw." + kind
			rng.step = mini(index, 719)
			var parameters: Array = row.get("arguments", []) as Array
			var value: Variant
			match kind:
				"random": value = rng.random()
				"getrandbits": value = rng.getrandbits(parameters[0] as int)
				"uniform": value = rng.uniform(parameters[0] as float, parameters[1] as float)
				"randint": value = rng.randint(parameters[0] as int, parameters[1] as int)
				"choice": value = rng.choice(parameters[0] as Array)
				"gauss": value = rng.gauss(parameters[0] as float, parameters[1] as float)
			_expect(MatchTraceComparison.first_difference(row["value"], value, "$.bit_value" if kind in ["getrandbits", "randint"] else "$") == null, "RNG: " + kind + "/" + str(index))
			index += 1
		_expect(MatchTraceComparison.first_difference(item["audit"], rng.history()) == null, "RNG purpose/order/word consumption")
		var expected_state: Dictionary = item["state"] as Dictionary
		var actual_state: Dictionary = rng.state_payload()
		_expect(MatchTraceComparison.first_difference(expected_state["words"], actual_state["words"], "$.rng_words") == null, "MT state after multiple twists")
		_expect((expected_state["index"] as int) == (actual_state["index"] as int), "MT index")
		_expect(MatchTraceComparison.first_difference(expected_state["gauss_next"], actual_state["gauss_next"]) == null, "Gaussian cache")


func _check_clocks(cases: Array) -> void:
	for row: Dictionary in cases:
		var clock: MatchClock = MatchClock.new()
		clock.state = "PLAYING"
		clock.game_time = row["game_time"] as float
		clock.halftime_done = clock.game_time >= 2700
		clock.banner = row["banner"] as String
		clock.banner_timer = row["timer"] as float
		var transition: String = clock.advance(row["dt"] as float, row["waiting"] as bool)
		_expect(absf(clock.game_time - (row["after"] as float)) < 1e-9, "clock: " + (row["name"] as String))
		_expect(transition == (row["transition"] as String), "phase: " + (row["name"] as String))
		_expect(clock.simulation_elapsed == (row["dt"] as float), "physics still runs during waits")


func _rng_observation(rng: ObservedMatchRandom, cursor: int) -> Dictionary:
	var state: Dictionary = rng.state_payload()
	return {"rng_words": state["words"], "rng_index": state["index"], "gauss_next": state["gauss_next"],
		"rng_word_count": rng.word_count, "rng_draws": rng.history().slice(cursor)}


func _replay(input: Dictionary) -> Dictionary:
	var kernel: MatchKernel = MatchKernel.from_input(input, true)
	_expect(kernel.error.is_empty(), "kernel create: " + kernel.error)
	var entries: Array[Dictionary] = []
	var event_cursor: int = 0
	var rng_cursor: int = 0
	var index: int = 0
	for operation: Dictionary in input["operations"] as Array:
		_expect(kernel.apply(operation), "kernel operation: " + kernel.error)
		var observation: Dictionary = kernel.observe(event_cursor)
		(observation["snapshot"] as Dictionary)["rng"] = _rng_observation(kernel.rng, rng_cursor)
		rng_cursor = kernel.rng.history().size()
		if not (observation["events"] as Array).is_empty():
			event_cursor = ((observation["events"] as Array)[-1] as Dictionary)["sequence"] as int
		observation["operation_index"] = index
		entries.append(observation)
		index += 1
	var settings: Dictionary = (input["repro_input"] as Dictionary)["settings"] as Dictionary
	return {"format": MatchProtocol.values()["trace_format"], "version": MatchProtocol.values()["version"],
		"source": {"implementation": "godot-foundation", "execution": "simulation", "rng": "CPython-compatible MT19937/integer-seed subset",
			"seed_text": settings["seed"] as String}, "entries": entries}


func _test_kernel(input: Dictionary, randomize: bool = false) -> MatchKernel:
	var copied: Dictionary = input.duplicate(true)
	((copied["repro_input"] as Dictionary)["settings"] as Dictionary)["max_steps"] = 15000
	var kernel: MatchKernel = MatchKernel.from_input(copied, true)
	_expect(kernel.apply({"kind": "START"}), "test start")
	var probe: KernelStepProbe = KernelStepProbe.new()
	probe.randomize = randomize
	_expect(kernel.register_system("players", probe.players), "player stage")
	_expect(kernel.register_system("decisions", probe.decisions), "decision stage")
	_expect(kernel.register_system("ball", probe.ball), "ball stage")
	kernel._state.clock.banner_timer = 0.0
	kernel._state.ball.owner = null
	kernel._state.ball.velocity.x = 12.0
	kernel._state.home.players[0].velocity.y = 7.0
	return kernel


func _check_steps(input: Dictionary) -> void:
	for speed: int in [1, 2, 3, 5, 10, 100]:
		_expect(MatchOperation.read({"kind": "SET_SPEED", "value": speed}).is_valid(), "integer speed API")
		_expect(MatchOperation.read({"kind": "SET_SPEED", "value": float(speed)}).is_valid(), "JSON float speed API")
	var incomplete: MatchKernel = MatchKernel.from_input(input)
	_expect(not incomplete.apply({"kind": "STEP", "dt": 0.05}), "start required")
	_expect(incomplete.apply({"kind": "START"}), "foundation start")
	_expect(not incomplete.apply({"kind": "START"}), "no double start")
	incomplete._state.clock.banner_timer = 0.0
	var before: Dictionary = incomplete.observe()
	_expect(not incomplete.apply({"kind": "STEP", "dt": 0.05}), "missing systems stop live clock")
	_expect(MatchTraceComparison.first_difference(before, incomplete.observe()) == null, "failed step changes no state")
	_expect(not incomplete.register_system("unknown", Callable()), "invalid system rejected")
	_expect(not incomplete.apply({"kind": "STEP", "dt": 0.051}), "max fixed dt")
	_expect(not MatchKernel.from_input({}).error.is_empty(), "invalid input rejected")
	_check_invalid_rosters(input)
	var headless: MatchKernel = _test_kernel(input, true)
	var rendered: MatchKernel = _test_kernel(input, true)
	for index: int in 20:
		_expect(headless.apply({"kind": "STEP", "dt": 0.05}), "direct tick")
	var driver: FixedStepDriver = FixedStepDriver.new(rendered)
	for index: int in 60:
		driver.advance(1.0 / 60.0)
		var draw_count: int = rendered.rng.word_count
		rendered.observe()
		_expect(rendered.rng.word_count == draw_count, "drawing does not consume RNG")
	_expect(MatchTraceComparison.first_difference(headless.observe(), rendered.observe()) == null, "render frequency does not change states")
	_expect(MatchTraceComparison.first_difference(headless.rng.history(), rendered.rng.history()) == null, "render frequency does not change draws")
	_check_frame_rates_and_speeds(input, headless)
	_expect(rendered._state.clock.game_time == 10.0 and rendered._state.step == 20, "20 fixed ticks per second")
	var field: Array = (MatchProtocol.values()["kernel"] as Dictionary)["field"] as Array
	_expect(absf(rendered._state.ball.position.x - ((field[0] as float) + (field[2] as float) / 2 + 12.0)) < 1e-8, "ball state is updated")
	var probe: KernelStepProbe = (rendered._systems["players"] as Callable).get_object() as KernelStepProbe
	_expect(probe.player_updates == 20 and probe.decision_updates == 20 and probe.ball_updates == 20 and probe.last_dt == 0.05, "every executed tick updates all systems")
	_expect(rendered._state.home.players[0].position.y != (before["snapshot"]["home"]["players"][0]["position"][1] as float), "player state is updated")
	var fast: MatchKernel = _test_kernel(input, true)
	_expect(fast.apply({"kind": "SET_SPEED", "value": 100}), "speed supported")
	var fast_driver: FixedStepDriver = FixedStepDriver.new(fast)
	_expect(fast_driver.advance(0.01, 2) == 2 and fast_driver.pending_time > 0.8, "budget retains backlog")
	_expect(fast_driver.advance(0.0, 50) == 18, "retained backlog is fully simulated")
	_expect(fast._state.step == 20 and fast._state.clock.game_time == 10.0, "speed changes tick count, not tick size")
	_expect(fast_driver.advance(NAN) == -1 and fast_driver.advance(-1) == -1, "invalid elapsed rejected")
	_expect(fast_driver.advance(0.0, 0) == -1, "invalid pump budget rejected")
	_expect(FixedStepDriver.new(MatchKernel.from_input(input)).advance(0.05) == -1, "unstarted driver rejected")
	var missing_driver: FixedStepDriver = FixedStepDriver.new(incomplete)
	_expect(missing_driver.advance(0.1) == -1 and missing_driver.pending_time == 0.1, "missing stages retain backlog without changing clock")
	var paused_state: Dictionary = fast.observe()
	_expect(fast.apply({"kind": "PAUSE"}), "pause")
	_expect(fast_driver.advance(1.0) == 0, "paused driver")
	_expect(fast.apply({"kind": "STEP", "dt": 0.05}), "paused tick is no-op")
	_expect(fast._state.step == ((paused_state["snapshot"] as Dictionary)["step"] as int), "paused clock/state frozen")
	_expect(fast.apply({"kind": "RESUME"}), "resume")
	var budget_state: Dictionary = fast.observe()
	fast._state.max_steps = fast._state.step
	_expect(not fast.apply({"kind": "STEP", "dt": 0.05}), "step budget")
	_expect(MatchTraceComparison.first_difference(budget_state, fast.observe()) == null, "budget does not manufacture time")
	var waiting: MatchKernel = _test_kernel(input)
	waiting._state.restart = {"kind": "FREE_KICK"}
	_expect(waiting.apply({"kind": "STEP", "dt": 0.05}), "restart systems update")
	_expect(waiting._state.clock.game_time == 0 and waiting._state.clock.simulation_elapsed == 0.05, "local restart clock stopped")
	_expect(waiting._state.ball.position.x != headless._state.ball.position.x, "restart still updates state")
	var detached: Dictionary = waiting.observe()
	detached["snapshot"]["home"]["players"][0]["position"][0] = -999
	_expect(waiting._state.home.players[0].position.x != -999, "observation is detached")
	var full: MatchKernel = _test_kernel(input)
	var count: int = 0
	while full.is_playing() and count < 12000:
		if not full.apply({"kind": "STEP", "dt": 0.05}):
			break
		count += 1
	_expect(not full.is_playing() and full._state.clock.game_time == 5400 and count == 10800, "90 minute foundation clock with all test stages")
	_expect(full._state.clock.halftime_done, "halftime reached")
	_expect(full.observe()["result"] == null, "unmigrated football result is not fabricated")
	var ended: Dictionary = full.observe()
	_expect(full.apply({"kind": "STEP", "dt": 0.05}), "fulltime no-op")
	_expect(MatchTraceComparison.first_difference(ended, full.observe()) == null, "ended state does not move")
	var object: Object = full._state.ball
	_expect(not object is Node, "Node-free state")


func _check_invalid_rosters(input: Dictionary) -> void:
	for change: Dictionary in [{"bench": null}, {"bench": [null]}, {"tactic": []}, {"tactical_discipline": true}, {"tactical_discipline": 1.1}, {"starters": []}]:
		var copied: Dictionary = input.duplicate(true)
		var team: Dictionary = copied["repro_input"]["teams"]["home"] as Dictionary
		team.merge(change, true)
		_expect(not MatchKernel.from_input(copied).error.is_empty(), "malformed normalized team rejected")
	for change: Dictionary in [{"raw": null}, {"number": true}, {"name": []}, {"slot": ["FW", NAN, 0.5]}, {"slot": ["FW", 1.1, 0.5]}, {"slot": ["FW", 0.5]}, {"slot": ["invalid", 0.5, 0.5]}]:
		var copied: Dictionary = input.duplicate(true)
		var player: Dictionary = copied["repro_input"]["teams"]["home"]["starters"][0] as Dictionary
		player.merge(change, true)
		_expect(not MatchKernel.from_input(copied).error.is_empty(), "malformed normalized player rejected")
	var no_keeper: Dictionary = input.duplicate(true)
	for player: Dictionary in no_keeper["repro_input"]["teams"]["home"]["starters"] as Array:
		(player["slot"] as Array)[0] = "DF"
	_expect(not MatchKernel.from_input(no_keeper).error.is_empty(), "keeper required")


func _check_frame_rates_and_speeds(input: Dictionary, expected: MatchKernel) -> void:
	for frequency: int in [30, 120]:
		var kernel: MatchKernel = _test_kernel(input, true)
		var driver: FixedStepDriver = FixedStepDriver.new(kernel)
		for frame: int in frequency:
			driver.advance(1.0 / frequency)
			kernel.observe()
		_expect(MatchTraceComparison.first_difference(expected.observe(), kernel.observe()) == null, "frame rate state: " + str(frequency))
		_expect(MatchTraceComparison.first_difference(expected.rng.history(), kernel.rng.history()) == null, "frame rate RNG: " + str(frequency))
	for speed: int in [1, 2, 3, 5, 10, 100]:
		var kernel: MatchKernel = _test_kernel(input, true)
		_expect(kernel.apply({"kind": "SET_SPEED", "value": speed}), "set all supported speeds")
		var driver: FixedStepDriver = FixedStepDriver.new(kernel)
		_expect(driver.advance(1.0 / speed) == 20, "speed ticks: " + str(speed))
		var snapshot: Dictionary = kernel.observe()
		snapshot["snapshot"]["status"]["speed_multiplier"] = 1
		_expect(MatchTraceComparison.first_difference(expected.observe(), snapshot) == null, "speed changes pacing only")
		_expect(MatchTraceComparison.first_difference(expected.rng.history(), kernel.rng.history()) == null, "speed keeps RNG order")
