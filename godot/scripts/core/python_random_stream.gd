# {
#   責務: [PythonRandomStream: 整数seedからCPython互換の乱数列を生成する]
#   フィールド: [MASK: 32bit切詰めマスク; _words: MT19937の624語; _index: 次に消費する語; word_count: 消費語数; _gauss_next: 次回へ持ち越す標準正規乱数]
# }
class_name PythonRandomStream
extends RefCounted
## Integer-seeded CPython MT19937 exchange point, not Godot's platform RNG.
## Algorithm references and scope: doc/Godot試合核.md (independent implementation).

const MASK: int = 0xffffffff
var _words: PackedInt64Array = []
var _index: int = 624
var word_count: int = 0
var _gauss_next: Variant = null


# {
#   責務: [_init: 十進整数seedを絶対値の32bit語列へ変換して初期化する]
#   処理: [1: 正規の整数表記を検証する; 2: 符号を除いた各桁を下位語から蓄積する; 3: 語列を初期状態へ混ぜる]
#   引数: [seed_text: 正規化済み十進整数文字列。省略時は0]
#   戻り値: [void: 初期状態を設定。不正な表記はassertで拒否する]
# }
func _init(seed_text: String = "0") -> void:
	assert(MatchProtocol.is_seed_text(seed_text), "Canonical decimal integer seed required")
	# 整数型の桁数制限に依存せず、CPythonと同じ絶対値の下位語列を作る。
	var limbs: PackedInt64Array = [0]
	for digit: String in seed_text.trim_prefix("-"):
		var carry: int = digit.to_int()
		for index: int in limbs.size():
			var expanded: int = limbs[index] * 10 + carry
			limbs[index] = expanded & MASK
			carry = expanded >> 32
		if carry != 0:
			limbs.append(carry)
	_seed(limbs)


# {
#   責務: [_seed: 整数seedの語列をMT19937の内部状態へ混ぜる]
#   処理: [1: 固定seedから624語を準備する; 2: seed各語を循環して混ぜる; 3: 二巡目の混合と非ゼロ状態の保証を行う]
#   引数: [limbs: 下位語から並んだ空でない符号なし32bit語列]
#   戻り値: [void: _wordsを構築する。構築直後の初期化専用]
# }
func _seed(limbs: PackedInt64Array) -> void:
	# 最初の漸化式と以降の各混合は、必ず32bitへ切り詰める。
	_words.resize(624)
	_words[0] = 19650218
	for index: int in range(1, 624):
		var previous: int = _words[index - 1]
		_words[index] = (1812433253 * (previous ^ (previous >> 30)) + index) & MASK
	var index: int = 1
	var limb_index: int = 0
	# 状態またはseedの長い方を一巡し、長大な整数seedの全語を反映する。
	for iteration: int in maxi(624, limbs.size()):
		var previous: int = _words[index - 1]
		_words[index] = ((_words[index] ^ ((previous ^ (previous >> 30)) * 1664525)) + limbs[limb_index] + limb_index) & MASK
		index += 1
		limb_index = (limb_index + 1) % limbs.size()
		if index == 624:
			_words[0] = _words[623]
			index = 1
	# seed混合後にもう一巡し、全ゼロへの退化を先頭語の最上位bitで防ぐ。
	for iteration: int in 623:
		var previous: int = _words[index - 1]
		_words[index] = ((_words[index] ^ ((previous ^ (previous >> 30)) * 1566083941)) - index) & MASK
		index += 1
		if index == 624:
			_words[0] = _words[623]
			index = 1
	_words[0] = 0x80000000


# {
#   責務: [_uint32: MT19937から次の符号なし32bit語を消費する]
#   処理: [1: 状態を使い切った場合は624語を更新する; 2: 語の位置と消費数を進める; 3: 出力のbitを調整する]
#   引数: []
#   戻り値: [int: 0から2の32乗未満の乱数語。内部状態とword_countを進める]
# }
func _uint32() -> int:
	# Godot標準乱数へ置き換えるとseedと消費順の互換性が失われる。
	if _index == 624:
		for index: int in 624:
			var combined: int = (_words[index] & 0x80000000) | (_words[(index + 1) % 624] & 0x7fffffff)
			_words[index] = _words[(index + 397) % 624] ^ (combined >> 1) ^ (0x9908b0df if combined & 1 else 0)
		_index = 0
	var value: int = _words[_index]
	_index += 1
	word_count += 1
	# CPythonのMT19937と同じtemperingを語の消費後に行う。
	value ^= value >> 11
	value ^= (value << 7) & 0x9d2c5680
	value ^= (value << 15) & 0xefc60000
	return value ^ (value >> 18)


# {
#   責務: [random: CPythonと同じ53bit精度の一様乱数を生成する]
#   処理: [1: 二語の上位27bitと26bitを消費する; 2: 53bit整数を単位区間へ縮める]
#   引数: []
#   戻り値: [float: 0以上1未満の値。常に二語を消費する]
# }
func random() -> float:
	# 二語の下位bitを捨てる位置も互換性の一部になる。
	var high: int = _uint32() >> 5
	var low: int = _uint32() >> 6
	return (high * 67108864.0 + low) * (1.0 / 9007199254740992.0)


# {
#   責務: [getrandbits: 公開互換範囲の整数乱数を生成する]
#   処理: [1: bit数を検証する; 2: 0bitなら消費せず返す; 3: 必要な一語または二語を下位語から合成する]
#   引数: [bits: 必要なbit数。0から53まで]
#   戻り値: [int: 指定bit幅の非負整数。範囲外はassertで拒否する]
# }
func getrandbits(bits: int) -> int:
	assert(bits >= 0 and bits <= 53, "Portable bit API supports 0..53 bits")
	if bits == 0:
		return 0
	if bits <= 32:
		return _uint32() >> (32 - bits)
	# 33bit以上では先に消費した語を下位32bitへ置く。
	var low: int = _uint32()
	return low | ((_uint32() >> (64 - bits)) << 32)


# {
#   責務: [_below: 剰余による偏りを避けて上限未満の整数を選ぶ]
#   処理: [1: 上限を検証して必要bit数を求める; 2: 上限以上の値を引いた場合は引き直す]
#   引数: [limit: 正の排他的上限。9e15未満]
#   戻り値: [int: 0以上limit未満の値。引き直し回数も乱数消費に含む]
# }
func _below(limit: int) -> int:
	assert(limit > 0 and limit < 9e15, "Positive exactly representable integer limit required")
	var bits: int = 0
	var shifted: int = limit
	while shifted != 0:
		bits += 1
		shifted >>= 1
	var value: int = getrandbits(bits)
	# CPythonと同じ棄却法を使い、limitが2の冪でも消費順を維持する。
	while value >= limit:
		value = getrandbits(bits)
	return value


# {
#   責務: [uniform: 有限の両端を持つ区間へ一様乱数を写す]
#   処理: [1: 両端が有限か検証する; 2: 一回のrandomを区間へ線形変換する]
#   引数: [minimum: 区間の始点; maximum: 区間の終点。始点より小さくてもよい]
#   戻り値: [float: 変換した乱数。端点の丸めは浮動小数点演算に従う]
# }
func uniform(minimum: float, maximum: float) -> float:
	# 演算順序もPython参照実装と揃え、丸め差を増やさない。
	assert(is_finite(minimum) and is_finite(maximum))
	return minimum + (maximum - minimum) * random()


# {
#   責務: [randint: 両端を含む整数区間から乱数を選ぶ]
#   処理: [1: 両端の大小と絶対値を検証する; 2: 区間幅を排他的上限として抽選し始点を加える]
#   引数: [minimum: 含まれる下端; maximum: 含まれる上端。両端の絶対値は9e15未満で区間幅も_belowの範囲内]
#   戻り値: [int: 両端を含む整数。範囲外はassertで拒否する]
# }
func randint(minimum: int, maximum: int) -> int:
	# +1はmaximumを候補に含めるためで、_below自体の上限は含まない。
	assert(maximum >= minimum and absi(minimum) < 9e15 and absi(maximum) < 9e15)
	return minimum + _below(maximum - minimum + 1)


# {
#   責務: [choice: 空でない配列から偏りなく一要素を選ぶ]
#   処理: [1: 空配列を拒否する; 2: 配列長未満の整数で要素を参照する]
#   引数: [values: 選択候補。要素を複製せず返す]
#   戻り値: [Variant: 選ばれた要素。空配列はassertで拒否する]
# }
func choice(values: Array) -> Variant:
	# 配列の並べ替えや追加のrandom呼出しをせず、参照順を固定する。
	assert(not values.is_empty())
	return values[_below(values.size())]


# {
#   責務: [gauss: CPythonと同じ生成順とキャッシュで正規乱数を返す]
#   処理: [1: 平均と偏差が有限か検証する; 2: キャッシュがなければ一様乱数二個から二値を作る; 3: 一値を保持または消費し平均と偏差を適用する]
#   引数: [mean: 分布の平均; deviation: 標準正規乱数に掛ける有限の係数]
#   戻り値: [float: 正規乱数。キャッシュがあれば乱数語を消費しない]
# }
func gauss(mean: float, deviation: float) -> float:
	assert(is_finite(mean) and is_finite(deviation))
	var value: float
	# Box–Mullerで得た対の片方を次回へ残し、Pythonのgauss消費順を再現する。
	if _gauss_next == null:
		var angle: float = random() * TAU
		var radius: float = sqrt(-2.0 * log(1.0 - random()))
		value = cos(angle) * radius
		_gauss_next = sin(angle) * radius
	else:
		value = _gauss_next as float
		_gauss_next = null
	return mean + value * deviation


# {
#   責務: [state_payload: 乱数列の差分検証に必要な内部状態を観測する]
#   処理: [1: 状態語を通常配列へ写す; 2: 次語の位置と正規乱数キャッシュをまとめる]
#   引数: []
#   戻り値: [Dictionary: words・index・gauss_next。観測で乱数を消費しない]
# }
func state_payload() -> Dictionary:
	# PackedInt64Arrayを通常配列へ変換し、呼出し元に内部語列を渡さない。
	return {"words": Array(_words), "index": _index, "gauss_next": _gauss_next}
