# {
#   責務: [BallContactQuery: 距離・高さ・回収待ち・GKの手の規則から接触候補を抽出します]
#   フィールド: []
# }
class_name BallContactQuery
extends RefCounted
## Reference spatial/height/lock/recovery gates. Skill/control decisions follow #128.


# {
#   責務: [hands_legal: 対象GKが現在のボールを手で扱えるか確認します]
#   処理: [1: GKと自陣エリア内のボールに限定します; 2: 最終接触者を確認します; 3: 味方からの意図的なパス等を除外します]
#   引数: [state: ボールの位置と接触情報; player: 判定する選手]
#   戻り値: [bool: 手を使える場合true。捕球成否は判定しません]
# }
static func hands_legal(state: MatchState, player: PlayerState) -> bool:
	# 攻撃方向から自陣のゴールとエリアを求め、両チームへ同じ規則を使います。
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
	# 自身・相手・接触者なしは許可し、味方からの意図的な返球だけを制限します。
	if last == null or last == player or not last.identity.begins_with(player.identity.get_slice(":", 0) + ":"):
		return true
	if state.ball.intended == player:
		return false
	for token: String in ["パス", "スローイン", "ゴールキック", "コーナーキック"]:
		if token in state.ball.flight_type:
			return false
	return true


# {
#   責務: [save_candidate: 速い自由ボールに対するGKセーブの広めの幾何候補を抽出します]
#   処理: [1: 保持中や低速のボールを除外します; 2: 進行方向側の最初のGKと手の規則を確認します; 3: 最大到達範囲内なら候補を構成します]
#   引数: [state: 両チームと現在のボールを持つ試合状態]
#   戻り値: [BallContactCandidate: セーブ検討候補。対象なしはnull。実スキル・セーブの成否は別処理です]
# }
static func save_candidate(state: MatchState) -> BallContactCandidate:
	# 最終の手の半径は成否処理が決めるため、ここでは技能込みの上限を使います。
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


# {
#   責務: [touches: 自由ボールへ通常接触できる候補を参照順で列挙します]
#   処理: [1: 保持中は候補を返しません; 2: 退場と再取得待ちを除外します; 3: 高さ・到達半径と回収優先を計算します; 4: 優先側・距離・走査順で整列します]
#   引数: [state: ボールと現在の出場選手]
#   戻り値: [Array: 並べ替え済みの候補。所有者や接触の成否は変更しません]
# }
static func touches(state: MatchState) -> Array[BallContactCandidate]:
	var ball: BallState = state.ball
	if ball.owner != null:
		return []
	var rules: Dictionary = MatchProtocol.values()["ball_rules"] as Dictionary
	var scale: float = rules["visual_scale"] as float
	var results: Array[BallContactCandidate] = []
	var ordinal: int = 0
	# 同距離でも選手配列順を維持し、並べ替えで結果が揺れないようにします。
	for team: TeamState in [state.home, state.away]:
		for player: PlayerState in team.players:
			ordinal += 1
			if player.sent_off or (ball.pickup_lock > 0 and player == ball.last_touch):
				continue
			var legal: bool = hands_legal(state, player)
			# 手・空中・地上の到達条件を分け、回収優先側だけ半径を追加します。
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
				# 高速シュートのGK対応は先行するセーブ候補へ委ねます。
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


# {
#   責務: [_nearer: 接触候補の優先順を比較します]
#   処理: [1: 回収優先値を比較します; 2: 同順位なら距離二乗を比較します; 3: 同距離なら元の走査順を使います]
#   引数: [first: 先の候補; second: 後の候補]
#   戻り値: [bool: firstを先に並べる場合true]
# }
static func _nearer(first: BallContactCandidate, second: BallContactCandidate) -> bool:
	if first.priority != second.priority:
		return first.priority < second.priority
	if first.distance_squared != second.distance_squared:
		return first.distance_squared < second.distance_squared
	return first.ordinal < second.ordinal
