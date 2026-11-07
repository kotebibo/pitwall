extends SceneTree
## Renders the 3D car (CarModel3D) to transparent PNGs for brand art: key art,
## social images, avatars. Same toon + 1 px outline look as CarShowcase, but
## with a free camera (orthographic or perspective) and auto-framing, so every
## image is rendered at an exact pixel density (pixels per metre) and can be
## scaled up afterwards with nearest filtering.
##
##   godot --path game -s res://scenes/car3d/render_brand.gd
##   godot --path game -s res://scenes/car3d/render_brand.gd -- jobs=D:/x/jobs.json out=D:/x/renders
##
## Needs a GPU (not --headless). Without jobs= it renders the standard set
## below into <repo>/brand/renders/_src/ (tools/brand/render_jobs.py drives the
## full set used by the brand kit). A job is a Dictionary:
##   name      file name (without .png)
##   yaw       turntable angle in radians (0 = side view, nose right; negative
##             turns the nose toward the camera)
##   pitch     camera angle above the ground, degrees (90 = top-down)
##   ppm       pixels per metre (orthographic; for perspective: at the target)
##   persp     true for a perspective camera; dist = camera distance (m)
##   primary, secondary   paint and accent colours (hex)
##   compound  tyre stripe: soft, medium, hard
##   look      parts, e.g. {"rear_wing": "beam"}
##   wing_open, steer, shadow (also writes <name>_shadow.png: the blob alone)
##   target    [x, y, z] look-at point on the car (default: centre of its box)
##   margin    empty pixels around the car (default 4)
##   light_energy [key, fill, rim], ambient   lighting overrides
##   outline   false to skip the 1 px outline (tiny icon sources)
##
## Next to each <name>.png it writes <name>.json with the camera (origin,
## basis, projection, pixels per metre) so 2D backdrops can be drawn in the
## exact same projection (the ground is the plane Y = 0).

const CarScript := preload("res://scenes/car3d/car_model.gd")
const SHADOW_SHADER := preload("res://scenes/car3d/blob_shadow.gdshader")

const FAR := 60.0
const BASE_PITCH := 24.0

## Outline pass that works for orthographic and perspective cameras: depth is
## turned back into view-space metres with the inverse projection.
const OUTLINE_CODE := """
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, depth_test_disabled, cull_disabled, shadows_disabled, fog_disabled;

uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;
uniform vec4 color : source_color = vec4(0.035, 0.038, 0.05, 1.0);
uniform float threshold = 0.12;

void vertex() {
	POSITION = vec4(VERTEX.xy * 2.0, 0.0, 1.0);
}

float raw(vec2 uv) {
	return texture(depth_tex, uv).r;
}

float lin(vec2 uv, mat4 inv) {
	float d = raw(uv);
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	vec3 ndc = vec3(uv * 2.0 - 1.0, d * 2.0 - 1.0);
#else
	vec3 ndc = vec3(uv * 2.0 - 1.0, d);
#endif
	vec4 v = inv * vec4(ndc, 1.0);
	return -v.z / v.w;
}

bool is_bg(vec2 uv) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	return raw(uv) >= 0.99999;
#else
	return raw(uv) <= 0.00001;
#endif
}

void fragment() {
	vec2 px = 1.0 / VIEWPORT_SIZE;
	if (is_bg(SCREEN_UV)) {
		discard;
	}
	float d = lin(SCREEN_UV, INV_PROJECTION_MATRIX);
	float l = lin(SCREEN_UV - vec2(px.x, 0.0), INV_PROJECTION_MATRIX);
	float r = lin(SCREEN_UV + vec2(px.x, 0.0), INV_PROJECTION_MATRIX);
	float u = lin(SCREEN_UV - vec2(0.0, px.y), INV_PROJECTION_MATRIX);
	float b = lin(SCREEN_UV + vec2(0.0, px.y), INV_PROJECTION_MATRIX);
	float e = max(l + r - 2.0 * d, u + b - 2.0 * d);
	if (e < threshold) {
		discard;
	}
	ALBEDO = color.rgb;
	ALPHA = color.a;
}
"""

const RED := "e8352b"
const INK := "f1efea"
const PURPLE := "a855f7"

var _vp: SubViewport
var _cam: Camera3D
var _rig: Node3D
var _table: Node3D
var _car: CarModel3D
var _shadow: MeshInstance3D
var _outline: MeshInstance3D
var _lights: Array[DirectionalLight3D] = []
var _env: Environment

var _jobs: Array = []
var _out := ""
var _i := 0
var _phase := 0
var _wait := 0
var _job: Dictionary = {}
var _meta: Dictionary = {}
var _retries := 0


func _initialize() -> void:
	_out = ProjectSettings.globalize_path("res://").path_join("../brand/renders/_src").simplify_path()
	var jobs_path := ""
	var only := ""
	for a: String in OS.get_cmdline_user_args():
		if a.begins_with("jobs="):
			jobs_path = a.substr(5)
		elif a.begins_with("out="):
			_out = a.substr(4)
		elif a.begins_with("only="):
			only = a.substr(5)
	if jobs_path != "":
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(jobs_path))
		if parsed is Array:
			_jobs = parsed
		else:
			push_error("render_brand: could not read jobs from " + jobs_path)
	else:
		_jobs = _standard_jobs()
	if only != "":
		_jobs = _jobs.filter(func(j: Dictionary) -> bool: return String(j["name"]).contains(only))
	DirAccess.make_dir_recursive_absolute(_out)
	_build_stage()
	print("render_brand: %d jobs -> %s" % [_jobs.size(), _out])


## The default set: five angles in brand red, plus two colourways.
func _standard_jobs() -> Array:
	var red := {"primary": RED, "secondary": INK, "compound": "medium"}
	var white := {"primary": INK, "secondary": RED, "compound": "soft"}
	var purple := {"primary": PURPLE, "secondary": INK, "compound": "hard"}
	var angles := {
		"hero": {"yaw": -0.62, "pitch": 22.0, "steer": 0.14},
		"hero_left": {"yaw": PI + 0.62, "pitch": 22.0, "steer": -0.14},
		"rear34": {"yaw": 0.75, "pitch": 26.0},
		"side": {"yaw": 0.0, "pitch": 4.0},
		"top": {"yaw": PI / 2.0, "pitch": 90.0},
		"low_front": {"yaw": -1.12, "pitch": 6.0, "persp": true, "dist": 8.0, "steer": 0.2},
	}
	var jobs: Array = []
	for a: String in angles:
		var j: Dictionary = (angles[a] as Dictionary).duplicate()
		j.merge(red)
		j["name"] = "car_%s_red" % a
		j["ppm"] = 60.0
		j["shadow"] = true
		jobs.append(j)
	for c: Array in [["white", white], ["purple", purple]]:
		for a: String in ["hero", "hero_left", "rear34", "side"]:
			var j: Dictionary = (angles[a] as Dictionary).duplicate()
			j.merge(c[1])
			j["name"] = "car_%s_%s" % [a, c[0]]
			j["ppm"] = 60.0
			j["shadow"] = true
			jobs.append(j)
	return jobs


func _build_stage() -> void:
	_vp = SubViewport.new()
	_vp.own_world_3d = true
	_vp.transparent_bg = true
	_vp.msaa_3d = Viewport.MSAA_DISABLED
	_vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED
	_vp.positional_shadow_atlas_size = 0
	_vp.audio_listener_enable_3d = false
	_vp.gui_disable_input = true
	_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_vp.size = Vector2i(256, 256)
	root.add_child(_vp)

	_env = Environment.new()
	_env.background_mode = Environment.BG_CLEAR_COLOR
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_env.ambient_light_color = Color(0.36, 0.38, 0.46)
	_env.ambient_light_energy = 1.8
	_env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	_env.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED

	_cam = Camera3D.new()
	_cam.keep_aspect = Camera3D.KEEP_HEIGHT
	_cam.near = 0.1
	_cam.far = FAR
	_cam.environment = _env
	_cam.current = true
	_vp.add_child(_cam)

	# Lights as in CarShowcase (key left, cool fill right, warm rim from behind).
	# They sit on a rig that turns with the camera pitch, so every angle is lit
	# the way the showcase lights its default view.
	_rig = Node3D.new()
	_vp.add_child(_rig)
	_add_light(Vector3(-0.55, 0.8, 0.6), Color(1.0, 0.96, 0.9), 1.0)
	_add_light(Vector3(0.9, 0.3, 0.4), Color(0.55, 0.68, 0.98), 0.38)
	_add_light(Vector3(0.35, 0.5, -1.0), Color(1.0, 0.88, 0.78), 1.3)

	_table = Node3D.new()
	_vp.add_child(_table)
	var shadow_mat := ShaderMaterial.new()
	shadow_mat.shader = SHADOW_SHADER
	var plane := PlaneMesh.new()
	plane.size = Vector2(6.6, 2.8)
	_shadow = MeshInstance3D.new()
	_shadow.mesh = plane
	_shadow.material_override = shadow_mat
	_shadow.position.y = 0.004
	_shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_shadow.visible = false
	_table.add_child(_shadow)

	_car = CarScript.new()
	_table.add_child(_car)

	var outline_shader := Shader.new()
	outline_shader.code = OUTLINE_CODE
	var outline_mat := ShaderMaterial.new()
	outline_mat.shader = outline_shader
	outline_mat.render_priority = 100
	var quad := QuadMesh.new()
	quad.size = Vector2(1, 1)
	var outline := MeshInstance3D.new()
	outline.mesh = quad
	outline.material_override = outline_mat
	outline.extra_cull_margin = 16384.0
	outline.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	outline.position = Vector3(0, 0, -0.5)
	_cam.add_child(outline)
	_outline = outline


func _add_light(from: Vector3, c: Color, energy: float) -> void:
	var l := DirectionalLight3D.new()
	l.light_color = c
	l.light_energy = energy
	l.shadow_enabled = false
	l.transform = Transform3D(Basis.looking_at(-from.normalized(), Vector3.UP), Vector3.ZERO)
	_rig.add_child(l)
	_lights.append(l)


func _process(_delta: float) -> bool:
	if _wait > 0:
		_wait -= 1
		return false
	if _i >= _jobs.size():
		print("render_brand: done")
		return true
	match _phase:
		0:
			_job = _jobs[_i]
			_apply_job(_job)
			_phase = 1
			_wait = 40  # rake / wing flap settle, materials compile
		1:
			_frame_job(_job)
			_phase = 2
			_wait = 3
		2:
			# The window may stop drawing (minimised or covered): force a frame
			# and retry a few times if the car came out empty.
			RenderingServer.force_draw(false)
			if _empty() and _retries < 8:
				_retries += 1
				_wait = 4
				return false
			if _retries >= 8:
				push_warning("render_brand: %s rendered empty" % _job["name"])
			_retries = 0
			_save(String(_job["name"]))
			var f := FileAccess.open(_out.path_join(String(_job["name"]) + ".json"), FileAccess.WRITE)
			if f:
				f.store_string(JSON.stringify(_meta, "	"))
				f.close()
			if bool(_job.get("shadow", false)):
				_car.visible = false
				_shadow.visible = true
				_phase = 3
				_wait = 3
			else:
				_next()
		3:
			RenderingServer.force_draw(false)
			_save(String(_job["name"]) + "_shadow")
			_car.visible = true
			_shadow.visible = false
			_next()
	return false


func _next() -> void:
	_i += 1
	_phase = 0


func _apply_job(j: Dictionary) -> void:
	_car.set_parts(CarScript.DEFAULT_LOOK.duplicate().merged(j.get("look", {}), true))
	_car.set_colors(Color(String(j.get("primary", RED))), Color(String(j.get("secondary", INK))))
	_car.set_compound(String(j.get("compound", "medium")))
	_car.set_wing_open(bool(j.get("wing_open", false)))
	_car.steer = float(j.get("steer", 0.0))
	_car.ride_offset = 0.0
	_car.visible = true
	_shadow.visible = false
	_outline.visible = bool(j.get("outline", true))
	var e: Array = j.get("light_energy", [1.0, 0.38, 1.3])
	for k in 3:
		_lights[k].light_energy = float(e[k])
	_env.ambient_light_energy = float(j.get("ambient", 1.8))


## Car-local bounding box of everything visible.
func _car_box() -> AABB:
	var box := AABB()
	var first := true
	var inv := _car.global_transform.affine_inverse()
	for n: Node in _car.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if mi.mesh == null or not mi.is_visible_in_tree():
			continue
		var b: AABB = (inv * mi.global_transform) * mi.get_aabb()
		if first:
			box = b
			first = false
		else:
			box = box.merge(b)
	return box


func _frame_job(j: Dictionary) -> void:
	var yaw := float(j.get("yaw", -0.6))
	var pitch := deg_to_rad(clampf(float(j.get("pitch", BASE_PITCH)), -10.0, 90.0))
	var ppm := float(j.get("ppm", 60.0))
	var persp := bool(j.get("persp", false))
	var dist := float(j.get("dist", 10.0)) if persp else 25.0
	var margin := int(j.get("margin", 4))
	_table.rotation = Vector3(0, yaw, 0)
	_rig.rotation = Vector3(-(pitch - deg_to_rad(BASE_PITCH)), 0, 0)
	var box := _car_box()
	var target := box.get_center()
	if j.has("target"):
		var t: Array = j["target"]
		target = Vector3(float(t[0]), float(t[1]), float(t[2]))
	var rot := Basis(Vector3.UP, yaw)
	var tw := rot * target
	var dir := Vector3(0.0, sin(pitch), cos(pitch))
	var up := Vector3.UP if pitch < deg_to_rad(80.0) else Vector3(0, 0, -1)
	var pos := tw + dir * dist
	_cam.transform = Transform3D(Basis.looking_at(tw - pos, up), pos)
	var cam_inv := _cam.transform.affine_inverse()
	# Project the box corners and size the viewport around them, centred on the target.
	var hx := 0.0
	var hy := 0.0
	var f_px := ppm * dist
	for i in 8:
		var c: Vector3 = cam_inv * (rot * box.get_endpoint(i))
		var sx := c.x * ppm
		var sy := c.y * ppm
		if persp:
			sx = f_px * c.x / maxf(0.1, -c.z)
			sy = f_px * c.y / maxf(0.1, -c.z)
		hx = maxf(hx, absf(sx))
		hy = maxf(hy, absf(sy))
	var w := 2 * (ceili(hx) + margin)
	var h := 2 * (ceili(hy) + margin)
	_vp.size = Vector2i(w, h)
	if persp:
		_cam.projection = Camera3D.PROJECTION_PERSPECTIVE
		_cam.fov = rad_to_deg(2.0 * atan((h * 0.5) / f_px))
	else:
		_cam.projection = Camera3D.PROJECTION_ORTHOGONAL
		_cam.size = h / ppm
	var b := _cam.transform.basis
	_meta = {
		"w": w, "h": h, "yaw": yaw, "pitch": rad_to_deg(pitch), "ppm": ppm, "persp": persp, "f_px": f_px,
		"origin": [pos.x, pos.y, pos.z], "right": [b.x.x, b.x.y, b.x.z], "up": [b.y.x, b.y.y, b.y.z],
		"back": [b.z.x, b.z.y, b.z.z], "target": [tw.x, tw.y, tw.z],
		"forward": [cos(yaw), 0.0, -sin(yaw)],
	}


func _empty() -> bool:
	var img := _vp.get_texture().get_image()
	if img == null or img.is_empty():
		return true
	return img.is_invisible()


func _save(name_: String) -> void:
	var img := _vp.get_texture().get_image()
	if img.get_format() != Image.FORMAT_RGBA8:
		img.convert(Image.FORMAT_RGBA8)
	var path := _out.path_join(name_ + ".png")
	var err := img.save_png(path)
	print("render_brand: %s %dx%d %s" % [path, img.get_width(), img.get_height(), "ok" if err == OK else "error %d" % err])
