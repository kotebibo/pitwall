class_name TuningPanel
extends Control
## Car setup the way an engineer sees it: wing flaps in side profile that tilt
## as you add angle, and rotary dials on the steering wheel for brake bias and
## the differential. Changes are whole steps, like a real setup sheet.
##
## Beside them, what the setup does on track: PERFORMANCE bars (CarPerf, from
## CarSim's own formulas) for this setup against the one you came in with, one
## sentence on the change and one line per control on what it does now.

signal changed

const FLAP_DEG_PER_STEP := 2.5  # wing flap angle per setup step
const WHEEL := "res://assets/sprites/ui/%s.png"
const STANDARD := {"front_wing": 6, "rear_wing": 6, "brake_bias": 57, "differential": 6}
const GAP := 10.0
const INTRO_H := 26.0
const WING_H := 118.0

var locked := false
var _base: Dictionary = {}  # the setup when the garage opened: what the bars compare against
var _intro: RichTextLabel
var _lines := {}  # setup key -> RichTextLabel: what that control does now
var _hint: Label
var _side: VBoxContainer
var _caption: Label
var _bars: PerfPanel.PerfBars
var _summary: RichTextLabel
var _undo: Button
var _test: Button
var _col_w := 200.0
var _wings := {}  # setup key -> Rect2 of its block
var _wheel_rect := Rect2()
var _dials: Array[Dictionary] = []
var _hover_dial := -1
## setup_metrics() by setup, driver stats and parts: a dial turn asks for the same cars again
static var _cache := {}


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_PASS
	tooltip_text = " "  # enables _get_tooltip
	_base = Profile.setup.duplicate()
	var args := Api.args
	if OS.is_debug_build() and "--locked" in args:
		locked = true  # testing: the parc ferme look
	if OS.is_debug_build() and "--tune" in args and args.find("--tune") + 1 < args.size():
		# testing: start from a changed setup, e.g. -- --tune 8,9,62,8 (front wing, rear wing, brake bias, diff); never saved
		var v := args[args.find("--tune") + 1].split(",")
		for i in mini(v.size(), 4):
			Profile.setup[["front_wing", "rear_wing", "brake_bias", "differential"][i]] = int(v[i])
	_intro = _rich()
	add_child(_intro)
	for key: String in ["front_wing", "rear_wing"]:
		_add_steppers(key)
		_lines[key] = _rich()
		add_child(_lines[key])
	# under the steering wheel: how to turn the dials, then what each does now
	_side = Ui.vbox(4)
	add_child(_side)
	_hint = Ui.label("Click a dial: the left half turns it down, the right half up. Scrolling works too.", Ui.SIZE_SMALL, Ui.INK_3)
	_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_side.add_child(_hint)
	for key: String in ["brake_bias", "differential"]:
		_lines[key] = _rich()
		_side.add_child(_lines[key])
	_add_perf()
	resized.connect(_layout)
	_layout()
	_refresh()
	if OS.is_debug_build() and "--tune-drive" in args:
		_test_drive.call_deferred()  # testing: open TEST DRIVE straight away


func _rich() -> RichTextLabel:
	var l := RichTextLabel.new()
	l.bbcode_enabled = true
	l.fit_content = true
	l.scroll_active = false
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.mouse_filter = Control.MOUSE_FILTER_PASS
	l.add_theme_font_size_override("normal_font_size", Ui.SIZE_SMALL)
	l.add_theme_font_size_override("bold_font_size", Ui.SIZE_SMALL)
	l.add_theme_font_override("bold_font", Ui.font_bold)
	l.add_theme_color_override("default_color", Ui.INK_2)
	l.add_theme_constant_override("line_separation", -2)
	return l


func _add_steppers(key: String) -> void:
	for dir in [-1, 1]:
		var b := Ui.button("-" if dir < 0 else "+")
		b.custom_minimum_size = Vector2(18, 16)
		b.size = b.custom_minimum_size
		b.disabled = locked
		b.tooltip_text = ("Less" if dir < 0 else "More") + (" front" if key == "front_wing" else " rear") + " wing flap angle"
		b.set_meta("wing", key)
		b.set_meta("dir", dir)
		b.pressed.connect(func() -> void: _step(key, dir))
		add_child(b)


## The right-hand column: PERFORMANCE bars, the sentence on the change, UNDO and TEST DRIVE.
func _add_perf() -> void:
	var panel := Ui.panel()
	panel.name = "Perf"
	add_child(panel)
	var v := Ui.vbox(3)
	panel.add_child(v)
	var head := Ui.hbox(6)
	head.add_child(Ui.label("PERFORMANCE", Ui.SIZE_SMALL, Ui.INK_2, true))
	_caption = Ui.label("vs the setup you came in with", Ui.SIZE_SMALL, Ui.INK_3)
	_caption.clip_text = true
	_caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(_caption)
	v.add_child(head)
	_bars = PerfPanel.PerfBars.new()
	_bars.use(CarPerf.SETUP_KEYS, CarPerf.SETUP_SPAN, CarPerf.SETUP_HELP)
	_bars.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_child(_bars)
	_summary = _rich()
	_summary.add_theme_color_override("default_color", Ui.INK)
	v.add_child(_summary)
	var buttons := Ui.hbox(4)
	v.add_child(buttons)
	_undo = Ui.button("UNDO CHANGES")
	_undo.tooltip_text = "Back to the setup you had when you came into the garage."
	_undo.custom_minimum_size = Vector2(0, 20)
	_undo.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_undo.pressed.connect(_reset)
	buttons.add_child(_undo)
	_test = Ui.button("TEST DRIVE")
	_test.custom_minimum_size = Vector2(0, 20)
	_test.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_test.pressed.connect(_test_drive)
	buttons.add_child(_test)
	var legend := Ui.label("Green: better than before. Red: worse. Yellow: neither, just different. The tick in each bar is the standard setup.", Ui.SIZE_SMALL, Ui.INK_3)
	legend.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(legend)


## Three columns under the intro line: wings, steering wheel, performance.
func _layout() -> void:
	var w := size.x
	_col_w = floorf((w - GAP * 2.0) / 3.0)
	_intro.position = Vector2(6, 2)
	_intro.size = Vector2(w - 12, 0)
	var top := INTRO_H
	var spare := maxf(0.0, (size.y - top - WING_H * 2.0) / 3.0)
	_wings["front_wing"] = Rect2(0, top + minf(spare, 12.0), _col_w, WING_H)
	_wings["rear_wing"] = Rect2(0, top + minf(spare, 12.0) * 2.0 + WING_H, _col_w, WING_H)
	for c in get_children():
		if c is Button and c.has_meta("wing"):
			var r: Rect2 = _wings[c.get_meta("wing")]
			var dir: int = c.get_meta("dir")
			(c as Button).position = r.position + Vector2(r.size.x - (44.0 if dir < 0 else 20.0), 40)
	for key: String in _wings:
		var r: Rect2 = _wings[key]
		var l: RichTextLabel = _lines[key]
		l.position = r.position + Vector2(0, 80)
		l.size = Vector2(r.size.x, 0)
	var wx := _col_w + GAP
	var wheel_w := minf(192.0, _col_w)
	_wheel_rect = Rect2(Vector2(wx + (_col_w - wheel_w) / 2.0, top + minf(spare, 12.0)), Vector2(wheel_w, wheel_w * 112.0 / 192.0))
	_side.position = Vector2(wx, _wheel_rect.end.y + 6)
	_side.size = Vector2(_col_w, 0)
	var perf := get_node("Perf") as Control
	perf.position = Vector2((_col_w + GAP) * 2.0 - 4, top + minf(spare, 12.0) - 6)
	perf.size = Vector2(w - perf.position.x, size.y - perf.position.y)  # a full-height column, like the parts page's
	queue_redraw()


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


func _reset() -> void:
	if locked or _base == Profile.setup:
		return
	for k: String in _base:
		Profile.setup[k] = _base[k]
	if has_node("/root/Sfx"):
		get_node("/root/Sfx").call("play", "ui_dial")
	_refresh()
	changed.emit()


func _refresh() -> void:
	var now := _metrics(Profile.setup)
	var before := _metrics(_base)
	_bars.show_cars(before, now, _metrics(STANDARD))
	var same := _base == Profile.setup
	if locked:
		_intro.text = "[color=#f2c230][b]PARC FERME: SETUP LOCKED.[/b] Your first qualifying run today locked this setup until the event closes. The bars show what it does on track.[/color]"
		_summary.text = "Locked for today's qualifying. You can change it again when the next event opens."
	else:
		_intro.text = "[b][color=#f1efea]Set the car up for this track.[/color][/b] More wing grips in the corners, less wing is faster on the straights. Try a setup in Practice: [color=#f2c230]your first qualifying run of the day locks it[/color] (parc ferme)."
		_summary.text = change_sentence(_base, Profile.setup, before, now)
	_lines["front_wing"].text = _front_wing_line()
	_lines["rear_wing"].text = _rear_wing_line()
	_lines["brake_bias"].text = _brake_bias_line()
	_lines["differential"].text = _diff_line()
	_undo.disabled = locked or same
	_test.disabled = locked or same
	_test.tooltip_text = "Change the setup first: then the autopilot drives a lap of Mtkvari with the old and the new setup." if same else "The autopilot drives a lap of Mtkvari with the setup you came in with and with this one, and shows where it gains or loses time."
	for c in get_children():
		if c is Button and c.has_meta("wing"):
			(c as Button).disabled = locked
	queue_redraw()


## CarPerf.setup_metrics for a setup with today's driver and the fitted parts.
static func _metrics(setup: Dictionary) -> Dictionary:
	var stats := Profile.stats()
	var spec := Catalog.car_spec()
	var key := "%s|%s|%s" % [setup, stats, spec]
	if not _cache.has(key):
		if _cache.size() > 200:
			_cache.clear()
		_cache[key] = CarPerf.setup_metrics(CarPerf.car(setup, stats, spec))
	return _cache[key]


## The setup now with one control back at its standard value.
static func _with(key: String, value: int) -> Dictionary:
	var s: Dictionary = Profile.setup.duplicate()
	s[key] = value
	return s


# ---- words ----

static func _green(t: String) -> String:
	return "[color=#3ecf6a]%s[/color]" % t


static func _red(t: String) -> String:
	return "[color=#e8352b]%s[/color]" % t


static func _yellow(t: String) -> String:
	return "[color=#f2c230]%s[/color]" % t


## A signed whole number of km/h, green when better.
static func _kmh(d: float, what: String) -> String:
	var t := "%+d km/h %s" % [roundi(d), what]
	return _green(t) if d > 0.0 else _red(t)


## One sentence on what changed since `from` and what it does on track (a and b: _metrics of each).
static func change_sentence(from: Dictionary, to: Dictionary, a: Dictionary, b: Dictionary) -> String:
	var what: Array[String] = []
	var dfw := int(to["front_wing"]) - int(from["front_wing"])
	var drw := int(to["rear_wing"]) - int(from["rear_wing"])
	if dfw != 0 and drw != 0 and signi(dfw) == signi(drw):
		what.append("more wing" if dfw > 0 else "less wing")
	else:
		if dfw != 0:
			what.append("more front wing" if dfw > 0 else "less front wing")
		if drw != 0:
			what.append("more rear wing" if drw > 0 else "less rear wing")
	var dbb := int(to["brake_bias"]) - int(from["brake_bias"])
	if dbb != 0:
		what.append("brake bias forward" if dbb > 0 else "brake bias back")
	var dd := int(to["differential"]) - int(from["differential"])
	if dd != 0:
		what.append("diff more locked" if dd > 0 else "diff more open")
	if what.is_empty():
		return "This is the setup you came in with. Change a wing or a dial and the bars show what it does on track."
	# [how big (1 = just noticeable), words, 1 better / -1 worse / 0 neither]
	var fx := []
	var d: float = b["fast_corner"] - a["fast_corner"]
	if absf(d) >= 0.5:
		fx.append([absf(d) / 0.5, _kmh(d, "through fast corners"), signi(roundi(d))])
	d = b["top_speed"] - a["top_speed"]
	if absf(d) >= 0.5:
		fx.append([absf(d) / 0.5, _kmh(d, "top speed"), signi(roundi(d))])
	d = b["slow_corner"] - a["slow_corner"]
	if absf(d) >= 0.5:
		fx.append([absf(d) / 0.5, _kmh(d, "in slow corners"), signi(roundi(d))])
	d = a["braking"] - b["braking"]
	if absf(d) >= 0.1:
		var t := "stops %.1f m %s from 200 km/h" % [absf(d), "shorter" if d > 0.0 else "longer"]
		fx.append([absf(d) / 0.1, _green(t) if d > 0.0 else _red(t), 1 if d > 0.0 else -1])
	d = a["acceleration"] - b["acceleration"]
	if absf(d) >= 0.01:
		var t := "0-200 km/h %.2f s %s" % [absf(d), "quicker" if d > 0.0 else "slower"]
		fx.append([absf(d) / 0.01, _green(t) if d > 0.0 else _red(t), 1 if d > 0.0 else -1])
	d = b["balance"] - a["balance"]
	if absf(d) >= 0.005:
		fx.append([absf(d) / 0.005, _yellow("balance %.1f%% to the %s" % [absf(d) * 100.0, "front" if d > 0.0 else "rear"]), 0])
	if a["locks_first"] != b["locks_first"]:
		if b["locks_first"] == "front":
			fx.append([6.0, _yellow("now the fronts lock first (stable)"), 0])
		else:
			fx.append([6.0, _red("now the rears lock first (the car can spin)"), -1])
	if dd != 0:
		fx.append([5.0, _yellow("more traction on the throttle, but it turns less" if dd > 0 else "turns more easily on the throttle, but the rears spin sooner"), 0])
	fx.sort_custom(func(x: Array, y: Array) -> bool: return x[0] > y[0])
	var pick := fx.slice(0, 3)
	# always show the price of a change, if it has one
	var has_bad := pick.any(func(x: Array) -> bool: return x[2] < 0)
	if not has_bad and pick.size() == 3:
		for x: Array in fx.slice(3):
			if x[2] < 0:
				pick[2] = x
				break
	pick.sort_custom(func(x: Array, y: Array) -> bool: return x[2] > y[2])
	var head := ", ".join(what)
	head = head.left(1).to_upper() + head.substr(1)
	if pick.is_empty():
		return "[b]%s[/b]: almost no change on track." % head
	var words: Array[String] = []
	for x: Array in pick:
		words.append(String(x[1]))
	return "[b]%s[/b]: %s." % [head, ", ".join(words)]


func _front_wing_line() -> String:
	var v := int(Profile.setup["front_wing"])
	var m := _metrics(Profile.setup)
	var t := "[b][color=#f1efea]Front wing %d/11:[/color][/b] " % v
	if v > 6:
		t += "more front grip, a sharper turn-in; the rear gets lighter and can slide."
	elif v < 6:
		t += "less front grip: the car runs wide in corners, the rear stays calm."
	else:
		t += "standard, a neutral car."
	t += " " + _yellow("Balance %d%% front." % roundi(float(m["balance"]) * 100.0))
	if v != 6:
		t += " " + _corner_words(m, _metrics(_with("front_wing", 6))) + " vs 6."
	return t


## Corner speed against car s: fast corners (90 m), or medium ones (60 m) when both cars take the fast ones flat out.
static func _corner_words(m: Dictionary, s: Dictionary) -> String:
	var flat := float(m["fast_corner"]) >= float(m["top_speed"]) * 0.995 or float(s["fast_corner"]) >= float(s["top_speed"]) * 0.995
	if flat:
		return _kmh(float(m["cornering"]) - float(s["cornering"]), "in medium corners")
	return _kmh(float(m["fast_corner"]) - float(s["fast_corner"]), "in fast corners")


func _rear_wing_line() -> String:
	var v := int(Profile.setup["rear_wing"])
	var t := "[b][color=#f1efea]Rear wing %d/11:[/color][/b] " % v
	if v > 6:
		t += "more grip in fast corners, but more drag on the straights."
	elif v < 6:
		t += "less drag: faster on the straights, less grip in fast corners."
	else:
		t += "standard, halfway between corners and straights."
	if v != 6:
		var m := _metrics(Profile.setup)
		var s := _metrics(_with("rear_wing", 6))
		t += " %s, %s vs 6." % [_corner_words(m, s), _kmh(float(m["top_speed"]) - float(s["top_speed"]), "top speed")]
	return t


func _brake_bias_line() -> String:
	var v := int(Profile.setup["brake_bias"])
	var m := _metrics(Profile.setup)
	var best := int(m["best_bias"])
	var t := "[b][color=#f1efea]Brake bias %d%% front:[/color][/b] " % v
	if v < best - 1:
		var shorter := float(m["braking"]) - float(_metrics(_with("brake_bias", best))["braking"])
		t += "the rears lock first when you brake hard, so the car can spin. " + _green("%d%% stops %.1f m shorter." % [best, shorter])
	elif v > best:
		t += "the fronts lock first: stable, but the car runs wide if you brake too late."
	else:
		t += "front and rear lock at about the same time: " + _green("the shortest stops for this car.")
	t += " %.1f m from 200 km/h." % float(m["braking"])
	return t


func _diff_line() -> String:
	var v := int(Profile.setup["differential"])
	var t := "[b][color=#f1efea]Differential %d/11:[/color][/b] " % v
	if v > 6:
		t += "more locked: more traction out of slow corners, but the car resists turning on the throttle."
	elif v < 6:
		t += "more open: the car turns easily on the throttle, but the rears spin sooner out of slow corners."
	else:
		t += "standard, halfway between traction and turning."
	if v != 6:
		var stats := Profile.stats()
		var spec := Catalog.car_spec()
		var now: float = CarPerf.car(Profile.setup, stats, spec)["traction_grip"]
		var std: float = CarPerf.car(_with("differential", 6), stats, spec)["traction_grip"]
		var d := (now - std) / std * 100.0
		var tx := "Rear grip on the throttle %+.1f%% vs 6." % d
		t += " " + (_green(tx) if d > 0.0 else _red(tx))
	return t


# ---- drawing ----

func _wing(r: Rect2, key: String, title: String, front: bool) -> void:
	var steps := int(Profile.setup[key])
	var angle := deg_to_rad(4.0 + steps * FLAP_DEG_PER_STEP)
	var main := PartCard.texture(WHEEL % ("front_wing_side" if front else "wing_side_main"))
	var flap := PartCard.texture(WHEEL % ("front_wing_side_flap" if front else "wing_side_flap"))
	var origin := r.position
	draw_string(Ui.font_bold, origin + Vector2(0, 9), title, HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_SMALL, Ui.INK_2)
	draw_string(Ui.font_bold, origin + Vector2(0, 12), "%.1f°" % rad_to_deg(angle), HORIZONTAL_ALIGNMENT_RIGHT, r.size.x, Ui.SIZE_HEADING, Ui.INK)
	var base := origin + Vector2(14, 48)
	# airflow lines bending over the wing: more angle, more turning
	for k in 4:
		var y := base.y - 14 + k * 7
		var pts := PackedVector2Array()
		for x in 18:
			var u := x / 17.0
			var bend := -sin(clampf((u - 0.35) * 2.2, 0.0, 1.0) * PI * 0.5) * angle * 30.0 * (1.0 - k * 0.2)
			pts.append(Vector2(base.x - 12 + u * 140, y + bend))
		draw_polyline(pts, Color(0.37, 0.78, 0.9, 0.18), 1.0)
	if main and flap:
		var ms := main.get_size()
		draw_texture_rect(main, Rect2(base, ms), false)
		draw_set_transform(base + Vector2(ms.x * 0.62, ms.y * 0.15), -angle, Vector2.ONE)
		draw_texture(flap, Vector2(0, -flap.get_height() * 0.5))
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	else:
		# drawn aerofoils
		var mp := PackedVector2Array([base + Vector2(0, 6), base + Vector2(45, 0), base + Vector2(90, 5), base + Vector2(45, 9)])
		draw_colored_polygon(mp, Color("2b2f36"))
		draw_set_transform(base + Vector2(82, 2), -angle, Vector2.ONE)
		draw_colored_polygon(PackedVector2Array([Vector2(0, 0), Vector2(30, -2), Vector2(52, 2), Vector2(30, 4)]), Ui.RED)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	# the setting, between the steppers
	draw_string(Ui.font_bold, origin + Vector2(r.size.x - 72, 52), "%d/11" % steps, HORIZONTAL_ALIGNMENT_CENTER, 24, Ui.SIZE_SMALL, Ui.INK)
	draw_line(origin + Vector2(0, 74), origin + Vector2(r.size.x, 74), Ui.LINE, 1.0)


func _draw() -> void:
	# the intro line on a dark strip, so it reads over the garage wall
	draw_rect(Rect2(0, 0, size.x, INTRO_H - 4), Color(0.06, 0.065, 0.075, 0.92))
	draw_rect(Rect2(0, 0, 2, INTRO_H - 4), Ui.YELLOW if locked else Ui.RED)
	_wing(_wings.get("front_wing", Rect2()), "front_wing", "FRONT WING FLAP", true)
	_wing(_wings.get("rear_wing", Rect2()), "rear_wing", "REAR WING FLAP", false)
	# Steering wheel with two rotary dials
	var wheel := PartCard.texture(WHEEL % "steering_wheel")
	var wpos := _wheel_rect.position
	var wsize := _wheel_rect.size
	if wheel:
		draw_texture_rect(wheel, Rect2(wpos, wsize), false)
	else:
		draw_rect(Rect2(wpos, wsize), Color("16181c"))
		draw_rect(Rect2(wpos + Vector2(wsize.x * 0.3, wsize.y * 0.15), Vector2(wsize.x * 0.4, wsize.y * 0.3)), Color("0b0c0e"))
	var sx := wsize.x / 192.0
	var sockets := _sockets()
	var screen: Rect2 = sockets.get("screen", Rect2(62, 18, 68, 30))
	var scr := Rect2(wpos + screen.position * sx, screen.size * sx)
	draw_string(Ui.font_bold, scr.position + Vector2(4, scr.size.y * 0.42), "BB %.1f" % float(Profile.setup["brake_bias"]), HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_SMALL, Color("3ecf6a"))
	draw_string(Ui.font_bold, scr.position + Vector2(4, scr.size.y * 0.85), "DIFF %d" % int(Profile.setup["differential"]), HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_SMALL, Ui.YELLOW)
	_dials.clear()
	var socket_list: Array = sockets.get("rotaries", [Vector2(40, 70), Vector2(152, 70)])
	var specs := [["brake_bias", 50, 64, "BRAKE BIAS"], ["differential", 1, 11, "DIFF"]]
	for i in specs.size():
		var spec: Array = specs[i]
		var centre: Vector2 = wpos + (socket_list[mini(i, socket_list.size() - 1)] as Vector2) * sx
		_dial(centre, 11.0 * sx, spec, i == _hover_dial)
		_dials.append({"centre": centre, "radius": 14.0 * sx, "spec": spec})
	if locked:
		# the controls dimmed and framed in yellow; the words and the bars stay readable
		var area := Rect2(0, INTRO_H, _col_w * 2.0 + GAP, size.y - INTRO_H)
		draw_rect(area, Color(0.08, 0.08, 0.09, 0.55))
		draw_rect(area.grow(-0.5), Color(Ui.YELLOW, 0.6), false, 1.0)


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
			return "BRAKE BIAS: the share of the braking done by the front wheels.\nToo far back and the rears lock first: the car can spin. Too far forward and the fronts lock: the car runs wide.\nClick the left or right half, or scroll."
		return "DIFFERENTIAL: how tightly the two rear wheels are locked together on the throttle.\nLocked: more traction out of slow corners. Open: the car turns more easily.\nClick the left or right half, or scroll."
	if (_wings.get("front_wing", Rect2()) as Rect2).has_point(at):
		return "FRONT WING FLAP: more angle = more front grip and a sharper turn-in, a little more drag."
	if (_wings.get("rear_wing", Rect2()) as Rect2).has_point(at):
		return "REAR WING FLAP: more angle = more rear grip in fast corners, but more drag: less top speed and battery."
	return ""


func _dial_at(p: Vector2) -> int:
	for i in _dials.size():
		if p.distance_to(_dials[i]["centre"]) <= float(_dials[i]["radius"]) * 1.6:
			return i
	return -1


## "wings 6/8 · brakes 61% front · diff 6"
static func _setup_text(s: Dictionary) -> String:
	return "wings %d/%d · brakes %d%% front · diff %d" % [int(s["front_wing"]), int(s["rear_wing"]), int(s["brake_bias"]), int(s["differential"])]


## Recomputes the bars and words: the parts or driver stats may have changed (the garage loads them after it opens).
func refresh() -> void:
	_refresh()


## TEST DRIVE: the autopilot laps Mtkvari with the setup you came in with and with this one.
func _test_drive() -> void:
	if locked or _base == Profile.setup:
		return
	var host: Node = self
	while host != null and not host is GarageScreen:
		host = host.get_parent()
	if host == null:
		host = get_tree().root
	var panel := TestDrivePanel.new()
	var spec := Catalog.car_spec()
	panel.base_spec = spec
	panel.part_spec = spec
	panel.base_setup = _base.duplicate()
	panel.part_setup = Profile.setup.duplicate()
	panel.title = "NEW SETUP: " + _setup_text(Profile.setup).to_upper()
	panel.caption = "Against the setup you came in with: %s." % _setup_text(_base)
	panel.base_name = "old setup"
	panel.part_name = "new setup"
	panel.change_name = "the new setup"
	host.add_child(panel)
	await panel.closed
	panel.queue_free()
