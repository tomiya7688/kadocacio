# {
#   責務: [MatchOperation: ホスト操作を検証し独立した値として保持する]
#   フィールド: [error: 読込失敗理由; kind: 操作種別; _payload: 検証済み操作の複製]
# }
class_name MatchOperation
extends RefCounted
## Detached validated host operation, not a player's AI action.

var error: String = ""
var kind: String = ""
var _payload: Dictionary = {}


# {
#   責務: [read: 操作の型・項目・固定dt・倍率を検証する]
#   処理: [1: 種別と必須項目を検査; 2: 種別固有の値を検査; 3: 正常入力を複製して保持]
#   引数: [payload: 外部操作値]
#   戻り値: [MatchOperation: 検証結果。失敗理由はerror]
# }
static func read(payload: Variant) -> MatchOperation:
	var result: MatchOperation = MatchOperation.new()
	if not payload is Dictionary:
		result.error = "unknown match operation"
		return result
	var data: Dictionary = payload as Dictionary
	if not data.get("kind") is String or not (MatchProtocol.values()["operations"] as Array).has(data["kind"]):
		result.error = "unknown match operation"
		return result
	result.kind = data["kind"] as String
	var field: String = "dt" if result.kind == "STEP" else "value" if result.kind == "SET_SPEED" else ""
	if data.size() != (1 if field.is_empty() else 2) or (not field.is_empty() and not data.has(field)):
		result.error = "unexpected/missing operation fields"
		return result
	if result.kind == "STEP":
		var value: Variant = data["dt"]
		if not (value is int or value is float) or not is_finite(value as float) or (value as float) <= 0 or (value as float) > (MatchProtocol.values()["max_dt"] as float):
			result.error = "invalid STEP dt"
			return result
	if result.kind == "SET_SPEED" and (not MatchProtocol.is_integer(data["value"]) or not (MatchProtocol.values()["speeds"] as Array).has(data["value"] as float)):
		result.error = "unsupported speed"
		return result
	result._payload = data.duplicate(true)
	return result


# {
#   責務: [is_valid: 読込済み操作を適用可能か確認する]
#   処理: [1: 診断が空で操作値が存在するか確認]
#   引数: []
#   戻り値: [bool: 有効な読込後だけtrue]
# }
func is_valid() -> bool:
	return error.is_empty() and not _payload.is_empty()


# {
#   責務: [to_payload: 内部値を変更させない独立操作辞書を返す]
#   処理: [1: 保持値を深く複製]
#   引数: []
#   戻り値: [Dictionary: 消費側が変更できる操作値]
# }
func to_payload() -> Dictionary:
	return _payload.duplicate(true)
