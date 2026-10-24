class_name MigrationPaths
extends RefCounted
## Sole development path boundary; distribution roots are deferred to #143.


static func data_root() -> String:
	var override: String = OS.get_environment("KADOCALCIO_DATA_ROOT")
	return override.replace("\\", "/").simplify_path() if not override.is_empty() else ProjectSettings.globalize_path("res://").path_join("..").simplify_path()


static func preferences_path() -> String:
	return data_root().path_join("user_data/config/godot_ui_settings.json")


static func team_roots() -> PackedStringArray:
	var roots: PackedStringArray = []
	for path: String in [data_root().path_join("user_data/teams"), data_root().path_join("teams")]:
		if DirAccess.dir_exists_absolute(path):
			roots.append(path)
	return roots
