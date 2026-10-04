class_name UiPreferencesRepository
extends RefCounted
## Godot-only user config. Never seeds/writes Python preferences, teams or saves.

var diagnostic: String = ""


func load_preferences(path: String) -> UiPreferences:
	diagnostic = ""
	if not FileAccess.file_exists(path):
		return UiPreferences.from_payload({})
	var parsed: Dictionary = StrictJsonReader.read_file(path)
	if not (parsed["error"] as String).is_empty() or not parsed["data"] is Dictionary:
		diagnostic = "Godot設定を読み込めないため既定値で起動します（自動上書きしません）"
		return UiPreferences.from_payload({})
	return UiPreferences.from_payload(parsed["data"] as Dictionary)


func save_preferences(path: String, preferences: UiPreferences) -> Error:
	var status: Error = DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	if status != OK:
		return status
	var temporary: String = path + ".tmp"
	var file: FileAccess = FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return FileAccess.get_open_error()
	file.store_string(JSON.stringify(preferences.to_payload(), "\t") + "\n")
	file.flush()
	var write_error: Error = file.get_error()
	file.close()
	return write_error if write_error != OK else DirAccess.rename_absolute(temporary, path)
