class_name TeamJsonRepository
extends RefCounted
## Read-only filesystem adapter. Callers supply roots; never seeds or edits teams.


func load_file(path: String, root: String) -> TeamLoadResult:
	var absolute: String = ProjectSettings.globalize_path(path.replace("\\", "/")).simplify_path()
	var base: String = ProjectSettings.globalize_path(root.replace("\\", "/")).simplify_path().trim_suffix("/")
	if not absolute.begins_with(base + "/"):
		return TeamLoadResult.failure("outside_root", path, "$", "指定したチームフォルダの外です")
	var source: String = absolute.trim_prefix(base + "/")
	var document: Dictionary = StrictJsonReader.read_file(absolute)
	if not (document["error"] as String).is_empty():
		return TeamLoadResult.failure("json_read", source, "$", document["error"] as String, document["line"] as int)
	return load_payload(document["data"], source)


func load_payload(payload: Variant, source: String = "<memory>") -> TeamLoadResult:
	var result: TeamLoadResult = TeamLoadResult.new()
	result.diagnostics = TeamPayloadValidator.validate(payload, source)
	if result.diagnostics.is_empty():
		result.team = TeamPayloadDecoder.decode(payload as Dictionary, source)
	return result


func discover(roots: PackedStringArray) -> TeamCatalog:
	var catalog: TeamCatalog = TeamCatalog.new()
	var seen_ids: Dictionary = {}
	var seen_sources: Dictionary = {}
	for root: String in roots:
		var base: String = ProjectSettings.globalize_path(root.replace("\\", "/")).simplify_path().trim_suffix("/")
		var paths: Array[String] = []
		_collect(base, paths, catalog.diagnostics)
		paths.sort_custom(_path_before)
		for path: String in paths:
			var loaded: TeamLoadResult = load_file(path, base)
			catalog.diagnostics.append_array(loaded.diagnostics)
			if not loaded.is_valid():
				continue
			var team: TeamDefinition = loaded.team
			if seen_ids.has(team.team_id):
				if seen_ids[team.team_id] == base:
					catalog.diagnostics.append(TeamDataDiagnostic.new("duplicate_team_id", team.source, "チームID", "同一フォルダでチームIDが重複: " + team.team_id))
				continue
			if seen_sources.has(team.source):
				continue
			seen_ids[team.team_id] = base
			seen_sources[team.source] = true
			if team.short_name.is_empty():
				team.short_name = team.name.substr(0, 3)
			catalog.teams.append(team)
	return catalog


static func _path_before(left: String, right: String) -> bool:
	return left.to_lower() < right.to_lower()


func _collect(folder: String, paths: Array[String], diagnostics: Array[TeamDataDiagnostic]) -> void:
	var directory: DirAccess = DirAccess.open(folder)
	if directory == null:
		diagnostics.append(TeamDataDiagnostic.new("directory_read", folder, "$", "チームフォルダを読み込めません"))
		return
	for file: String in directory.get_files():
		var path: String = folder.path_join(file)
		if file.get_extension().to_lower() == "json" and not directory.is_link(file):
			paths.append(path)
	for child: String in directory.get_directories():
		if not directory.is_link(child):
			_collect(folder.path_join(child), paths, diagnostics)
