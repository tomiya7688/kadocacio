# {
#   責務: [PlayerState: 保存用の選手定義から独立した一人の試合内状態を所有します]
#   フィールド: [definition: 試合用定義; identity: 所属側と番号から作る試合内ID; direction: 攻撃方向; positionとvelocityとtarget: 現在の座標・速度・目標; staminaとstamina_max: 現在残量と最大容量; command: 現在の行動; sent_off: 退場状態; personal_tactic_timerとskillとroam_timer: 判断タイマーと個人倍率; contact_jump_accuracy: 接触候補で使う現在の実効精度。疲労による更新は後続の身体システムが担当します]
# }
class_name PlayerState
extends RefCounted
## Runtime player values, separate from saved definitions and rendering Nodes.

var definition: PlayerDefinition
var identity: String
var direction: int
var position: SimulationCoordinate = SimulationCoordinate.new()
var velocity: SimulationCoordinate = SimulationCoordinate.new()
var target: SimulationCoordinate = SimulationCoordinate.new()
var stamina: float
var stamina_max: float
var command: String = "HOLD_POSITION"
var sent_off: bool = false
var personal_tactic_timer: float
var skill: float
var roam_timer: float
# Current effective contact value; body/fatigue system #126 owns later updates.
var contact_jump_accuracy: float


# {
#   責務: [_init: 定義から満タンの選手状態と初期配置を構成します]
#   処理: [1: 定義・ID・方向を保持します; 2: 正規化能力から容量と接触精度を設定します; 3: Pythonと同順で初期乱数を取得して配置します]
#   引数: [player: 試合用選手定義; side: 所属側の識別名; index: 名簿内番号; team_direction: 攻撃方向; rng: 試合専用乱数]
#   戻り値: [void: 新しい試合内選手を構成します。元のJSONは変更しません]
# }
func _init(player: PlayerDefinition, side: String, index: int, team_direction: int, rng: ObservedMatchRandom) -> void:
	# 容量は契約の基準と能力幅から決め、疲労更新を先取りしません。
	definition = player
	identity = "%s:%d" % [side, index]
	direction = team_direction
	var rules: Dictionary = MatchProtocol.values()["kernel"] as Dictionary
	stamina_max = (rules["stamina_base"] as float) + (player.normalized_stats["MaxStamina"] as float) * (rules["stamina_span"] as float)
	stamina = stamina_max
	contact_jump_accuracy = player.normalized_stats["JumpAccuracy"] as float
	# 初期化の乱数順を維持し、観測や描画用の抽選を加えません。
	personal_tactic_timer = rng.uniform(1.5, 4.0)
	skill = rng.uniform(0.88, 1.12)
	roam_timer = rng.uniform(0.4, 1.8)
	reset_position(rng)


# {
#   責務: [reset_position: 定義の配置比率から再開時の位置と行動を設定します]
#   処理: [1: 攻撃方向に合わせて配置を反転します; 2: 座標・速度・目標を初期化します; 3: GKまたは通常の行動と徘徊タイマーを設定します]
#   引数: [rng: 徘徊時間を抽選する試合専用乱数]
#   戻り値: [void: スタミナ残量や選手定義は変更しません]
# }
func reset_position(rng: ObservedMatchRandom) -> void:
	# 同じ比率の配置を、両側の自陣で利用します。
	var field: Array = (MatchProtocol.values()["kernel"] as Dictionary)["field"] as Array
	var slot: Array = definition.slot as Array
	var home_x: float = slot[1] as float
	var world_x: float = home_x if direction == 1 else 1.0 - home_x
	position.set_values((field[0] as float) + world_x * (field[2] as float), (field[1] as float) + (slot[2] as float) * (field[3] as float))
	velocity.set_values(0, 0)
	target.set_values(position.x, position.y)
	command = "GUARD_GOAL" if slot[0] == "GK" else "HOLD_POSITION"
	roam_timer = rng.uniform(0.4, 1.8)
