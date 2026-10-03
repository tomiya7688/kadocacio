class_name TeamPayloadValidator
extends RefCounted
## Formation/tactic/identity validation only; no state mutation or I/O.


static func validate(payload: Variant, source: String) -> Array[TeamDataDiagnostic]:
	var errors: Array[TeamDataDiagnostic] = []
	if not payload is Dictionary:
		errors.append(TeamDataDiagnostic.new("payload_type", source, "$", "チームJSONはオブジェクトが必要です"))
		return errors
	var data: Dictionary = payload as Dictionary
	if not data.get("選手一覧", []) is Array:
		errors.append(TeamDataDiagnostic.new("players_type", source, "選手一覧", "配列が必要です"))
		return errors
	var starters: int = 0
	var keepers: int = 0
	var rows: Array = data.get("選手一覧", []) as Array
	for index: int in rows.size():
		var field: String = "選手一覧[%d]" % index
		if not rows[index] is Dictionary:
			errors.append(TeamDataDiagnostic.new("player_type", source, field, "選手はオブジェクトが必要です"))
			continue
		var raw: Dictionary = TeamPayloadDecoder.canonical_keys(rows[index] as Dictionary)
		if not JsonValue.integer_valid(raw.get("PositionX", 0)) or not JsonValue.integer_valid(raw.get("PositionY", 0)):
			errors.append(TeamDataDiagnostic.new("position_type", source, field + ".ポジションX/Y", "整数が必要です"))
			continue
		if not JsonValue.integer_valid(raw.get("JerseyNumber", index + 1)):
			errors.append(TeamDataDiagnostic.new("number_type", source, field + ".背番号", "整数が必要です"))
		var y: int = JsonValue.integer(raw.get("PositionY", 0))
		var x: int = JsonValue.integer(raw.get("PositionX", 0))
		if y < 0 or y > 11 or (y >= 1 and y <= 10 and (x < 1 or x > 15)):
			errors.append(TeamDataDiagnostic.new("position_range", source, field + ".ポジションX/Y", "控えY=0、GK Y=11、それ以外X=1..15/Y=1..10"))
		if y != 0:
			starters += 1
		if y == 11:
			keepers += 1
	if starters < 7 or starters > 11:
		errors.append(TeamDataDiagnostic.new("starter_count", source, "フォーメーション", "先発は7〜11人必要です: %d" % starters))
	if keepers < 1:
		errors.append(TeamDataDiagnostic.new("goalkeeper_required", source, "フォーメーション", "GKは1人以上必要です"))
	if not data.get("チーム情報", {}) is Dictionary:
		errors.append(TeamDataDiagnostic.new("info_type", source, "チーム情報", "オブジェクトが必要です"))
		return errors
	var info: Dictionary = data.get("チーム情報", {}) as Dictionary
	var tactic: String = JsonValue.text(info.get("戦術", "バランス")).strip_edges()
	if not (TeamContract.values()["tactics"] as Dictionary).has(tactic):
		errors.append(TeamDataDiagnostic.new("tactic_unknown", source, "チーム情報.戦術", "不明な戦術: " + tactic))
	if not JsonValue.integer_valid(info.get("ゾーン手前", 3)) or not JsonValue.integer_valid(info.get("ゾーン奥", 7)):
		errors.append(TeamDataDiagnostic.new("zone_type", source, "チーム情報.ゾーン", "整数が必要です"))
	else:
		var near: int = JsonValue.integer(info.get("ゾーン手前", 3))
		var far: int = JsonValue.integer(info.get("ゾーン奥", 7))
		if not (1 <= near and near <= far and far <= 10):
			errors.append(TeamDataDiagnostic.new("zone_range", source, "チーム情報.ゾーン", "1 <= 手前 <= 奥 <= 10が必要です"))
	var team_id: String = JsonValue.text(data.get("チームID", "")).strip_edges() if data.get("チームID") else ""
	if not team_id.is_empty() and RegEx.create_from_string("^team:[A-Za-z0-9._:-]+$").search(team_id) == null:
		errors.append(TeamDataDiagnostic.new("team_id_invalid", source, "チームID", "team:で始まる英数字IDが必要です"))
	return errors
