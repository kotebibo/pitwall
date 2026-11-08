class_name TuningPanel
extends Control
## Car setup the way an engineer sees it: wing flaps in side profile that tilt
## as you add angle, and rotary dials on the steering wheel for brake bias and
## the differential. Changes are whole steps, like a real setup sheet.

signal changed

const FLAP_DEG_PER_STEP := 2.5  # wing flap angle per setup step
const WHEEL := "res://assets/sprites/ui/%s.png"

var locked := false
var _readout: Label
var _dials: Array[Dictionary] = []
var _hover_dial := -1


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_PASS
	tooltip_text = " "  # enables _get_tooltip
	_readout = Ui.label("", Ui.SIZE_SMALL, Ui.INK)
	_readout.position = Vector2(8, 0)
	add_child(_readout)
	for spec: Array in [["front_wing", Vector2(0.06, 0.12)], ["rear_wing", Vector2(0.06, 0.52)]]:
		_add_steppers(spec[0], spec[1])
	resized.connect(_place_buttons)
	_place_buttons()
	_refresh()


func _add_steppers(key: String, at: Vector2) -> void:
	for dir in [-1, 1]:
		var b := Ui.button("-" if dir < 0 else "+")
		b.custom_minimum_size = Vector2(18, 16)
		b.disabled = locked
		b.set_meta("rel", at + Vector2(0.30 if dir > 0 else 0.22, 0.30))
		b.pressed.connect(func() -> void: _step(key, dir))
		add_child(b)


func _place_buttons() -> void:
	for c in get_children():
		if c is Button and c.has_meta("rel"):
			var rel: Vector2 = c.get_meta("rel")
			(c as Button).position = rel * size


func _step(key: String, dir: int) -> void:
	if locked:
		return
	var lo := 50 if key == "brake_bias" else 1
	var hi := 64 if key == "brake_bias" else 11
	var v := clampi(int(Profile.setup.get(key, 6)) + dir, lo, hi)
	if v == int(Profile.setup.get(key, 6)):
		return
	Profile.setup[key] = v
	if has_node("/root/Sfx"):
		get_node("/root/Sfx").call("play", "ui_dial")
	_refresh()
	changed.emit()


func _refresh() -> void:
	var fw: float = Profile.setup["front_wing"] - 6
	var rw: float = Profile.setup["rear_wing"] - 6
	var k_down := 3.0 + 0.06 * fw + 0.10 * rw
	var k_drag := 0.80 + 0.008 * fw + 0.032 * rw
	var front := 0.44 + 0.012 * fw - 0.010 * rw
	var top := pow(400000.0 / k_drag, 1.0 / 3.0) * 3.6
	var top_boost := pow(750000.0 / k_drag, 1.0 / 3.0) * 3.6
	var df := k_down * pow(250 / 3.6, 2) / 9.81
	_readout.text = "TOP SPEED %d KM/H   BOOST %d   DOWNFORCE @250 %d KG   BALANCE %d%% FRONT" % [roundi(top), roundi(top_boost), roundi(df), roundi(front * 100)]
	queue_redraw()


# ---- drawing ----

func _wing(origin: Vector2, scale_px: float, key: String, title: String, front: bool) -> void:
	var steps := int(Profile.setup[key])
	var angle := deg_to_rad(4.0 + steps * FLAP_DEG_PER_STEP)
	var main := PartCard.texture(WHEEL % ("front_wing_side" if front else "wing_side_main"))
	var flap := PartCard.texture(WHEEL % ("front_wing_side_flap" if front else "wing_side_flap"))
	draw_string(Ui.font_bold, origin + Vector2(0, -6), title, HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_SMALL, Ui.INK_2)
	draw_string(Ui.font_bold, origin + Vector2(150, -6), "%.1f°" % rad_to_deg(angle), HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_HEADING, Ui.INK)
	var base := origin + Vector2(10, 30)
	# airflow lines bending over the wing: more angle, more turning
	for k in 4:
		var y := base.y - 18 + k * 9
		var pts := PackedVector2Array()
		for x in 18:
			var u := x / 17.0
			var bend := -sin(clampf((u - 0.35) * 2.2, 0.0, 1.0) * PI * 0.5) * angle * 40.0 * (1.0 - k * 0.2)
			pts.append(Vector2(base.x - 20 + u * 200, y + bend))
		draw_polyline(pts, Color(0.37, 0.78, 0.9, 0.18), 1.0)
	if main and flap:
		var ms := main.get_size() * scale_px
		draw_texture_rect(main, Rect2(base, ms), false)
		draw_set_transform(base + Vector2(ms.x * 0.62, ms.y * 0.15), -angle, Vector2(scale_px, scale_px))
		draw_texture(flap, Vector2(0, -flap.get_height() * 0.5))
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	else:
		# drawn aerofoils
		var mp := PackedVector2Array([base + Vector2(0, 8), base + Vector2(60, 0), base + Vector2(120, 6), base + Vector2(60, 12)])
		draw_colored_polygon(mp, Color("2b2f36"))
		draw_set_transform(base + Vector2(110, 2), -angle, Vector2.ONE)
		draw_colored_polygon(PackedVector2Array([Vector2(0, 0), Vector2(40, -3), Vector2(70, 2), Vector2(40, 5)]), Ui.RED)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	draw_string(Ui.font, origin + Vector2(0, 74), "%d / 11" % steps, HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_SMALL, Ui.INK_3)


func _draw() -> void:
	var w := size.x
	var h := size.y
	_wing(Vector2(w * 0.06, h * 0.14), 1.6, "front_wing", "FRONT WING FLAP", true)
	_wing(Vector2(w * 0.06, h * 0.54), 1.6, "rear_wing", "REAR WING FLAP", false)
	# Steering wheel with two rotary dials
	var wheel := PartCard.texture(WHEEL % "steering_wheel")
	var wpos := Vector2(w * 0.52, h * 0.16)
	var wsize := Vector2(w * 0.44, w * 0.44 * 112.0 / 192.0)
	if wheel:
		draw_texture_rect(wheel, Rect2(wpos, wsize), false)
	else:
		draw_rect(Rect2(wpos, wsize), Color("16181c"))
		draw_rect(Rect2(wpos + Vector2(wsize.x * 0.3, wsize.y * 0.15), Vector2(wsize.x * 0.4, wsize.y * 0.3)), Color("0b0c0e"))
	var sx := wsize.x / 192.0
	var sockets := _sockets()
	var screen: Rect2 = sockets.get("screen", Rect2(62, 18, 68, 30))
	var scr := Rect2(wpos + screen.position * sx, screen.size * sx)
	draw_string(Ui.font_bold, scr.position + Vector2(4, scr.size.y * 0.42), "BB %.1f" % float(Profile.setup["brake_bias"]), HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_BODY, Color("3ecf6a"))
	draw_string(Ui.font_bold, scr.position + Vector2(4, scr.size.y * 0.85), "DIFF %d" % int(Profile.setup["differential"]), HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_BODY, Ui.YELLOW)
	_dials.clear()
	var socket_list: Array = sockets.get("rotaries", [Vector2(40, 70), Vector2(152, 70)])
	var specs := [["brake_bias", 50, 64, "BRAKE BIAS"], ["differential", 1, 11, "DIFF"]]
	for i in specs.size():
		var spec: Array = specs[i]
		var centre: Vector2 = wpos + (socket_list[mini(i, socket_list.size() - 1)] as Vector2) * sx
		_dial(centre, 11.0 * sx, spec, i == _hover_dial)
		_dials.append({"centre": centre, "radius": 14.0 * sx, "spec": spec})
	draw_string(Ui.font, Vector2(wpos.x, wpos.y + wsize.y + 14), "Click a dial: left side turns down, right side up. Scroll works too.", HORIZONTAL_ALIGNMENT_LEFT, wsize.x, Ui.SIZE_SMALL, Ui.INK_3)
	var tips := [
		"FRONT WING: turn-in and front grip. Too much and the rear gets nervous.",
		"REAR WING: grip in fast corners, but drag: top speed and battery suffer.",
		"BRAKE BIAS: forward is stable but locks the fronts; rearward rotates the car.",
		"DIFF: locked puts power down out of slow corners; open lets the car turn.",
	]
	var ty := wpos.y + wsize.y + 30
	for t: String in tips:
		# wrapped, not cut off, when a line is wider than the wheel column
		draw_multiline_string(Ui.font, Vector2(wpos.x, ty), t, HORIZONTAL_ALIGNMENT_LEFT, wsize.x + 20, Ui.SIZE_SMALL, -1, Ui.INK_2)
		ty += Ui.font.get_multiline_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, wsize.x + 20, Ui.SIZE_SMALL).y
	if locked:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.08, 0.08, 0.09, 0.45))
		draw_string(Ui.font_bold, Vector2(0, h * 0.5), "PARC FERME · SETUP LOCKED FOR QUALIFYING", HORIZONTAL_ALIGNMENT_CENTER, w, Ui.SIZE_HEADING, Ui.YELLOW)


func _sockets() -> Dictionary:
	var path := "res://assets/sprites/ui/steering_wheel.json"
	if not FileAccess.file_exists(path):
		return {}
	var d: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not d is Dictionary:
		return {}
	var out := {}
	var rot: Array = []
	for key: String in ["rotaries", "rotary_sockets", "sockets"]:
		if (d as Dictionary).get(key) is Array:
			for s: Variant in d[key]:
				if s is Array:
					rot.append(Vector2(s[0], s[1]))
				elif s is Dictionary and (s as Dictionary).get("center") is Array:
					rot.append(Vector2(s["center"][0], s["center"][1]))  # steering_wheel.json: {"id", "center": [x, y]}
				elif s is Dictionary:
					rot.append(Vector2(s.get("x", 0), s.get("y", 0)))
	if rot.size() >= 2:
		# use the two lowest sockets (thumb dials)
		rot.sort_custom(func(a: Vector2, b: Vector2) -> bool: return a.y > b.y)
		var pair := [rot[0], rot[1]]
		pair.sort_custom(func(a: Vector2, b: Vector2) -> bool: return a.x < b.x)
		out["rotaries"] = pair
	var sc: Variant = (d as Dictionary).get("screen")
	if sc is Array and (sc as Array).size() == 4:
		out["screen"] = Rect2(sc[0], sc[1], sc[2], sc[3])
	elif sc is Dictionary:
		out["screen"] = Rect2(sc.get("x", 0), sc.get("y", 0), sc.get("w", 0), sc.get("h", 0))
	return out


func _dial(c: Vector2, r: float, spec: Array, hover: bool) -> void:
	var key: String = spec[0]
	var lo: int = spec[1]
	var hi: int = spec[2]
	var v := int(Profile.setup[key])
	var t := float(v - lo) / float(hi - lo)
	var angle := lerpf(-2.35, 2.35, t) - PI / 2
	var ring := PartCard.texture(WHEEL % "rotary_ring")
	var knob := PartCard.texture(WHEEL % "rotary")
	if ring:
		draw_texture_rect(ring, Rect2(c - Vector2(r, r) * 1.4, Vector2(r, r) * 2.8), false)
	else:
		for k in 11:
			var a := lerpf(-2.35, 2.35, k / 10.0) - PI / 2
			draw_line(c + Vector2.from_angle(a) * r * 1.15, c + Vector2.from_angle(a) * r * 1.35, Ui.INK_3, 1.0)
	if knob:
		draw_set_transform(c, angle + PI / 2, Vector2(r * 2.0 / knob.get_width(), r * 2.0 / knob.get_height()))
		draw_texture(knob, -knob.get_size() / 2.0)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	else:
		draw_circle(c, r, Color("2b2f36"))
		draw_line(c, c + Vector2.from_angle(angle) * r, Ui.INK, 2.0)
	if hover:
		draw_arc(c, r * 1.5, 0, TAU, 32, Ui.RED, 1.0)
	draw_string(Ui.font_bold, c + Vector2(-30, r * 1.6 + 10), spec[3], HORIZONTAL_ALIGNMENT_CENTER, 60, Ui.SIZE_SMALL, Ui.INK_2)


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		var hover := _dial_at((event as InputEventMouseMotion).position)
		if hover != _hover_dial:
			_hover_dial = hover
			queue_redraw()
	elif event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
		var mb := event as InputEventMouseButton
		var i := _dial_at(mb.position)
		if i < 0:
			return
		var key: String = _dials[i]["spec"][0]
		if mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			_step(key, 1)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_step(key, -1)
		elif mb.button_index == MOUSE_BUTTON_LEFT:
			_step(key, 1 if mb.position.x >= (_dials[i]["centre"] as Vector2).x else -1)
		accept_event()


func _get_tooltip(at: Vector2) -> String:
	var d := _dial_at(at)
	if d >= 0:
		var key: String = _dials[d]["spec"][0]
		if key == "brake_bias":
			return "BRAKE BIAS: share of braking on the front wheels.\nForward: stable, but the fronts lock. Back: the car rotates into corners, the rear can lock.\nClick left or right half, or scroll."
		return "DIFFERENTIAL: how much the rear wheels are locked together on throttle.\nLocked: traction out of slow corners. Open: the car turns more easily.\nClick left or right half, or scroll."
	if at.x < size.x * 0.5:
		if at.y < size.y * 0.5:
			return "FRONT WING FLAP: more angle = more front grip and sharper turn-in, a little more drag."
		return "REAR WING FLAP: more angle = more rear grip in fast corners, less top speed and battery."
	return ""


func _dial_at(p: Vector2) -> int:
	for i in _dials.size():
		if p.distance_to(_dials[i]["centre"]) <= float(_dials[i]["radius"]) * 1.6:
			return i
	return -1
