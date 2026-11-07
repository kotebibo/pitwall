class_name CircuitView
extends Control
## The race replay on the real circuit: every car drawn with the pixel-art car
## and placed along the racing line. Within a lap, a car's position follows the
## circuit's speed profile, so cars slow for corners and fly down the straights.

const PIT_IN := 0.90
const PIT_OUT := 0.995
const PIT_BOX := 0.955

## Each: {"dist": laps as float, "pit": 0..1, "color": Color, "you": bool, "out": bool}
var cars: Array[Dictionary] = []
var follow := 0
var track_id := "mtkvari"

var _view: SubViewport
var _rect: TextureRect
var _render: TrackRender
var _views: Array[CarView] = []
var _cam: Camera2D
var _time := PackedFloat32Array()  # cumulative profile time at each point, 0..1
var _cam_rot := 0.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
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
	resized.connect(_resize)
	var world := Node2D.new()
	_view.add_child(world)
	_render = TrackRender.new()
	world.add_child(_render)
	_render.setup(TrackData.load_id(track_id))
	_cam = Camera2D.new()
	_cam.ignore_rotation = false
	world.add_child(_cam)
	_cam.make_current()
	# time along the lap from the speed profile
	var n := _render.line.size()
	_time.resize(n + 1)
	var acc := 0.0
	for i in n:
		_time[i] = acc
		var v := maxf(_render.line_kmh[i] / 3.6, 15.0)
		acc += _render.line[i].distance_to(_render.line[(i + 1) % n]) / v
	_time[n] = acc
	for i in n + 1:
		_time[i] /= acc
	_resize()


func _resize() -> void:
	var win := get_window().size
	var px := DriveScreen.pixel_scale(win.y)
	var scale := size / get_viewport_rect().size
	_view.size = Vector2i(maxi(1, ceili(win.x * scale.x / px)), maxi(1, ceili(win.y * scale.y / px)))


func set_cars(list: Array[Dictionary]) -> void:
	cars = list
	while _views.size() < cars.size():
		var v := CarView.new()
		v.z_index = 5
		_view.get_child(0).add_child(v)
		_views.append(v)
	for i in cars.size():
		var c := cars[i]
		var v := _views[i]
		if v.body != c["color"]:
			v.body = c["color"]
			v.build()
		v.modulate = Color(1, 1, 1, 0.35) if c["out"] else Color.WHITE
		v.z_index = 6 if c["you"] else 5
		var p := pose(fposmod(float(c["dist"]), 1.0))
		var lane := (i - (cars.size() - 1) * 0.5) * 0.9
		var pit := float(c["pit"])
		var n: Vector2 = p[2]
		v.position = (p[0] as Vector2) + n * (lane * (1.0 - pit) - pit * 11.0)
		v.rotation = p[1]
		v.braking = false


## [position, heading, right normal] at a fraction of a lap (by time, not distance).
func pose(frac: float) -> Array:
	var n := _render.line.size()
	var lo := 0
	var hi := n
	while hi - lo > 1:
		var m := (lo + hi) >> 1
		if _time[m] <= frac:
			lo = m
		else:
			hi = m
	var t := (frac - _time[lo]) / maxf(_time[lo + 1] - _time[lo], 0.000001)
	var a := _render.line[lo]
	var b := _render.line[(lo + 1) % n]
	var dir := (b - a).normalized()
	return [a.lerp(b, t), dir.angle(), Vector2(-dir.y, dir.x)]


func _process(delta: float) -> void:
	if _views.is_empty() or follow >= _views.size():
		return
	var target := _views[follow]
	_cam_rot = lerp_angle(_cam_rot, target.rotation + PI / 2, 1.0 - exp(-2.0 * delta))
	_cam.rotation = _cam_rot
	_cam.zoom = Vector2.ONE * (_view.size.y / 120.0)
	_cam.position = _cam.position.lerp(target.position, 1.0 - exp(-8.0 * delta)) if _cam.position.distance_to(target.position) < 80.0 else target.position
