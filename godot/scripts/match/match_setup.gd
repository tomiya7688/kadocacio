# {
#   責務: [MatchSetup: 初期名簿・試合開始状態とキックオフ配置を構成します]
#   フィールド: []
# }
class_name MatchSetup
extends RefCounted
## Match-local initial rosters/formation/kickoff, preserving reference draw order.


# {
#   責務: [create: 検証済み入力から未開始の試合状態を構成します]
#   処理: [1: 設定を独立状態へ保持します; 2: 両チームを順に構成します; 3: ホーム側の初期キックオフ配置を設定します]
#   引数: [input: 正式な試合入力; rng: 初期状態用の試合乱数]
#   戻り値: [MatchState: 元入力と座標を共有しない試合状態]
# }
static func create(input: Dictionary, rng: ObservedMatchRandom) -> MatchState:
	# 初期状態の構成だけを担当し、通常プレイの段階は実行しません。
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


# {
#   責務: [start: 試合開始時の名簿・判断時刻・通知と配置を設定します]
#   処理: [1: 両名簿と監督・選手の判断タイマーを作り直します; 2: 時計をプレイ状態へ変えて開始通知を追加します; 3: キックオフ位置を再設定します]
#   引数: [state: 初期化済み試合状態; rng: Pythonと同じ順で取得する試合乱数]
#   戻り値: [void: 開始直後の状態へ更新します]
# }
static func start(state: MatchState, rng: ObservedMatchRandom) -> void:
	# 構築時の抽選を使い回さず、参照実装と同じ開始時の順序で更新します。
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


# {
#   責務: [reset_positions: 準備状態を解除して全選手とボールをキックオフへ再配置します]
#   処理: [1: 再開・予約キック・未解決の検出を解除します; 2: 全選手を初期配置へ戻します; 3: FWを優先して中央に近い保持者を選びます; 4: ボールの飛行を解除して保持を設定します]
#   引数: [state: 配置を更新する試合状態; kickoff_team: キックオフする側; rng: 徘徊タイマー用の試合乱数]
#   戻り値: [void: スコアと時計・選手のスタミナは維持します]
# }
static func reset_positions(state: MatchState, kickoff_team: TeamState, rng: ObservedMatchRandom) -> void:
	# 古い再開や未解決の接触を、再配置後へ持ち越しません。
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
	# FWがいない合法な編成でも、フィールド選手を保持者の候補にできます。
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
	# 同距離は元の名簿順を維持し、追加の乱数を消費しません。
	var nearest: float = INF
	for player: PlayerState in candidates:
		var distance: float = pow(player.position.x - center_x, 2) + pow(player.position.y - center_y, 2)
		if distance < nearest:
			nearest = distance
			owner = player
	owner.position.set_values(center_x - kickoff_team.direction * 12, center_y)
	# ボールの飛行を解除した後で、キックオフの保持者とオフセットを設定します。
	owner.command = "KEEP_BALL"
	state.ball.position.set_values(center_x, center_y, 4.0)
	state.ball.velocity.set_values(0, 0)
	BallPossessionSystem.reset_flight(state.ball, center_x, center_y)
	state.ball.owner = owner
	state.ball.last_touch = owner
	state.ball.control_offset = kickoff_team.direction * 10.0
	state.ball.control_offset_y = 0.0
