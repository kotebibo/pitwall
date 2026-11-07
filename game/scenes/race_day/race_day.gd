class_name RaceDayScreen
extends Control
## Race day: you start where you qualified, then call the race from the pit
## wall: aero package, starting tyre, one or two stops, how hard to push.
## The setup is locked on Solana before the seed is revealed.

signal locked(race: Dictionary)
signal back

const TRACK_ID := "mtkvari"
const LAPS := 24
const DESIGNS := [["HIGH DOWNFORCE", "Corner grip"], ["BALANCED", "Suits Mtkvari"], ["LOW DRAG", "Straight speed"]]
const TYRES := [["SOFT", "Fast, wears out", Color("e8352b")], ["MEDIUM", "All-rounder", Color("f2c230")], ["HARD", "Lasts all race", Color("f1efea")]]
const STOPS := [["1 STOP", "Less time in the pits"], ["2 STOPS", "Fresher tyres, more pace"]]

var _design := 1
var _tyre := 1
var _stops := 1
var _risk := 40
var _risk_label: Label
var _lock_button: Button
var _status: Label
var _driver_box: VBoxContainer
var _groups := {}


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(MenuBackdrop.new())
	var shade := ColorRect.new()
	shade.color = Color(Ui.BG, 0.72)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(shade)
	_build()
	_load_driver()


func _glass() -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.075, 0.09, 0.9)
	sb.border_color = Color(1, 1, 1, 0.08)
	sb.set_border_width_all(1)
	sb.border_width_top = 2
	sb.set_content_margin_all(8)
	p.add_theme_stylebox_override("panel", sb)
	return p


func _build() -> void:
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 14)
	add_child(margin)
	var cols := Ui.hbox(12)
	margin.add_child(cols)

	var left := Ui.vbox(6)
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(left)
	var head := Ui.hbox(8)
	var backb := Ui.button("<")
	backb.pressed.connect(func() -> void: back.emit())
	head.add_child(backb)
	head.add_child(Ui.label("RACE DAY", Ui.SIZE_TITLE, Ui.INK, true))
	var you: Dictionary = Profile.event.get("you", {})
	var grid := int(you.get("position", 0)) if you.get("position") != null else 0
	var sub := Ui.label("MTKVARI CIRCUIT · %d LAPS%s" % [LAPS, ("  ·  YOU START P%d" % grid) if grid > 0 else ""], Ui.SIZE_SMALL, Ui.YELLOW if grid > 0 else Ui.INK_2, true)
	sub.size_flags_vertical = Control.SIZE_SHRINK_END
	head.add_child(sub)
	left.add_child(head)
	var strat := _glass()
	left.add_child(strat)
	var sv := Ui.vbox(5)
	strat.add_child(sv)
	sv.add_child(_section("AERO PACKAGE"))
	sv.add_child(_choice_row("design", DESIGNS.size(), _design, _draw_design))
	sv.add_child(_section("STARTING TYRE"))
	sv.add_child(_choice_row("tyre", TYRES.size(), _tyre, _draw_tyre))
	sv.add_child(_section("STRATEGY"))
	sv.add_child(_choice_row("stops", STOPS.size(), _stops - 1, _draw_stops))
	var risk_head := Ui.hbox()
	risk_head.add_child(_section("HOW HARD TO PUSH"))
	_risk_label = Ui.label("", Ui.SIZE_SMALL, Ui.INK, true)
	_risk_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_risk_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	risk_head.add_child(_risk_label)
	sv.add_child(risk_head)
	var slider := HSlider.new()
	slider.min_value = 0
	slider.max_value = 100
	slider.step = 5
	slider.value = _risk
	slider.focus_mode = Control.FOCUS_NONE
	slider.value_changed.connect(_on_risk)
	sv.add_child(slider)
	sv.add_child(Ui.label("Pushing gains time every lap, but raises the chance of a mistake that ends your race.", Ui.SIZE_SMALL, Ui.INK_3))
	_on_risk(_risk)

	var right := Ui.vbox(6)
	right.custom_minimum_size = Vector2(196, 0)
	cols.add_child(right)
	var dp := _glass()
	right.add_child(dp)
	_driver_box = Ui.vbox(3)
	dp.add_child(_driver_box)
	_driver_box.add_child(Ui.label("Loading driver…", Ui.SIZE_SMALL, Ui.INK_2))
	var push := Control.new()
	push.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(push)
	_status = Ui.label("Locks your call on Solana before the race seed is revealed. Nobody can change it after.", Ui.SIZE_SMALL, Ui.INK_2)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	right.add_child(_status)
	_lock_button = Ui.button("LOCK SETUP", true)
	_lock_button.custom_minimum_size = Vector2(0, 32)
	_lock_button.add_theme_font_size_override("font_size", Ui.SIZE_HEADING)
	_lock_button.pressed.connect(_on_lock)
	right.add_child(_lock_button)


func _section(text: String) -> Label:
	return Ui.label(text, Ui.SIZE_SMALL, Ui.INK_2, true)


func _choice_row(key: String, count: int, selected: int, painter: Callable) -> HBoxContainer:
	var row := Ui.hbox(5)
	var group := ButtonGroup.new()
	var buttons: Array[Button] = []
	for i in count:
		var b := Button.new()
		b.toggle_mode = true
		b.button_group = group
		b.focus_mode = Control.FOCUS_NONE
		b.custom_minimum_size = Vector2(0, 40)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.button_pressed = i == selected
		b.draw.connect(func() -> void: painter.call(b, i))
		b.pressed.connect(func() -> void:
			match key:
				"design": _design = i
				"tyre": _tyre = i
				"stops": _stops = i + 1
			for o in buttons:
				o.queue_redraw())
		row.add_child(b)
		buttons.append(b)
	_groups[key] = buttons
	return row


func _texts(b: Button, title: String, hint: String, x: float) -> void:
	b.draw_string(Ui.font_bold, Vector2(x, 17), title, HORIZONTAL_ALIGNMENT_LEFT, b.size.x - x - 4, Ui.SIZE_BODY, Ui.INK)
	b.draw_string(Ui.font, Vector2(x, 31), hint, HORIZONTAL_ALIGNMENT_LEFT, b.size.x - x - 4, Ui.SIZE_SMALL, Ui.INK_2 if not b.button_pressed else Ui.INK)


func _draw_design(b: Button, i: int) -> void:
	# a rear wing seen from the side, flap angle by package
	var c := Vector2(18, 20)
	var angle := [0.75, 0.42, 0.12][i] as float
	b.draw_line(c + Vector2(-10, 4), c + Vector2(4, 2), Ui.INK_2, 3.0)
	b.draw_line(c + Vector2(4, 0), c + Vector2(4, 0) + Vector2.from_angle(-angle) * 10.0, Ui.RED, 3.0)
	_texts(b, DESIGNS[i][0], DESIGNS[i][1], 36)


func _draw_tyre(b: Button, i: int) -> void:
	var c := Vector2(18, 20)
	b.draw_circle(c, 12.0, Color("111214"))
	b.draw_arc(c, 9.0, 0, TAU, 32, TYRES[i][2], 2.0)
	b.draw_circle(c, 5.0, Color("3b3d43"))
	_texts(b, TYRES[i][0], TYRES[i][1], 36)


func _draw_stops(b: Button, i: int) -> void:
	var x0 := 8.0
	var w := 60.0
	b.draw_rect(Rect2(x0, 30, w, 3), Color(1, 1, 1, 0.15))
	var pits: Array = [[LAPS / 2], [LAPS / 3, 2 * LAPS / 3]][i]
	for lap: int in pits:
		var x: float = x0 + w * lap / LAPS
		b.draw_rect(Rect2(x - 1, 26, 3, 11), Ui.YELLOW)
	b.draw_string(Ui.font_bold, Vector2(x0, 17), STOPS[i][0], HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_BODY, Ui.INK)
	b.draw_string(Ui.font, Vector2(x0 + w + 8, 33), STOPS[i][1], HORIZONTAL_ALIGNMENT_LEFT, b.size.x - x0 - w - 10, Ui.SIZE_SMALL, Ui.INK_2)


func _on_risk(value: float) -> void:
	_risk = int(value)
	var word := "SAFE" if _risk < 35 else ("PUSH" if _risk > 65 else "BALANCED")
	_risk_label.text = "%d · %s" % [_risk, word]
	_risk_label.add_theme_color_override("font_color", Ui.RED if _risk > 65 else (Color("3ecf6a") if _risk < 35 else Ui.YELLOW))


func _load_driver() -> void:
	var d: Variant = await Api.get_json("/api/driver")
	for c in _driver_box.get_children():
		c.queue_free()
	if not d is Dictionary:
		_driver_box.add_child(Ui.label("Driver unavailable (server offline).", Ui.SIZE_SMALL, Ui.INK_2))
		_lock_button.disabled = true
		return
	_driver_box.add_child(Ui.label("YOUR DRIVER", Ui.SIZE_SMALL, Ui.INK_2, true))
	_driver_box.add_child(Ui.label(String(d["name"]).to_upper(), Ui.SIZE_HEADING, Ui.INK, true))
	_driver_box.add_child(Ui.label("LV %d · %d XP · %d RACES · %d WINS" % [d["level"], d["xp"], d["races"], d["wins"]], Ui.SIZE_SMALL, Ui.INK_2))
	for stat: Array in [["PACE", "pace"], ["RACECRAFT", "racecraft"], ["TYRES", "tyreManagement"]]:
		var row := Ui.hbox(6)
		var name_label := Ui.label(stat[0], Ui.SIZE_SMALL, Ui.INK_2)
		name_label.custom_minimum_size = Vector2(62, 0)
		row.add_child(name_label)
		row.add_child(Ui.stat_bar(int(d[stat[1]])))
		row.add_child(Ui.label(str(int(d[stat[1]])), Ui.SIZE_SMALL, Ui.INK, true))
		_driver_box.add_child(row)
	var chain_link := Ui.button("DRIVER ON SOLANA  >")
	chain_link.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
	chain_link.pressed.connect(Api.open_address.bind(String(d["address"])))
	_driver_box.add_child(chain_link)


func _on_lock() -> void:
	_lock_button.disabled = true
	_lock_button.text = "LOCKING ON SOLANA…"
	_status.text = "Posting the race and your call to Solana devnet."
	var race: Variant = await Api.post_json("/api/races", {
		"trackId": TRACK_ID, "player": Profile.id, "design": _design, "tyre": _tyre, "stops": _stops, "risk": _risk,
	})
	if race is Dictionary and (race as Dictionary).has("raceId"):
		locked.emit(race)
	else:
		_status.text = "Couldn't start the race. Is the server running?"
		_lock_button.disabled = false
		_lock_button.text = "LOCK SETUP"
