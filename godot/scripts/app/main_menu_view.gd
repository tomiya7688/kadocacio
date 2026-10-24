class_name GodotMainMenuView
extends Control
## Four migration entry routes; exposes intent signals only.

signal route_requested(route: String)
signal settings_requested
signal exit_requested

var route_buttons: Array[Button] = []
var settings_button: Button
var exit_button: Button


func _ready() -> void:
	var column: VBoxContainer = UiLayout.page(self, "カドカルチョ")
	column.add_child(UiLayout.label("GODOT EDITION  /  開発プレビュー", 16))
	column.add_child(UiLayout.label("チームデータと画面を段階移行中です。通常プレイは run_game.bat。", 18))
	var grid: GridContainer = GridContainer.new()
	grid.columns = 2
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	grid.add_theme_constant_override("h_separation", 16)
	grid.add_theme_constant_override("v_separation", 16)
	column.add_child(grid)
	for entry: Array in [["league_start", "リーグ戦を開始", "シーズンを始める / 本体は移行待ち"], ["league_editor", "リーグ戦エディタ", "大会の配置と日程 / 本体は移行待ち"], ["team_editor", "チームエディタ", "チームを編集 / 本体は移行待ち"], ["match_test", "試合テスト", "チーム・会場を選択 / 演算は移行待ち"]]:
		var control: Button = UiLayout.button((entry[1] as String) + "\n" + (entry[2] as String))
		control.custom_minimum_size.x = 400
		control.size_flags_vertical = Control.SIZE_EXPAND_FILL
		control.pressed.connect(route_requested.emit.bind(entry[0] as String))
		grid.add_child(control)
		route_buttons.append(control)
	var footer: HBoxContainer = HBoxContainer.new()
	column.add_child(footer)
	settings_button = UiLayout.button("設定  /  Esc")
	settings_button.pressed.connect(settings_requested.emit)
	footer.add_child(settings_button)
	exit_button = UiLayout.button("閉じる")
	exit_button.pressed.connect(exit_requested.emit)
	footer.add_child(exit_button)
