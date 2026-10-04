class_name FixedStepDriver
extends RefCounted
## Fixed-tick accumulator with retained backlog; frames never create partial ticks.

var pending_time: float = 0.0
var _kernel: MatchKernel


func _init(kernel: MatchKernel) -> void:
	_kernel = kernel


func advance(real_dt: float, max_steps: int = 256) -> int:
	if not is_finite(real_dt) or real_dt < 0 or max_steps < 1:
		return -1
	if not _kernel.is_ready():
		return -1
	if _kernel.is_paused() or not _kernel.is_playing():
		pending_time = 0.0
		return 0
	pending_time += real_dt * _kernel.speed()
	var fixed_dt: float = MatchProtocol.values()["max_dt"] as float
	var count: int = 0
	while pending_time + 1e-12 >= fixed_dt and count < max_steps:
		if not _kernel.apply({"kind": "STEP", "dt": fixed_dt}):
			return -1
		pending_time = maxf(0.0, pending_time - fixed_dt)
		count += 1
		if not _kernel.is_playing():
			pending_time = 0.0
			break
	return count
