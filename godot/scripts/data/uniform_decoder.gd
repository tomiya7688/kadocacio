class_name UniformDecoder
extends RefCounted
## Pixel-uniform normalization only; preserves Python padding/token fallback behavior.


static func normalize(value: Variant) -> Dictionary:
	var source: Dictionary = value as Dictionary if value is Dictionary else {}
	if source.get("ユニフォーム") is Dictionary:
		source = source["ユニフォーム"] as Dictionary
	var parts: Dictionary = source.get("パーツ", {}) as Dictionary if source.get("パーツ") is Dictionary else {}
	var definition: Dictionary = TeamContract.values()["uniform"] as Dictionary
	var sizes: Dictionary = definition["parts"] as Dictionary
	var result: Dictionary = {"バージョン": definition["version"], "パーツ": {}}
	var hex: RegEx = RegEx.create_from_string("^#[0-9A-Fa-f]{6}$")
	for part: String in sizes:
		var size: Array = sizes[part] as Array
		var fallback: String = "S" if part.ends_with("脚") else "P"
		var input: Array = parts.get(part) as Array if parts.get(part) is Array else []
		var rows: Array[Array] = []
		for y: int in range(size[1] as int):
			var input_row: Array = input[y] as Array if y < input.size() and input[y] is Array else []
			var row: Array[String] = []
			for x: int in range(size[0] as int):
				var cell: String = JsonValue.text(input_row[x]) if x < input_row.size() else ""
				row.append(cell.to_upper() if cell.to_upper() in ["P", "S"] or hex.search(cell) != null else fallback)
			rows.append(row)
		(result["パーツ"] as Dictionary)[part] = rows
	return result
