extends SceneTree
## Headless check of saved key bindings. Each step is its own process, so
## "load" really reads the file a previous run wrote:
##   godot --headless --path game -s res://scenes/settings/test_settings.gd -- save
##   godot --headless --path game -s res://scenes/settings/test_settings.gd -- load
##   godot --headless --path game -s res://scenes/settings/test_settings.gd -- corrupt
##   godot --headless --path game -s res://scenes/settings/test_settings.gd -- missing
## "save" backs up the player's own settings.cfg; "missing" (run it last) puts it back.

const PATH := "user://settings.cfg"
const BACKUP := "user://settings.cfg.test-backup"

var _ok := true


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var mode := args[0] if args.size() > 0 else "save"
	if mode == "save" or mode == "ui":
		if FileAccess.file_exists(PATH) and not FileAccess.file_exists(BACKUP):
			DirAccess.copy_absolute(ProjectSettings.globalize_path(PATH), ProjectSettings.globalize_path(BACKUP))
		DirAccess.remove_absolute(ProjectSettings.globalize_path(PATH))
	elif mode == "corrupt":
		var f := FileAccess.open(PATH, FileAccess.WRITE)
		f.store_string("[controls\ndrive_brake=[[[ not a value\n}{ garbage")
		f.close()
	elif mode == "missing":
		DirAccess.remove_absolute(ProjectSettings.globalize_path(PATH))
	if mode == "ui":
		_ui.call_deferred()
		return
	_run.call_deferred(mode)


## The screen itself, fed real key events: rebind, move, ESC cancels, ESC closes.
func _ui() -> void:
	var settings := root.get_node("Settings")
	settings.call("reset_controls")
	# loaded at run time: in -s mode the autoloads it uses only exist once the tree runs
	var screen: Control = load("res://scenes/settings/settings_screen.gd").new()
	var closed := [false]
	screen.connect("closed", func() -> void: closed[0] = true)
	root.add_child(screen)
	await process_frame
	screen.call("_start_capture", "drive_brake", 0)
	_press(KEY_B)
	_check(settings.call("keys_text", "drive_brake") == "B / SPACE", "click BRAKE key 1, press B")
	screen.call("_start_capture", "drive_boost", 1)
	_press(KEY_SPACE)
	var status := String((screen.get("_status") as Label).text)
	print("  status: " + status)
	_check(settings.call("keys_text", "drive_boost") == "SHIFT / SPACE" and settings.call("keys_text", "drive_brake") == "B", "SPACE moved from BRAKE to BOOST")
	_check(status.contains("MOVED FROM BRAKE TO BOOST"), "the move is shown")
	screen.call("_start_capture", "drive_brake", 0)
	_press(KEY_ESCAPE)
	_check(settings.call("keys_text", "drive_brake") == "B" and not closed[0], "ESC cancels the rebind, screen stays")
	screen.call("_start_capture", "drive_brake", 0)
	_press(KEY_F3)
	_check(settings.call("keys_text", "drive_brake") == "B", "F3 is refused")
	_press(KEY_ESCAPE)
	_press(KEY_ESCAPE)
	_check(closed[0], "ESC closes the screen")
	settings.call("reset_controls")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(PATH))
	if FileAccess.file_exists(BACKUP):
		DirAccess.rename_absolute(ProjectSettings.globalize_path(BACKUP), ProjectSettings.globalize_path(PATH))
	print("[ui] %s" % ("ALL OK" if _ok else "FAILED"))
	quit(0 if _ok else 1)


func _press(code: Key) -> void:
	for down: bool in [true, false]:
		var e := InputEventKey.new()
		e.physical_keycode = code
		e.keycode = code
		e.pressed = down
		root.push_input(e)


func _run(mode: String) -> void:
	# a fresh Settings, as the autoload builds it at start-up (from no actions at all)
	for a: String in DriveInput.DEFAULT_KEYS:
		if InputMap.has_action(a):
			InputMap.erase_action(a)
	var settings: Node = load("res://autoload/settings.gd").new()
	root.add_child(settings)
	DriveInput.ensure_actions()  # what a drive calls: must not overwrite the saved keys
	var s := settings as Object
	print("[%s] drive_brake events: %s" % [mode, _events("drive_brake")])
	print("[%s] brake text: %s  · boost text: %s  · tyres: %s %s %s" % [mode, s.call("keys_text", "drive_brake"), s.call("keys_text", "drive_boost"),
		s.call("key_text", "race_tyre_soft"), s.call("key_text", "race_tyre_medium"), s.call("key_text", "race_tyre_hard")])
	match mode:
		"save":
			_check(s.call("keys_text", "drive_brake") == "S / SPACE", "defaults with no file")
			var moved: String = s.call("rebind", "drive_brake", 0, KEY_B)
			_check(moved == "", "B was free")
			_check(s.call("keys_text", "drive_brake") == "B / SPACE", "brake slot 0 is B")
			moved = s.call("rebind", "drive_boost", 1, KEY_SPACE)
			_check(moved == "drive_brake", "SPACE moved from brake to boost")
			_check(s.call("keys_text", "drive_brake") == "B", "brake lost SPACE")
			_check(s.call("keys_text", "drive_boost") == "SHIFT / SPACE", "boost got SPACE")
			s.call("rebind", "race_tyre_hard", 0, KEY_H)
			s.call("rebind", "drive_brake", 1, KEY_B)  # already in slot 0: swaps
			_check(s.call("keys_text", "drive_brake") == "B", "same key in both slots stays one key")
			s.call("set_show_fps", true)
			_check(FileAccess.file_exists(PATH), "settings.cfg written")
			print(FileAccess.get_file_as_string(PATH))
		"load":
			_check(s.call("keys_text", "drive_brake") == "B", "brake is B after reload")
			_check(s.call("keys_text", "drive_boost") == "SHIFT / SPACE", "boost kept SPACE after reload")
			_check(s.call("key_text", "race_tyre_hard") == "H", "hard tyre is H after reload")
			_check(s.get("show_fps") == true, "show fps kept")
			# what DriveInput.poll reads in a drive: B brakes now, S doesn't
			_check(_brakes(KEY_B), "pressing B brakes")
			_check(not _brakes(KEY_S), "pressing S doesn't brake any more")
			s.call("reset_controls")
			_check(s.call("keys_text", "drive_brake") == "S / SPACE", "reset to defaults")
		"corrupt", "missing":
			_check(s.call("keys_text", "drive_brake") == "S / SPACE", "defaults when the file is " + mode)
			_check(s.call("keys_text", "drive_boost") == "SHIFT / E", "boost defaults when the file is " + mode)
			_check(_brakes(KEY_S) and _brakes(KEY_SPACE), "S and SPACE brake")
			if mode == "missing" and FileAccess.file_exists(BACKUP):
				DirAccess.rename_absolute(ProjectSettings.globalize_path(BACKUP), ProjectSettings.globalize_path(PATH))
				print("restored the player's own settings.cfg")
	print("[%s] %s" % [mode, "ALL OK" if _ok else "FAILED"])
	quit(0 if _ok else 1)


func _events(action: String) -> String:
	var out := PackedStringArray()
	for e in InputMap.action_get_events(action):
		out.append(e.as_text())
	return ", ".join(out)


func _brakes(code: Key) -> bool:
	var e := InputEventKey.new()
	e.physical_keycode = code
	e.pressed = true
	return e.is_action("drive_brake") and InputMap.event_is_action(e, "drive_brake")


func _check(cond: bool, what: String) -> void:
	print("  %s  %s" % ["ok  " if cond else "FAIL", what])
	if not cond:
		_ok = false
