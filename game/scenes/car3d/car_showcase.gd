class_name CarShowcase
extends Control
## The 3D car on a turntable, rendered small in its own SubViewport and scaled
## up with nearest filtering, so it reads as pixel art next to the 2D sprites.
## Drop it into any menu: it fills its rect, spins slowly, can be dragged
## around, and zooms to a part area with focus(). Renders only while visible.

const CarModelScript := preload("res://scenes/car3d/car_model.gd")
const FLOOR_SHADER := preload("res://scenes/car3d/floor.gdshader")
const SHADOW_SHADER := preload("res://scenes/car3d/blob_shadow.gdshader")
const OUTLINE_SHADER := preload("res://scenes/car3d/outline.gdshader")

const YELLOW := Color("f2c230")
const FAR := 40.0

## Camera framing per part area: turntable yaw (radians; null = keep spinning),
## pitch (degrees down), visible height (metres) and look-at point on the car.
const VIEWS := {
	"": {"yaw": null, "pitch": 24.0, "size": 4.3, "target": Vector3(-0.1, 0.3, 0.0)},
	"front_wing": {"yaw": -0.75, "pitch": 22.0, "size": 2.5, "target": Vector3(2.3, 0.25, 0.0)},
	"rear_wing": {"yaw": 0.6, "pitch": 36.0, "size": 2.4, "target": Vector3(-2.4, 0.66, 0.0)},
	"sidepods": {"yaw": -0.45, "pitch": 26.0, "size": 3.0, "target": Vector3(0.0, 0.4, 0.3)},
	"floor": {"yaw": 0.7, "pitch": 11.0, "size": 3.4, "target": Vector3(-1.0, 0.2, 0.0)},
	"suspension": {"yaw": -1.05, "pitch": 26.0, "size": 1.8, "target": Vector3(1.55, 0.35, 0.45)},
	"power_unit": {"yaw": 0.7, "pitch": 36.0, "size": 2.8, "target": Vector3(-1.5, 0.6, 0.0)},
}

## Physical screen pixels per rendered 3D pixel (the "pixel art" size).
@export var pixel_size := 3:
	set(v):
		pixel_size = maxi(1, v)
		_last_scale = -1.0
## Turn the turntable when idle.
@export var spin := true
@export var spin_speed := 0.45
## Transparent background (the menu shows through); otherwise `background`.
@export var transparent := true:
	set(v):
		transparent = v
		_apply_background()
@export var background := Color("141518"):
	set(v):
		background = v
		_apply_background()
@export var show_floor := true:
	set(v):
		show_floor = v
		if _floor:
			_floor.visible = v
## Extra zoom on top of the framing (1 = fit).
@export var zoom := 1.0
## Mouse/touch drag rotates the car.
@export var interactive := true:
	set(v):
		interactive = v
		mouse_filter = Control.MOUSE_FILTER_STOP if v else Control.MOUSE_FILTER_IGNORE
## Seconds after a drag before the view drifts back to spin / focus.
@export var return_delay := 3.0
## Gentle idle motion: chassis breathing and a little steering.
@export var idle_motion := true

var car: CarModel3D

var _vp: SubViewport
var _tex: TextureRect
var _cam: Camera3D
var _env: Environment
var _table: Node3D
var _floor: MeshInstance3D
var _floor_mat: ShaderMaterial
var _outline_mat: ShaderMaterial
var _focus := ""
var _yaw := -0.6
var _yaw_vel := 0.0
var _spin_k := 1.0
var _dragging := false
var _idle := 99.0
var _pitch := deg_to_rad(24.0)
var _pitch_off := 0.0
var _size := 4.3
var _target := Vector3(-0.1, 0.3, 0.0)
var _time := 0.0
var _pulse := -1.0
var _last_scale := -1.0
var _last_size := Vector2.ZERO


func _init() -> void:
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	_vp = SubViewport.new()
	_vp.name = "Viewport3D"
	_vp.own_world_3d = true
	_vp.transparent_bg = true
	_vp.msaa_3d = Viewport.MSAA_DISABLED
	_vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED
	_vp.positional_shadow_atlas_size = 0
	_vp.audio_listener_enable_3d = false
	_vp.gui_disable_input = true
	_vp.render_target_update_mode = SubViewport.UPDATE_WHEN_VISIBLE
	_vp.size = Vector2i(64, 64)
	add_child(_vp)

	_env = Environment.new()
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_env.ambient_light_color = Color(0.36, 0.38, 0.46)
	_env.ambient_light_energy = 1.8
	_env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	_env.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED

	_cam = Camera3D.new()
	_cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	_cam.keep_aspect = Camera3D.KEEP_HEIGHT
	_cam.near = 0.1
	_cam.far = FAR
	_cam.environment = _env
	_cam.current = true
	_vp.add_child(_cam)

	_add_light(Vector3(-0.55, 0.8, 0.6), Color(1.0, 0.96, 0.9), 1.0)   # key, camera left
	_add_light(Vector3(0.9, 0.3, 0.4), Color(0.55, 0.68, 0.98), 0.38)  # fill, cool, right
	_add_light(Vector3(0.35, 0.5, -1.0), Color(1.0, 0.88, 0.78), 1.3)  # rim, from behind

	_table = Node3D.new()
	_table.name = "Turntable"
	_vp.add_child(_table)
	_floor_mat = ShaderMaterial.new()
	_floor_mat.shader = FLOOR_SHADER
	_floor_mat.render_priority = -2
	var disc := PlaneMesh.new()
	disc.size = Vector2(7.4, 7.4)
	_floor = MeshInstance3D.new()
	_floor.mesh = disc
	_floor.material_override = _floor_mat
	_floor.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_table.add_child(_floor)
	var shadow_mat := ShaderMaterial.new()
	shadow_mat.shader = SHADOW_SHADER
	shadow_mat.render_priority = -1
	var plane := PlaneMesh.new()
	plane.size = Vector2(6.6, 2.8)
	var shadow := MeshInstance3D.new()
	shadow.mesh = plane
	shadow.material_override = shadow_mat
	shadow.position.y = 0.004
	shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_table.add_child(shadow)

	car = CarModelScript.new()
	car.name = "Car"
	_table.add_child(car)

	# Full-screen outline pass (reads the depth buffer).
	_outline_mat = ShaderMaterial.new()
	_outline_mat.shader = OUTLINE_SHADER
	_outline_mat.render_priority = 100
	_outline_mat.set_shader_parameter("depth_range", FAR - 0.1)
	var quad := QuadMesh.new()
	quad.size = Vector2(1, 1)
	var outline := MeshInstance3D.new()
	outline.name = "Outline"
	outline.mesh = quad
	outline.material_override = _outline_mat
	outline.extra_cull_margin = 16384.0
	outline.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	outline.position = Vector3(0, 0, -1.0)
	_cam.add_child(outline)

	_tex = TextureRect.new()
	_tex.name = "Pixels"
	_tex.texture = _vp.get_texture()
	_tex.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_tex.stretch_mode = TextureRect.STRETCH_SCALE
	_tex.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_tex.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_tex)


func _ready() -> void:
	_apply_background()
	interactive = interactive
	_floor.visible = show_floor
	_update_active()
	_layout()
	_place_camera()


func _add_light(from: Vector3, c: Color, energy: float) -> void:
	var l := DirectionalLight3D.new()
	l.light_color = c
	l.light_energy = energy
	l.shadow_enabled = false
	l.transform = Transform3D(Basis.looking_at(-from.normalized(), Vector3.UP), Vector3.ZERO)
	_vp.add_child(l)


func _apply_background() -> void:
	if _vp == null:
		return
	_vp.transparent_bg = transparent
	if transparent:
		_env.background_mode = Environment.BG_CLEAR_COLOR
	else:
		_env.background_mode = Environment.BG_COLOR
		_env.background_color = background


# ---- API ----

func set_parts(look: Dictionary) -> void:
	car.set_parts(look)


func set_colors(primary: Color, secondary: Color) -> void:
	car.set_colors(primary, secondary)


func set_compound(c: String) -> void:
	car.set_compound(c)


func set_wing_open(open: bool) -> void:
	car.set_wing_open(open)


## Plays the "part fitted" pop + flash on an area, with a pulse across the floor.
func fit_part(area: String, flash: Color = YELLOW) -> void:
	car.fit_part(area, flash)
	_pulse = 0.0
	_floor_mat.set_shader_parameter("pulse_color", flash)


func highlight(area: String) -> void:
	car.highlight(area)


## Turns and zooms toward a part area ("front_wing", "rear_wing", "sidepods",
## "floor", "suspension", "power_unit"); "" returns to the spinning overview.
func focus(area: String) -> void:
	var a := area if VIEWS.has(area) else ""
	if a == _focus:
		return
	_focus = a
	_idle = return_delay + 1.0
	if a == "":
		_spin_k = 0.0


func focused() -> String:
	return _focus


## Sets the turntable angle directly (radians; 0 = side view, nose right;
## negative turns the nose toward the camera).
func set_yaw(yaw: float) -> void:
	_yaw = yaw
	_yaw_vel = 0.0


## Where an area of the car appears, in this control's local coordinates
## (e.g. to draw leader lines from part slots to the car).
func area_screen_point(area: String) -> Vector2:
	var world := car.global_transform * car.area_point(area) if car.is_inside_tree() else car.area_point(area)
	var p := _cam.unproject_position(world)
	return _tex.position + p / Vector2(_vp.size) * _tex.size


# ---- layout and rendering ----

func _notification(what: int) -> void:
	if what == NOTIFICATION_VISIBILITY_CHANGED or what == NOTIFICATION_ENTER_TREE:
		_update_active()
	elif what == NOTIFICATION_RESIZED:
		_last_scale = -1.0


func _update_active() -> void:
	var on := is_visible_in_tree()
	set_process(on)
	_vp.render_target_update_mode = SubViewport.UPDATE_WHEN_VISIBLE if on else SubViewport.UPDATE_DISABLED
	_vp.process_mode = Node.PROCESS_MODE_INHERIT if on else Node.PROCESS_MODE_DISABLED


## Physical screen pixels per unit of this control (canvas stretch included).
func _screen_scale() -> float:
	if not is_inside_tree():
		return 1.0
	var xf := get_viewport().get_final_transform() * get_global_transform_with_canvas()
	return maxf(0.01, absf(xf.get_scale().x))


func _layout() -> void:
	var s := _screen_scale()
	_last_scale = s
	_last_size = size
	var px := float(pixel_size)
	var vs := Vector2i(maxi(8, ceili(size.x * s / px)), maxi(8, ceili(size.y * s / px)))
	if _vp.size != vs:
		_vp.size = vs
	_tex.size = Vector2(vs) * px / s
	_tex.position = ((size - _tex.size) * 0.5).floor()


func _place_camera() -> void:
	var aspect := float(_vp.size.x) / maxf(1.0, float(_vp.size.y))
	var s := _size / maxf(0.1, zoom)
	# Keep the framed width on narrow controls.
	s = maxf(s, s * 1.5 / aspect)
	_cam.size = s
	_table.rotation.y = _yaw
	var tw := Basis(Vector3.UP, _yaw) * _target
	var p := clampf(_pitch + _pitch_off, deg_to_rad(2.0), deg_to_rad(80.0))
	var pos := tw + Vector3(0.0, sin(p), cos(p)) * 18.0
	_cam.transform = Transform3D(Basis.looking_at(tw - pos, Vector3.UP), pos)


func _process(delta: float) -> void:
	_time += delta
	if size != _last_size or not is_equal_approx(_screen_scale(), _last_scale):
		_layout()
	var view: Dictionary = VIEWS.get(_focus, VIEWS[""])
	_idle += delta
	if not _dragging:
		_yaw += _yaw_vel * delta
		_yaw_vel *= exp(-delta * 3.5)
		if _idle > return_delay:
			_pitch_off = lerpf(_pitch_off, 0.0, 1.0 - exp(-delta * 2.0))
			if view["yaw"] == null:
				if spin:
					_spin_k = move_toward(_spin_k, 1.0, delta * 0.6)
					_yaw += spin_speed * _spin_k * delta
			else:
				_yaw = lerp_angle(_yaw, float(view["yaw"]), 1.0 - exp(-delta * 3.0))
	var k := 1.0 - exp(-delta * 3.2)
	_pitch = lerpf(_pitch, deg_to_rad(float(view["pitch"])), k)
	_size = lerpf(_size, float(view["size"]), k)
	_target = _target.lerp(view["target"] as Vector3, k)
	_yaw = wrapf(_yaw, -PI, PI)
	_place_camera()
	if idle_motion:
		car.ride_offset = sin(_time * 1.7) * 0.008
		car.steer = sin(_time * 0.8) * 0.12
	if _pulse >= 0.0:
		_pulse += delta
		if _pulse > 1.0:
			_pulse = -1.0
		_floor_mat.set_shader_parameter("pulse", _pulse)


func _gui_input(event: InputEvent) -> void:
	if not interactive:
		return
	var mb := event as InputEventMouseButton
	if mb and mb.button_index == MOUSE_BUTTON_LEFT:
		_dragging = mb.pressed
		_idle = 0.0
		_spin_k = 0.0
		accept_event()
		return
	var mm := event as InputEventMouseMotion
	if mm and _dragging:
		var dx := mm.relative.x * 0.012
		_yaw += dx
		_yaw_vel = lerpf(_yaw_vel, dx * 60.0, 0.5)
		_pitch_off = clampf(_pitch_off + mm.relative.y * 0.006, -0.3, 0.45)
		_idle = 0.0
		accept_event()
