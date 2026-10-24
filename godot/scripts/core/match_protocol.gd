# {
#   責務: [MatchProtocol: Pythonから生成された境界規約と共通数値制約を提供する]
#   フィールド: [_values: 初回読込後に再利用する規約辞書]
# }
class_name MatchProtocol
extends RefCounted
## Generated boundary policy; this is not a football engine or RNG implementation.

static var _values: Dictionary = {}


# {
#   責務: [values: 同一規約を全境界クラスで参照する]
#   処理: [1: 未読込なら生成JSONをロード; 2: キャッシュを返す]
#   引数: []
#   戻り値: [Dictionary: 読取専用として扱う共有規約]
# }
static func values() -> Dictionary:
	if _values.is_empty():
		_values = JSON.parse_string(FileAccess.get_file_as_string("res://data/match_contract.json")) as Dictionary
	return _values


# {
#   責務: [is_integer: 両実装で丸めず交換できる整数か判定する]
#   処理: [1: 数値型・有限性・整数性・絶対値9e15未満を確認]
#   引数: [value: 外部数値候補]
#   戻り値: [bool: 共通整数制約を満たすならtrue]
# }
static func is_integer(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(value as float) and floorf(value as float) == (value as float) and absf(value as float) < 9.0e15


# {
#   責務: [is_seed_text: 大整数seedの正規十進表記を検証する]
#   処理: [1: 型・負のゼロ・桁上限を確認; 2: 符号と先頭ゼロを正規表現で検査]
#   引数: [value: seed候補]
#   戻り値: [bool: 4096桁以内の正規表記ならtrue]
# }
static func is_seed_text(value: Variant) -> bool:
	if not value is String or value == "-0" or (value as String).trim_prefix("-").length() > 4096:
		return false
	var pattern: RegEx = RegEx.new()
	pattern.compile("^-?(0|[1-9][0-9]*)$")
	return pattern.search(value as String) != null
