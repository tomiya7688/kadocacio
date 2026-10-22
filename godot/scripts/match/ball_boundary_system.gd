# {
#   責務: [BallBoundarySystem: 参照順序でボールのポスト接触・ゴール候補・場外を検出します]
#   フィールド: []
# }
class_name BallBoundarySystem
extends RefCounted
## Reference-ordered post/goal/touchline/endline detection. Restarts follow #129.


# {
#   責務: [detect: ボールの境界状態を判定し必要な跳ね返りだけを反映します]
#   処理: [1: コートとゴールの境界を取得します; 2: 指定されたポストミスの反射を処理します; 3: ゴール候補・タッチライン・エンドラインの順に検出します]
#   引数: [state: 現在のボールと最終接触者を持つ試合状態]
#   戻り値: [BallBoundaryEvent: 最初に成立した検出。該当なしはnull。得点確定と再開進行は行いません]
# }
static func detect(state: MatchState) -> BallBoundaryEvent:
	# 正本の寸法を使い、ライン上は場内として扱います。
	var ball: BallState = state.ball
	var field: Array = MatchProtocol.values()["kernel"]["field"] as Array
	var left: float = field[0] as float
	var right: float = left + (field[2] as float)
	var top: float = field[1] as float
	var bottom: float = top + (field[3] as float)
	var center_y: float = (top + bottom) / 2
	var rules: Dictionary = MatchProtocol.values()["ball_rules"] as Dictionary
	var goal_half: float = rules["goal_half_width"] as float
	var crossed: bool = ball.position.x > right or ball.position.x < left
	# POST指定のシュートだけを先に跳ね返し、後の得点検出と二重に扱いません。
	if ball.shot_outcome == "POST" and "シュート" in ball.flight_type and crossed:
		var goal_x: float = right if ball.position.x > right else left
		var inward: float = -1.0 if ball.position.x > right else 1.0
		var post_y: float = center_y + (goal_half if ball.position.y >= center_y else -goal_half)
		ball.position.set_values(goal_x + inward * 3, post_y, ball.position.z)
		ball.velocity.x *= -0.48
		ball.velocity.y = (center_y - post_y) * 1.35 - ball.velocity.y * 0.28
		ball.velocity.z = maxf(24.0, absf(ball.velocity.z) * 0.42)
		ball.curve_acceleration = 0.0
		ball.curve_vector.set_values(0, 0)
		ball.knuckle_amplitude = 0.0
		ball.flight_type = "ポスト跳ね返り"
		ball.shot_outcome = ""
		ball.catch_forbidden = false
		return BallBoundaryEvent.new("POST", "", goal_x, post_y)
	# 同じ更新で複数ラインを越えた場合も、Pythonと同じ優先順を維持します。
	if crossed and absf(ball.position.y - center_y) <= goal_half and ball.position.z <= (rules["goal_height"] as float):
		return BallBoundaryEvent.new("GOAL", "HOME" if ball.position.x > right else "AWAY", ball.position.x, ball.position.y)
	if ball.position.y < top or ball.position.y > bottom:
		ball.shot_outcome = ""
		var receiving: String = "AWAY" if ball.last_touch != null and ball.last_touch.identity.begins_with("HOME:") else "HOME"
		return BallBoundaryEvent.new("THROW_IN", receiving, clampf(ball.position.x, left + 16, right - 16), top if ball.position.y < top else bottom)
	if crossed:
		# 最終接触が守備側ならコーナー、それ以外はゴールキック候補です。
		var left_exit: bool = ball.position.x < left
		var defending: String = "HOME" if left_exit else "AWAY"
		var attacking: String = "AWAY" if left_exit else "HOME"
		ball.shot_outcome = ""
		if ball.last_touch != null and ball.last_touch.identity.begins_with(defending + ":"):
			return BallBoundaryEvent.new("CORNER_KICK", attacking, left if left_exit else right, top if ball.position.y < center_y else bottom)
		return BallBoundaryEvent.new("GOAL_KICK", defending, left + 52 if left_exit else right - 52, center_y)
	return null
