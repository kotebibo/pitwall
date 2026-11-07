class_name CarPreview
extends Control
## The car in the garage: the 3D showcase on its turntable, rebuilt part by
## part as the player tries and fits parts, with leader lines to the slots.

var look := {}
var color := Ui.RED
## Area → slot point (local) to draw a leader line from the car to it.
var leaders := {}
var highlight := "":
	set(v):
		highlight = v
		if _show:
			_show.highlight(v)
var _show: CarShowcase
var _lines: Control


func _ready() -> void:
	_show = CarShowcase.new()
	_show.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_show)
	_lines = Control.new()
	_lines.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_lines.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_lines.draw.connect(_draw_lines)
	add_child(_lines)
	rebuild()


## All six areas: the four the sprites show plus suspension and power unit.
func _full_look() -> Dictionary:
	var l := look.duplicate()
	for area: String in ["suspension", "power_unit"]:
		if not l.has(area):
			l[area] = String(Catalog.equipped_part(area).get("concept", ""))
	return l


func rebuild() -> void:
	if _show == null:
		return
	_show.set_parts(_full_look())
	_show.set_colors(color, Ui.INK)


## Plays the "fitted" pop and flash on that part.
func fitted(area: String = "") -> void:
	if _show and area != "":
		_show.fit_part(area)


## Turns the camera to a part area ("" = spinning overview).
func focus(area: String) -> void:
	if _show:
		_show.focus(area)


func area_point(area: String) -> Vector2:
	return _show.area_screen_point(area) if _show else size / 2


func _process(_delta: float) -> void:
	_lines.queue_redraw()


func _draw_lines() -> void:
	for area: String in leaders:
		var from := area_point(area)
		var to: Vector2 = leaders[area]
		var col := Ui.INK if area == highlight else Color(1, 1, 1, 0.22)
		var elbow := Vector2(to.x, from.y) if absf(to.y - from.y) > absf(to.x - from.x) * 0.3 else (from + to) / 2.0
		_lines.draw_polyline(PackedVector2Array([from, elbow, to]), col, 1.0)
		_lines.draw_rect(Rect2(from - Vector2(2, 2), Vector2(4, 4)), Ui.RED if area == highlight else col)
