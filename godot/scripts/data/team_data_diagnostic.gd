class_name TeamDataDiagnostic
extends RefCounted

var code: String
var source: String
var field: String
var message: String
var line: int


func _init(error_code: String, file: String, key: String, detail: String, error_line: int = 0) -> void:
	code = error_code
	source = file
	field = key
	message = detail
	line = error_line


func to_dictionary() -> Dictionary:
	return {"code": code, "source": source, "field": field, "message": message, "line": line}
