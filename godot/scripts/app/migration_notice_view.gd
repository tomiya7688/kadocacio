class_name MigrationNoticeView
extends Control
## Honest unavailable route screen, shared by three separate entry scenes.

signal back_requested

@export var heading: String = ""
@export_multiline var explanation: String = ""
var back_button: Button


func _ready() -> void:
	var column: VBoxContainer = UiLayout.page(self, heading)
	var body: RichTextLabel = UiLayout.text_area(180)
	body.text = "未実装 / GODOT移行待ち\n\n" + explanation + "\n\n現在の機能はPython版 run_game.bat で利用できます。"
	column.add_child(body)
	var unavailable: Button = UiLayout.button("この機能はまだ開始できません")
	unavailable.disabled = true
	column.add_child(unavailable)
	back_button = UiLayout.button("メインメニューに戻る")
	back_button.pressed.connect(back_requested.emit)
	column.add_child(back_button)
