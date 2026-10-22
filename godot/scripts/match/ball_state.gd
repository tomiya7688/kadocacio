# {
#   責務: [BallState: 試合内の一個のボールの座標と保持・飛行情報を所有します]
#   フィールド: [
#     positionとvelocity: 平面と鉛直の運動状態; ownerとlast_touch: 保持者と最終接触者;
#     control_offsetとcontrol_offset_y: 保持者からの平面オフセット; intendedとintended_destination: 受取予定者と予定位置;
#     pickup_lock: 最終接触者の再取得待ち秒; curve_accelerationとcurve_vector: 曲がりの加速度;
#     knuckle_amplitudeとknuckle_phase: 揺れの振幅と位相; flight_type: 飛行の種別;
#     flight_serialとshot_serial: 飛行とシュートの識別通番; shot_deceptionとshot_outcomeとshot_miss_announced: シュートの読みづらさ・結果種別・通知済み状態;
#     pass_outcomeとpass_brake: パスの結果種別と着地後の減速; eye_contact_bonus: 受取時の補助値;
#     catch_forbiddenとlast_keeper_response: 捕球禁止と直近のGK応答; recovery_teamとrecovery_timer: こぼれ球回収の優先側と残り秒
#   ]
# }
class_name BallState
extends RefCounted
## Node-free flight/possession metadata. Rules live in dedicated ball systems.

var position: SimulationCoordinate = SimulationCoordinate.new()
var velocity: SimulationCoordinate = SimulationCoordinate.new()
var owner: PlayerState = null
var last_touch: PlayerState = null
var control_offset: float = 10.0
var control_offset_y: float = 0.0
var intended: PlayerState = null
var intended_destination: SimulationCoordinate = SimulationCoordinate.new()
var pickup_lock: float = 0.0
var curve_acceleration: float = 0.0
var curve_vector: SimulationCoordinate = SimulationCoordinate.new()
var knuckle_amplitude: float = 0.0
var knuckle_phase: float = 0.0
var flight_type: String = ""
var flight_serial: int = 0
var shot_serial: int = 0
var shot_deception: float = 0.0
var shot_outcome: String = ""
var shot_miss_announced: bool = false
var pass_outcome: String = ""
var pass_brake: float = 0.0
var eye_contact_bonus: float = 0.0
var catch_forbidden: bool = false
var last_keeper_response: String = ""
var recovery_team: TeamState = null
var recovery_timer: float = 0.0
