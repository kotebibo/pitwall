class_name DriveScreen
extends Control
## Drive a session. The physics steps at 120 ticks per second in
## _physics_process; drawing interpolates between ticks. Every input is
## recorded by SessionSim, so a lap can be re-driven and verified.

signal exited

const GHOST_COLOR := Color("f1efea")

var kind := SessionSim.Kind.QUALIFYING
var track_id := "mtkvari"
var title := "QUALIFYING"
var setup := {"front_wing": 6, "rear_wing": 6, "brake_bias": 57, "differential": 6}
var stats := {"braking": 50, "cornering": 50, "traction": 50, "energy": 50}
## Optional: async () -> {"attempt": String, "seed": PackedByteArray}. Without it, attempts are local.
var on_attempt: Callable
## Send personal-best runs to the server to be re-driven and recorded on-chain.
var verify_laps := false
## Parts spec for the physics (see game/data/parts.json) and the concepts the car looks like.
var car_spec := {}
var car_parts := {}
var team_color := Ui.RED
## First-time tutorial: start from a standstill and pass four checked steps.
var tutorial := false
var _rookie: RookieTest
## Attempt id of the fastest other player's verified lap: raced as a ghost.
var rival_attempt := ""
var rival_name := ""
var _rival: CarView
var _rival_path := PackedVector3Array()

var _track: TrackData
var _session: SessionSim
var _input := DriveInput.new()
var _view: SubViewport
var _view_rect: TextureRect
var _world: Node2D
var _render: TrackRender
var _line: RacingLine
var _smoke: CPUParticles2D
var _camera: Camera2D
var _audio: CarAudio
var _car: CarView
var _ghost: CarView
var _skids: SkidMarks
var _sparks: CPUParticles2D
var _hud: DriveHud
var _pause: Control
var _state := "loading"
var _attempt_id := ""
var _prev := Vector3.ZERO  # x, y, heading of the last two ticks, for smooth drawing
var _cur := Vector3.ZERO
var _cam_rot := 0.0
var _cam_zoom := 3.0
var _shake := 0.0
var _north_up := false

var _lap_number := 0
var _lap_tick0 := 0
var _lap_path := PackedVector3Array()
var _best_path := PackedVector3Array()
var _lap_time_at := PackedInt64Array()
var _best_time_at := PackedInt64Array()
var _best_us := 0
var _sectors_stale := false
## Set from the command line (--autopilot) to drive itself, for demos and screenshots.
var _autopilot: Autopilot


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	DriveInput.ensure_actions()
	RenderingServer.set_default_clear_color(Ui.BG)
	_track = TrackData.load_id(track_id)
	if "--autopilot" in Api.args:
		_autopilot = Autopilot.new(_track)
	_build()
	_start_attempt()
	if rival_attempt != "":
		_load_rival()


## Re-drives the rival's verified run with the same physics to get their exact path.
func _load_rival() -> void:
	var g: Variant = await Api.get_json("/api/attempts/%s/ghost" % rival_attempt)
	if not g is Dictionary or not (g as Dictionary).get("lap") is Dictionary:
		return
	var d: Dictionary = g
	var seed := PackedByteArray()
	var hex := String(d.get("seed", ""))
	for i in range(0, hex.length() - 1, 2):
		seed.append(hex.substr(i, 2).hex_to_int())
	var car: Dictionary = d.get("car", {}) if d.get("car") is Dictionary else {}
	var sim := SessionSim.new(_track, d.get("setup", {}), d.get("stats", {}), seed, SessionSim.Kind.QUALIFYING, car)
	var raw := SessionSim.decode_inputs(Marshalls.base64_to_raw(String(d.get("inputs", ""))))
	var lap: Dictionary = d["lap"]
	var ticks: Array = lap.get("ticks", [0, 0])
	var start := int(float(ticks[0])) >> 16
	var end := (int(float(ticks[1])) >> 16) + 1
	var path := PackedVector3Array()
	var n := mini(raw.size() / 4, end + 1)
	for i in n:
		sim.step(raw[4 * i] - 128, raw[4 * i + 1], raw[4 * i + 2], raw[4 * i + 3])
		if i + 1 >= start and i + 1 <= end:
			var c := sim.car
			path.append(Vector3(c.px / 65536.0, c.py / 65536.0, c.heading / 65536.0))
		if i % 1500 == 0:
			await get_tree().process_frame  # keep the game smooth while re-driving
			if not is_inside_tree():
				return
	_rival_path = path
	print_verbose("rival ghost: %d ticks from %s" % [path.size(), rival_attempt])
	rival_name = String(d.get("name", "RIVAL"))
	_hud.flash("GHOST LOADED: %s · %s" % [rival_name.to_upper(), Ui.format_time(int(lap.get("us", 0)) / 1000)], DriveHud.PURPLE, 3.0)


func _exit_tree() -> void:
	get_viewport().canvas_transform = Transform2D.IDENTITY
	RenderingServer.set_default_clear_color(Ui.BG)


## Pixel size of the world: it renders at a fraction of the screen and is scaled
## up with crisp pixels, so track, cars and effects share one pixel-art grid.
static func pixel_scale(window_h: int) -> int:
	var args := Api.args
	if OS.is_debug_build() and args.has("--pixel-scale") and args.find("--pixel-scale") + 1 < args.size():
		return clampi(int(args[args.find("--pixel-scale") + 1]), 1, 4)  # video recording
	return clampi(roundi(window_h / 480.0), 1, 4)


func _build() -> void:
	_view = SubViewport.new()
	_view.disable_3d = true
	_view.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_LINEAR
	_view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(_view)
	_view_rect = TextureRect.new()
	_view_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_view_rect.texture = _view.get_texture()
	_view_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_view_rect.stretch_mode = TextureRect.STRETCH_SCALE
	_view_rect.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_view_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_view_rect)
	get_window().size_changed.connect(_resize_view)
	_resize_view()

	_world = Node2D.new()
	_view.add_child(_world)
	_render = TrackRender.new()
	_world.add_child(_render)
	_render.setup(_track)
	if kind == SessionSim.Kind.PRACTICE:
		_line = RacingLine.new()
		_line.setup(_render)
		_world.add_child(_line)
	_skids = SkidMarks.new()
	_skids.z_index = 2
	_world.add_child(_skids)
	_ghost = CarView.new()
	_ghost.ghost = true
	_ghost.body = GHOST_COLOR
	if not car_parts.is_empty():
		_ghost.parts = car_parts
	_ghost.visible = false
	_ghost.z_index = 4
	_world.add_child(_ghost)
	_rival = CarView.new()
	_rival.ghost = true
	_rival.body = Color("a855f7")
	_rival.visible = false
	_rival.z_index = 4
	_world.add_child(_rival)
	_car = CarView.new()
	_car.body = team_color
	if not car_parts.is_empty():
		_car.parts = car_parts
	_car.z_index = 5
	_world.add_child(_car)
	_smoke = _make_smoke()
	_world.add_child(_smoke)
	_sparks = _make_sparks()
	_sparks.z_index = 6
	_world.add_child(_sparks)
	_camera = Camera2D.new()
	_camera.ignore_rotation = false
	_world.add_child(_camera)
	_camera.make_current()
	_audio = CarAudio.new()
	add_child(_audio)
	Sfx.stop_music()

	var layer := CanvasLayer.new()
	add_child(layer)
	_hud = DriveHud.new()
	_hud.title = "%s · %s" % [title, _track.name.to_upper()]
	layer.add_child(_hud)
	_hud.set_track(_render.points)
	_pause = _build_pause()
	_pause.theme = Ui.theme  # a CanvasLayer breaks theme inheritance
	layer.add_child(_pause)


func _resize_view() -> void:
	var win := get_window().size
	var px := pixel_scale(win.y)
	_view.size = Vector2i(ceili(win.x / float(px)), ceili(win.y / float(px)))


func _make_smoke() -> CPUParticles2D:
	var p := CPUParticles2D.new()
	p.emitting = false
	p.amount = 48
	p.lifetime = 0.9
	p.local_coords = false
	p.spread = 180.0
	p.initial_velocity_min = 0.5
	p.initial_velocity_max = 3.0
	p.gravity = Vector2.ZERO
	p.damping_min = 1.0
	p.damping_max = 2.0
	p.scale_amount_min = 1.2
	p.scale_amount_max = 2.6
	var curve := Curve.new()
	curve.add_point(Vector2(0, 0.6))
	curve.add_point(Vector2(1, 1.6))
	p.scale_amount_curve = curve
	var ramp := Gradient.new()
	ramp.set_color(0, Color(0.85, 0.85, 0.88, 0.45))
	ramp.set_color(1, Color(0.85, 0.85, 0.88, 0.0))
	p.color_ramp = ramp
	p.z_index = 3
	return p


func _make_sparks() -> CPUParticles2D:
	var p := CPUParticles2D.new()
	p.emitting = false
	p.one_shot = true
	p.amount = 24
	p.lifetime = 0.35
	p.explosiveness = 0.9
	p.spread = 70.0
	p.initial_velocity_min = 8.0
	p.initial_velocity_max = 30.0
	p.gravity = Vector2.ZERO
	p.scale_amount_min = 0.3
	p.scale_amount_max = 0.6
	p.color = Color("ffb347")
	return p


func _build_pause() -> Control:
	var root := ColorRect.new()
	root.color = Color(0.03, 0.035, 0.045, 0.78)
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.visible = false
	var panel := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.075, 0.09, 0.95)
	sb.border_color = Ui.RED
	sb.border_width_top = 3
	sb.set_content_margin_all(12)
	panel.add_theme_stylebox_override("panel", sb)
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(230, 0)
	panel.position = Vector2(-115, -100)
	root.add_child(panel)
	var box := Ui.vbox(5)
	panel.add_child(box)
	box.add_child(Ui.label("PAUSED", Ui.SIZE_TITLE, Ui.INK, true))
	box.add_child(Ui.label(title + "  ·  " + _track.name.to_upper(), Ui.SIZE_SMALL, Ui.INK_2))
	var resume := Ui.button("RESUME", true)
	resume.custom_minimum_size = Vector2(0, 24)
	resume.pressed.connect(_toggle_pause)
	box.add_child(resume)
	var restart := Ui.button("RESTART RUN  (R)")
	restart.pressed.connect(func() -> void:
		_toggle_pause()
		_start_attempt())
	box.add_child(restart)
	var cam := Ui.button("CAMERA: CHASE / NORTH UP  (C)")
	cam.pressed.connect(func() -> void: _north_up = not _north_up)
	box.add_child(cam)
	var mute := Ui.button("SOUND: ON / OFF")
	mute.pressed.connect(func() -> void: Sfx.toggle_mute())
	box.add_child(mute)
	var leave := Ui.button("EXIT TO WEEKEND")
	leave.pressed.connect(func() -> void: exited.emit())
	box.add_child(leave)
	var keys := Ui.label("STEER A/D  ·  THROTTLE W  ·  BRAKE SPACE or S  ·  BOOST SHIFT  ·  REVERSE X\nGAMEPAD: STICK, RT, LT, A BOOST, B REVERSE  ·  F3 FPS", Ui.SIZE_SMALL, Ui.INK_3)
	box.add_child(keys)
	return root


func _start_attempt() -> void:
	_state = "loading"
	var seed := PackedByteArray()
	_attempt_id = ""
	if on_attempt.is_valid():
		var res: Variant = await on_attempt.call()
		if res is Dictionary and (res as Dictionary).has("seed"):
			seed = res["seed"]
			_attempt_id = res.get("attempt", "")
			# the server re-drives with this exact car, so drive with it too
			if (res as Dictionary).get("car") is Dictionary:
				car_spec = res["car"]
			# and with the same driver stats and setup
			if (res as Dictionary).get("stats") is Dictionary:
				stats = res["stats"]
			if (res as Dictionary).get("setup") is Dictionary:
				setup = res["setup"]
		else:
			_hud.flash("SERVER UNAVAILABLE: OFFLINE RUN", Ui.YELLOW, 4.0)
	if seed.is_empty():
		seed = Crypto.new().generate_random_bytes(32)
	_session = SessionSim.new(_track, setup, stats, seed, kind, car_spec)
	if _audio:
		_audio.stop_all()
	if tutorial:
		_session.car.place(_track, _track.spawn_index, 0)
		_rookie = RookieTest.new(_track)
		_rookie.step_changed.connect(func(i: int, t: String, text: String) -> void:
			_hud.tut_step = i
			_hud.tut_title = t
			_hud.tut_text = text
			Sfx.play("ui_confirm"))
		_rookie.feedback.connect(func(text: String, good: bool) -> void:
			_hud.flash(text, DriveHud.GREEN if good else Ui.RED, 3.0)
			Sfx.play("sector_green" if good else "ui_error"))
		_rookie.passed.connect(_rookie_passed)
		_rookie.start()
	_skids.clear()
	_lap_number = 0
	_lap_path.clear()
	_lap_time_at = _filled(_track.size(), -1)
	_cur = _state_vec()
	_prev = _cur
	_cam_rot = _cur.z + PI / 2
	_hud.lap = 0
	_hud.sectors = []
	_hud.has_delta = false
	_hud.waiting = true
	_state = "waiting"


static func _filled(n: int, v: int) -> PackedInt64Array:
	var a := PackedInt64Array()
	a.resize(n)
	a.fill(v)
	return a


func _state_vec() -> Vector3:
	var c := _session.car
	return Vector3(c.px / 65536.0, c.py / 65536.0, c.heading / 65536.0)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("drive_pause"):
		_toggle_pause()
	elif event.is_action_pressed("drive_restart") and _state != "loading":
		_pause.visible = false
		_start_attempt()
	elif event is InputEventKey and (event as InputEventKey).pressed and (event as InputEventKey).physical_keycode == KEY_C:
		_north_up = not _north_up
	elif event is InputEventKey and (event as InputEventKey).pressed and (event as InputEventKey).physical_keycode == KEY_F3:
		_hud.show_fps = not _hud.show_fps


func _toggle_pause() -> void:
	if _state == "driving" or _state == "waiting":
		_pause.visible = true
		_state = "paused_" + _state
		_audio.set_paused(true)
	elif _state.begins_with("paused_"):
		_pause.visible = false
		_state = _state.trim_prefix("paused_")
		_audio.set_paused(false)


func _physics_process(_delta: float) -> void:
	if _session == null:
		return
	var car := _session.car
	if _state == "waiting":
		_poll(car)
		if _input.throttle > 0:
			_state = "driving"
			_hud.waiting = false
		else:
			return
	if _state != "driving":
		return
	_poll(car)
	_prev = _cur
	_session.step(_input.steer, _input.throttle, _input.brake, _input.buttons())
	_cur = _state_vec()
	_after_tick()


func _poll(car: CarSim) -> void:
	if _autopilot:
		var a := _autopilot.drive(car)
		_input.steer = a[0]
		_input.throttle = a[1]
		_input.brake = a[2]
		_input.boost = a[3] == 1
		return
	_input.poll(car)


func _rookie_passed() -> void:
	_hud.tut_title = ""
	Profile.tutorial_done = true
	Profile.save()
	Api.track("rookie_passed")
	_hud.flash("ROOKIE TEST PASSED · YOU'RE CLEARED TO QUALIFY", DriveHud.PURPLE, 5.0)
	Sfx.play("lap_purple")
	await get_tree().create_timer(5.0).timeout
	if is_inside_tree():
		exited.emit()


func _after_tick() -> void:
	var car := _session.car
	if _rookie:
		_rookie.tick(_session)
	if _session.lap_number != _lap_number:
		_lap_number = _session.lap_number
		_lap_tick0 = _session.tick
		_lap_path.clear()
		_lap_time_at = _filled(_track.size(), -1)
		_sectors_stale = true
	if _lap_number > 0:
		_lap_path.append(_cur)
		var now := _session.current_lap_us()
		if _lap_time_at[car.idx] < 0:
			_lap_time_at[car.idx] = now
		if _best_time_at.size() > 0 and _best_time_at[car.idx] >= 0:
			_hud.delta_us = now - _best_time_at[car.idx]
			_hud.has_delta = true

	for e in _session.events:
		match e["type"]:
			"sector":
				var t: int = e["us"]
				if _sectors_stale:
					_hud.sectors = []
					_sectors_stale = false
				_hud.sectors.append(t)
				var i: int = int(e["sector"]) - 1
				if _session.lap_valid and (i >= _hud.best_sectors.size() or t < _hud.best_sectors[i]):
					Sfx.play("sector_green")
				if _session.lap_valid and (i >= _hud.best_sectors.size() or t < _hud.best_sectors[i]):
					while _hud.best_sectors.size() <= i:
						_hud.best_sectors.append(1 << 40)
					_hud.best_sectors[i] = t
			"lap":
				_on_lap(e["lap"])
			"limits":
				_hud.flash("TRACK LIMITS · LAP DELETED", Ui.RED)
				Sfx.play("lap_deleted")
			"wall":
				var hit: int = e["speed"]
				_audio.impact(hit / 65536.0 / 25.0)
				if hit > 3 * 65536:
					_sparks.position = Vector2(_cur.x, _cur.y)
					_sparks.restart()
					_shake = minf(hit / 65536.0 / 25.0, 1.0)
	var sliding := car.front_locked or car.rear_sliding
	if sliding:
		_skids.add(Vector2(_prev.x, _prev.y), Vector2(_cur.x, _cur.y), _prev.z, _cur.z, car.front_locked)
	var on_grass := car.surface == CarSim.Surface.GRASS and car.speed > 8 * 65536
	_smoke.emitting = (sliding and car.speed > 4 * 65536) or on_grass
	if _smoke.emitting:
		var back := Vector2.from_angle(_cur.z) * (1.7 if car.front_locked else -2.2)
		_smoke.position = Vector2(_cur.x, _cur.y) + back
		_smoke.color = Color("c9b48a") if on_grass else Color.WHITE


func _on_lap(lap: Dictionary) -> void:
	var us: int = lap["us"]
	_hud.last_us = us
	_hud.sectors.assign(lap["sectors"])
	_sectors_stale = true
	if not lap["valid"]:
		_hud.flash("LAP DELETED", Ui.RED)
		Sfx.play("lap_deleted")
		return
	var sectors: Array = lap["sectors"]
	if sectors.size() == 3:
		var i := 2
		while _hud.best_sectors.size() <= i:
			_hud.best_sectors.append(1 << 40)
		_hud.best_sectors[i] = mini(_hud.best_sectors[i], int(sectors[2]))
	if _best_us == 0 or us < _best_us:
		var gain := _best_us - us if _best_us > 0 else 0
		_best_us = us
		_hud.best_us = us
		_best_path = _lap_path.duplicate()
		_best_time_at = _lap_time_at.duplicate()
		var text := "PERSONAL BEST  " + Ui.format_time(us / 1000)
		if gain > 0:
			text += "   -%.3f" % (gain / 1000000.0)
		_hud.flash(text, DriveHud.GREEN, 3.5)
		Sfx.play("lap_pb")
		if verify_laps and _attempt_id != "":
			_verify(us)
	else:
		_hud.flash(Ui.format_time(us / 1000) + "   +%.3f" % ((us - _best_us) / 1000000.0), Ui.YELLOW)


## The server re-drives the whole run from its inputs; only then does the lap count.
func _verify(us: int) -> void:
	var res: Variant = await Api.post_json("/api/attempts/%s/run" % _attempt_id, {"inputs": _session.encoded_inputs()})
	if not is_inside_tree():
		return
	if res is Dictionary and bool((res as Dictionary).get("verified", false)):
		var r: Dictionary = res
		var best: Variant = r.get("best")
		var in_passes: Array = r.get("pass", [])
		if best is Dictionary and int((best as Dictionary).get("us", 0)) == us and not in_passes.is_empty():
			# race pass lap: where it puts you in your passes
			var p: Dictionary = in_passes[0]
			_hud.flash("VERIFIED · %s  P%d OF %d" % [String(p.get("pool", "RACE PASS")), int(p.get("rank", 0)), int(p.get("of", 0))], DriveHud.GREEN, 3.5)
			Sfx.play("verified")
		elif best is Dictionary and int((best as Dictionary).get("us", 0)) == us:
			_hud.flash("VERIFIED  P%d  · RECORDING ON SOLANA" % int(r.get("position", 0)), DriveHud.PURPLE if int(r.get("position", 0)) == 1 else DriveHud.GREEN, 3.5)
			Sfx.play("lap_purple" if int(r.get("position", 0)) == 1 else "verified")
			var packs: Array = r.get("packsEarned", [])
			if not packs.is_empty():
				await get_tree().create_timer(3.6).timeout
				if is_inside_tree():
					_hud.flash("DEVELOPMENT PACK EARNED · OPEN IT IN THE GARAGE", Ui.YELLOW, 4.0)
					Sfx.play("coins")
		else:
			_hud.flash("SERVER RE-DRIVE DID NOT MATCH THIS LAP", Ui.RED, 4.0)
	else:
		_hud.flash("COULD NOT VERIFY: SERVER UNAVAILABLE", Ui.YELLOW, 3.0)


var _gear := 1
var _tips_shown := {}


## Practice coaching: each tip once, at the moment it matters.
func _tips(car: CarSim, v: float) -> void:
	if _state != "driving" or _hud.message != "":
		return
	var tip := ""
	if not _tips_shown.has("line"):
		tip = "line"
	elif _hud.brake_warning and not _tips_shown.has("brake"):
		tip = "brake"
	elif car.straight_mode and not _tips_shown.has("sm"):
		tip = "sm"
	elif (_track.flags[car.idx] & TrackData.FLAG_STRAIGHT_MODE) != 0 and car.battery > 2000000 and not car.boosting and _input.throttle > 240 and not _hud.brake_warning and not _tips_shown.has("boost"):
		tip = "boost"
	elif car.off_track and not _tips_shown.has("limits"):
		tip = "limits"
	elif car.rear_sliding and v > 10.0 and not _tips_shown.has("traction"):
		tip = "traction"
	if tip == "":
		return
	_tips_shown[tip] = true
	var text: String = {
		"line": "THE LINE READS YOUR SPEED: RED = BRAKE BY HERE, YELLOW = LIFT",
		"brake": "BRAKE NOW · BOARDS COUNT DOWN 150 · 100 · 50 M",
		"sm": "STRAIGHT MODE: WINGS OPEN ON THE BLUE STRAIGHTS",
		"boost": "HOLD SHIFT (A) FOR BOOST: +350 KW FROM THE BATTERY",
		"limits": "FOUR WHEELS PAST THE WHITE LINE DELETES THE LAP",
		"traction": "REAR STEPPING OUT: EASE THE THROTTLE",
	}[tip]
	_hud.flash(text, Ui.YELLOW, 4.0)


## An 8-speed gearbox for the dash and the sound only (the physics has no gears).
func _gearbox(kmh: float) -> float:
	var top := func(g: int) -> float: return 95.0 * pow(350.0 / 95.0, (g - 1) / 7.0)
	var rpm: float = 11500.0 * kmh / float(top.call(_gear))
	if rpm > 11300.0 and _gear < 8:
		_gear += 1
	elif rpm < 7000.0 and _gear > 1:
		_gear -= 1
	return clampf(11500.0 * kmh / float(top.call(_gear)), 4000.0, 11800.0)


func _process(delta: float) -> void:
	if _session == null:
		return
	var car := _session.car
	var a := Engine.get_physics_interpolation_fraction() if _state == "driving" else 1.0
	var pos := Vector2(lerpf(_prev.x, _cur.x, a), lerpf(_prev.y, _cur.y, a))
	var heading := lerp_angle(_prev.z, _cur.z, a)
	_car.position = pos
	_car.rotation = heading
	_car.steer = car.steer_angle / 65536.0
	_car.braking = _input.brake > 0
	_car.boosting = car.boosting
	_car.straight_mode = car.straight_mode

	# Ghost of the best lap, matched by time into the lap
	var g := _session.tick - _lap_tick0
	_rival.visible = _lap_number > 0 and g >= 0 and g < _rival_path.size()
	if _rival.visible:
		var rp := _rival_path[g]
		_rival.position = Vector2(rp.x, rp.y)
		_rival.rotation = rp.z
	_ghost.visible = _lap_number > 0 and g >= 0 and g < _best_path.size()
	if _ghost.visible:
		var gp := _best_path[g]
		_ghost.position = Vector2(gp.x, gp.y)
		_ghost.rotation = gp.z
		_hud.map_ghost = Vector2(gp.x, gp.y)
	else:
		_hud.map_ghost = Vector2(-1, -1)

	# Camera: chase (follows the direction of travel, not every twitch of the nose)
	# or north up; zooms out with speed so braking points come into view in time.
	var v := car.speed / 65536.0
	var visible_m := lerpf(78.0, 150.0, clampf(v / 85.0, 0.0, 1.0))
	_cam_zoom = lerpf(_cam_zoom, _view.size.y / visible_m, 1.0 - exp(-2.0 * delta))
	_camera.zoom = Vector2(_cam_zoom, _cam_zoom)
	var travel := heading
	if v > 6.0:
		travel = Vector2(car.vx, car.vy).angle()
	var target_rot := 0.0 if _north_up else travel + PI / 2
	_cam_rot = lerp_angle(_cam_rot, target_rot, 1.0 - exp(-3.2 * delta))
	_camera.rotation = _cam_rot
	var view_h := _view.size.y / _cam_zoom
	var ahead := Vector2.from_angle(_cam_rot - PI / 2) * view_h * 0.26 if not _north_up else Vector2.from_angle(travel) * view_h * 0.25 * clampf(v / 40.0, 0.0, 1.0)
	_shake = maxf(_shake - delta * 3.0, 0.0)
	var jitter := Vector2(randf_range(-1, 1), randf_range(-1, 1)) * _shake * 1.5
	_camera.position = pos + ahead + jitter

	# HUD
	_hud.lap = _session.lap_number
	_hud.lap_us = _session.current_lap_us()
	_hud.lap_valid = _session.lap_valid
	_hud.speed_kmh = roundi(v * 3.6)
	_hud.throttle = _input.throttle
	_hud.brake = _input.brake
	_hud.battery = car.battery / float(CarSim.BATTERY_MAX)
	_hud.boosting = car.boosting
	_hud.straight_mode = car.straight_mode
	_hud.straight_zone = (_track.flags[car.idx] & TrackData.FLAG_STRAIGHT_MODE) != 0
	var slip := 1.0 if car.front_locked or car.rear_sliding else clampf(absf(car.yaw_rate / 65536.0) * v / 40.0 - 0.6, 0.0, 0.6)
	var surface := 0 if car.surface == CarSim.Surface.ASPHALT else (1 if car.surface == CarSim.Surface.KERB else 2)
	var running := _state == "driving"
	_audio.update(v if running else 0.0, _input.throttle / 255.0 if running else 0.0, _input.brake / 255.0, slip if running else 0.0, car.front_locked and running, surface, car.boosting and running, car.straight_mode, delta)
	_audio.scrape(running and car.wall_hit > 0)
	_hud.rpm = _audio.rpm
	_hud.gear = _audio.gear
	_hud.device = "GAMEPAD" if _input.using_gamepad else "KEYBOARD"
	_hud.map_car = pos
	if _line:
		_line.follow(car.idx, v)
		_hud.brake_warning = _line.brake_warning(car.idx, v)
		if not tutorial:
			_tips(car, v)
