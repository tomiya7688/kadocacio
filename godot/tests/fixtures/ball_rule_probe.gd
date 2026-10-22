# {
#   責務: [BallRuleProbe: ボール試験で更新回数と明示指定した接触成否を観測する]
#   フィールド: [save_resultとtouch_result: 模擬成否; savesとtouches: 接触呼出数; player_updatesとdecision_updates: 準備配置用段階の呼出数]
# }
class_name BallRuleProbe
extends RefCounted
## Test seam only: no AI/movement, and explicitly selected keeper/touch outcomes.

var save_result: bool = false
var touch_result: bool = false
var saves: int = 0
var touches: int = 0
var player_updates: int = 0
var decision_updates: int = 0


# {
#   責務: [players: 選手更新段階が準備中にも呼び出されることを記録する]
#   処理: [1: 更新回数を増加。移動演算の代用品は作らない]
#   引数: [_state: 接続シグネチャ用の状態; _dt: 固定秒; _rng: 乱数。いずれも消費しない]
#   戻り値: [void: 観測カウンタのみ更新]
# }
func players(_state: MatchState, _dt: float, _rng: ObservedMatchRandom) -> void:
	player_updates += 1


# {
#   責務: [decisions: 判断更新段階が準備中にも呼び出されることを記録する]
#   処理: [1: 更新回数を増加。AI判断は模擬しない]
#   引数: [_state: 接続シグネチャ用の状態; _dt: 固定秒; _rng: 消費しない乱数]
#   戻り値: [void: 観測カウンタのみ更新]
# }
func decisions(_state: MatchState, _dt: float, _rng: ObservedMatchRandom) -> void:
	decision_updates += 1


# {
#   責務: [save: セーブ候補の到達を記録して試験で指定した成否を返す]
#   処理: [1: 呼出数を増加; 2: 指定結果を返す]
#   引数: [_state: 試合状態; _candidate: 候補; _rng: 乱数。試験接続では状態変更や乱数消費をしない]
#   戻り値: [bool: save_resultの模擬成否]
# }
func save(_state: MatchState, _candidate: BallContactCandidate, _rng: ObservedMatchRandom) -> bool:
	saves += 1
	return save_result


# {
#   責務: [touch: 通常接触候補の到達を記録して試験で指定した成否を返す]
#   処理: [1: 呼出数を増加; 2: 指定結果を返す]
#   引数: [_state: 試合状態; _candidate: 候補; _rng: 消費しない乱数]
#   戻り値: [bool: touch_resultの模擬成否]
# }
func touch(_state: MatchState, _candidate: BallContactCandidate, _rng: ObservedMatchRandom) -> bool:
	touches += 1
	return touch_result
