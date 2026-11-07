class_name SkidMarks
extends Node2D
## Tyre marks left when wheels lock or slide. Keeps the most recent ones.

const MAX_MARKS := 1600
const REAR := Vector2(-2.0, 0.8)
const FRONT := Vector2(1.7, 0.8)

var _marks := PackedVector2Array()  # pairs of points
var _dirty := false


func clear() -> void:
	_marks.clear()
	queue_redraw()


func add(a: Vector2, b: Vector2, ha: float, hb: float, front: bool) -> void:
	var off := FRONT if front else REAR
	for side: float in [-1.0, 1.0]:
		var o := Vector2(off.x, off.y * side)
		_marks.append(a + o.rotated(ha))
		_marks.append(b + o.rotated(hb))
	if _marks.size() > MAX_MARKS * 2:
		_marks = _marks.slice(_marks.size() - MAX_MARKS * 2)
	_dirty = true


func _process(_delta: float) -> void:
	if _dirty:
		_dirty = false
		queue_redraw()


func _draw() -> void:
	if _marks.size() >= 2:
		draw_multiline(_marks, Color(0.06, 0.06, 0.07, 0.55), 0.35)
