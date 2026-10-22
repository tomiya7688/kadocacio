# {
#   責務: [ObservedMatchRandom: 乱数列を変えずに基本抽選の履歴を任意で記録する]
#   フィールド: [enabled: 記録の有効状態; purpose: 抽選用途; step: 物理更新番号; _events: 抽選結果と消費語位置の履歴。乱数状態は親クラスが保持]
# }
class_name ObservedMatchRandom
extends PythonRandomStream
## Opt-in primitive draw audit. Observation/rendering never consumes this stream.

var enabled: bool = false
var purpose: String = "construct"
var step: int = 0
var _events: Array[Dictionary] = []


# {
#   責務: [random: 親の一様乱数を一回生成して観測情報を付ける]
#   処理: [1: 消費前の語数を覚える; 2: 親のrandomを呼ぶ; 3: 有効時だけ履歴へ記録する]
#   引数: []
#   戻り値: [float: 親と同じ0以上1未満の値。記録の有無は抽選結果を変えない]
# }
func random() -> float:
	# 観測用の抽選を追加せず、親が消費した語の区間だけを記録する。
	var before: int = word_count
	var value: float = super.random()
	_record("random", [], value, before)
	return value


# {
#   責務: [getrandbits: 親の整数乱数を生成してbit数と消費位置を記録する]
#   処理: [1: 消費前の語数を覚える; 2: 親のgetrandbitsを呼ぶ; 3: 有効時だけ履歴へ記録する]
#   引数: [bits: 親クラスの公開範囲である0から53のbit数]
#   戻り値: [int: 親と同じ非負整数。不正なbit数は親が拒否する]
# }
func getrandbits(bits: int) -> int:
	# 0bit時に語を消費しない性質も親の実装へ委ねる。
	var before: int = word_count
	var value: int = super.getrandbits(bits)
	_record("getrandbits", [bits], value, before)
	return value


# {
#   責務: [_record: 記録が有効な場合だけ基本抽選一件の観測情報を追加する]
#   処理: [1: 有効フラグを確認する; 2: 用途・引数・結果・消費語区間を追加する; 3: bit抽選には整数比較用の値を添える]
#   引数: [method: 基本抽選名; arguments: 基本抽選の引数; value: 抽選結果; before: 抽選前の消費語数]
#   戻り値: [void: 有効時だけ_eventsを更新し、無効時は何もしない]
# }
func _record(method: String, arguments: Array, value: Variant, before: int) -> void:
	# sequenceは記録した件数で採番するため、記録停止中の抽選は含まない。
	if enabled:
		_events.append({"sequence": _events.size() + 1, "step": step, "purpose": purpose,
			"method": method, "arguments": arguments, "value": value,
			"word_before": before, "word_after": word_count})
		if method == "getrandbits":
			_events[-1]["bit_value"] = value


# {
#   責務: [history: 呼出し元から変更されない独立した観測履歴を返す]
#   処理: [1: 履歴の配列と内部辞書を再帰的に複製する]
#   引数: []
#   戻り値: [Array[Dictionary]: 履歴の深いコピー。乱数状態と元履歴を変更しない]
# }
func history() -> Array[Dictionary]:
	# テスト側で差分表示用に編集しても保存済みの履歴を壊さない。
	return _events.duplicate(true)
