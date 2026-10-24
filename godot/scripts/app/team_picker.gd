class_name TeamPicker
extends VBoxContainer
## Search/selection/details for one side. Uses native LineEdit IME and editing.

signal selection_changed

var teams: Array[TeamDefinition] = []
var selected_team: TeamDefinition = null
var search: LineEdit
var list: ItemList
var details: RichTextLabel
var _indices: Array[int] = []


func _ready() -> void:
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	search = LineEdit.new()
	search.placeholder_text = "チーム名・フォルダで検索（日本語可）"
	search.clear_button_enabled = true
	search.text_changed.connect(_filter)
	add_child(search)
	list = ItemList.new()
	list.custom_minimum_size.y = 130
	list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list.item_selected.connect(_select)
	add_child(list)
	details = UiLayout.text_area(130)
	add_child(details)
	_filter("")


func _filter(query: String) -> void:
	list.clear()
	_indices.clear()
	for index: int in teams.size():
		var team: TeamDefinition = teams[index]
		if query.is_empty() or (team.name + " " + team.short_name + " " + team.source).to_lower().contains(query.to_lower()):
			_indices.append(index)
			var item: int = list.add_item(team.name)
			list.set_item_tooltip(item, team.name + "\n" + team.source)
	_select(0 if not _indices.is_empty() else -1)


func _select(item: int) -> void:
	selected_team = teams[_indices[item]] if item >= 0 else null
	if selected_team == null:
		details.text = "一致する有効なチームがありません。"
	else:
		list.deselect_all()
		list.select(item)
		var team: TeamDefinition = selected_team
		details.text = team.name + "\n" + team.source + "\n先発 %d人 / 控え %d人\n" % [team.starters.size(), team.bench.size()] + (team.description if not team.description.is_empty() else "チーム紹介は未登録です。")
	selection_changed.emit()
