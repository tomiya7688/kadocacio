# {
#   責務: [BallBoundaryEvent: 検出したポスト接触・得点候補・場外と再開候補の位置を保持します]
#   フィールド: [kind: 検出種別; side: 得点候補側または再開側。ポストは空文字; spot: 検出または再開候補の平面座標]
# }
class_name BallBoundaryEvent
extends RefCounted
## One detected post/goal/exit, not a completed restart or scored match result.

var kind: String
var side: String
var spot: SimulationCoordinate


# {
#   責務: [_init: 一回の境界検出を独立した値へ構成します]
#   処理: [1: 種別と対象側を保存します; 2: 位置を専用座標へ保持します]
#   引数: [event_kind: 検出種別; team_side: 対象チーム側; x: 検出位置の横座標; y: 検出位置の縦座標]
#   戻り値: [void: 検出値を初期化します。得点加算や再開処理は行いません]
# }
func _init(event_kind: String, team_side: String, x: float, y: float) -> void:
	# 元のボール座標を共有せず、検出時点の位置を保持します。
	kind = event_kind
	side = team_side
	spot = SimulationCoordinate.new()
	spot.set_values(x, y)


# {
#   責務: [to_payload: 境界検出を外部観測用の値へ変換します]
#   処理: [1: 種別・側・平面位置を新しい辞書と配列へ写します]
#   引数: []
#   戻り値: [Dictionary: 元の座標を共有しない観測値]
# }
func to_payload() -> Dictionary:
	return {"kind": kind, "side": side, "spot": [spot.x, spot.y]}
