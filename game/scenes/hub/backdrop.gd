class_name MenuBackdrop
extends Control
## Live menu background: the circuit with an AI car lapping it, filmed by a
## slow cinematic camera, rendered on the same pixel grid as the driving view.

var track_id := "mtkvari"
var _view: SubViewport
var _rect: TextureRect
var _world: Node2D
var _car: CarView
var _cam: Camera2D
var _sim: SessionSim
var _pilot: Autopilot
var _prev := Vector3.ZERO
var _cur := Vector3.ZERO
var _cam_rot := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var track := TrackData.load_id(track_id)
	_view = SubViewport.new()
	_view.disable_3d = true
	_view.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_LINEAR
	add_child(_view)
	_rect = TextureRect.new()
	_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_rect.texture = _view.get_texture()
	_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_rect.stretch_mode = TextureRect.STRETCH_SCALE
	_rect.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_rect)
	get_window().size_changed.connect(_resize)
	_resize()
	_world = Node2D.new()
	_view.add_child(_world)
	var render := TrackRender.new()
	_world.add_child(render)
	render.setup(track)
	_car = CarView.new()
	_car.parts = Catalog.car_look()
	_car.z_index = 5
	_world.add_child(_car)
	_cam = Camera2D.new()
	_cam.ignore_rotation = false
	_world.add_child(_cam)
	_cam.make_current()
	_pilot = Autopilot.new(track)
	_pilot.pace = 0.97
	_sim = SessionSim.new(track, Profile.setup, Profile.stats(), PackedByteArray([128, 0, 0]), SessionSim.Kind.PRACTICE, Catalog.car_spec())
	# start somewhere scenic: a few seconds in
	for i in 120 * 4:
		_tick()
	_cam_rot = _cur.z + PI / 2


func _resize() -> void:
	var win := get_window().size
	var px := DriveScreen.pixel_scale(win.y)
	_view.size = Vector2i(ceili(win.x / float(px)), ceili(win.y / float(px)))


func _tick() -> void:
	var a := _pilot.drive(_sim.car)
	_prev = _cur
	_sim.step(a[0], a[1], a[2], a[3])
	var c := _sim.car
	_cur = Vector3(c.px / 65536.0, c.py / 65536.0, c.heading / 65536.0)
	if _sim.inputs.size() > 4 * 120 * 600:
		_sim.inputs.clear()  # the menu never needs the log


func _physics_process(_delta: float) -> void:
	if is_visible_in_tree():
		_tick()


func _process(delta: float) -> void:
	var f := Engine.get_physics_interpolation_fraction()
	var pos := Vector2(lerpf(_prev.x, _cur.x, f), lerpf(_prev.y, _cur.y, f))
	var heading := lerp_angle(_prev.z, _cur.z, f)
	_car.position = pos
	_car.rotation = heading
	_car.steer = _sim.car.steer_angle / 65536.0
	_car.straight_mode = _sim.car.straight_mode
	_car.boosting = _sim.car.boosting
	# Slow, smooth camera that lags the car and sits it on the right third
	_cam_rot = lerp_angle(_cam_rot, heading + PI / 2, 1.0 - exp(-0.9 * delta))
	_cam.rotation = _cam_rot
	_cam.zoom = Vector2.ONE * (_view.size.y / 72.0)
	# the car sits just below the centre, in the open space between menu and panels
	_cam.position = pos + Vector2.from_angle(_cam_rot - PI / 2) * (_view.size.y / _cam.zoom.y) * 0.12
