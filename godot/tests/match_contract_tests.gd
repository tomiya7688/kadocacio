extends SceneTree
## Contract read/roundtrip/diff tests only. Godot football execution is not implemented.

var _failures: int = 0
var _assertions: int = 0


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size() != 4 or args[0] != "--fixture" or args[2] != "--output":
		push_error("Pass --fixture and --output")
		quit(2)
		return
	var document: Dictionary = StrictJsonReader.read_file(args[1])
	_expect((document["error"] as String).is_empty(), "fixture JSON read")
	var fixture: Dictionary = document["data"] as Dictionary
	var input: MatchInputRecord = MatchInputRecord.read(fixture["input"])
	_expect(input.is_valid(), "reference input: " + input.error)
	_expect((input.to_payload()["repro_input"] as Dictionary)["settings"] is Dictionary, "detached settings")
	var seed: String = ((input.to_payload()["repro_input"] as Dictionary)["settings"] as Dictionary)["seed"] as String
	_expect(seed == "9223372036854788153", "seed wider than int64 is lossless text")
	var detached: Dictionary = input.to_payload()
	detached["operations"] = []
	_expect(not (input.to_payload()["operations"] as Array).is_empty(), "input does not expose mutable state")
	var reference: MatchTraceRecord = MatchTraceRecord.read(fixture["reference"])
	_expect(reference.is_valid(), "reference observations: " + reference.error)
	var exported: Dictionary = reference.to_payload()
	(exported["source"] as Dictionary)["implementation"] = "godot-contract-roundtrip"
	(exported["source"] as Dictionary)["execution"] = "contract_roundtrip"
	(exported["source"] as Dictionary)["rng"] = "not_executed/reference_observations_only"
	var report: Dictionary = MatchTraceComparison.compare(reference, MatchTraceRecord.read(exported))
	_expect(report["same_observations"] as bool, "native roundtrip matches")
	_expect((report["scope"] as String) == "contract_roundtrip" and (report["kernel_parity"] as String) == "not_evaluated", "must not claim simulated Godot parity")
	for item: Variant in fixture["input_cases"] as Array:
		var row: Dictionary = item as Dictionary
		_expect(MatchInputRecord.read(row["input"]).is_valid() == (row["valid"] as bool), "input rejection: " + (row["name"] as String))
	for item: Variant in fixture["trace_cases"] as Array:
		var row: Dictionary = item as Dictionary
		_expect(MatchTraceRecord.read(row["trace"]).is_valid() == (row["valid"] as bool), "trace rejection: " + (row["name"] as String))
	for item: Variant in fixture["comparison_cases"] as Array:
		var row: Dictionary = item as Dictionary
		var actual: Dictionary = MatchTraceComparison.compare(MatchTraceRecord.read(row["expected"]), MatchTraceRecord.read(row["actual"]))
		_expect(MatchTraceComparison.first_difference(row["report"], actual) == null, "first-difference oracle: " + (row["name"] as String))
	_expect(MatchTraceComparison.first_difference({"home_score": 0}, {"home_score": 0.0000001}) != null, "score exact even inside floating tolerance")
	_expect(MatchTraceComparison.first_difference(false, 0) != null, "bool is not a number")
	_expect(MatchTraceComparison.first_difference([1], [1, 2]) != null, "list length")
	_expect(MatchTraceComparison.first_difference({}, {"missing": null}) != null, "missing is not null")
	var invalid: Dictionary = reference.to_payload()
	(invalid["entries"] as Array)[0] = {}
	_expect(not MatchTraceRecord.read(invalid).is_valid(), "invalid trace rejected")
	_expect(not (MatchTraceComparison.compare(MatchTraceRecord.read(invalid), reference)["same_observations"] as bool), "invalid cannot pass")
	var nonfinite: Dictionary = reference.to_payload()
	nonfinite["extra"] = NAN
	_expect(not MatchTraceRecord.read(nonfinite).is_valid(), "nonfinite observation")
	_expect(not MatchOperation.read({"kind": "STEP", "dt": NAN}).is_valid(), "nonfinite step")
	_expect(not MatchOperation.read({"kind": "SET_SPEED", "value": true}).is_valid(), "boolean speed")
	var operation_object: Object = MatchOperation.new()
	var trace_object: Object = reference
	_expect(not operation_object is Node and not trace_object is Node, "Node-free boundaries")
	var file: FileAccess = FileAccess.open(args[3], FileAccess.WRITE)
	_expect(file != null, "native export")
	if file != null:
		file.store_string(JSON.stringify(exported))
		file.close()
	print("KADOCALCIO_MATCH_CONTRACT_TESTS: %d assertions, %d failures; kernel parity NOT evaluated" % [_assertions, _failures])
	quit(0 if _failures == 0 else 1)


func _expect(condition: bool, description: String) -> void:
	_assertions += 1
	if not condition:
		_failures += 1
		push_error("Assertion failed: " + description)
