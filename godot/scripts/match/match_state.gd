# {
#   責務: [MatchState: 一試合の変更可能な進行状態を演算核の内部で保持します]
#   フィールド: [
#     homeとaway: 両チーム; ball: ボール; clock: 試合時計と演算経過; events: 発生順の通知;
#     stepとmax_steps: 固定更新回数と上限; pausedとspeed_multiplier: 停止と再生倍率;
#     venue_modeとai_rethink_multiplier: 会場区分と判断周期倍率; restartとthrow_in: 再開準備; pending_kick: 予約キック;
#     ball_boundaryとball_contact: 成否処理を待つ検出; foul_countとcard_countとrestart_counts: 反則・カード・再開種別の集計
#   ]
# }
class_name MatchState
extends RefCounted
## Mutable engine-owned state; callers obtain MatchSnapshot copies instead.

var home: TeamState
var away: TeamState
var ball: BallState = BallState.new()
var clock: MatchClock = MatchClock.new()
var events: MatchEventLog = MatchEventLog.new()
var step: int = 0
var paused: bool = false
var speed_multiplier: int = 1
var max_steps: int
var venue_mode: String
var ai_rethink_multiplier: float
var restart: Dictionary = {}
var throw_in: Dictionary = {}
var pending_kick: Dictionary = {}
var ball_boundary: BallBoundaryEvent = null
var ball_contact: BallContactCandidate = null
var foul_count: int = 0
var card_count: int = 0
var restart_counts: Dictionary = {"THROW_IN": 0, "FREE_KICK": 0, "PENALTY_KICK": 0, "GOAL_KICK": 0, "CORNER_KICK": 0}
