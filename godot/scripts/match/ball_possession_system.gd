# {
#   責務: [BallPossessionSystem: ボールの飛行情報の解除・保持開始・ノックバック時の解放を反映します]
#   フィールド: []
# }
class_name BallPossessionSystem
extends RefCounted
## Ball-only claim/reset/spill effects. Decision timing/skills stay with later units.


# {
#   責務: [reset_flight: 次の保持に引き継がない飛行情報を初期化します]
#   処理: [1: 受取予定・再取得待ち・速度と曲がりを解除します; 2: パス・シュート・GK応答・回収優先の情報を解除します]
#   引数: [ball: 初期化対象; x: 新しい予定先の横座標; y: 新しい予定先の縦座標]
#   戻り値: [void: owner・last_touch・現在位置と飛行通番は変更しません]
# }
static func reset_flight(ball: BallState, x: float, y: float) -> void:
	# 所有者や最終接触者の変更は、この関数を使う保持・再配置処理が担当します。
	ball.intended = null
	ball.pickup_lock = 0.0
	ball.velocity.set_values(0, 0)
	ball.curve_acceleration = 0.0
	ball.curve_vector.set_values(0, 0)
	ball.knuckle_amplitude = 0.0
	ball.flight_type = ""
	ball.shot_deception = 0.0
	ball.shot_outcome = ""
	ball.shot_miss_announced = false
	ball.pass_outcome = ""
	ball.pass_brake = 0.0
	ball.intended_destination.set_values(x, y)
	ball.eye_contact_bonus = 0.0
	ball.catch_forbidden = false
	ball.last_keeper_response = ""
	ball.recovery_team = null
	ball.recovery_timer = 0.0


# {
#   責務: [claim: 取得が決まった選手へボールの保持を移します]
#   処理: [1: 既存の再取得待ち時間を保存して飛行情報を解除します; 2: 所有者・最終接触者・高さ・保持オフセットを設定します]
#   引数: [ball: 保持対象; player: 取得が成立した選手; offset_x: 保持時の横オフセット; offset_y: 保持時の縦オフセット]
#   戻り値: [void: 平面位置と取得の成功率は決めません。選手AIや動作も変更しません]
# }
static func claim(ball: BallState, player: PlayerState, offset_x: float, offset_y: float = 0.0) -> void:
	# claimだけで待ち時間を消さず、Pythonのchange_ownerと同じ値を引き継ぎます。
	var lock: float = ball.pickup_lock
	reset_flight(ball, player.position.x, player.position.y)
	ball.pickup_lock = lock
	ball.owner = player
	ball.last_touch = player
	ball.position.z = 5.0
	ball.control_offset = offset_x
	ball.control_offset_y = offset_y


# {
#   責務: [release_knockback: 弾き飛ばされた保持者からボールを解放します]
#   処理: [1: 保持者以外の要求を無視します; 2: その選手の予約キックと保持情報を解除します; 3: こぼれ球の位置・速度・回収優先を設定します]
#   引数: [state: ボールと予約キックを持つ試合状態; player: 弾き飛ばされた選手; direction_x: 呼出元で決定した方向の横成分; direction_y: 方向の縦成分; recovery: タックル側の回収優先チーム。通常はnull]
#   戻り値: [void: こぼれ球を反映します。接触やタックルの成否・選手のノックバックは判定しません]
# }
static func release_knockback(state: MatchState, player: PlayerState, direction_x: float, direction_y: float, recovery: TeamState = null) -> void:
	var ball: BallState = state.ball
	# 他の選手のボールや予約キックを解除しません。
	if ball.owner != player:
		return
	if state.pending_kick.get("player") == player.identity:
		state.pending_kick.clear()
	ball.owner = null
	ball.last_touch = player
	ball.intended = null
	ball.eye_contact_bonus = 0.0
	ball.catch_forbidden = false
	ball.last_keeper_response = ""
	ball.pickup_lock = 0.16 if recovery != null else 0.34
	# タックル側の回収優先が指定された時は、ボールを後方へ短くこぼす規則を維持します。
	var offset: float = -6.0 if recovery != null else 12.0
	var power: float = 46.0 if recovery != null else 82.0
	ball.position.set_values(player.position.x + direction_x * offset, player.position.y + direction_y * offset, 6.0)
	ball.velocity.set_values(player.velocity.x * 0.16 + direction_x * power, player.velocity.y * 0.16 + direction_y * power, 18.0)
	ball.curve_acceleration = 0.0
	ball.curve_vector.set_values(0, 0)
	ball.knuckle_amplitude = 0.0
	ball.flight_type = "フィジカルこぼれ球"
	ball.recovery_team = recovery
	ball.recovery_timer = 1.25 if recovery != null else 0.0
