class_name UiPreferences
extends RefCounted
## Desired future simulation settings and currently applied display preferences.

var cpu_limit: int = 100
var simulation_mode: String = "PRECISE"
var gpu_rendering: bool = true
var window_size_index: int = 1
var fullscreen: bool = false


static func from_payload(payload: Dictionary) -> UiPreferences:
	var result: UiPreferences = UiPreferences.new()
	var definition: Dictionary = UiContract.values()
	var cpu: float = JsonValue.number(payload.get("CPU使用率上限"), definition["cpu_default"] as float)
	if not is_finite(cpu):
		cpu = definition["cpu_default"] as float
	result.cpu_limit = int(clampf(cpu, definition["cpu_min"] as float, definition["cpu_max"] as float))
	var mode: String = JsonValue.text(payload.get("リーグ裏試合モード", definition["mode_default"])).to_upper()
	result.simulation_mode = mode if (definition["modes"] as Dictionary).has(mode) else definition["mode_default"] as String
	result.gpu_rendering = payload["GPU描画"] as bool if payload.get("GPU描画") is bool else true
	var index: int = JsonValue.integer(payload.get("ウィンドウサイズ", 1)) if JsonValue.integer_valid(payload.get("ウィンドウサイズ", 1)) else 1
	result.window_size_index = clampi(index, 0, (definition["window_sizes"] as Array).size() - 1)
	result.fullscreen = payload["全画面"] as bool if payload.get("全画面") is bool else false
	return result


func to_payload() -> Dictionary:
	return {"CPU使用率上限": cpu_limit, "リーグ裏試合モード": simulation_mode,
		"GPU描画": gpu_rendering, "ウィンドウサイズ": window_size_index, "全画面": fullscreen}
