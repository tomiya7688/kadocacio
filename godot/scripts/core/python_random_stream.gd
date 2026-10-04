class_name PythonRandomStream
extends RefCounted
## Integer-seeded CPython MT19937 exchange point, not Godot's platform RNG.
## Algorithm references and scope: doc/Godot試合核.md (independent implementation).

const MASK: int = 0xffffffff
var _words: PackedInt64Array = []
var _index: int = 624
var word_count: int = 0
var _gauss_next: Variant = null


func _init(seed_text: String = "0") -> void:
	assert(MatchProtocol.is_seed_text(seed_text), "Canonical decimal integer seed required")
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


func _seed(limbs: PackedInt64Array) -> void:
	_words.resize(624)
	_words[0] = 19650218
	for index: int in range(1, 624):
		var previous: int = _words[index - 1]
		_words[index] = (1812433253 * (previous ^ (previous >> 30)) + index) & MASK
	var index: int = 1
	var limb_index: int = 0
	for iteration: int in maxi(624, limbs.size()):
		var previous: int = _words[index - 1]
		_words[index] = ((_words[index] ^ ((previous ^ (previous >> 30)) * 1664525)) + limbs[limb_index] + limb_index) & MASK
		index += 1
		limb_index = (limb_index + 1) % limbs.size()
		if index == 624:
			_words[0] = _words[623]
			index = 1
	for iteration: int in 623:
		var previous: int = _words[index - 1]
		_words[index] = ((_words[index] ^ ((previous ^ (previous >> 30)) * 1566083941)) - index) & MASK
		index += 1
		if index == 624:
			_words[0] = _words[623]
			index = 1
	_words[0] = 0x80000000


func _uint32() -> int:
	if _index == 624:
		for index: int in 624:
			var combined: int = (_words[index] & 0x80000000) | (_words[(index + 1) % 624] & 0x7fffffff)
			_words[index] = _words[(index + 397) % 624] ^ (combined >> 1) ^ (0x9908b0df if combined & 1 else 0)
		_index = 0
	var value: int = _words[_index]
	_index += 1
	word_count += 1
	value ^= value >> 11
	value ^= (value << 7) & 0x9d2c5680
	value ^= (value << 15) & 0xefc60000
	return value ^ (value >> 18)


func random() -> float:
	var high: int = _uint32() >> 5
	var low: int = _uint32() >> 6
	return (high * 67108864.0 + low) * (1.0 / 9007199254740992.0)


func getrandbits(bits: int) -> int:
	assert(bits >= 0 and bits <= 53, "Portable bit API supports 0..53 bits")
	if bits == 0:
		return 0
	if bits <= 32:
		return _uint32() >> (32 - bits)
	var low: int = _uint32()
	return low | ((_uint32() >> (64 - bits)) << 32)


func _below(limit: int) -> int:
	assert(limit > 0 and limit < 9e15, "Positive exactly representable integer limit required")
	var bits: int = 0
	var shifted: int = limit
	while shifted != 0:
		bits += 1
		shifted >>= 1
	var value: int = getrandbits(bits)
	while value >= limit:
		value = getrandbits(bits)
	return value


func uniform(minimum: float, maximum: float) -> float:
	assert(is_finite(minimum) and is_finite(maximum))
	return minimum + (maximum - minimum) * random()


func randint(minimum: int, maximum: int) -> int:
	assert(maximum >= minimum and absi(minimum) < 9e15 and absi(maximum) < 9e15)
	return minimum + _below(maximum - minimum + 1)


func choice(values: Array) -> Variant:
	assert(not values.is_empty())
	return values[_below(values.size())]


func gauss(mean: float, deviation: float) -> float:
	assert(is_finite(mean) and is_finite(deviation))
	var value: float
	if _gauss_next == null:
		var angle: float = random() * TAU
		var radius: float = sqrt(-2.0 * log(1.0 - random()))
		value = cos(angle) * radius
		_gauss_next = sin(angle) * radius
	else:
		value = _gauss_next as float
		_gauss_next = null
	return mean + value * deviation


func state_payload() -> Dictionary:
	return {"words": Array(_words), "index": _index, "gauss_next": _gauss_next}
