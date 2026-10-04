class_name GodotMatchTestView
extends Control
## Exhibition setup only. No fabricated match execution/result.

signal back_requested

var catalog: TeamCatalog
var home: TeamPicker
var away: TeamPicker
var venue: OptionButton
var venue_label: Label
var back_button: Button


func _ready() -> void:
	var column: VBoxContainer = UiLayout.page(self, "試合テスト / チーム選択")
	var diagnostic_label: Label = UiLayout.label("有効なチーム %d件 / 読込診断 %d件（問題のあるファイルは選択対象外）" % [catalog.teams.size(), catalog.diagnostics.size()], 16)
	if not catalog.diagnostics.is_empty():
		var diagnostics: PackedStringArray = []
		for diagnostic: TeamDataDiagnostic in catalog.diagnostics:
			diagnostics.append(diagnostic.source + " / " + diagnostic.field + ": " + diagnostic.message)
		diagnostic_label.tooltip_text = "\n".join(diagnostics)
	column.add_child(diagnostic_label)
	var sides: HBoxContainer = HBoxContainer.new()
	sides.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sides.add_theme_constant_override("separation", 24)
	column.add_child(sides)
	home = _picker(sides, "HOME")
	away = _picker(sides, "AWAY")
	if away.teams.size() > 1:
		away._select(1)
	venue = OptionButton.new()
	for name: String in ["HOME側ホーム", "中立地", "AWAY側ホーム"]:
		venue.add_item(name)
	venue.selected = 1
	venue.item_selected.connect(_update_venue.unbind(1))
	column.add_child(venue)
	venue_label = UiLayout.label("", 16)
	column.add_child(venue_label)
	home.selection_changed.connect(_update_venue)
	away.selection_changed.connect(_update_venue)
	_update_venue()
	var footer: HBoxContainer = HBoxContainer.new()
	column.add_child(footer)
	var start: Button = UiLayout.button("試合演算・3D表示は移行待ち")
	start.disabled = true
	footer.add_child(start)
	back_button = UiLayout.button("メインメニューに戻る")
	back_button.pressed.connect(back_requested.emit)
	footer.add_child(back_button)


func _picker(parent: HBoxContainer, label: String) -> TeamPicker:
	var column: VBoxContainer = VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.size_flags_stretch_ratio = 1.0
	parent.add_child(column)
	column.add_child(UiLayout.label(label, 16))
	var picker: TeamPicker = TeamPicker.new()
	picker.teams = catalog.teams
	column.add_child(picker)
	return picker


func _update_venue() -> void:
	venue_label.text = "チームを選択してください。"
	if home.selected_team != null and away.selected_team != null:
		venue_label.text = [home.selected_team.home_court, "中立スタジアム", away.selected_team.home_court][venue.selected] as String


func setup_request() -> Dictionary:
	if home.selected_team == null or away.selected_team == null:
		return {}
	return {"home_id": home.selected_team.team_id, "away_id": away.selected_team.team_id, "venue": venue_label.text}
