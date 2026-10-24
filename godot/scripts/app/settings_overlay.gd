class_name GodotSettingsOverlay
extends Control
## Native, keyboard/IME-capable settings controls. Simulation knobs are pending.

signal close_requested
signal display_changed

var preferences: UiPreferences
var cpu: SpinBox
var modes: OptionButton
var dimensions: OptionButton
var fullscreen: CheckButton
var gpu: CheckButton
var close_button: Button
var status: Label


func _ready() -> void:
	var column: VBoxContainer = UiLayout.page(self, "設定 / Escで戻る")
	var scroll: ScrollContainer = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	var form: VBoxContainer = VBoxContainer.new()
	form.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	form.add_theme_constant_override("separation", 8)
	scroll.add_child(form)
	var contract: Dictionary = UiContract.values()
	form.add_child(UiLayout.label("CPU演算枠の上限（OS全体の使用率を制限する値ではありません）", 18))
	cpu = SpinBox.new()
	cpu.min_value = contract["cpu_min"] as float
	cpu.max_value = contract["cpu_max"] as float
	cpu.step = 1.0
	cpu.suffix = "%"
	cpu.value = preferences.cpu_limit
	cpu.value_changed.connect(_change_cpu)
	form.add_child(cpu)
	form.add_child(UiLayout.label("リーグ裏試合の計算モード", 18))
	modes = OptionButton.new()
	var definitions: Dictionary = contract["modes"] as Dictionary
	for key: String in definitions:
		var definition: Dictionary = definitions[key] as Dictionary
		modes.add_item(definition["label"] as String)
		var index: int = modes.item_count - 1
		modes.set_item_metadata(index, key)
		modes.set_item_tooltip(index, definition["description"] as String)
		if key == preferences.simulation_mode:
			modes.selected = index
	modes.item_selected.connect(_change_mode)
	form.add_child(modes)
	form.add_child(UiLayout.label("ウィンドウサイズ（16:9を維持）", 18))
	dimensions = OptionButton.new()
	for size: Array in contract["window_sizes"] as Array:
		dimensions.add_item("%d × %d" % [size[0] as int, size[1] as int])
	dimensions.selected = preferences.window_size_index
	dimensions.item_selected.connect(_change_dimensions)
	form.add_child(dimensions)
	fullscreen = CheckButton.new()
	fullscreen.text = "全画面表示 / F11"
	fullscreen.button_pressed = preferences.fullscreen
	fullscreen.toggled.connect(_change_fullscreen)
	form.add_child(fullscreen)
	gpu = CheckButton.new()
	gpu.text = "GPU描画の希望設定を保存"
	gpu.button_pressed = preferences.gpu_rendering
	gpu.toggled.connect(_change_gpu)
	form.add_child(gpu)
	form.add_child(UiLayout.label("CPU上限・計算モードは試合核の移行後に適用します。現在は希望値の保存のみです。\nGodotの画面描画はGPUを使用します。この項目によるCPU描画への切替・GPU試合演算は未実装です。", 16))
	status = UiLayout.label("Godot専用設定へ保存します。Python版の設定・チーム・セーブは変更しません。", 16)
	column.add_child(status)
	close_button = UiLayout.button("設定を保存して閉じる")
	close_button.pressed.connect(close_requested.emit)
	column.add_child(close_button)


func _change_cpu(value: float) -> void:
	preferences.cpu_limit = int(value)


func _change_mode(index: int) -> void:
	preferences.simulation_mode = modes.get_item_metadata(index) as String


func _change_dimensions(index: int) -> void:
	preferences.window_size_index = index
	display_changed.emit()


func _change_fullscreen(value: bool) -> void:
	preferences.fullscreen = value
	display_changed.emit()


func _change_gpu(value: bool) -> void:
	preferences.gpu_rendering = value


func sync_display() -> void:
	fullscreen.set_pressed_no_signal(preferences.fullscreen)
