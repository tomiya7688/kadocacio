extends SceneTree
## Real-engine smoke assertions; the Python runner also validates every .gd file.

const BOOTSTRAP_SCENE: PackedScene = preload("res://scenes/app/bootstrap.tscn")

var _failures: int = 0
var _assertions: int = 0


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_expect(DisplayServer.get_name() == "headless", "tests must run headless")
	_expect((Engine.get_version_info()["major"] as int) == 4, "engine major")
	_expect(str(ProjectSettings.get_setting("application/run/main_scene")) == BOOTSTRAP_SCENE.resource_path, "main scene")
	_expect((ProjectSettings.get_setting("display/window/size/viewport_width") as int) == 1280, "viewport width")
	_expect((ProjectSettings.get_setting("display/window/size/viewport_height") as int) == 720, "viewport height")
	_expect(str(ProjectSettings.get_setting("display/window/stretch/aspect")) == "keep", "aspect ratio")
	var scene: Node = BOOTSTRAP_SCENE.instantiate()
	_expect(scene is Control, "bootstrap is presentation only")
	root.add_child(scene)
	await process_frame
	var button: Button = scene.get_node("%Exit") as Button
	_expect(button != null, "exit control")
	if button == null:
		quit(1)
		return
	_expect(button.has_focus(), "keyboard focus")
	_expect(button.pressed.is_connected(Callable(scene, "_request_exit")), "exit handler")
	scene.queue_free()
	await process_frame
	print("KADOCALCIO_TESTS: %d assertions, %d failures" % [_assertions, _failures])
	quit(0 if _failures == 0 else 1)


func _expect(condition: bool, description: String) -> void:
	_assertions += 1
	if not condition:
		_failures += 1
		push_error("Assertion failed: " + description)
