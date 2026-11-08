class_name RaceScreen
extends Control
## A driven race against the AI field: pick a start tyre, watch the grid while
## the five lights come on, race five laps with a real pit stop, then the server
## re-drives the race from your inputs and settles it on Solana.

signal exited

const COMPOUNDS := ["SOFT", "MEDIUM", "HARD"]
const COMPOUND_COLORS := [Color("e8352b"), Color("f2c230"), Color("f1efea")]

var setup := {}
var stats := {}
var car_spec := {}
var car_parts := {}

var _info: Dictionary = {}
var _race: RaceSim
var _track: TrackData
var _view: SubViewport
var _world: Node2D
var _render: TrackRender
var _cars: Array[CarView] = []
var _camera: Camera2D
var _hud: DriveHud
var _layer: CanvasLayer
var _input := DriveInput.new()
var _audio: CarAudio
var _autopilot: AiDriver
var _state := "choose"
var _prev := PackedVector3Array()
var _cur := PackedVector3Array()
var _cam_rot := 0.0
var _cam_zoom := 3.0
var _intro_t := 0.0
var _next_tyre := 1
var _start_tyre := 0
var _names: Array = []
var _colors: Array[Color] = []
var _overlay: Control
var _pit_timer := 0.0
var _crew: Node2D
var _last_pos := 0
var _esc_at := -10.0
var _ui: Control
var _ambience: AudioStreamPlayer  # grid and crowd loops
var _limiter: AudioStreamPlayer  # pit-limiter engine stutter
var _limiter_on := false
var _contact_at := 0.0
var _lollipop: Array = []
var _crew_t := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	DriveInput.ensure_actions()
	_track = TrackData.load_id("mtkvari")
	_build_world()
	if "--autopilot" in Api.args:
		_autopilot = AiDriver.new(_track, 955)
		_autopilot.pit_lap = 2  # in at the end of lap 2
	_choose_tyre()


# ---- world ----

func _build_world() -> void:
	_view = SubViewport.new()
	_view.disable_3d = true
	_view.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_LINEAR
	add_child(_view)
	var rect := TextureRect.new()
	rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	rect.texture = _view.get_texture()
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.stretch_mode = TextureRect.STRETCH_SCALE
	rect.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(rect)
	get_window().size_changed.connect(_resize)
	_resize()
	_world = Node2D.new()
	_view.add_child(_world)
	_render = TrackRender.new()
	_world.add_child(_render)
	_render.setup(_track)
	_crew = Node2D.new()
	_crew.z_index = 7
	_crew.visible = false
	_world.add_child(_crew)
	_camera = Camera2D.new()
	_camera.ignore_rotation = false
	_world.add_child(_camera)
	_camera.make_current()
	_camera.position = _render.points[0]
	_audio = CarAudio.new()
	add_child(_audio)
	_ambience = _loop_player()
	_limiter = _loop_player()
	Sfx.stop_music()
	_layer = CanvasLayer.new()
	add_child(_layer)
	# a CanvasLayer breaks theme inheritance: give its root the game theme
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.theme = Ui.theme
	_layer.add_child(root)
	_ui = root
	_hud = DriveHud.new()
	_hud.race_mode = true
	_hud.title = "RACE · MTKVARI CIRCUIT"
	_ui.add_child(_hud)
	_hud.set_track(_render.points)


## A dedicated looping player (the Sfx pool is for one-shots).
func _loop_player() -> AudioStreamPlayer:
	var pl := AudioStreamPlayer.new()
	pl.bus = "SFX"
	add_child(pl)
	return pl


func _loop(pl: AudioStreamPlayer, sound: String, db_offset: float = 0.0) -> void:
	var st := Sfx.stream(sound)
	if st == null:
		return
	pl.stream = Sfx.make_looping(st)
	pl.volume_db = float(Sfx.GAIN_DB.get(sound, 0.0)) + db_offset
	pl.play()


func _resize() -> void:
	var win := get_window().size
	var px := DriveScreen.pixel_scale(win.y)
	_view.size = Vector2i(ceili(win.x / float(px)), ceili(win.y / float(px)))


# ---- before the start ----

func _glass_panel(accent: Color = Ui.RED) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.075, 0.09, 0.94)
	sb.border_color = accent
	sb.border_width_top = 3
	sb.set_content_margin_all(12)
	p.add_theme_stylebox_override("panel", sb)
	return p


func _choose_tyre() -> void:
	_overlay = ColorRect.new()
	(_overlay as ColorRect).color = Color(0.03, 0.035, 0.045, 0.7)
	_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_ui.add_child(_overlay)
	var panel := _glass_panel()
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(330, 0)
	panel.position = Vector2(-165, -90)
	_overlay.add_child(panel)
	var v := Ui.vbox(6)
	panel.add_child(v)
	v.add_child(Ui.label("RACE · 5 LAPS", Ui.SIZE_TITLE, Ui.INK, true))
	var you: Dictionary = Profile.event.get("you", {})
	var grid := int(you.get("position", 0)) if you.get("position") != null else 0
	v.add_child(Ui.label(("YOU START P%d FROM QUALIFYING" % grid) if grid > 0 else "SET A QUALIFYING TIME TO MOVE UP THE GRID", Ui.SIZE_SMALL, Ui.YELLOW, true))
	var rules := Ui.label("You must use two tyre compounds: pit once. Drive into the pit lane on the left of the main straight, stop in your red box, and your crew changes the tyres.", Ui.SIZE_SMALL, Ui.INK_2)
	rules.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	rules.custom_minimum_size = Vector2(306, 0)
	v.add_child(rules)
	v.add_child(Ui.label("STARTING TYRE", Ui.SIZE_SMALL, Ui.INK_2, true))
	var row := Ui.hbox(5)
	v.add_child(row)
	var hints := ["Fast, wears out", "All-rounder", "Lasts, slower"]
	var group := ButtonGroup.new()
	for k in 3:
		var b := Button.new()
		b.toggle_mode = true
		b.button_group = group
		b.button_pressed = k == 0
		b.focus_mode = Control.FOCUS_NONE
		b.custom_minimum_size = Vector2(96, 42)
		b.draw.connect(func() -> void:
			var c := Vector2(16, 21)
			b.draw_circle(c, 11.0, Color("111214"))
			b.draw_arc(c, 8.0, 0, TAU, 32, COMPOUND_COLORS[k], 2.0)
			b.draw_circle(c, 4.0, Color("3b3d43"))
			b.draw_string(Ui.font_bold, Vector2(32, 18), COMPOUNDS[k], HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_BODY, Ui.INK)
			b.draw_string(Ui.font, Vector2(32, 31), hints[k], HORIZONTAL_ALIGNMENT_LEFT, 62, 6, Ui.INK_2))
		b.pressed.connect(func() -> void: _start_tyre = k)
		row.add_child(b)
	var buttons := Ui.hbox(6)
	v.add_child(buttons)
	var back := Ui.button("BACK")
	back.pressed.connect(func() -> void: exited.emit())
	buttons.add_child(back)
	var go := Ui.button("TO THE GRID  >", true)
	go.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	go.custom_minimum_size = Vector2(0, 26)
	go.pressed.connect(func() -> void:
		go.disabled = true
		go.text = "SETTING UP THE RACE ON SOLANA…"
		_start())
	buttons.add_child(go)
	if _autopilot:
		await get_tree().create_timer(0.5).timeout
		go.pressed.emit()


func _start() -> void:
	var res: Variant = null
	if not "--offline" in Api.args:
		res = await Api.post_json("/api/drivenraces", {"player": Profile.id, "compound": _start_tyre})
	if res is Dictionary and (res as Dictionary).has("entries"):
		_info = res
		Api.track("race_start", "start tyre %d" % _start_tyre)
	else:
		_info = _offline_race()
		_hud.flash("OFFLINE RACE: NOT VERIFIED", Ui.YELLOW, 4.0)
	var seed := PackedByteArray()
	var hex := String(_info.get("seed", ""))
	for i in range(0, hex.length() - 1, 2):
		seed.append(hex.substr(i, 2).hex_to_int())
	var grid: Array = []
	for g: Variant in _info.get("grid", [0, 1, 2, 3, 4, 5]):
		grid.append(int(g))
	_race = RaceSim.new(_track, _info["entries"], seed, grid, int(_info.get("laps", 5)))
	_names = _info.get("names", [])
	_colors.clear()
	for c: Variant in _info.get("colors", []):
		_colors.append(Color(String(c)))
	while _colors.size() < _race.cars.size():
		_colors.append(Ui.TEAM_COLORS[_colors.size() % Ui.TEAM_COLORS.size()])
	_next_tyre = _race.next_compound[0]
	for i in _race.cars.size():
		var v := CarView.new()
		v.body = _colors[i]
		if i == 0 and not car_parts.is_empty():
			v.parts = car_parts
		v.z_index = 6 if i == 0 else 5
		_world.add_child(v)
		_cars.append(v)
		var c := _race.cars[i]
		_prev.append(Vector3(c.px / 65536.0, c.py / 65536.0, c.heading / 65536.0))
	_cur = _prev.duplicate()
	_overlay.queue_free()
	_overlay = null
	_state = "intro"
	_intro_t = 0.0
	_loop(_ambience, "grid_ambience")


## Without the server: the same race, deterministic, just not verified.
func _offline_race() -> Dictionary:
	var entries := [{"setup": setup, "stats": stats, "car": car_spec, "crew": 70, "compound": _start_tyre}]
	var paces := [962, 956, 950, 944, 938]
	for k in 5:
		entries.append({"setup": {}, "stats": {"braking": 70, "cornering": 70, "traction": 65, "energy": 65}, "car": {},
			"pace": paces[k], "crew": 50 + k * 8, "compound": k % 2, "pit_lap": 2 + k % 2, "pit_compound": 1 - k % 2})
	return {"entries": entries, "grid": [1, 2, 0, 3, 4, 5], "laps": 5, "seed": "4f2a9c",
		"names": ["You", "Kutaisi GP", "Batumi", "Rustavi", "Gori", "Mtskheta"]}


# ---- simulation ----

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and (event as InputEventKey).pressed:
		match (event as InputEventKey).physical_keycode:
			KEY_1: _next_tyre = 0
			KEY_2: _next_tyre = 1
			KEY_3: _next_tyre = 2
			KEY_ESCAPE:
				var now := Time.get_ticks_msec() / 1000.0
				if now - _esc_at < 2.0 or _state in ["choose", "results"]:
					exited.emit()
				else:
					_esc_at = now
					_hud.flash("PRESS ESC AGAIN TO RETIRE", Ui.YELLOW, 2.0)


func _physics_process(_delta: float) -> void:
	if _race == null or not (_state in ["lights", "racing", "pit", "cooldown", "results"]):
		return
	if _state == "results" and _race.finished():
		return  # the field is home: the input log is complete
	var car := _race.cars[0]
	var cmd: Array[int]
	if _autopilot:
		cmd = _autopilot_cmd()
	else:
		_input.poll(car)
		cmd = [_input.steer, _input.throttle, _input.brake, _input.buttons()]
	if _state in ["cooldown", "results"]:
		# after the flag: a slow in-lap along the racing line, out of everyone's way
		var d := _autopilot if _autopilot else AiDriver.new(_track, 600)
		if not _autopilot:
			_autopilot = d
			_autopilot.pitted = true
		cmd = d.drive(car, 0, 25 * 65536, 0)
		cmd[3] = 0
	for i in _race.cars.size():
		var c := _race.cars[i]
		_prev[i] = _cur[i]
	_race.step(cmd[0], cmd[1], cmd[2], cmd[3] | ((_next_tyre + 1) << 2))
	for i in _race.cars.size():
		var c := _race.cars[i]
		_cur[i] = Vector3(c.px / 65536.0, c.py / 65536.0, c.heading / 65536.0)
	_events()


func _autopilot_cmd() -> Array[int]:
	var car := _race.cars[0]
	var lane := 0
	var limit := 0
	var entering := car.in_pit_lane or car.idx >= _track.pit_in  # never across the pit exit
	if not _autopilot.pitted and _race.crossings[0] >= _autopilot.pit_lap and _track.in_pit_zone(car.idx) and entering:
		lane = _track.pit_center
		limit = mini(RaceSim.PIT_LIMIT, _race.box_approach_speed(0))
	return _autopilot.drive(car, lane, limit, _race._blocked_side(0))


func _events() -> void:
	for e: Dictionary in _race.events:
		match String(e["type"]):
			"light":
				Sfx.play("start_light")
			"go":
				_state = "racing"
				Sfx.play("start_go")
				_loop(_ambience, "crowd_loop", -6.0)
				_hud.flash("LIGHTS OUT AND AWAY WE GO", Ui.INK, 2.0)
			"pit_in":
				if int(e["car"]) == 0:
					_state = "pit"
					_pit_timer = float(e["ticks"]) / 120.0
					_show_crew(true)
					_pit_sounds(float(e["ticks"]) / 120.0)
					if e["fumble"]:
						_hud.flash("STUCK WHEEL NUT!", Ui.RED, 2.0)
			"pit_out":
				if int(e["car"]) == 0:
					_state = "racing"
					_show_crew(false)
					Sfx.play("jack_down")
					Sfx.play("pit_release", -8.0)
					_hud.flash("GO GO GO · %s TYRES" % COMPOUNDS[int(e["compound"])], Color("3ecf6a"), 2.0)
					if _autopilot:
						_autopilot.pitted = true
			"lap":
				if int(e["car"]) == 0:
					var lap: int = e["lap"]
					if lap == _race.laps:
						_hud.flash("FINAL LAP", Ui.YELLOW, 2.0)
						Sfx.play("last_lap")
			"finish":
				if int(e["car"]) == 0:
					_state = "cooldown"
					Sfx.play("chequered")
					var pos := _race.order().find(0) + 1
					_hud.flash("CHEQUERED FLAG · P%d" % pos, DriveHud.PURPLE if pos == 1 else Ui.INK, 4.0)
					_finish_later()
			"contact":
				var now := Time.get_ticks_msec() / 1000.0
				if (int(e["a"]) == 0 or int(e["b"]) == 0) and now - _contact_at > 0.25:
					_contact_at = now
					Sfx.play_varied("car_contact", clampf(float(e["speed"]) / 65536.0 - 6.0, -8.0, 2.0))


func _finish_later() -> void:
	await get_tree().create_timer(4.0).timeout
	if is_inside_tree():
		_results()


# ---- drawing ----

func _process(delta: float) -> void:
	if _race == null:
		return
	var f := Engine.get_physics_interpolation_fraction()
	for i in _cars.size():
		var a := _prev[i]
		var b := _cur[i]
		var v := _cars[i]
		v.position = Vector2(lerpf(a.x, b.x, f), lerpf(a.y, b.y, f))
		v.rotation = lerp_angle(a.z, b.z, f)
		var c := _race.cars[i]
		v.steer = c.steer_angle / 65536.0
		v.straight_mode = c.straight_mode
		v.boosting = c.boosting
		v.braking = c.speed > 3 * 65536 and c.accel_long < -6 * 65536
	var me := _race.cars[0]
	var pos := _cars[0].position
	var heading := _cars[0].rotation
	var speed := me.speed / 65536.0

	match _state:
		"intro":
			# fly along the grid from the back to the front
			_intro_t += delta
			var t := clampf(_intro_t / 3.5, 0.0, 1.0)
			var back := _render.points[(_track.size() - 30) % _track.size()]
			var front := _render.points[2]
			var p := back.lerp(front, smoothstep(0.0, 1.0, t))
			_camera.position = p
			_camera.rotation = lerp_angle(_camera.rotation, Vector2(_track.dir_x[0], _track.dir_y[0]).angle() + PI / 2, 1.0 - exp(-3.0 * delta))
			_cam_zoom = lerpf(_cam_zoom, _view.size.y / 60.0, 1.0 - exp(-2.0 * delta))
			_camera.zoom = Vector2.ONE * _cam_zoom
			_hud.lights = -1
			if t >= 1.0:
				_state = "lights"
				_cam_rot = _camera.rotation
		"pit":
			_pit_timer = maxf(_pit_timer - delta, 0.0)
			_cam_zoom = lerpf(_cam_zoom, _view.size.y / 26.0, 1.0 - exp(-4.0 * delta))
			_camera.zoom = Vector2.ONE * _cam_zoom
			_camera.position = _camera.position.lerp(pos, 1.0 - exp(-6.0 * delta))
			_hud.pit_text = "PIT STOP  %.1f s" % _pit_timer
			_animate_crew(delta)
		_:
			var visible_m := lerpf(80.0, 150.0, clampf(speed / 85.0, 0.0, 1.0))
			if _state == "lights":
				visible_m = 70.0
			_cam_zoom = lerpf(_cam_zoom, _view.size.y / visible_m, 1.0 - exp(-2.0 * delta))
			_camera.zoom = Vector2.ONE * _cam_zoom
			var travel := heading if speed < 6.0 else Vector2(me.vx, me.vy).angle()
			_cam_rot = lerp_angle(_cam_rot, travel + PI / 2, 1.0 - exp(-3.2 * delta))
			_camera.rotation = _cam_rot
			var view_h := _view.size.y / _cam_zoom
			_camera.position = pos + Vector2.from_angle(_cam_rot - PI / 2) * view_h * (0.26 if _state != "lights" else 0.1)

	_update_hud(me, speed, delta)


func _update_hud(me: CarSim, speed: float, delta: float) -> void:
	_hud.lights = _race.lights_on() if _state in ["lights", "intro"] and not _race.started() else -1
	if _state == "intro":
		_hud.lights = 0
	_hud.speed_kmh = roundi(speed * 3.6)
	_hud.throttle = _input.throttle
	_hud.brake = _input.brake
	_hud.battery = me.battery / float(CarSim.BATTERY_MAX)
	_hud.boosting = me.boosting
	_hud.straight_mode = me.straight_mode
	_hud.straight_zone = (_track.flags[me.idx] & TrackData.FLAG_STRAIGHT_MODE) != 0
	_hud.tyre_compound = me.compound
	_hud.tyre_wear = me.wear / 1000000.0
	_hud.next_tyre = _next_tyre
	_hud.race_lap = _race.crossings[0]
	_hud.race_laps = _race.laps
	_hud.map_car = _cars[0].position
	var others := []
	for i in range(1, _cars.size()):
		others.append({"p": _cars[i].position, "c": _colors[i]})
	_hud.map_others = others
	# positions tower, gaps from distance to the car ahead
	var order := _race.order()
	var rows := []
	for k in order.size():
		var i: int = order[k]
		var gap := ""
		if k > 0:
			if _race.finish_fp[i] >= 0 and _race.finish_fp[order[0]] >= 0:
				gap = "+%.1f" % ((_race.race_us(i) - _race.race_us(order[0])) / 1000000.0)
			else:
				var metres := (_race.progress[order[k - 1]] - _race.progress[i]) * 4.0
				gap = "+%.1f" % (metres / maxf(_race.cars[i].speed / 65536.0, 20.0))
		rows.append({"pos": k + 1, "name": _short(i), "gap": gap, "color": _colors[i], "you": i == 0, "pit": _race.pit_state[i] == RaceSim.Pit.STOPPED})
	_hud.race_rows = rows
	var my_pos := order.find(0) + 1
	if _race.started() and _last_pos != 0 and my_pos != _last_pos and _state == "racing":
		Sfx.play("overtake" if my_pos < _last_pos else "position_lost")
	_last_pos = my_pos
	# pit instructions
	if _state == "pit":
		pass
	elif _race.pit_stops[0] == 0 and _race.started():
		var laps_left := _race.laps - _race.crossings[0] + 1
		var in_zone := _track.in_pit_zone(me.idx)
		if me.in_pit_lane and in_zone:
			_hud.pit_text = "PIT LANE · STOP IN THE RED BOX · NEXT TYRE"
		elif laps_left <= 2 or me.wear > 550000:
			_hud.pit_text = "BOX THIS LAP · KEEP LEFT ON THE MAIN STRAIGHT"
		else:
			_hud.pit_text = ""
	else:
		_hud.pit_text = ""
	_hud.device = "GAMEPAD" if _input.using_gamepad else "KEYBOARD"
	var slip := 1.0 if me.front_locked or me.rear_sliding else 0.0
	var surface := 0 if me.surface == CarSim.Surface.ASPHALT else (1 if me.surface == CarSim.Surface.KERB else 2)
	var running := _state in ["racing", "cooldown"]
	_audio.update(speed, _input.throttle / 255.0 if running else (0.15 if _state == "lights" else 0.0), _input.brake / 255.0, slip, me.front_locked, surface, me.boosting, me.straight_mode, delta)
	var limited := me.in_pit_lane and _track.in_pit_zone(me.idx) and me.lateral < -_track.pit_inner and _state == "racing"
	if limited != _limiter_on:
		_limiter_on = limited
		_audio.set_ghost(limited)
		if limited:
			Sfx.play("pit_limiter_on")
			_loop(_limiter, "pit_limiter", -5.0)
		else:
			_limiter.stop()
	if _state == "pit":
		_limiter.stop()
	_hud.rpm = _audio.rpm if running else 4000.0
	_hud.gear = _audio.gear


func _short(i: int) -> String:
	if i == 0:
		return "YOU"
	var n := String(_names[i]) if i < _names.size() else "CAR %d" % i
	return n.get_slice(" ", 0)


# ---- pit crew cutscene ----

func _show_crew(on: bool) -> void:
	_crew.visible = on
	for c in _crew.get_children():
		c.queue_free()
	_lollipop = []
	if not on:
		return
	var car := _cars[0]
	_crew.position = car.position
	_crew.rotation = car.rotation
	var sc := CarView.M_PER_PX * CarView.VISUAL_SCALE
	_crew.scale = Vector2(sc, sc)
	var path := "res://assets/sprites/race/crew.json"
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
	if not data is Dictionary:
		return
	var sprites: Dictionary = data["sprites"]
	var k := 0
	for c: Dictionary in data["pit_stop_layout"]["crew"]:
		var base: String = c["sprite"]
		var name := base
		if base == "crew_tyre_gunner" or base == "crew_tyre_carrier":
			name = base + ("_a" if k % 2 == 0 else "_b")
		elif base == "crew_lollipop":
			name = "crew_lollipop_stop"
		k += 1
		var info: Dictionary = sprites.get(name, {})
		var size: Array = info.get("size", [16, 16])
		var anchor: Array = (info.get("anchors", {}) as Dictionary).get(String(c["anchor"]), [0, 0])
		var flip: bool = c.get("flip_v", false)
		var ay: float = (float(size[1]) - float(anchor[1])) if flip else float(anchor[1])
		var origin := Vector2(float(c["at"][0]) - float(anchor[0]), float(c["at"][1]) - ay)
		var group := Node2D.new()
		group.position = origin
		group.z_index = -2 if c.get("layer", "") == "under_car" else 0
		_crew.add_child(group)
		var layers: Array[String] = [name + "_paint"]
		if base == "crew_tyre_carrier":
			layers.append("tyre_held_" + ["soft", "medium", "hard"][_next_tyre])
		layers.append(name + "_detail")
		for layer: String in layers:
			var tex := PartCard.texture("res://assets/sprites/race/%s.png" % layer)
			if tex == null:
				continue
			var sp := Sprite2D.new()
			sp.texture = tex
			sp.centered = false
			sp.flip_v = flip
			if layer.begins_with("tyre_held"):
				var wc: Array = (info.get("anchors", {}) as Dictionary).get("wheel_center", [8, 13])
				var wy: float = (float(size[1]) - float(wc[1])) if flip else float(wc[1])
				sp.centered = true
				sp.position = Vector2(float(wc[0]), wy)
			elif layer.ends_with("_paint"):
				sp.modulate = _colors[0]
			group.add_child(sp)
		if base == "crew_lollipop":
			_lollipop = [group, name]


func _lollipop_go() -> void:
	if _lollipop.is_empty():
		return
	var group: Node2D = _lollipop[0]
	for c in group.get_children():
		var sp := c as Sprite2D
		if sp and sp.texture:
			sp.texture = PartCard.texture(sp.texture.resource_path.replace("_stop_", "_go_"))


## Jack up, four wheel guns a moment apart, new tyres on, guns again, jack down.
func _pit_sounds(stop_s: float) -> void:
	Sfx.play("pit_radio")
	Sfx.play("jack_up")
	var tree := get_tree()
	await tree.create_timer(0.25).timeout
	for k in 4:
		if not is_inside_tree() or _state != "pit":
			return
		Sfx.play_varied("wheel_gun", 0.0 if k == 0 else -3.0)
		await tree.create_timer(0.03 + 0.02 * k).timeout
	await tree.create_timer(maxf(stop_s - 1.2, 0.3)).timeout
	if not is_inside_tree() or _state != "pit":
		return
	Sfx.play("tyre_drop")
	for k in 4:
		Sfx.play_varied("wheel_gun", 0.0 if k == 0 else -3.0)
		await tree.create_timer(0.04 + 0.02 * k).timeout


func _animate_crew(delta: float) -> void:
	# alternate a/b frames, neighbours out of step, so the crew look busy
	_crew_t += delta
	var phase := int(_crew_t * 6.0)
	for g in _crew.get_children():
		var frame := "_a_" if (phase + g.get_index()) % 2 == 0 else "_b_"
		for c in g.get_children():
			var sp := c as Sprite2D
			if sp == null or sp.texture == null:
				continue
			var path := sp.texture.resource_path
			if path.contains("_a_") or path.contains("_b_"):
				var want := path.replace("_a_", frame).replace("_b_", frame)
				if want != path:
					sp.texture = PartCard.texture(want)
	if _pit_timer < 0.35:
		_lollipop_go()


# ---- results ----

func _results() -> void:
	_state = "results"
	var order := _race.order()
	var pos := order.find(0) + 1
	_overlay = ColorRect.new()
	(_overlay as ColorRect).color = Color(0.03, 0.035, 0.045, 0.82)
	_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_ui.add_child(_overlay)
	if pos <= 3:
		_podium(pos)
	var panel := _glass_panel(DriveHud.PURPLE if pos == 1 else Ui.RED)
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_RIGHT)
	panel.position = Vector2(-300, -150)
	panel.custom_minimum_size = Vector2(280, 0)
	_overlay.add_child(panel)
	var v := Ui.vbox(3)
	panel.add_child(v)
	v.add_child(Ui.label("P%d" % pos, 48, DriveHud.PURPLE if pos == 1 else Ui.INK, true))
	v.add_child(Ui.label("RACE RESULT · MTKVARI", Ui.SIZE_SMALL, Ui.INK_2, true))
	for k in order.size():
		var i: int = order[k]
		var row := Ui.hbox(6)
		var sw := ColorRect.new()
		sw.color = _colors[i]
		sw.custom_minimum_size = Vector2(3, 10)
		row.add_child(sw)
		var name := Ui.label("%d  %s" % [k + 1, "YOU" if i == 0 else String(_names[i] if i < _names.size() else "")], Ui.SIZE_SMALL, Ui.RED if i == 0 else Ui.INK, i == 0)
		name.custom_minimum_size = Vector2(150, 0)
		row.add_child(name)
		var us := _race.race_us(i)
		var t := Ui.format_time(us / 1000) if k == 0 and us > 0 else ("+%.3f" % ((us - _race.race_us(order[0])) / 1000000.0) if us > 0 else "RUNNING")
		if _race.penalty_s[i] > 0:
			t += " (+%ds)" % _race.penalty_s[i]
		row.add_child(Ui.label(t, Ui.SIZE_SMALL, Ui.INK_2))
		v.add_child(row)
	var status := Ui.label("Waiting for the rest of the field to finish…", Ui.SIZE_SMALL, Ui.YELLOW)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(status)
	var links := Ui.hbox(4)
	v.add_child(links)
	var done := Ui.button("BACK TO WEEKEND", true)
	done.pressed.connect(func() -> void: exited.emit())
	v.add_child(done)
	if _info.has("raceId"):
		while not _race.finished():
			await get_tree().create_timer(0.25).timeout
			if not is_inside_tree():
				return
		status.text = "Sending your race to be re-driven and settled on Solana…"
		var res: Variant = null
		for attempt in 3:
			res = await Api.post_json("/api/drivenraces/%s/finish" % str(_info["raceId"]), {"inputs": _race.encoded_inputs()})
			if not is_inside_tree():
				return
			if res is Dictionary:
				break
			await get_tree().create_timer(2.0).timeout
		if res is Dictionary and bool((res as Dictionary).get("verified", false)):
			var r: Dictionary = res
			# JSON numbers arrive as floats, and Array.find(0) never matches 0.0
			var server_pos := 0
			var server_order: Array = r.get("order", [])
			for k in server_order.size():
				if int(server_order[k]) == 0:
					server_pos = k + 1
			status.text = "VERIFIED: the server re-drove your race and got P%d. Settled on Solana%s." % [server_pos, ", development pack earned" if not (r.get("packsEarned", []) as Array).is_empty() else ""]
			status.add_theme_color_override("font_color", Color("3ecf6a"))
			Sfx.play("verified")
			var txs: Dictionary = r.get("txs", {})
			for key: String in ["result", "settle"]:
				if txs.get(key) is String:
					var b := Ui.button(key.to_upper() + " TX  >")
					b.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
					var sig: String = txs[key]
					b.pressed.connect(func() -> void: Api.open_tx(sig))
					links.add_child(b)
		else:
			status.text = "Could not verify: " + (Api.last_error if Api.last_error != "" else "server offline")
			status.add_theme_color_override("font_color", Ui.RED)
	else:
		status.text = "Offline race: not verified."


func _podium(pos: int) -> void:
	Sfx.play("podium_music")
	Sfx.play("crowd_cheer")
	var stage := Control.new()
	stage.set_anchors_and_offsets_preset(Control.PRESET_CENTER_LEFT)
	stage.position = Vector2(30, -110)
	stage.custom_minimum_size = Vector2(260, 220)
	_overlay.add_child(stage)
	var podium_tex := PartCard.texture("res://assets/sprites/race/podium.png")
	var base_y := 170.0
	if podium_tex:
		var p := TextureRect.new()
		p.texture = podium_tex
		p.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		p.position = Vector2(30, base_y - podium_tex.get_height())
		p.size = podium_tex.get_size()
		stage.add_child(p)
	else:
		for k in 3:
			var h: float = [60.0, 44.0, 32.0][k]
			var x: float = [90.0, 30.0, 150.0][k]
			var r := ColorRect.new()
			r.color = Color(0.16, 0.17, 0.2)
			r.position = Vector2(x, base_y - h)
			r.size = Vector2(60, h)
			stage.add_child(r)
			var l := Ui.label(str(k + 1), Ui.SIZE_TITLE, Ui.INK, true)
			l.position = Vector2(x + 22, base_y - h + 6)
			stage.add_child(l)
	var trophy := PartCard.texture("res://assets/sprites/race/trophy.png")
	if trophy:
		var t := TextureRect.new()
		t.texture = trophy
		t.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		t.size = trophy.get_size() * 1.5
		t.position = Vector2([110.0, 50.0, 170.0][pos - 1], base_y - [60.0, 44.0, 32.0][pos - 1] - 52)
		stage.add_child(t)
		var bob := create_tween().set_loops()
		bob.tween_property(t, "position:y", t.position.y - 6, 0.5).set_trans(Tween.TRANS_SINE)
		bob.tween_property(t, "position:y", t.position.y, 0.5).set_trans(Tween.TRANS_SINE)
	var confetti := CPUParticles2D.new()
	confetti.position = Vector2(130, -20)
	confetti.amount = 120
	confetti.lifetime = 3.0
	confetti.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
	confetti.emission_rect_extents = Vector2(140, 4)
	confetti.direction = Vector2(0, 1)
	confetti.spread = 20.0
	confetti.gravity = Vector2(0, 60)
	confetti.initial_velocity_min = 20.0
	confetti.initial_velocity_max = 50.0
	confetti.angular_velocity_min = -200.0
	confetti.angular_velocity_max = 200.0
	confetti.scale_amount_min = 1.5
	confetti.scale_amount_max = 3.0
	var ramp := Gradient.new()
	ramp.set_color(0, Ui.RED)
	ramp.add_point(0.33, Ui.YELLOW)
	ramp.add_point(0.66, Color("5ec8e5"))
	ramp.set_color(1, Ui.INK)
	confetti.color_initial_ramp = ramp
	stage.add_child(confetti)
