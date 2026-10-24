# {
#   責務: [FixedStepDriver: 実時間を固定幅の試合更新へ変換し未処理時間を保持する]
#   フィールド: [pending_time: 倍速適用後の未処理秒数; _kernel: 更新要求の送信先となる試合核]
# }
class_name FixedStepDriver
extends RefCounted
## Fixed-tick accumulator with retained backlog; frames never create partial ticks.

var pending_time: float = 0.0
var _kernel: MatchKernel


# {
#   責務: [_init: 固定更新を送る試合核を保持する]
#   処理: [1: 渡された試合核への参照を保存する]
#   引数: [kernel: 固定ステップを適用する試合核]
#   戻り値: [void: 接続先だけを設定し、試合や時計は進めない]
# }
func _init(kernel: MatchKernel) -> void:
	# 試合状態は複製せず、入口操作と同じ核へ更新を送る。
	_kernel = kernel


# {
#   責務: [advance: 描画間隔と倍速から固定ステップだけを実行する]
#   処理: [1: 入力と核の準備状態を検証する; 2: 停止中は未処理時間を捨てる; 3: 倍速時間を蓄積し回数上限内で固定STEPを送る; 4: 終了時は残り時間を捨てる]
#   引数: [real_dt: 非負の有限な実経過秒; max_steps: 一回で実行する固定更新の上限。1以上]
#   戻り値: [int: 実行したSTEP数。不正入力・未準備・STEP拒否は-1。拒否前に成功した更新は巻き戻さない]
# }
func advance(real_dt: float, max_steps: int = 256) -> int:
	# 不正入力と未接続の核では、蓄積時間を増やさない。
	if not is_finite(real_dt) or real_dt < 0 or max_steps < 1:
		return -1
	if not _kernel.is_ready():
		return -1
	if _kernel.is_paused() or not _kernel.is_playing():
		# 停止中の時間を再開直後にまとめて消化しない。
		pending_time = 0.0
		return 0
	pending_time += real_dt * _kernel.speed()
	var fixed_dt: float = MatchProtocol.values()["max_dt"] as float
	var count: int = 0
	# 小さい端数STEPや時計だけの早送りはせず、上限超過分は次回へ残す。
	while pending_time + 1e-12 >= fixed_dt and count < max_steps:
		if not _kernel.apply({"kind": "STEP", "dt": fixed_dt}):
			return -1
		pending_time = maxf(0.0, pending_time - fixed_dt)
		count += 1
		if not _kernel.is_playing():
			# 試合終了後の余りを次の試合へ持ち越さない。
			pending_time = 0.0
			break
	return count
