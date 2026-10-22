# {
#   責務: [MatchKernel: 明示接続された試合段階へ固定更新と操作を配信する演算核です]
#   フィールド: [error: 直近の拒否理由; rng: 試合専用乱数; _state: 外部へ共有しない試合状態; _systems: 選手・判断・ボールの呼出先; _system_owners: 受信側を生存させる強参照; _started: 開始済みか]
# }
class_name MatchKernel
extends RefCounted
## Fixed-step foundation, not a complete football match. Missing systems fail closed.

var error: String = ""
var rng: ObservedMatchRandom
var _state: MatchState
var _systems: Dictionary = {}
var _system_owners: Dictionary = {}
var _started: bool = false


static func from_input(payload: Variant, audit_rng: bool = false) -> MatchKernel:
	var kernel: MatchKernel = MatchKernel.new()
	var input: MatchInputRecord = MatchInputRecord.read(payload)
	if not input.is_valid():
		kernel.error = input.error
		return kernel
	var record: Dictionary = input.to_payload()
	var repro: Dictionary = record["repro_input"] as Dictionary
	var teams: Dictionary = repro["teams"] as Dictionary
	var settings: Dictionary = repro["settings"] as Dictionary
	for side: String in ["home", "away"]:
		var team: Dictionary = teams[side] as Dictionary
		if not _valid_team_options(team) or not _valid_starters(team["starters"] as Array):
			kernel.error = "invalid normalized starters"
			return kernel
	kernel.rng = ObservedMatchRandom.new(settings["seed"] as String)
	kernel.rng.enabled = audit_rng
	kernel._state = MatchSetup.create(record, kernel.rng)
	return kernel


static func _valid_team_options(team: Dictionary) -> bool:
	var loyalty: Variant = team.get("tactical_discipline", 0.5)
	if not (loyalty is int or loyalty is float) or not is_finite(loyalty as float) or (loyalty as float) < 0 or (loyalty as float) > 1:
		return false
	if not team.get("tactic", "BALANCE") is String or not team.get("bench", []) is Array:
		return false
	for item: Variant in team.get("bench", []) as Array:
		if not item is Dictionary:
			return false
	return true


static func _valid_starters(records: Array) -> bool:
	if records.size() < 7 or records.size() > 11:
		return false
	var keepers: int = 0
	for item: Variant in records:
		if not item is Dictionary:
			return false
		var record: Dictionary = item as Dictionary
		if not record.get("raw") is Dictionary or not record.get("name") is String or not MatchProtocol.is_integer(record.get("number")) or not record.get("slot") is Array:
			return false
		var slot: Array = record["slot"] as Array
		if slot.size() != 3 or not ["FW", "MF", "DF", "GK"].has(slot[0]):
			return false
		for coordinate: Variant in slot.slice(1):
			if not (coordinate is int or coordinate is float) or not is_finite(coordinate as float) or (coordinate as float) < 0 or (coordinate as float) > 1:
				return false
		keepers += 1 if slot[0] == "GK" else 0
	return keepers > 0


func register_system(stage: String, update: Callable) -> bool:
	if not ["players", "decisions", "ball"].has(stage) or not update.is_valid() or not update.get_object() is RefCounted:
		error = "invalid simulation stage"
		return false
	_systems[stage] = update
	# A Callable does not retain a RefCounted receiver. Keep a strong owner to
	# prevent a valid stage becoming a dangling callback between fixed ticks.
	_system_owners[stage] = update.get_object()
	error = ""
	return true


func apply(payload: Variant) -> bool:
	var operation: MatchOperation = MatchOperation.read(payload)
	if _state == null or not operation.is_valid():
		error = "invalid session/operation"
		return false
	error = ""
	if operation.kind == "START":
		if _started:
			error = "START may only occur once"
			return false
		rng.purpose = "start"
		MatchSetup.start(_state, rng)
		_started = true
		return true
	if not _started:
		error = "START required"
		return false
	if operation.kind == "SET_SPEED":
		_state.speed_multiplier = operation.to_payload()["value"] as int
	elif operation.kind == "PAUSE" or operation.kind == "RESUME":
		_state.paused = operation.kind == "PAUSE"
	else:
		return _step(operation.to_payload()["dt"] as float)
	return true


# {
#   責務: [_step: 一固定時間の時計と接続済み段階の実行を指揮します]
#   処理: [1: ポーズ・終了と未解決の接触境界を確認します; 2: 更新上限と必須段階の存在を時計更新前に検査します; 3: 時計と前後半遷移を反映します; 4: 準備中または通常中の各段階を順に呼びます]
#   引数: [dt: 操作契約で検証済みの固定秒]
#   戻り値: [bool: 受理ならtrue。未接続・未解決・上限超過はerrorへ理由を保存してfalse]
# }
func _step(dt: float) -> bool:
	# 停止は受理しますが、未解決の物理イベントを時計だけで追い越しません。
	if _state.paused or _state.clock.state == "FULLTIME":
		return true
	if _state.ball_boundary != null or _state.ball_contact != null:
		error = "unresolved ball contact/boundary: migration resolver required"
		return false
	if _state.step >= _state.max_steps:
		error = "physics step budget exhausted"
		return false
	var banner_active: bool = _state.clock.banner_timer > 0
	var waiting: bool = not _state.restart.is_empty() or not _state.throw_in.is_empty()
	# No clock-only live-play fallback. Later migration units supply these stages.
	if not banner_active or waiting:
		for stage: String in ["players", "decisions", "ball"]:
			if not _systems.has(stage):
				error = "unimplemented simulation stage: " + stage
				return false
	rng.purpose = "step"
	# 試合時計の準備停止と、演算経過・段階の固定更新を区別します。
	rng.step = _state.step + 1
	var transition: String = _state.clock.advance(dt, waiting)
	_state.step += 1
	if banner_active and _state.ball.owner != null:
		_state.ball.position.x = _state.ball.owner.position.x + _state.ball.control_offset
		_state.ball.position.y = _state.ball.owner.position.y + _state.ball.control_offset_y
	if transition == "HALFTIME":
		# 前後半の再配置と終了は通常の選手段階を呼ぶ前に確定します。
		_state.events.append("ハーフタイム", _state.clock)
		MatchSetup.reset_positions(_state, _state.away, rng)
		return true
	if transition == "FULLTIME":
		_state.pending_kick.clear()
		_state.restart.clear()
		_state.throw_in.clear()
		_state.events.append("試合終了", _state.clock)
		return true
	if waiting:
		for stage: String in ["players", "decisions", "ball"]:
			(_systems[stage] as Callable).call(_state, dt, rng)
	elif not banner_active:
		for stage: String in ["players", "decisions", "ball"]:
			(_systems[stage] as Callable).call(_state, dt, rng)
	return true


func observe(after_sequence: int = 0) -> Dictionary:
	if not _started or after_sequence < 0:
		error = "START and nonnegative event cursor required"
		return {}
	return MatchSnapshot.capture(_state, after_sequence)


func is_ready() -> bool:
	return _started


# {
#   責務: [observe_ball: 現在のボールと未解決の境界・接触候補を観測します]
#   処理: [1: 未開始なら空を返します; 2: ボール・検出値を独立したペイロードへ変換します]
#   引数: []
#   戻り値: [Dictionary: ボール単体の部分観測。時間や乱数を進めません]
# }
func observe_ball() -> Dictionary:
	if not _started:
		return {}
	return {"ball": BallObservation.capture(_state.ball),
		"boundary": null if _state.ball_boundary == null else _state.ball_boundary.to_payload(),
		"contact": null if _state.ball_contact == null else _state.ball_contact.to_payload()}


func is_playing() -> bool:
	return _state != null and _state.clock.state == "PLAYING"


func is_paused() -> bool:
	return _state != null and _state.paused


func speed() -> int:
	return _state.speed_multiplier if _state != null else 1
