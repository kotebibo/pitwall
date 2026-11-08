extends Node
## Player settings (autoload "Settings"): key bindings and game options, saved
## per device to user://settings.cfg (IndexedDB in the web build). Sound levels
## stay with Sfx, which keeps them in user://audio.cfg.
##
##   Settings.keys_text("drive_brake")    # "S / SPACE": the keys bound right now
##   Settings.key_text("drive_restart")   # "R": the first key only, for short hints
##   Settings.rebind("drive_brake", 0, KEY_B)
##
## Any text that names a key gets it from here, so it always matches the bindings.

signal changed

const PATH := "user://settings.cfg"
const MAX_KEYS := 2

## Every rebindable action, in the order the settings screen lists them.
const ACTIONS: Array[String] = [
	"drive_throttle", "drive_brake", "drive_left", "drive_right", "drive_boost", "drive_reverse",
	"drive_restart", "drive_pause", "drive_camera", "race_tyre_soft", "race_tyre_medium", "race_tyre_hard",
]
const LABELS := {
	"drive_throttle": "THROTTLE",
	"drive_brake": "BRAKE",
	"drive_left": "STEER LEFT",
	"drive_right": "STEER RIGHT",
	"drive_boost": "BOOST",
	"drive_reverse": "REVERSE",
	"drive_restart": "RESTART LAP",
	"drive_pause": "PAUSE",
	"drive_camera": "CAMERA",
	"race_tyre_soft": "NEXT TYRE · SOFT",
	"race_tyre_medium": "NEXT TYRE · MEDIUM",
	"race_tyre_hard": "NEXT TYRE · HARD",
}
## Gamepad controls that are axes, not InputMap buttons (read in DriveInput.poll).
const PAD_AXES := {"drive_throttle": "RT", "drive_brake": "LT", "drive_left": "LEFT STICK", "drive_right": "LEFT STICK"}
const PAD_NAMES := {
	JOY_BUTTON_A: "A", JOY_BUTTON_B: "B", JOY_BUTTON_X: "X", JOY_BUTTON_Y: "Y",
	JOY_BUTTON_LEFT_SHOULDER: "LB", JOY_BUTTON_RIGHT_SHOULDER: "RB", JOY_BUTTON_START: "START", JOY_BUTTON_BACK: "BACK",
}
## Names that read better than the engine's ("Escape", "Kp 1"...).
const KEY_NAMES := {
	KEY_ESCAPE: "ESC", KEY_SPACE: "SPACE", KEY_SHIFT: "SHIFT", KEY_CTRL: "CTRL", KEY_ALT: "ALT",
	KEY_ENTER: "ENTER", KEY_KP_ENTER: "NUM ENTER", KEY_BACKSPACE: "BACKSPACE", KEY_TAB: "TAB",
	KEY_UP: "UP", KEY_DOWN: "DOWN", KEY_LEFT: "LEFT", KEY_RIGHT: "RIGHT",
	KEY_PAGEUP: "PAGE UP", KEY_PAGEDOWN: "PAGE DOWN", KEY_CAPSLOCK: "CAPS LOCK",
}

## Show the frames-per-second counter while driving (F3 toggles it too).
var show_fps := false
## Start drives with the north-up camera instead of the chase camera (C toggles it).
var north_up := false
var _names := {}  # physical keycode -> name shown, cached (the HUD asks every frame)


func _ready() -> void:
	# before any screen reads an action: defaults first, then the saved keys over them
	DriveInput.ensure_actions()
	load_settings()


# ---- reading bindings ----

## Physical keycodes bound to an action, in slot order.
func keys(action: String) -> Array[int]:
	var out: Array[int] = []
	if not InputMap.has_action(action):
		return out
	for e in InputMap.action_get_events(action):
		var k := e as InputEventKey
		if k:
			out.append(k.physical_keycode if k.physical_keycode != KEY_NONE else k.keycode)
	return out


## A key's name as printed on the player's keyboard (layout aware where the platform says).
func key_name(code: int) -> String:
	if KEY_NAMES.has(code):
		return KEY_NAMES[code]
	if _names.has(code):
		return _names[code]
	var shown := code as Key
	# only the desktop display servers know the layout (headless and web report an error)
	if DisplayServer.get_name() in ["Windows", "macOS", "X11", "Wayland"]:
		var mapped := DisplayServer.keyboard_get_keycode_from_physical(code as Key)
		if mapped != KEY_NONE:
			shown = mapped
	var name := OS.get_keycode_string(shown).to_upper()
	_names[code] = name if name != "" else "KEY %d" % code
	return _names[code]


## Every key of an action, for text: "S / SPACE". "NOT SET" when it has none.
func keys_text(action: String, separator: String = " / ") -> String:
	var names := PackedStringArray()
	for k in keys(action):
		names.append(key_name(k))
	return separator.join(names) if not names.is_empty() else "NOT SET"


## The first key of an action, for short hints ("R RESTART").
func key_text(action: String) -> String:
	var k := keys(action)
	return key_name(k[0]) if not k.is_empty() else "NOT SET"


## Gamepad controls of an action, read-only: "A / RB", "RT", or "" when it has none.
func pad_text(action: String) -> String:
	var names := PackedStringArray()
	if PAD_AXES.has(action):
		names.append(PAD_AXES[action])
	if InputMap.has_action(action):
		for e in InputMap.action_get_events(action):
			var j := e as InputEventJoypadButton
			if j:
				names.append(PAD_NAMES.get(j.button_index, "BUTTON %d" % j.button_index))
	return " / ".join(names)


## The driving keys in one line, for menus and the pause screen.
func controls_line() -> String:
	return "THROTTLE: %s  ·  BRAKE: %s  ·  STEER: %s / %s  ·  BOOST: %s  ·  REVERSE: %s" % [
		keys_text("drive_throttle"), keys_text("drive_brake"), key_text("drive_left"), key_text("drive_right"),
		keys_text("drive_boost"), keys_text("drive_reverse")]


## The action a key is bound to, or "".
func action_for_key(code: int) -> String:
	for a in ACTIONS:
		if code in keys(a):
			return a
	return ""


# ---- changing bindings ----

## Binds `code` to `slot` (0 or 1) of `action`. A key that belonged to another
## action moves here: returns that action, or "" when nothing moved.
func rebind(action: String, slot: int, code: int) -> String:
	var moved_from := ""
	for other in ACTIONS:
		if other == action:
			continue
		var theirs := keys(other)
		if code in theirs:
			theirs.erase(code)
			_set_keys(other, theirs)
			moved_from = other
	var mine := keys(action)
	var slots: Array[int] = [mine[0] if mine.size() > 0 else KEY_NONE, mine[1] if mine.size() > 1 else KEY_NONE]
	slot = clampi(slot, 0, MAX_KEYS - 1)
	if slots[1 - slot] == code:
		slots[1 - slot] = slots[slot]  # already in the other slot: swap them
	slots[slot] = code
	var result: Array[int] = []
	for k in slots:
		if k != KEY_NONE:
			result.append(k)
	_set_keys(action, result)
	save_settings()
	changed.emit()
	return moved_from


## Empties one slot of an action.
func clear_slot(action: String, slot: int) -> void:
	var mine := keys(action)
	if slot < mine.size():
		mine.remove_at(slot)
		_set_keys(action, mine)
		save_settings()
		changed.emit()


func reset_controls() -> void:
	for a in ACTIONS:
		var d: Array[int] = []
		for k: int in DriveInput.DEFAULT_KEYS.get(a, []):
			d.append(k)
		_set_keys(a, d)
	save_settings()
	changed.emit()


func set_show_fps(on: bool) -> void:
	show_fps = on
	save_settings()
	changed.emit()


func set_north_up(on: bool) -> void:
	north_up = on
	save_settings()
	changed.emit()


## Replaces an action's keyboard keys; its gamepad buttons stay.
func _set_keys(action: String, codes: Array[int]) -> void:
	if not InputMap.has_action(action):
		InputMap.add_action(action)
	for e in InputMap.action_get_events(action):
		if e is InputEventKey:
			InputMap.action_erase_event(action, e)
	for k in codes:
		var e := InputEventKey.new()
		e.physical_keycode = k as Key
		InputMap.action_add_event(action, e)


# ---- saving ----

func save_settings() -> void:
	var cfg := ConfigFile.new()
	for a in ACTIONS:
		cfg.set_value("controls", a, keys(a))
	cfg.set_value("game", "show_fps", show_fps)
	cfg.set_value("game", "north_up", north_up)
	var err := cfg.save(PATH)
	if err != OK:
		push_warning("settings: could not save %s (%s)" % [PATH, error_string(err)])


## Applies user://settings.cfg over the defaults. A missing file, a file that
## doesn't parse, or a bad entry leaves the defaults in place.
func load_settings() -> void:
	var cfg := ConfigFile.new()
	if not FileAccess.file_exists(PATH):
		return
	var err := cfg.load(PATH)
	if err != OK:
		push_warning("settings: %s unreadable (%s), using the defaults" % [PATH, error_string(err)])
		return
	var taken := {}
	for a in ACTIONS:
		var v: Variant = cfg.get_value("controls", a, null)
		if not v is Array:
			continue
		var codes: Array[int] = []
		for k: Variant in v:
			if not (k is int or k is float):
				continue
			var code := int(k)
			# ESC is kept for "back" and cancelling a rebind: only PAUSE may have it
			if code <= 0 or (code == KEY_ESCAPE and a != "drive_pause"):
				continue
			if taken.has(code) or codes.size() >= MAX_KEYS:
				continue
			codes.append(code)
			taken[code] = a
		_set_keys(a, codes)
	# a default key that no saved action claims would now be on two actions: drop it there
	for a in ACTIONS:
		var mine := keys(a)
		var kept: Array[int] = []
		for code in mine:
			if not taken.has(code) or taken[code] == a:
				kept.append(code)
		if kept.size() != mine.size():
			_set_keys(a, kept)
	show_fps = cfg.get_value("game", "show_fps", false) == true
	north_up = cfg.get_value("game", "north_up", false) == true
