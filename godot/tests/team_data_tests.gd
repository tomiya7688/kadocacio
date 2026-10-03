extends SceneTree
## Python oracle parity and native read-only repository/error tests.

var _failures: int = 0
var _assertions: int = 0


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size() != 2 or args[0] != "--oracle":
		push_error("Pass --oracle with a Python reference fixture")
		quit(2)
		return
	var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[1])) as Dictionary
	var repository: TeamJsonRepository = TeamJsonRepository.new()
	var cases: Array = fixture["cases"] as Array
	for item: Variant in cases:
		var row: Dictionary = item as Dictionary
		var source: String = row["source"] as String
		var result: TeamLoadResult = repository.load_payload(row["payload"], source)
		_expect(result.is_valid() == (row["valid"] as bool), source + ": validity")
		if result.is_valid() and (row["valid"] as bool):
			_equal(result.team.to_choice(), row["choice"], source)
			_equal(result.team.original_payload, row["payload"], source + ": original payload")
			var parameters: Array[Dictionary] = []
			for player: PlayerDefinition in result.team.starters + result.team.bench:
				parameters.append(player.to_parameters())
			_equal(parameters, row["parameters"], source + ": parameters")
		else:
			_expect(not result.diagnostics.is_empty(), source + ": diagnostics")
	for file_item: Variant in fixture["files"] as Array:
		var file: Dictionary = file_item as Dictionary
		var loaded: TeamLoadResult = repository.load_file(file["path"] as String, file["root"] as String)
		_expect(loaded.is_valid(), (file["source"] as String) + ": file read")
		if loaded.is_valid():
			_expect(loaded.team.source == (file["source"] as String), "relative folder source")
	_test_repository(repository, fixture["catalog_root"] as String)
	_test_diagnostics(repository)
	_test_json()
	_test_scale()
	var definition: Object = TeamDefinition.new()
	_expect(not definition is Node, "data model must not be a Node")
	print("KADOCALCIO_TEAM_TESTS: %d cases, %d assertions, %d failures" % [cases.size(), _assertions, _failures])
	quit(0 if _failures == 0 else 1)


func _test_repository(repository: TeamJsonRepository, folder: String) -> void:
	var good: TeamLoadResult = repository.load_file(folder.path_join("nested/good.json"), folder)
	_expect(good.is_valid(), "BOM/team read")
	var missing: TeamLoadResult = repository.load_file(folder.path_join("missing.json"), folder)
	_expect(not missing.is_valid() and missing.diagnostics[0].code == "json_read", "missing file diagnostic")
	var outside: TeamLoadResult = repository.load_file(folder.path_join("../outside.json"), folder)
	_expect(outside.diagnostics[0].code == "outside_root", "path outside root")
	var mixed: TeamLoadResult = repository.load_file(folder.replace("\\", "/").path_join("nested/good.json"), folder)
	_expect(mixed.is_valid() and mixed.team.source == "nested/good.json", "mixed Windows/POSIX separators")
	var catalog: TeamCatalog = repository.discover(PackedStringArray([folder]))
	_expect(catalog.teams.size() == 1, "recursive discovery/duplicate exclusion")
	var codes: PackedStringArray = []
	for diagnostic: TeamDataDiagnostic in catalog.diagnostics:
		codes.append(diagnostic.code)
	_expect("json_read" in codes and "duplicate_team_id" in codes, "catalog diagnostics")
	var overrides: TeamCatalog = repository.discover(PackedStringArray([folder, folder.path_join("nested")]))
	_expect(overrides.teams.size() == 1, "first root wins stable ID")
	var absent: TeamCatalog = repository.discover(PackedStringArray([folder.path_join("missing")]))
	_expect(absent.diagnostics[0].code == "directory_read", "directory error")
	if good.is_valid():
		var original_name: String = good.team.name
		var copy: Dictionary = good.team.to_choice()
		copy["name"] = "modified"
		(copy["starters"] as Array).clear()
		_expect(good.team.name == original_name and not good.team.starters.is_empty(), "export copy isolation")
		var raw_copy: Dictionary = good.team.starters[0].to_record()["raw"] as Dictionary
		raw_copy["Name"] = "changed"
		_expect((good.team.starters[0].raw.get("Name") != "changed") as bool, "raw export copy isolation")
		var record: Dictionary = good.team.starters[0].to_record()
		(record["slot"] as Array)[1] = 42.0
		_expect(((good.team.starters[0].slot as Array)[1] != 42.0) as bool, "position export copy isolation")


func _test_diagnostics(repository: TeamJsonRepository) -> void:
	var invalid: TeamLoadResult = repository.load_payload({"選手一覧": [null]}, "broken/team.json")
	_expect(not invalid.is_valid() and invalid.team == null, "invalid payload has no partial definition")
	var error: Dictionary = invalid.diagnostics[0].to_dictionary()
	_expect((error["code"] == "player_type") as bool, "player error code")
	_expect((error["source"] == "broken/team.json") as bool, "player error source")
	_expect((error["field"] == "選手一覧[0]") as bool, "player error field")
	_expect(not (error["message"] as String).is_empty(), "human diagnostic")


func _test_json() -> void:
	for text: String in ['{"x":1,}', '[1,]', '{"x":01}', '{"x":1.}', '"raw\nnewline"', '"\\ud800"', '"\\uXXXX"', '"\\q"', '{"x":+1}', '']:
		var parsed: Dictionary = StrictJsonReader.parse(text)
		_expect(not (parsed["error"] as String).is_empty(), "strict JSON rejection")
	var unicode: Dictionary = StrictJsonReader.parse('"\\ud83d\\ude42"')
	_expect((unicode["data"] == "🙂") as bool, "valid escaped surrogate pair")
	var valid: Dictionary = StrictJsonReader.parse('{"x": [true, false, null, -1.25e2], "s":"comma,} is a string"}')
	_expect((valid["error"] as String).is_empty(), "valid JSON tokens")
	var multiline: Dictionary = StrictJsonReader.parse('{\n"x": 1,\n}')
	_expect((multiline["line"] == 3) as bool, "JSON diagnostic line")


func _test_scale() -> void:
	for entry: Variant in (TeamContract.values()["scale"] as Dictionary)["grades"] as Array:
		var row: Dictionary = entry as Dictionary
		_expect(StatScale.grade(row["minimum"] as float) == (row["rank"] as String), "grade threshold")
	_expect(StatScale.grade(499.0) == "E-" and StatScale.grade(4999.0) == "A+", "grade below thresholds")
	_expect(JsonValue.round_even(2062.5) == 2062 and JsonValue.round_even(687.5) == 688, "Python ties-to-even")
	_expect(StatScale.normalize(0, 0) == 0.0 and StatScale.normalize(5500, 0) == 1.0, "scale endpoints")


func _equal(actual: Variant, expected: Variant, path: String) -> void:
	if (actual is int or actual is float) and (expected is int or expected is float):
		_expect(absf((actual as float) - (expected as float)) <= 1e-9, path + ": numeric")
	elif actual is Dictionary and expected is Dictionary:
		var left: Dictionary = actual as Dictionary
		var right: Dictionary = expected as Dictionary
		_expect(left.size() == right.size(), path + ": key count")
		for key: String in right:
			_expect(left.has(key), path + "." + key + ": key")
			if left.has(key):
				_equal(left[key], right[key], path + "." + key)
	elif actual is Array and expected is Array:
		var left: Array = actual as Array
		var right: Array = expected as Array
		_expect(left.size() == right.size(), path + ": array size")
		for index: int in mini(left.size(), right.size()):
			_equal(left[index], right[index], path + "[%d]" % index)
	else:
		_expect((actual == expected) as bool, path + ": value")


func _expect(condition: bool, detail: String) -> void:
	_assertions += 1
	if not condition:
		_failures += 1
		if _failures <= 15:
			push_error("Team data assertion: " + detail)
