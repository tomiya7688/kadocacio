# {
#   責務: [ball_physics_tests: 実Godotの自由ボール規則を参照fixtureと固定更新・未移行障壁で検査する]
#   フィールド: [_assertions: 検査数; _failures: 失敗数; _entries: 外部再照合へ出す観測列]
# }
extends SceneTree
## Isolated actual ball rules, not football AI, contact success or restart parity.

var _assertions: int = 0
var _failures: int = 0
var _entries: Array[Dictionary] = []


# {
#   責務: [_initialize: 初期化後のボール検査を予約します]
#   処理: [1: 検査本体を遅延呼出しへ登録します]
#   引数: []
#   戻り値: [void: SceneTree初期化後に検査を実行します]
# }
func _initialize() -> void:
	_run.call_deferred()


# {
#   責務: [_expect: 一つの不変条件の検査結果を記録します]
#   処理: [1: 検査数を増やします; 2: 不成立なら失敗数と診断ログを更新します]
#   引数: [condition: 成功条件; label: 違反時の診断]
#   戻り値: [void: 最後の終了コードへ反映します]
# }
func _expect(condition: bool, label: String) -> void:
	_assertions += 1
	if not condition:
		_failures += 1
		push_error(label)


# {
#   責務: [_run: ボール規則と再開準備の回帰試験を実行して外部観測を保存する]
#   処理: [1: 引数と公開fixtureを読込; 2: 各弾道・ペース・障壁・準備中停止を検査; 3: 参照列と比較して観測・終了コードを保存]
#   引数: []
#   戻り値: [void: 試験成否でプロセスを終了。全試合や接触成否を認定しない]
# }
func _run() -> void:
	# 正式な引数でのみ入力を読み、入力不正を演算の成功へ置き換えません。
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size() != 4 or args[0] != "--fixture" or args[2] != "--output":
		quit(2)
		return
	var parsed: Dictionary = StrictJsonReader.read_file(args[1])
	_expect((parsed["error"] as String).is_empty(), "ball fixture")
	var fixture: Dictionary = parsed["data"] as Dictionary
	# 全ケースの実観測を生成し、代表弾道だけはペース非依存も確認します。
	for item: Dictionary in fixture["cases"] as Array:
		_replay(fixture["input"] as Dictionary, item)
		if item["name"] in ["slow_roll", "fast_roll", "lofted", "curve", "knuckle"]:
			_check_pacing(fixture["input"] as Dictionary, item)
	_check_integration(fixture["input"] as Dictionary, (fixture["cases"] as Array)[0] as Dictionary)
	_check_preparation(fixture["input"] as Dictionary, (fixture["cases"] as Array)[0] as Dictionary)
	# 再出力した期待値ではなく、実更新から得た観測列を外部比較へ渡します。
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


# {
#   責務: [_configured: Python参照のボール単体入力を試合状態へ復元します]
#   処理: [1: 開始済み核を作成します; 2: 選手の座標・速度・退場状態と接触精度を復元します; 3: ボールの付随情報と参照を復元します; 4: 指定された保持・解放を適用します]
#   引数: [input: 共通試合入力; item: ボール単体ケース]
#   戻り値: [MatchKernel: AIと選手移動を進めない検証専用の試合核]
# }
func _configured(input: Dictionary, item: Dictionary) -> MatchKernel:
	var copied: Dictionary = input.duplicate(true)
	# 観測された接触精度を直接設定し、後続の疲労更新や選手移動は接続しません。
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


# {
#   責務: [_replay: 一ケースを実Godotで固定更新して全時点をPython参照と比較します]
#   処理: [1: 入力状態とGK応答の模擬接続を構成します; 2: 通常接触は成否処理前で止めます; 3: 各時点を実更新して比較します; 4: 実観測を外部再照合用の列へ保存します]
#   引数: [input: 正式試合入力; item: 初期値と期待時点列を持つボールケース]
#   戻り値: [void: 差分を失敗数へ記録し、実観測を_entriesへ追記します]
# }
func _replay(input: Dictionary, item: Dictionary) -> void:
	var kernel: MatchKernel = _configured(input, item)
	var system: BallSimulationSystem = BallSimulationSystem.new()
	var probe: BallRuleProbe = BallRuleProbe.new()
	# GK成否はPythonと同様に模擬し、通常接触は所有変更前の最初の候補を観測します。
	_expect(system.connect_contacts(probe.save, probe.touch), "connect keeper seam")
	system._touch_resolver = Callable()
	# 期待値は更新回数と比較に使い、実座標や候補は必ず演算で取得します。
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


# {
#   責務: [_simulation: 固定ドライバー経由のボール検査核を構成します]
#   処理: [1: ボールの初期状態を復元します; 2: 選手・判断の試験用段階と実ボール段階を明示登録します]
#   引数: [input: 正式試合入力; item: ボールの初期ケース]
#   戻り値: [MatchKernel: 行動AIや接触成否を代用しない部分演算専用の核]
# }
func _simulation(input: Dictionary, item: Dictionary) -> MatchKernel:
	var kernel: MatchKernel = _configured(input, item)
	var system: BallSimulationSystem = BallSimulationSystem.new()
	var probe: BallRuleProbe = BallRuleProbe.new()
	_expect(kernel.register_system("players", probe.players) and kernel.register_system("decisions", probe.decisions) and kernel.register_system("ball", system.update), "real ball stage")
	return kernel


# {
#   責務: [_check_pacing: 描画頻度と倍速を変えても同じボール演算になることを確認します]
#   処理: [1: 直接固定更新二十回の参照を作ります; 2: 三頻度と全六倍速で固定ドライバーを進めます; 3: 更新数・ボール値・乱数消費を比較します]
#   引数: [input: 正式試合入力; item: 比較する代表弾道]
#   戻り値: [void: 時計だけの進行や観測の乱数消費があれば失敗します]
# }
func _check_pacing(input: Dictionary, item: Dictionary) -> void:
	# 比較基準も同じ核と実ボール更新で作り、結果式へ置き換えません。
	var expected: MatchKernel = _simulation(input, item)
	for tick: int in 20:
		_expect(expected.apply({"kind": "STEP", "dt": 0.05}), "headless ball step")
	for frequency: int in [30, 60, 120]:
		# 倍速ごとに実時間を短くし、物理時間は一秒二十tickへ揃えます。
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


# {
#   責務: [_check_preparation: 再開準備中に自由ボールが動かず配置段階と演算経過だけが進むことを確認する]
#   処理: [1: スローとセットプレーの準備状態を作る; 2: 直接更新と固定20tickのボール・時計・候補・呼出数を確認; 3: 準備解除後の飛行再開を確認]
#   引数: [input: 公開試合入力; item: 自由ボールの初期fixture]
#   戻り値: [void: 準備中の誤接触・時計進行・演算全停止を試験失敗にする]
# }
func _check_preparation(input: Dictionary, item: Dictionary) -> void:
	for preparation: String in ["restart", "throw_in"]:
		var kernel: MatchKernel = _configured(input, item)
		var system: BallSimulationSystem = BallSimulationSystem.new()
		var probe: BallRuleProbe = BallRuleProbe.new()
		kernel._state.ball.owner = null
		kernel._state.ball.velocity.set_values(1000, 0)
		kernel._state.home.players[1].position.set_values(kernel._state.ball.position.x, kernel._state.ball.position.y)
		if preparation == "restart":
			kernel._state.restart = {"kind": "FREE_KICK"}
		else:
			kernel._state.throw_in = {"side": "HOME"}
		var before: Dictionary = kernel.observe_ball()
		var words: int = kernel.rng.word_count
		system.update(kernel._state, 0.05, kernel.rng)
		_expect(MatchTraceComparison.first_difference(before, kernel.observe_ball()) == null, "direct preparation skips free ball")
		_expect(kernel.register_system("players", probe.players) and kernel.register_system("decisions", probe.decisions) and kernel.register_system("ball", system.update), "preparation stage connection")
		for tick: int in 20:
			_expect(kernel.apply({"kind": "STEP", "dt": 0.05}), "preparation continues without false contact barrier")
		_expect(MatchTraceComparison.first_difference(before, kernel.observe_ball()) == null, "preparation freezes ball and contact queues")
		_expect(kernel._state.clock.game_time == 0.0 and is_equal_approx(kernel._state.clock.simulation_elapsed, 1.0), "preparation freezes match clock but not elapsed simulation")
		_expect(probe.player_updates == 20 and probe.decision_updates == 20, "preparation still updates positioning stages")
		_expect(probe.saves == 0 and probe.touches == 0 and kernel.rng.word_count == words, "preparation has no contact resolution or RNG consumption")
		kernel._state.restart.clear()
		kernel._state.throw_in.clear()
		_expect(kernel.apply({"kind": "STEP", "dt": 0.05}), "free ball resumes after preparation")
		var initial_x: float = (before["ball"]["position"] as Array)[0] as float
		_expect(kernel._state.ball.position.x != initial_x and kernel._state.clock.game_time > 0.0, "normal ball flight and match clock resume")


# {
#   責務: [_check_integration: ボール接続の未解決障壁と観測・保持変更の境界を検査します]
#   処理: [1: 未解決の境界と接触で次STEPが停止することを確認します; 2: 観測値の編集が実状態へ戻らないことを確認します; 3: 無効接続の拒否とセーブの先行順を検査します; 4: 保持者の解放で予約キックが解除されることを確認します]
#   引数: [input: 正式試合入力; item: 検証核の初期ボールケース]
#   戻り値: [void: 未移行成否の偽進行や所有情報の残留があれば失敗します]
# }
func _check_integration(input: Dictionary, item: Dictionary) -> void:
	# 境界検出だけで得点を確定したり、未解決のまま時計を進めたりしません。
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
	# 観測を破壊的に変更しても、演算側の座標は所有者が保持します。
	snapshot["ball"]["position"][0] = -999
	_expect(contact._state.ball.position.x != -999, "flight observation detached")
	var system: BallSimulationSystem = BallSimulationSystem.new()
	# 接続の有効性と、境界検出より先に処理するセーブの順序を確認します。
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
	# こぼれた後に古い保持者の予約キックが発動しないことを確認します。
	pending._state.ball.owner = pending._state.home.players[1]
	pending._state.pending_kick = {"player": pending._state.ball.owner.identity}
	BallPossessionSystem.release_knockback(pending._state, pending._state.ball.owner, 1, 0)
	_expect(pending._state.pending_kick.is_empty() and pending._state.ball.owner == null, "spill cancels owner's kick")
