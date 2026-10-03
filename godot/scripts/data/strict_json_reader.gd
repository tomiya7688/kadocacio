class_name StrictJsonReader
extends RefCounted
## Godot JSON accepts trailing commas/control characters; reject these before parsing.
## Result is data/error/line. Does not deserialize Objects or emit errors for bad input.


static func read_file(path: String) -> Dictionary:
	var file: FileAccess = FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {"data": null, "error": "ファイルを読み込めません", "line": 0}
	return parse(file.get_as_text())


static func parse(text: String) -> Dictionary:
	text = text.trim_prefix("\ufeff")
	var invalid: int = _invalid_token(text)
	if invalid >= 0:
		return {"data": null, "error": "JSONのトークンが不正です", "line": text.substr(0, invalid).count("\n") + 1}
	var parser: JSON = JSON.new()
	var status: Error = parser.parse(text)
	if status != OK:
		return {"data": null, "error": parser.get_error_message(), "line": parser.get_error_line()}
	return {"data": parser.data, "error": "", "line": 0}


static func _invalid_token(text: String) -> int:
	var scalar: RegEx = RegEx.create_from_string("^(null|true|false|-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?)$")
	var previous: String = ""
	var index: int = 0
	while index < text.length():
		var character: String = text[index]
		if character in [" ", "\n", "\r", "\t"]:
			index += 1
			continue
		if character == '"':
			var end: int = _string_end(text, index)
			if end < 0:
				return index
			index = end + 1
			previous = "string"
			continue
		if character in ["{", "}", "[", "]", ",", ":"]:
			if previous == "," and character in ["}", "]"]:
				return index
			previous = character
			index += 1
			continue
		var start: int = index
		while index < text.length() and not text[index] in ["{", "}", "[", "]", ",", ":", '"', " ", "\n", "\r", "\t"]:
			index += 1
		if scalar.search(text.substr(start, index - start)) == null:
			return start
		previous = "scalar"
	return -1


static func _string_end(text: String, start: int) -> int:
	var index: int = start + 1
	while index < text.length():
		if text[index] == '"':
			return index
		if text.unicode_at(index) < 32:
			return -1
		if text[index] == "\\":
			index += 1
			if index >= text.length() or not text[index] in ['"', "\\", "/", "b", "f", "n", "r", "t", "u"]:
				return -1
			if text[index] == "u":
				var unit: int = _unicode_unit(text, index + 1)
				if unit < 0 or (unit >= 0xDC00 and unit <= 0xDFFF):
					return -1
				index += 4
				if unit >= 0xD800 and unit <= 0xDBFF:
					if text.substr(index + 1, 2) != "\\u":
						return -1
					var low: int = _unicode_unit(text, index + 3)
					if low < 0xDC00 or low > 0xDFFF:
						return -1
					index += 6
		index += 1
	return -1


static func _unicode_unit(text: String, index: int) -> int:
	var token: String = text.substr(index, 4)
	if token.length() != 4 or RegEx.create_from_string("^[0-9a-fA-F]{4}$").search(token) == null:
		return -1
	return token.hex_to_int()
