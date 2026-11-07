class_name CoachTour
extends Control
## A guided tour: dims the screen except one highlighted control, with a
## callout that explains it, NEXT and SKIP. Steps can run code first (switch a
## tab, select a slot) so the thing being explained is on screen.

signal finished

## Each step: {"target": Callable -> Control (or Rect2), "title": String, "text": String, "before": Callable (optional)}
var steps: Array[Dictionary] = []
var _i := -1
var _rect := Rect2()
var _shown_rect := Rect2()
var _box: PanelContainer
var _title: Label
var _text: Label
var _count: Label
var _next: Button
var _t := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	theme = Ui.theme
	_box = PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.075, 0.09, 0.97)
	sb.border_color = Ui.YELLOW
	sb.border_width_top = 3
	sb.set_content_margin_all(10)
	_box.add_theme_stylebox_override("panel", sb)
	_box.custom_minimum_size = Vector2(230, 0)
	add_child(_box)
	var v := Ui.vbox(4)
	_box.add_child(v)
	_count = Ui.label("", Ui.SIZE_SMALL, Ui.YELLOW, true)
	v.add_child(_count)
	_title = Ui.label("", Ui.SIZE_HEADING, Ui.INK, true)
	v.add_child(_title)
	_text = Ui.label("", Ui.SIZE_SMALL, Ui.INK_2)
	_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_text.custom_minimum_size = Vector2(210, 0)
	v.add_child(_text)
	var row := Ui.hbox(6)
	v.add_child(row)
	var skip := Ui.button("SKIP TOUR")
	skip.pressed.connect(_finish)
	row.add_child(skip)
	_next = Ui.button("NEXT  >", true)
	_next.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_next.pressed.connect(_advance)
	row.add_child(_next)
	_advance()


func _advance() -> void:
	_i += 1
	if _i >= steps.size():
		_finish()
		return
	var s := steps[_i]
	var before: Variant = s.get("before")
	if before is Callable and (before as Callable).is_valid():
		(before as Callable).call()
	await get_tree().process_frame
	await get_tree().process_frame
	_count.text = "GARAGE TOUR  ·  %d / %d" % [_i + 1, steps.size()]
	_title.text = String(s.get("title", ""))
	_text.text = String(s.get("text", ""))
	_next.text = "GOT IT" if _i == steps.size() - 1 else "NEXT  >"
	_rect = _target_rect(s)
	_place_box()
	if has_node("/root/Sfx"):
		get_node("/root/Sfx").call("play", "ui_toggle")


func _target_rect(s: Dictionary) -> Rect2:
	var t: Variant = s.get("target")
	if t is Callable:
		t = (t as Callable).call()
	if t is Control:
		var r := (t as Control).get_global_rect()
		return Rect2(r.position - get_global_rect().position, r.size).grow(4)
	if t is Rect2:
		return t
	return Rect2(size / 2, Vector2.ZERO)


func _place_box() -> void:
	await get_tree().process_frame
	var bs := _box.size
	var pos := Vector2(_rect.end.x + 10, _rect.position.y)
	if pos.x + bs.x > size.x - 6:
		pos.x = _rect.position.x - bs.x - 10
	if pos.x < 6:
		pos = Vector2(clampf(_rect.get_center().x - bs.x / 2, 6, size.x - bs.x - 6), _rect.end.y + 10)
		if pos.y + bs.y > size.y - 6:
			pos.y = _rect.position.y - bs.y - 10
			if pos.y < 6:
				# no room around a big target: sit at the bottom of the screen
				pos = Vector2(size.x / 2 - bs.x / 2, size.y - bs.y - 8)
	pos.y = clampf(pos.y, 6, size.y - bs.y - 6)
	_box.position = pos


func _finish() -> void:
	finished.emit()
	queue_free()


func _process(delta: float) -> void:
	_t += delta
	_shown_rect.position = _shown_rect.position.lerp(_rect.position, 1.0 - exp(-12.0 * delta))
	_shown_rect.size = _shown_rect.size.lerp(_rect.size, 1.0 - exp(-12.0 * delta))
	queue_redraw()


func _draw() -> void:
	var r := _shown_rect
	var dim := Color(0.02, 0.025, 0.03, 0.72)
	draw_rect(Rect2(0, 0, size.x, r.position.y), dim)
	draw_rect(Rect2(0, r.end.y, size.x, size.y - r.end.y), dim)
	draw_rect(Rect2(0, r.position.y, r.position.x, r.size.y), dim)
	draw_rect(Rect2(r.end.x, r.position.y, size.x - r.end.x, r.size.y), dim)
	var pulse := 0.6 + 0.4 * sin(_t * 4.0)
	draw_rect(r, Color(Ui.YELLOW, pulse), false, 2.0)


func _gui_input(event: InputEvent) -> void:
	# clicks outside the callout advance the tour; the highlighted control stays look-only
	if event is InputEventMouseButton and (event as InputEventMouseButton).pressed and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		accept_event()
