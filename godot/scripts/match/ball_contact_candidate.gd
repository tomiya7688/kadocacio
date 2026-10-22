# {
#   責務: [BallContactCandidate: 接触可能範囲に入った選手と幾何条件・選択順を保持します]
#   フィールド: [player: 候補選手; kind: 通常接触またはGKセーブ; radius: 平面到達半径; distance_squared: ボールとの距離二乗; hands_legal: 手を使用可能か; priority: こぼれ球回収側の優先値; ordinal: 同順位時に保つ走査順]
# }
class_name BallContactCandidate
extends RefCounted
## Geometric contact eligibility, not a successful trap/header/save probability.

var player: PlayerState
var kind: String = "TOUCH"
var radius: float
var distance_squared: float
var hands_legal: bool
var priority: int
var ordinal: int


# {
#   責務: [to_payload: 候補の識別情報を観測用の値へ変換します]
#   処理: [1: 種別・選手ID・手の使用可否を辞書へ写します]
#   引数: []
#   戻り値: [Dictionary: 接触成功を意味しない候補の観測値]
# }
func to_payload() -> Dictionary:
	return {"kind": kind, "player": player.identity, "hands_legal": hands_legal}
