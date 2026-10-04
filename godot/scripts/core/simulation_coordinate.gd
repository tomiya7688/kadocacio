class_name SimulationCoordinate
extends RefCounted
## 64-bit scalar world coordinates; render Vector3 conversion belongs to the view.

var x: float = 0.0
var y: float = 0.0
var z: float = 0.0


func set_values(next_x: float, next_y: float, next_z: float = 0.0) -> void:
	x = next_x
	y = next_y
	z = next_z


func to_array() -> Array[float]:
	return [x, y, z]
