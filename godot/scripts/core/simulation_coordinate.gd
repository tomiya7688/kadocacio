# {
#   責務: [SimulationCoordinate: 描画のVector3に依存しない64bit実数のワールド座標を保持する]
#   フィールド: [x: ピッチ長手方向; y: ピッチ幅方向; z: 地面からの高さ。単位は試合のワールド座標]
# }
class_name SimulationCoordinate
extends RefCounted
## 64-bit scalar world coordinates; render Vector3 conversion belongs to the view.

var x: float = 0.0
var y: float = 0.0
var z: float = 0.0


# {
#   責務: [set_values: 同一座標オブジェクトの三成分を置き換える]
#   処理: [1: 渡された三成分を変換せず保存する]
#   引数: [next_x: 次の長手座標; next_y: 次の幅座標; next_z: 次の高さ。省略時は地面の0]
#   戻り値: [void: 座標を更新する。範囲検証や描画変換は行わない]
# }
func set_values(next_x: float, next_y: float, next_z: float = 0.0) -> void:
	# 物理側の数値精度を保ち、表示用のVector3変換は表示側へ任せる。
	x = next_x
	y = next_y
	z = next_z


# {
#   責務: [to_array: 境界JSONへ渡せる成分順の独立配列を作る]
#   処理: [1: x・y・zの順に新しい配列へ格納する]
#   引数: []
#   戻り値: [Array[float]: 長手・幅・高さの三成分。元の座標は変更しない]
# }
func to_array() -> Array[float]:
	# 配列を編集しても演算中の座標オブジェクトには書き戻されない。
	return [x, y, z]
