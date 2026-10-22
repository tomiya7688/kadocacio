# {
#   責務: [MatchClock: 物理経過時間と再開待機を除く試合時計を保持する]
#   フィールド: [state: 試合フェーズ; game_time: 試合内の経過秒; simulation_elapsed: 待機も含む演算秒; halftime_done: 前半終了済みフラグ; banner: 案内種別; banner_timer: 案内の残り物理秒。倍速は適用済み]
# }
class_name MatchClock
extends RefCounted
## Playing and physics clocks, including kickoff/half-time banners and local waits.

var state: String = "TITLE"
var game_time: float = 0.0
var simulation_elapsed: float = 0.0
var halftime_done: bool = false
var banner: String = ""
var banner_timer: float = 0.0


# {
#   責務: [advance: 一物理更新ぶんの時計とハーフタイム・試合終了遷移を計算する]
#   処理: [1: 演算時間と案内の残り時間を更新する; 2: 再開待機または開始予告中なら試合時計を止める; 3: 規定倍率で試合時計を進め前後半の境界へ揃える]
#   引数: [dt: 呼出し元が検証した非負の固定物理秒; restart_waiting: この試合の再開準備中か]
#   戻り値: [String: HALFTIME・FULLTIMEまたは空文字。時計と案内、終了時のstateを更新する]
# }
func advance(dt: float, restart_waiting: bool) -> String:
	# セットプレー準備中も物理と案内は進め、止めるのはこの試合の時計だけ。
	simulation_elapsed += dt
	var banner_active: bool = banner_timer > 0
	if banner_active:
		banner_timer = maxf(0.0, banner_timer - dt)
	var kickoff_preview: bool = banner_active and banner == "KICK OFF" and game_time <= 0.0001
	if restart_waiting or kickoff_preview:
		return ""
	var rules: Dictionary = MatchProtocol.values()["kernel"] as Dictionary
	# 倍速はドライバが適用済みなので、ここでは試合時計の倍率だけを掛ける。
	game_time += dt * (rules["clock_rate"] as float)
	var duration: float = rules["match_seconds"] as float
	if not halftime_done and game_time >= duration / 2.0 - 0.000001:
		# 浮動小数の端数を半分へ揃え、前半終了を一度だけ通知する。
		halftime_done = true
		game_time = duration / 2.0
		banner = "HALF TIME"
		banner_timer = 2.4
		return "HALFTIME"
	if game_time >= duration - 0.000001:
		# 終了時刻を越えた分は記録せず、終了フェーズへ切り替える。
		game_time = duration
		state = "FULLTIME"
		return "FULLTIME"
	return ""
