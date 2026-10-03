class_name TeamLoadResult
extends RefCounted

var team: TeamDefinition = null
var diagnostics: Array[TeamDataDiagnostic] = []


func is_valid() -> bool:
	return team != null and diagnostics.is_empty()


static func failure(code: String, source: String, field: String, message: String, line: int = 0) -> TeamLoadResult:
	var result: TeamLoadResult = TeamLoadResult.new()
	result.diagnostics.append(TeamDataDiagnostic.new(code, source, field, message, line))
	return result
