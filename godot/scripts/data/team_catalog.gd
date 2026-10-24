class_name TeamCatalog
extends RefCounted
## Partial valid teams remain available alongside per-file diagnostics.

var teams: Array[TeamDefinition] = []
var diagnostics: Array[TeamDataDiagnostic] = []
