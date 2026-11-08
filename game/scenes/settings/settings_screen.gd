class_name SettingsScreen
extends Control
## Settings, as an overlay over whatever is on screen (the hub, or a paused
## drive or race, so the session carries on afterwards): CONTROLS (rebind the
## keys, see the gamepad), SOUND (bus levels, mute) and GAME (FPS, camera).
##
## While it is open it takes every key and gamepad button, so nothing reaches
## the screen underneath. ESC goes back (or cancels a rebind).

signal closed

const TABS: Array[String] = ["CONTROLS", "SOUND", "GAME"]
## Keys the screens keep for themselves: never bound to an action.
const RESERVED := {KEY_ESCAPE: "ESC is kept for going back", KEY_F3: "F3 is kept for the FPS counter"}
## Sliders and the bus each one sets.
const BUSES := [["MASTER", "Master"], ["MUSIC", "Music"], ["EFFECTS", "SFX"]]

var tab := 0
var _pages: Array[Control] = []
var _tab_buttons: Array[Button] = []
var _slots := {}  # action -> [Button, Button]
var _capture_action := ""
var _capture_slot := -1
var _status: Label
var _flash_action := ""
var _mute: Button
var _volume_labels := {}  # bus -> Label
var _cam_hint: Label


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	theme = Ui.theme
	process_mode = Node.PROCESS_MODE_ALWAYS
	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.025, 0.03, 0.8)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	var panel := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.075, 0.09, 0.98)
	sb.border_color = Ui.RED
	sb.border_width_top = 3
	sb.set_content_margin_all(10)
	sb.content_margin_left = 14
	sb.content_margin_right = 14
	panel.add_theme_stylebox_override("panel", sb)
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	panel.custom_minimum_size = Vector2(430, 0)
	add_child(panel)
	var box := Ui.vbox(6)
	panel.add_child(box)

	var head := Ui.hbox(4)
	box.add_child(head)
	var title := Ui.label("SETTINGS", Ui.SIZE_HEADING, Ui.INK, true)
	title.custom_minimum_size = Vector2(92, 0)
	head.add_child(title)
	for i in TABS.size():
		var b := Ui.button(TABS[i])
		b.toggle_mode = true
		b.custom_minimum_size = Vector2(70, 0)
		b.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
		_mark_pressed(b)
		b.pressed.connect(show_tab.bind(i))
		head.add_child(b)
		_tab_buttons.append(b)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(spacer)
	var close := Ui.button("DONE", true)
	close.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
	close.custom_minimum_size = Vector2(56, 0)
	close.pressed.connect(_close)
	head.add_child(close)
	var rule := ColorRect.new()
	rule.color = Ui.LINE
	rule.custom_minimum_size = Vector2(0, 1)
	box.add_child(rule)

	_pages.append(_build_controls())
	_pages.append(_build_sound())
	_pages.append(_build_game())
	for p in _pages:
		box.add_child(p)
	# every tab as tall as the tallest, so the panel doesn't jump between tabs
	var tallest := 0.0
	for p in _pages:
		tallest = maxf(tallest, p.get_combined_minimum_size().y)
	for p in _pages:
		p.custom_minimum_size.y = tallest
	show_tab(tab)
	Settings.changed.connect(_refresh_slots)
	Settings.changed.connect(_refresh_cam_hint)


func show_tab(i: int) -> void:
	tab = clampi(i, 0, TABS.size() - 1)
	_cancel_capture()
	for k in _pages.size():
		_pages[k].visible = k == tab
		_tab_buttons[k].set_pressed_no_signal(k == tab)


## A toggle button that reads clearly as selected: red-edged when pressed.
func _mark_pressed(b: Button) -> void:
	var on := _cap(Ui.RED_DARK, Ui.RED)
	on.content_margin_top = 4
	on.content_margin_bottom = 4
	on.content_margin_left = 8
	on.content_margin_right = 8
	b.add_theme_stylebox_override("pressed", on)
	b.add_theme_stylebox_override("hover_pressed", on)


func _close() -> void:
	_cancel_capture()
	Sfx.play("ui_back")
	closed.emit()
	queue_free()


# ---- CONTROLS ----

func _build_controls() -> Control:
	var page := Ui.vbox(1)
	var head := Ui.hbox(4)
	page.add_child(head)
	head.add_child(_cell("ACTION", 112, Ui.INK_3, true))
	head.add_child(_cell("KEY", 82, Ui.INK_3, true))
	head.add_child(_cell("SECOND KEY", 82, Ui.INK_3, true))
	head.add_child(_cell("GAMEPAD", 100, Ui.INK_3, true))
	for action in Settings.ACTIONS:
		var row := Ui.hbox(4)
		page.add_child(row)
		row.add_child(_cell(String(Settings.LABELS[action]), 112, Ui.INK, false))
		var pair: Array[Button] = []
		for slot in Settings.MAX_KEYS:
			var b := _slot_button()
			b.gui_input.connect(_on_slot_input.bind(action, slot))
			b.pressed.connect(_start_capture.bind(action, slot))
			row.add_child(b)
			pair.append(b)
		_slots[action] = pair
		row.add_child(_cell(Settings.pad_text(action) if Settings.pad_text(action) != "" else "-", 100, Ui.INK_3, false))
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0, 3)
	page.add_child(gap)
	_status = Ui.label("", Ui.SIZE_SMALL, Ui.INK_2)
	page.add_child(_status)
	var foot := Ui.hbox(6)
	page.add_child(foot)
	var reset := Ui.button("RESET TO DEFAULTS")
	reset.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
	reset.pressed.connect(func() -> void:
		_cancel_capture()
		Settings.reset_controls()
		_say("ALL KEYS ARE BACK TO THEIR DEFAULTS", Ui.INK))
	foot.add_child(reset)
	var note := Ui.label("GAMEPAD: SHOWN FOR REFERENCE", Ui.SIZE_SMALL, Ui.INK_3)
	note.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	note.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	note.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	foot.add_child(note)
	_refresh_slots()
	_say_help()
	return page


func _cell(text: String, width: float, color: Color, bold: bool) -> Label:
	var l := Ui.label(text, Ui.SIZE_SMALL, color, bold)
	l.custom_minimum_size = Vector2(width, 0)
	l.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	l.clip_text = true
	return l


## A keycap: a small dark button that shows one key.
func _slot_button() -> Button:
	var b := Button.new()
	b.focus_mode = Control.FOCUS_NONE
	b.toggle_mode = true
	b.custom_minimum_size = Vector2(82, 15)
	b.clip_text = true
	b.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
	b.add_theme_font_override("font", Ui.font_bold)
	b.add_theme_stylebox_override("normal", _cap(Color(0.05, 0.055, 0.065), Ui.LINE_STRONG))
	b.add_theme_stylebox_override("hover", _cap(Color(0.11, 0.115, 0.13), Ui.INK_3))
	b.add_theme_stylebox_override("pressed", _cap(Ui.RED_DARK, Ui.RED))
	b.add_theme_stylebox_override("hover_pressed", _cap(Ui.RED_DARK, Ui.RED))
	b.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	return b


func _cap(bg: Color, border: Color) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(1)
	s.border_width_bottom = 2
	s.content_margin_left = 4
	s.content_margin_right = 4
	s.content_margin_top = 1
	s.content_margin_bottom = 1
	s.anti_aliasing = false
	return s


func _refresh_slots() -> void:
	for action: String in _slots:
		var keys := Settings.keys(action)
		var pair: Array = _slots[action]
		for slot in pair.size():
			var b: Button = pair[slot]
			var capturing := action == _capture_action and slot == _capture_slot
			b.set_pressed_no_signal(capturing)
			if capturing:
				b.text = "PRESS A KEY"
				b.add_theme_color_override("font_color", Ui.INK)
			elif slot < keys.size():
				b.text = Settings.key_name(keys[slot])
				b.add_theme_color_override("font_color", Ui.YELLOW if action == _flash_action else Ui.INK)
			else:
				b.text = "-"
				b.add_theme_color_override("font_color", Ui.INK_3)
			b.tooltip_text = "Click, then press the key for %s. Right-click clears it." % String(Settings.LABELS[action])


func _start_capture(action: String, slot: int) -> void:
	_capture_action = action
	_capture_slot = slot
	_flash_action = ""
	_refresh_slots()
	_say("PRESS THE NEW KEY FOR %s  ·  ESC CANCELS" % String(Settings.LABELS[action]), Ui.YELLOW)


func _cancel_capture() -> void:
	if _capture_action == "":
		return
	_capture_action = ""
	_capture_slot = -1
	_refresh_slots()
	_say_help()


func _on_slot_input(event: InputEvent, action: String, slot: int) -> void:
	var mb := event as InputEventMouseButton
	if mb and mb.pressed and mb.button_index == MOUSE_BUTTON_RIGHT:
		_cancel_capture()
		if slot < Settings.keys(action).size():
			Settings.clear_slot(action, slot)
			_say("%s: KEY CLEARED" % String(Settings.LABELS[action]), Ui.INK_2)
		accept_event()


func _say(text: String, color: Color) -> void:
	if _status:
		_status.text = text
		_status.add_theme_color_override("font_color", color)


func _say_help() -> void:
	_say("CLICK A KEY TO CHANGE IT, THEN PRESS THE NEW ONE  ·  RIGHT-CLICK CLEARS IT", Ui.INK_2)


## Every key and gamepad button stops here while the screen is open.
func _input(event: InputEvent) -> void:
	if not is_visible_in_tree():
		return
	var key := event as InputEventKey
	if key:
		get_viewport().set_input_as_handled()
		if not key.pressed or key.echo:
			return
		var code := key.physical_keycode if key.physical_keycode != KEY_NONE else key.keycode
		if _capture_action != "":
			if code == KEY_ESCAPE:
				_cancel_capture()
				Sfx.play("ui_back")
			elif RESERVED.has(code):
				_say(String(RESERVED[code]).to_upper() + "  ·  PICK ANOTHER KEY", Ui.RED)
				Sfx.play("ui_error")
			else:
				_bind(code)
		elif code == KEY_ESCAPE:
			_close()
		return
	var pad := event as InputEventJoypadButton
	if pad:
		get_viewport().set_input_as_handled()
		if pad.pressed and pad.button_index in [JOY_BUTTON_B, JOY_BUTTON_START]:
			if _capture_action != "":
				_cancel_capture()
			else:
				_close()


func _bind(code: int) -> void:
	var action := _capture_action
	var slot := _capture_slot
	_capture_action = ""
	_capture_slot = -1
	var moved := Settings.rebind(action, slot, code)
	var name := Settings.key_name(code)
	if moved != "":
		_flash_action = moved
		_say("%s MOVED FROM %s TO %s" % [name, String(Settings.LABELS[moved]), String(Settings.LABELS[action])], Ui.YELLOW)
	else:
		_flash_action = ""
		_say("%s: %s" % [String(Settings.LABELS[action]), Settings.keys_text(action)], Color("3ecf6a"))
	_refresh_slots()
	Sfx.play("ui_confirm")


# ---- SOUND ----

func _build_sound() -> Control:
	var page := Ui.vbox(8)
	page.add_child(Ui.label("Changes play straight away. Release EFFECTS or MASTER to hear a sample.", Ui.SIZE_SMALL, Ui.INK_2))
	for pair: Array in BUSES:
		var label: String = pair[0]
		var bus: String = pair[1]
		var row := Ui.hbox(8)
		page.add_child(row)
		row.add_child(_cell(label, 70, Ui.INK, true))
		var s := HSlider.new()
		s.min_value = 0.0
		s.max_value = 100.0
		s.step = 5.0
		s.value = roundf(Sfx.get_volume(bus) * 100.0)
		s.custom_minimum_size = Vector2(250, 14)
		s.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		s.focus_mode = Control.FOCUS_NONE
		row.add_child(s)
		var value := _cell("%d%%" % roundi(s.value), 40, Ui.INK_2, true)
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		row.add_child(value)
		_volume_labels[bus] = value
		s.value_changed.connect(func(v: float) -> void:
			Sfx.set_volume(bus, v / 100.0)
			value.text = "%d%%" % roundi(v))
		s.drag_ended.connect(func(_changed: bool) -> void:
			if bus != "Music":
				Sfx.play("sector_green"))
	_mute = Ui.button("")
	_mute.toggle_mode = true
	_mute.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
	_mute.custom_minimum_size = Vector2(160, 20)
	_mute.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	_mute.button_pressed = Sfx.is_muted()
	_mark_pressed(_mute)
	_mute.toggled.connect(func(on: bool) -> void:
		Sfx.set_muted(on)
		_refresh_mute())
	page.add_child(_mute)
	_refresh_mute()
	return page


func _refresh_mute() -> void:
	_mute.text = "SOUND MUTED  ·  CLICK TO UNMUTE" if Sfx.is_muted() else "MUTE ALL SOUND"
	var tex := PartCard.texture("res://assets/sprites/ui/%s.png" % ("icon_mute" if Sfx.is_muted() else "icon_sound"))
	if tex:
		_mute.icon = tex


# ---- GAME ----

func _build_game() -> Control:
	var page := Ui.vbox(6)
	page.add_child(Ui.label("CAMERA AT THE START OF A DRIVE", Ui.SIZE_SMALL, Ui.INK_2, true))
	var cams: Array[String] = ["CHASE", "NORTH UP"]
	var cam := Ui.choice_row(cams, 1 if Settings.north_up else 0, func(i: int) -> void: Settings.set_north_up(i == 1))
	cam.custom_minimum_size = Vector2(240, 0)
	cam.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	for b in cam.get_children():
		_mark_pressed(b as Button)
	page.add_child(cam)
	_cam_hint = Ui.label("", Ui.SIZE_SMALL, Ui.INK_3)
	page.add_child(_cam_hint)
	page.add_child(Ui.label("FPS COUNTER WHILE DRIVING", Ui.SIZE_SMALL, Ui.INK_2, true))
	var fps_options: Array[String] = ["HIDDEN", "SHOWN"]
	var fps := Ui.choice_row(fps_options, 1 if Settings.show_fps else 0, func(i: int) -> void: Settings.set_show_fps(i == 1))
	fps.custom_minimum_size = Vector2(240, 0)
	fps.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	for b in fps.get_children():
		_mark_pressed(b as Button)
	page.add_child(fps)
	page.add_child(Ui.label("F3 shows or hides it while you drive.", Ui.SIZE_SMALL, Ui.INK_3))
	_refresh_cam_hint()
	return page


func _refresh_cam_hint() -> void:
	_cam_hint.text = "%s switches the camera while you drive." % Settings.keys_text("drive_camera", " or ")
