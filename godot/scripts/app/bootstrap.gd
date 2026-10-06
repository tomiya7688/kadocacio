class_name KadocalcioBootstrap
extends Control
## UI route orchestration only. Repositories own I/O; no match simulation here.

const ROUTES: Dictionary = {
	"menu": preload("res://scenes/app/main_menu.tscn"),
	"league_start": preload("res://scenes/app/league_start.tscn"),
	"league_editor": preload("res://scenes/app/league_editor.tscn"),
	"team_editor": preload("res://scenes/app/team_editor.tscn"),
	"match_test": preload("res://scenes/app/match_test.tscn"),
}

var preferences: UiPreferences
var catalog: TeamCatalog
var page: Control
var settings: GodotSettingsOverlay
var current_route: String = "menu"
var _content: Control
var _previous_focus: WeakRef
var _repository: UiPreferencesRepository = UiPreferencesRepository.new()


func _ready() -> void:
	theme = MenuTheme.build()
	preferences = _repository.load_preferences(MigrationPaths.preferences_path())
	catalog = TeamJsonRepository.new().discover(MigrationPaths.team_roots())
	_content = Control.new()
	add_child(_content)
	_content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	show_route("menu")
	settings = GodotSettingsOverlay.new()
	settings.preferences = preferences
	add_child(settings)
	settings.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	settings.hide()
	settings.close_requested.connect(close_settings)
	settings.display_changed.connect(_apply_display)
	if not _repository.diagnostic.is_empty():
		settings.status.text = _repository.diagnostic
	_apply_display()
	print("KADOCALCIO_BOOTSTRAP_READY")
	if OS.get_cmdline_user_args().has("--smoke-exit"):
		_request_exit.call_deferred()


func show_route(route: String) -> void:
	if (settings != null and settings.visible) or not ROUTES.has(route):
		return
	if page != null:
		_content.remove_child(page)
		page.queue_free()
	current_route = route
	page = (ROUTES[route] as PackedScene).instantiate() as Control
	if page is GodotMatchTestView:
		(page as GodotMatchTestView).catalog = catalog
	_content.add_child(page)
	page.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	if page is GodotMainMenuView:
		var menu: GodotMainMenuView = page as GodotMainMenuView
		menu.route_requested.connect(show_route)
		menu.settings_requested.connect(open_settings)
		menu.exit_requested.connect(_request_exit)
		menu.route_buttons[0].grab_focus()
	elif page is GodotMatchTestView:
		var match_view: GodotMatchTestView = page as GodotMatchTestView
		match_view.back_requested.connect(show_route.bind("menu"))
		match_view.home.search.grab_focus()
	else:
		var notice: MigrationNoticeView = page as MigrationNoticeView
		notice.back_requested.connect(show_route.bind("menu"))
		notice.back_button.grab_focus()


func open_settings() -> void:
	if settings.visible:
		return
	var focused: Control = get_viewport().gui_get_focus_owner()
	_previous_focus = weakref(focused) if focused != null else null
	_content.hide()
	settings.show()
	settings.close_button.grab_focus()


func close_settings() -> void:
	settings.cpu.apply()
	var status: Error = _repository.save_preferences(MigrationPaths.preferences_path(), preferences)
	if status != OK:
		settings.status.text = "設定の保存に失敗しました（%s）。閉じるを押して再試行してください。" % error_string(status)
		return
	settings.hide()
	_content.show()
	var focused: Control = _previous_focus.get_ref() as Control if _previous_focus != null else null
	if focused != null and focused.is_visible_in_tree():
		focused.grab_focus()


func _input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.is_pressed() or event.is_echo():
		return
	var focused: Control = get_viewport().gui_get_focus_owner()
	if focused is LineEdit and (focused as LineEdit).has_ime_text():
		return
	if focused is OptionButton and (focused as OptionButton).get_popup().visible:
		return
	var key: InputEventKey = event as InputEventKey
	if key.keycode == KEY_ESCAPE:
		if settings.visible:
			close_settings()
		else:
			open_settings()
		get_viewport().set_input_as_handled()
	elif key.keycode == KEY_F11:
		preferences.fullscreen = not preferences.fullscreen
		settings.sync_display()
		_apply_display()
		get_viewport().set_input_as_handled()


func _apply_display() -> void:
	WindowPreferencesController.apply(get_window(), preferences)


func _request_exit() -> void:
	print("KADOCALCIO_BOOTSTRAP_STOP")
	get_tree().quit(0)
