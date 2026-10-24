extends SceneTree
## Native UI assertions. Windowed opt-in additionally captures real render output.

const BOOTSTRAP_SCENE: PackedScene = preload("res://scenes/app/bootstrap.tscn")

var _failures: int = 0
var _assertions: int = 0
var _app: KadocalcioBootstrap
var _output: String


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var windowed: bool = OS.get_cmdline_user_args().has("--ui-window-test")
	_expect(windowed != (DisplayServer.get_name() == "headless"), "expected display backend")
	_expect((Engine.get_version_info()["major"] as int) == 4, "engine major")
	_expect(str(ProjectSettings.get_setting("application/run/main_scene")) == BOOTSTRAP_SCENE.resource_path, "main scene")
	_expect((ProjectSettings.get_setting("display/window/size/viewport_width") as int) == 1280, "viewport width")
	_expect((ProjectSettings.get_setting("display/window/size/viewport_height") as int) == 720, "viewport height")
	_expect(str(ProjectSettings.get_setting("display/window/stretch/aspect")) == "keep", "aspect ratio")
	_output = ProjectSettings.globalize_path("res://../user_data/logs/godot/ui_tests-" + ("windowed" if windowed else "headless")).simplify_path()
	OS.set_environment("KADOCALCIO_DATA_ROOT", _output)
	_prepare_fixtures()
	_test_preferences()
	_app = BOOTSTRAP_SCENE.instantiate() as KadocalcioBootstrap
	root.add_child(_app)
	await _settle()
	_expect(_app.catalog.teams.size() == 2 and _app.catalog.diagnostics.size() == 1, "catalog partial diagnostics")
	var menu: GodotMainMenuView = _app.page as GodotMainMenuView
	_expect(menu.route_buttons[0].has_focus(), "menu keyboard focus")
	_expect(menu.exit_requested.is_connected(_app._request_exit), "exit handler")
	await _key(KEY_TAB)
	_expect(menu.route_buttons[1].has_focus(), "Tab moves native focus")
	await _key(KEY_ENTER)
	_expect(_app.current_route == "league_editor", "Enter selects route")
	await _key(KEY_ENTER)
	_expect(_app.current_route == "menu", "Enter returns from unavailable route")
	for route: String in ["league_start", "team_editor"]:
		_app.show_route(route)
		await _settle()
		_expect(_app.page is MigrationNoticeView, "unavailable scene: " + route)
		_expect((_app.page as MigrationNoticeView).back_button.has_focus(), "unavailable back focus")
		await _key(KEY_ENTER)
	_expect(_app.current_route == "menu", "all unavailable routes return")
	menu = _app.page as GodotMainMenuView
	await _click(menu.route_buttons[3])
	_expect(_app.current_route == "match_test", "mouse chooses match test")
	var match_view: GodotMatchTestView = _app.page as GodotMatchTestView
	_expect(match_view.home.search.has_focus(), "team search focus")
	_expect(match_view.home.selected_team != match_view.away.selected_team, "different sides initially")
	match_view.venue.select(0)
	match_view.venue.item_selected.emit(0)
	_expect((match_view.setup_request()["venue"] as String) == match_view.home.selected_team.home_court, "home venue")
	match_view.venue.select(2)
	match_view.venue.item_selected.emit(2)
	_expect((match_view.setup_request()["venue"] as String) == match_view.away.selected_team.home_court, "away venue")
	match_view.venue.select(1)
	match_view.venue.item_selected.emit(1)
	_expect((match_view.setup_request()["venue"] as String) == "中立スタジアム", "neutral venue")
	await _key(KEY_ESCAPE)
	_expect(_app.settings.visible and not match_view.is_visible_in_tree(), "Esc opens modal and hides background")
	_app.show_route("menu")
	_expect(_app.current_route == "match_test", "background route cannot change")
	await _key(KEY_TAB)
	_expect(_app.settings.cpu.get_line_edit().has_focus(), "keyboard reaches CPU editor")
	await _key(KEY_A, false, true)
	await _text("55")
	_app.settings.modes.select(3)
	_app.settings.modes.item_selected.emit(3)
	_app.settings.gpu.button_pressed = false
	_app.settings.modes.grab_focus()
	await _key(KEY_ENTER)
	_expect(_app.settings.modes.get_popup().visible, "native mode popup")
	await _key(KEY_ESCAPE)
	_expect(_app.settings.visible and not _app.settings.modes.get_popup().visible, "Esc cancels popup without closing settings")
	await _key(KEY_ESCAPE)
	_expect(not _app.settings.visible and match_view.home.search.has_focus(), "Esc returns original focus")
	var restored: UiPreferences = UiPreferencesRepository.new().load_preferences(MigrationPaths.preferences_path())
	_expect(restored.cpu_limit == 55 and restored.simulation_mode == "LIGHT" and not restored.gpu_rendering, "committed keyboard setting persisted")
	await _key(KEY_ESCAPE)
	await _click(_app.settings.close_button)
	_expect(not _app.settings.visible, "mouse close restores page")
	match_view.home.search.text = "no matching team"
	match_view.home.search.text_changed.emit(match_view.home.search.text)
	_expect(match_view.home.selected_team == null and match_view.setup_request().is_empty(), "empty search safe")
	match_view.home.search.clear()
	match_view.home.search.text_changed.emit("")
	match_view.home.search.insert_text_at_caret("日本語")
	match_view.home.search.text_changed.emit(match_view.home.search.text)
	_expect(match_view.home.search.text == "日本語", "native Japanese text")
	match_view.home.search.caret_column = 2
	await _key(KEY_BACKSPACE, true)
	_expect(match_view.home.search.text == "日語", "held backspace/native caret")
	match_view.home.search.clear()
	match_view.home.search.text_changed.emit("")
	_expect(match_view.home.details.text.contains("[b]そのまま[/b]") and not match_view.home.details.bbcode_enabled, "description not markup")
	_expect(match_view.home.list.get_selected_items().size() == 1, "one highlighted team per side")
	await _settle()
	_check_bounds(match_view)
	if windowed:
		await _test_window()
	_app.queue_free()
	await _settle()
	print("KADOCALCIO_TESTS: %d assertions, %d failures" % [_assertions, _failures])
	quit(0 if _failures == 0 else 1)


func _prepare_fixtures() -> void:
	var folder: String = _output.path_join("teams/日本語フォルダ")
	_expect(DirAccess.make_dir_recursive_absolute(folder) == OK, "fixture folder")
	for index: int in 2:
		var players: Array[Dictionary] = []
		for player: int in 7:
			players.append({"名前": "選手%d" % player, "PositionX": player + 1, "PositionY": 11 if player == 0 else 1})
		var payload: Dictionary = {"チーム情報": {"チーム名": ("日本語の非常に長いチーム名".repeat(12) if index == 0 else "対戦相手"), "ホームコート": "ホーム%d" % index, "チーム紹介": ("紹介文 [b]そのまま[/b]。".repeat(300))}, "選手一覧": players}
		_write(folder.path_join("team%d.json" % index), JSON.stringify(payload))
	_write(folder.path_join("invalid.json"), "{invalid")
	# This only removes this test's exact previous settings file, never real config.
	var settings_file: String = MigrationPaths.preferences_path()
	if FileAccess.file_exists(settings_file):
		_expect(DirAccess.remove_absolute(settings_file) == OK, "reset isolated test config")


func _test_preferences() -> void:
	var repository: UiPreferencesRepository = UiPreferencesRepository.new()
	var path: String = _output.path_join("preferences-test.json")
	_write(path, "{invalid")
	var preferences: UiPreferences = repository.load_preferences(path)
	_expect(preferences.cpu_limit == 100 and preferences.simulation_mode == "PRECISE", "bad config default")
	_expect(not repository.diagnostic.is_empty() and FileAccess.get_file_as_string(path) == "{invalid", "bad config not overwritten")
	preferences.cpu_limit = 25
	_expect(repository.save_preferences(path, preferences) == OK, "atomic save replaces existing config")
	_expect(repository.load_preferences(path).cpu_limit == 25 and repository.diagnostic.is_empty(), "reload/reset diagnostic")
	preferences = UiPreferences.from_payload({"CPU使用率上限": "nan", "リーグ裏試合モード": "unknown", "GPU描画": "false", "ウィンドウサイズ": "bad", "全画面": "true"})
	_expect(preferences.cpu_limit == 100 and preferences.window_size_index == 1 and preferences.gpu_rendering and not preferences.fullscreen, "malformed preferences safe")
	_expect(UiPreferences.from_payload({"CPU使用率上限": -10, "ウィンドウサイズ": -1}).cpu_limit == 10, "CPU lower clamp")
	_expect(UiPreferences.from_payload({"CPU使用率上限": 9999, "ウィンドウサイズ": 999}).window_size_index == 3, "display upper clamp")


func _test_window() -> void:
	_app.settings.dimensions.select(0)
	_app.settings.dimensions.item_selected.emit(0)
	await _settle()
	_expect(root.size == Vector2i(960, 540), "native 960x540")
	_check_bounds(_app.page)
	await _capture("match-960.png")
	root.size = Vector2i(1280, 800)
	await _settle()
	_check_bounds(_app.page)
	await _key(KEY_ESCAPE)
	_expect(_app.settings.visible, "non16:9 keyboard input")
	await _capture("settings-1280x800.png")
	# Window-space input is transformed by the viewport (including letterbox).
	await _click(_app.settings.close_button, true)
	_expect(not _app.settings.visible, "non16:9 mouse maps to logical controls")
	await _key(KEY_F11)
	_expect(root.mode == Window.MODE_FULLSCREEN, "actual fullscreen mode")
	_check_bounds(_app.page)
	await _capture("match-fullscreen.png")
	await _key(KEY_F11)
	_expect(root.mode == Window.MODE_WINDOWED and root.size == Vector2i(960, 540), "F11 restores selected window size")
	_app.show_route("menu")
	await _settle()
	_check_bounds(_app.page)
	await _capture("menu-960.png")


func _check_bounds(view: Control) -> void:
	var bounds: Rect2 = Rect2(Vector2.ZERO, Vector2(1280, 720))
	for node: Node in view.find_children("*", "Control", true, false):
		var control: Control = node as Control
		if control.is_visible_in_tree() and (control is BaseButton or control is LineEdit or control is ItemList or control is RichTextLabel):
			_expect(bounds.grow(1).encloses(control.get_global_rect()), "control within logical canvas: " + control.get_class())


func _write(path: String, text: String) -> void:
	var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
	_expect(file != null, "test write")
	if file != null:
		file.store_string(text)
		file.close()


func _settle() -> void:
	for frame: int in 8:
		await process_frame


func _key(code: Key, echo: bool = false, control: bool = false) -> void:
	var event: InputEventKey = InputEventKey.new()
	event.keycode = code
	event.pressed = true
	event.echo = echo
	event.ctrl_pressed = control
	Input.parse_input_event(event)
	await _settle()
	event = InputEventKey.new()
	event.keycode = code
	Input.parse_input_event(event)
	await _settle()


func _text(text: String) -> void:
	for character: String in text:
		var event: InputEventKey = InputEventKey.new()
		event.unicode = character.unicode_at(0)
		event.pressed = true
		Input.parse_input_event(event)
		await _settle()
func _click(control: Control, window_space: bool = false) -> void:
	var point: Vector2 = control.get_global_rect().get_center()
	if window_space:
		point = root.get_final_transform() * point
	for pressed: bool in [true, false]:
		var event: InputEventMouseButton = InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.pressed = pressed
		root.push_input(event, not window_space)
		await _settle()


func _capture(name: String) -> void:
	await RenderingServer.frame_post_draw
	var image: Image = root.get_texture().get_image()
	_expect(image.save_png(_output.path_join(name)) == OK, "native screenshot " + name)


func _expect(condition: bool, description: String) -> void:
	_assertions += 1
	if not condition:
		_failures += 1
		push_error("Assertion failed: " + description)
