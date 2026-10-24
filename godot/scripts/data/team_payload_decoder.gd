class_name TeamPayloadDecoder
extends RefCounted
## Pure conversion of a validated payload; does not validate, read files or run AI.


static func canonical_keys(source: Dictionary) -> Dictionary:
	var result: Dictionary = source.duplicate(true)
	var aliases: Dictionary = TeamContract.values()["player_aliases"] as Dictionary
	for key: String in aliases:
		for alias: String in aliases[key] as Array:
			if source.has(alias):
				result[key] = source[alias]
				break
	return result


static func decode(payload: Dictionary, source: String) -> TeamDefinition:
	var team: TeamDefinition = TeamDefinition.new()
	team.source = source
	team.original_payload = payload.duplicate(true)
	var path_id: String = "json:" + source.replace("\\", "/")
	team.team_id = JsonValue.text(payload.get("チームID", "")).strip_edges() if payload.get("チームID") else ""
	if team.team_id.is_empty():
		team.team_id = path_id
	if payload.get("チームID別名") is Array:
		for alias: Variant in payload["チームID別名"] as Array:
			var label: String = JsonValue.text(alias).strip_edges() if alias else ""
			if not label.is_empty() and not label in team.legacy_ids:
				team.legacy_ids.append(label)
	if path_id != team.team_id and not path_id in team.legacy_ids:
		team.legacy_ids.append(path_id)
	var info: Dictionary = payload.get("チーム情報", {}) as Dictionary
	team.name = JsonValue.text(info.get("チーム名", source.get_file().get_basename()))
	team.short_name = JsonValue.text(info.get("チームの略称", "")).strip_edges()
	for key: String in ["チーム紹介", "チーム説明", "description", "teamDescription"]:
		if info.has(key):
			team.description = JsonValue.text(info[key])
			break
	team.tactic_label = JsonValue.text(info.get("戦術", "バランス")).strip_edges()
	team.tactic = (TeamContract.values()["tactics"] as Dictionary)[team.tactic_label] as String
	team.zone_near = JsonValue.integer(info.get("ゾーン手前", 3))
	team.zone_far = JsonValue.integer(info.get("ゾーン奥", 7))
	team.tactical_discipline = StatScale.percentage(info.get("戦術への忠実さ", 50.0))
	team.home_court = JsonValue.text(info.get("ホームコート", team.name + "ホーム")).strip_edges()
	team.primary = _color(info.get("チームカラー", ""))
	team.uniform_data = UniformDecoder.normalize(info.get("ユニフォーム"))
	var bounds: Array[float] = StatScale.bounds(payload)
	team.manager = _manager(info, bounds)
	for value: Variant in payload.get("選手一覧", []) as Array:
		var player: PlayerDefinition = _player(value as Dictionary, bounds, team.tactical_discipline, team.starters.size() + team.bench.size() + 1)
		if player.position_y == 0:
			team.bench.append(player)
		else:
			team.starters.append(player)
	return team


static func _manager(info: Dictionary, bounds: Array[float]) -> ManagerDefinition:
	var manager: ManagerDefinition = ManagerDefinition.new()
	manager.name = JsonValue.text(info.get("監督名", ""))
	var scale: Dictionary = TeamContract.values()["scale"] as Dictionary
	var activity: float = scale["manager_activity_default"] as float
	var intelligence: float = scale["manager_intelligence_default"] as float
	manager.tactic_aggression = _manager_stat(info, "戦術変更への積極性", activity, bounds)
	manager.substitution_aggression = _manager_stat(info, "選手交代への積極性", activity, bounds)
	manager.intelligence = _manager_stat(info, "インテリジェンス", intelligence, bounds)
	return manager


static func _manager_stat(info: Dictionary, key: String, fallback: float, bounds: Array[float]) -> float:
	# Manager remap is not rounded in Python; do not use the integer player remap.
	if not info.has(key):
		return StatScale.normalize(fallback, fallback)
	var numeric: float = JsonValue.number(info[key], bounds[0])
	if not is_finite(numeric):
		numeric = bounds[0]
	var unit: float = (clampf(numeric, bounds[0], bounds[1]) - bounds[0]) / maxf(1.0, bounds[1] - bounds[0])
	return clampf(unit, 0.0, 1.0)


static func decode_record(record: Dictionary, team_loyalty: float) -> PlayerDefinition:
	# Choice records already use current-scale canonical raw parameters.
	var player: PlayerDefinition = _player(record["raw"] as Dictionary, StatScale.current_bounds(), team_loyalty, record["number"] as int)
	player.name = record["name"] as String
	player.number = record["number"] as int
	player.slot = (record["slot"] as Array).duplicate()
	return player


static func _player(source: Dictionary, bounds: Array[float], team_loyalty: float, default_number: int) -> PlayerDefinition:
	var player: PlayerDefinition = PlayerDefinition.new()
	player.raw = canonical_keys(source)
	var keys: Array = TeamContract.values()["stat_keys"] as Array
	if bounds != StatScale.current_bounds():
		for key: String in keys:
			if player.raw.has(key):
				player.raw[key] = StatScale.remap(player.raw[key], bounds)
	player.name = JsonValue.text(player.raw.get("Name", "PLAYER"))
	player.number = JsonValue.integer(player.raw.get("JerseyNumber", default_number))
	player.position_x = JsonValue.integer(player.raw.get("PositionX", 0))
	player.position_y = JsonValue.integer(player.raw.get("PositionY", 0))
	if player.position_y != 0:
		player.slot = [role(player.position_y), 0.055, 0.5] if player.position_y == 11 else [role(player.position_y), 0.10 + (10 - player.position_y + 0.5) / 10.0 * 0.40, (player.position_x - 0.5) / 15.0]
	player.player_type = _player_type(player.raw.get("PlayerType", ""), role(player.position_y))
	player.skills = _skills(player.raw.get("Skills", []))
	player.tactical_discipline = StatScale.percentage(player.raw.get("TacticalDiscipline", team_loyalty * 100.0), team_loyalty * 100.0)
	player.normalized_stats = _stats(player.raw, player.player_type)
	return player


static func role(y: int) -> String:
	if y >= 1 and y <= 3: return "FW"
	if y >= 4 and y <= 7: return "MF"
	if y >= 8 and y <= 10: return "DF"
	return "GK" if y == 11 else "SUB"


static func _stats(raw: Dictionary, player_type: String) -> Dictionary:
	var contract: Dictionary = TeamContract.values()
	var defaults: float = (contract["scale"] as Dictionary)["player_default"] as float
	var fallback_keys: Dictionary = contract["stat_fallbacks"] as Dictionary
	var style: Dictionary = contract["style_fields"] as Dictionary
	var preferences: Dictionary = (contract["type_preferences"] as Dictionary)[player_type] as Dictionary
	var result: Dictionary = {}
	for key: String in contract["stat_keys"] as Array:
		var fallback: float = defaults
		for behavior: String in style:
			if style[behavior] == key:
				var limits: Array[float] = StatScale.current_bounds()
				fallback = limits[0] + (preferences[behavior] as float) * (limits[1] - limits[0])
		result[key] = StatScale.normalize(raw.get(key, raw.get(fallback_keys[key], fallback)), fallback)
	return result


static func _player_type(value: Variant, position_role: String) -> String:
	var contract: Dictionary = TeamContract.values()
	var label: String = JsonValue.text(value).strip_edges() if value else ""
	label = (contract["type_aliases"] as Dictionary).get(label, label) as String
	if label in (contract["player_types"] as Array):
		return label
	return {"GK": "バックアップ", "DF": "スイーパー", "MF": "オールラウンド", "FW": "ストライカー"}.get(position_role, "オールラウンド") as String


static func _skills(value: Variant) -> PackedStringArray:
	var result: PackedStringArray = []
	if not value is Array:
		return result
	var aliases: Dictionary = TeamContract.values()["skill_aliases"] as Dictionary
	for item: Variant in value as Array:
		var label: String = JsonValue.text(item).strip_edges()
		label = aliases.get(label, label) as String
		if label in (TeamContract.values()["skills"] as Array) and not label in result:
			result.append(label)
	result.sort()
	return result


static func _color(value: Variant) -> Array[int]:
	var result: Array[int] = []
	var text: String = (value as String).strip_edges() if value is String else ""
	while text.begins_with("#"):
		text = text.substr(1)
	if RegEx.create_from_string("^[0-9a-fA-F]{6}$").search(text) != null:
		for offset: int in [0, 2, 4]:
			result.append(text.substr(offset, 2).hex_to_int())
	else:
		for channel: Variant in TeamContract.values()["default_color"] as Array:
			result.append(channel as int)
	return result
