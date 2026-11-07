extends SceneTree
## Demo and visual test for the 3D car showcase. Record it with the movie maker:
##   godot --path game --write-movie D:/dev/shots3d/s.png --fixed-fps 30 --quit-after 720 \
##     -s res://scenes/car3d/showcase_test.gd
## Optional user args after "--":
##   demo            full-screen showcase cycling parts, colours, fits and focus (default)
##   grid=<area>     the area's concepts side by side, framed on that area
##   angles          one car from six angles
##   garage          the showcase at the garage's CarPreview rect, cycling focus
##   look=<a>:<c>,…  parts for grid/angles, e.g. look=floor:venturi,rear_wing:beam
##   px=<n>          pixel_size
##   hl=<area>       highlight an area (hover state)
##   bg=<hex>        backdrop colour behind the (transparent) showcase
##   opaque          opaque showcase background instead of transparent

const ShowcaseScript := preload("res://scenes/car3d/car_showcase.gd")
const CarScript := preload("res://scenes/car3d/car_model.gd")

const RED := Color("e8352b")
const INK := Color("f1efea")
const YELLOW := Color("f2c230")
const BLUE := Color("3f7fe0")
const PURPLE := Color("a855f7")

var _t := 0.0
var _show: CarShowcase
var _steps: Array = []
var _next := 0
var _px := 3
var _hl := ""
var _opaque := false


func _initialize() -> void:
	var mode := "demo"
	var area := "front_wing"
	var look := {}
	for a: String in OS.get_cmdline_user_args():
		if a.begins_with("grid="):
			mode = "grid"
			area = a.substr(5)
		elif a == "angles" or a == "demo" or a == "garage":
			mode = a
		elif a.begins_with("look="):
			for pair: String in a.substr(5).split(","):
				var kv := pair.split(":")
				if kv.size() == 2:
					look[kv[0]] = kv[1]
		elif a.begins_with("px="):
			_px = int(a.substr(3))
		elif a.begins_with("hl="):
			_hl = a.substr(3)
		elif a == "opaque":
			_opaque = true
	var bg := ColorRect.new()
	bg.color = Color("141518")
	for a: String in OS.get_cmdline_user_args():
		if a.begins_with("bg="):
			bg.color = Color(a.substr(3))
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(bg)
	match mode:
		"grid":
			_grid(area, look)
		"angles":
			_angles(look)
		"garage":
			_garage(look)
		_:
			_demo()


## A showcase filling the given fraction of the window (anchors).
func _make(rect: Rect2, look: Dictionary) -> CarShowcase:
	var s: CarShowcase = ShowcaseScript.new()
	s.pixel_size = _px
	s.anchor_left = rect.position.x
	s.anchor_top = rect.position.y
	s.anchor_right = rect.end.x
	s.anchor_bottom = rect.end.y
	s.set_parts(look)
	s.highlight(_hl)
	s.transparent = not _opaque
	root.add_child(s)
	return s


func _grid(area: String, look: Dictionary) -> void:
	var concepts: Array = CarScript.CONCEPTS.get(area, [])
	var n := concepts.size()
	for i in n:
		var l := look.duplicate()
		l[area] = concepts[i]
		var cell := Rect2((i % 2) * 0.5, (i / 2) * 0.5, 0.5, 0.5)
		var s := _make(cell, l)
		s.spin = false
		s.focus(area)
		var lab := Label.new()
		lab.text = "%s: %s" % [area, concepts[i]]
		lab.anchor_left = cell.position.x
		lab.anchor_top = cell.position.y
		lab.offset_left = 6
		lab.offset_top = 2
		root.add_child(lab)


func _angles(look: Dictionary) -> void:
	var yaws := [-0.6, 0.0, 0.6, 1.6, 2.6, -2.2]
	for i in 6:
		var s := _make(Rect2((i % 3) / 3.0, (i / 3) * 0.5, 1.0 / 3.0, 0.5), look)
		s.spin = false
		s.set_yaw(yaws[i])


## Same rect as the garage's CarPreview (anchor 0.64 x 0.78, offsets 10/46/-10/-42).
func _garage(look: Dictionary) -> void:
	for i in 2:
		var c: Control = ShowcaseScript.new() if i == 0 else ColorRect.new()
		c.anchor_right = 0.64
		c.anchor_bottom = 0.78
		c.offset_left = 10
		c.offset_top = 46
		c.offset_right = -10
		c.offset_bottom = -42
		if c is ColorRect:
			(c as ColorRect).color = Color(1, 1, 1, 0.05)
			c.mouse_filter = Control.MOUSE_FILTER_IGNORE
		else:
			_show = c as CarShowcase
			_show.pixel_size = _px
			_show.set_parts(look)
		root.add_child(c)
	var s := _show
	_steps = [
		[2.0, func() -> void: s.focus("sidepods")],
		[3.5, func() -> void: s.highlight("sidepods")],
		[4.0, func() -> void: _fit("sidepods", "undercut")],
		[5.5, func() -> void: s.focus("")],
	]


func _demo() -> void:
	_show = _make(Rect2(0, 0, 1, 1), {})
	_show.set_colors(RED, INK)
	# [time, Callable]
	var s := _show
	_steps = [
		[0.5, func() -> void: print("car triangles: ", s.car.triangles)],
		[1.2, func() -> void: _fit("front_wing", "inwash")],
		[2.4, func() -> void: s.focus("front_wing")],
		[3.4, func() -> void: _fit("front_wing", "highnose")],
		[4.6, func() -> void: s.focus("rear_wing")],
		[5.4, func() -> void: _fit("rear_wing", "beam")],
		[6.4, func() -> void: s.set_wing_open(true)],
		[7.2, func() -> void: s.set_wing_open(false)],
		[7.6, func() -> void: s.focus("sidepods")],
		[8.4, func() -> void: _fit("sidepods", "undercut")],
		[9.4, func() -> void: s.focus("floor")],
		[10.2, func() -> void: _fit("floor", "venturi")],
		[11.2, func() -> void: s.focus("suspension")],
		[11.9, func() -> void: _fit("suspension", "pullrod")],
		[12.8, func() -> void: s.focus("power_unit")],
		[13.5, func() -> void: _fit("power_unit", "efficiency")],
		[14.5, func() -> void: s.focus("")],
		[15.0, func() -> void: s.set_colors(BLUE, YELLOW)],
		[15.2, func() -> void: s.set_compound("soft")],
		[16.0, func() -> void: s.set_parts({"front_wing": "outwash", "rear_wing": "spoon", "sidepods": "zeropod", "floor": "high_rake", "power_unit": "topend"})],
		[17.0, func() -> void: s.highlight("rear_wing")],
		[18.0, func() -> void: s.highlight("sidepods")],
		[19.0, func() -> void: s.highlight("")],
		[19.2, func() -> void: s.set_colors(INK, RED)],
		[19.3, func() -> void: s.set_compound("hard")],
		[20.0, func() -> void: _drag(0)],
		[22.6, func() -> void: s.set_colors(PURPLE, INK)],
		[23.0, func() -> void: print("leader point front_wing: ", s.area_screen_point("front_wing"), " size ", s.size)],
	]


## Simulated mouse drag across the showcase (press, 12 moves, release).
func _drag(step: int) -> void:
	var c := _show.get_global_rect().get_center()
	if step == 0:
		var down := InputEventMouseButton.new()
		down.button_index = MOUSE_BUTTON_LEFT
		down.pressed = true
		down.position = c
		down.global_position = c
		Input.parse_input_event(down)
	if step < 12:
		var mm := InputEventMouseMotion.new()
		mm.button_mask = MOUSE_BUTTON_MASK_LEFT
		mm.relative = Vector2(9, 1)
		mm.position = c + Vector2(9 * step, step)
		mm.global_position = mm.position
		Input.parse_input_event(mm)
		_steps.insert(_next + 1, [_t + 0.033, func() -> void: _drag(step + 1)])
	else:
		var up := InputEventMouseButton.new()
		up.button_index = MOUSE_BUTTON_LEFT
		up.pressed = false
		up.position = c
		up.global_position = c
		Input.parse_input_event(up)


func _fit(area: String, concept: String) -> void:
	_show.set_parts({area: concept})
	_show.fit_part(area)


func _process(delta: float) -> bool:
	_t += delta
	while _next < _steps.size() and _t >= float(_steps[_next][0]):
		(_steps[_next][1] as Callable).call()
		_next += 1
	return false
