class_name WindowPreferencesController
extends RefCounted
## Native window changes; headless simulations never need display operations.


static func apply(window: Window, preferences: UiPreferences) -> void:
	if DisplayServer.get_name() == "headless":
		return
	window.mode = Window.MODE_FULLSCREEN if preferences.fullscreen else Window.MODE_WINDOWED
	if not preferences.fullscreen:
		var dimensions: Array = (UiContract.values()["window_sizes"] as Array)[preferences.window_size_index] as Array
		window.size = Vector2i(dimensions[0] as int, dimensions[1] as int)
		window.move_to_center()
