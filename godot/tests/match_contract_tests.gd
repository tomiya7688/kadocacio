# {
#   責務: [match_contract_tests: 実Godotで境界入力・観測の読込と差分を参照fixtureに照合する]
#   フィールド: [_failures: 失敗数; _assertions: 検査数]
# }
extends SceneTree
## Contract read/roundtrip/diff tests only. Godot football execution is not implemented.

var _failures: int = 0
var _assertions: int = 0


# {
#   責務: [_initialize: SceneTree準備後に境界試験を開始する]
#   処理: [1: 試験本体の遅延実行を予約]
#   引数: []
#   戻り値: [void: 起動イベントのみ登録]
# }
func _initialize() -> void:
	_run.call_deferred()


# {
#   責務: [_run: 共通fixtureの受理・拒否・比較結果を実エンジンで検証する]
#   処理: [1: 入出力引数とfixtureを読む; 2: 正常入力・不正値・期待差分を検査; 3: 再出力と終了コードを保存]
#   引数: []
#   戻り値: [void: 試験結果に応じてプロセスを終了。演算互換の認定はしない]
# }
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
	for value: Variant in [9000000000000000, -9000000000000000, 9e15, -9e15]:
		var oversized: Dictionary = reference.to_payload()
		oversized["extra"] = {"nested": [value]}
		_expect(not MatchTraceRecord.read(oversized).is_valid(), "oversized nested number")
	var portable: Dictionary = reference.to_payload()
	portable["extra"] = {"nested": [8999999999999999, -8999999999999999, 0.5, false]}
	_expect(MatchTraceRecord.read(portable).is_valid(), "portable nested number boundary")
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


# {
#   責務: [_expect: 検査結果を件数と診断へ集約する]
#   処理: [1: 検査数を増加; 2: 失敗時に件数とエラー表示を更新]
#   引数: [condition: 成否; description: 失敗理由]
#   戻り値: [void: 試験カウンタを更新]
# }
func _expect(condition: bool, description: String) -> void:
	_assertions += 1
	if not condition:
		_failures += 1
		push_error("Assertion failed: " + description)
