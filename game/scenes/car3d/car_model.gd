class_name CarModel3D
extends Node3D
## A modern F1 car built procedurally from low-poly, flat-shaded meshes for the
## 3D car showcase (car_showcase.gd). Each part area is its own mesh group, so
## fitting a part rebuilds only that group. Concepts match game/data/parts.json
## and the 2D sprites (scenes/drive/car_view.gd).
##
## Axes: +X is forward (nose), +Y up, the car is symmetric about Z = 0 and the
## wheels stand on Y = 0. Real proportions: 5.6 m long, 2.0 m wide, 3.6 m
## wheelbase, 0.72 m wheels.

const Kit := preload("res://scenes/car3d/mesh_kit.gd")
const TOON := preload("res://scenes/car3d/toon.gdshader")
const OVERLAY := preload("res://scenes/car3d/overlay.gdshader")
const HALO := preload("res://scenes/car3d/halo.gdshader")

const AREAS: Array[String] = ["front_wing", "rear_wing", "sidepods", "floor", "suspension", "power_unit"]
const CONCEPTS := {
	"front_wing": ["outwash", "inwash", "highnose"],
	"rear_wing": ["highdf", "spoon", "beam"],
	"sidepods": ["downwash", "zeropod", "undercut"],
	"floor": ["low_rake", "high_rake", "venturi"],
	"suspension": ["pushrod", "pullrod"],
	"power_unit": ["torque", "topend", "efficiency"],
}
const DEFAULT_LOOK := {
	"front_wing": "outwash", "rear_wing": "highdf", "sidepods": "downwash",
	"floor": "low_rake", "suspension": "pushrod", "power_unit": "torque",
}

const RED := Color("e8352b")
const YELLOW := Color("f2c230")
const INK := Color("f1efea")
const BLUE := Color("5ec8e5")
const CARBON := Color("252933")
const COMPOUND_COLORS := {
	"soft": Color("e8352b"), "medium": Color("f2c230"), "hard": Color("f1efea"),
	"inter": Color("43b047"), "wet": Color("3d7fe0"),
}

const FRONT_AXLE := 1.65
const REAR_AXLE := -1.95
const WHEEL_R := 0.36
const FRONT_TRACK := 0.85
const REAR_TRACK := 0.80
const FRONT_TYRE_W := 0.30
const REAR_TYRE_W := 0.40

## Point each part group scales and flashes around.
const PIVOTS := {
	"body": Vector3.ZERO, "front_wing": Vector3(2.45, 0.22, 0), "rear_wing": Vector3(-2.55, 0.72, 0),
	"sidepods": Vector3(-0.4, 0.4, 0), "floor": Vector3(-0.6, 0.05, 0), "power_unit": Vector3(-1.5, 0.6, 0),
	"suspension": Vector3.ZERO,
}
## Chassis pitch (nose down, degrees) and ride height change per floor concept.
const RAKE := {"low_rake": 0.0, "high_rake": 2.0, "venturi": 0.3}
const RIDE := {"low_rake": 0.0, "high_rake": 0.02, "venturi": -0.015}

## Concept per area, as in parts.json. Use set_parts() to change it.
var look := DEFAULT_LOOK.duplicate()
## Colour of the hover highlight (tint and rim).
var highlight_color := INK
var primary := RED
var secondary := INK
var compound := "medium"
var wing_open := false
## Front wheel steering angle (radians).
var steer := 0.0
## Extra chassis height on its suspension (metres), for idle bob.
var ride_offset := 0.0
## Triangles in the current model (for budgeting).
var triangles := 0

var _mats := {}
var _chassis: Node3D
var _groups := {}
var _tris := {}
var _wheels: Array[Node3D] = []
var _flap: Node3D
var _flap_delta := 0.0
var _flap_t := 0.0
var _rake := 0.0
var _rake_target := 0.0
var _ride := 0.0
var _fx := {}
var _overlays := {}
var _overlay_mats := {}
var _halo_mats := {}
var _halos := {}
var _susp_key := Vector2(INF, INF)
var _highlight := ""
var _time := 0.0
var _bounce := -1.0
var _shake := -1.0
var _built := false


func _init() -> void:
	_make_materials()


func _ready() -> void:
	_build_all()


# ---- API ----

## Fit concepts per area, e.g. {"front_wing": "inwash", "floor": "venturi"}.
## Missing areas keep their current concept; unknown concepts (e.g. "baseline")
## fall back to the area's standard look. Only changed groups are rebuilt.
func set_parts(new_look: Dictionary) -> void:
	var changed: Array[String] = []
	for area in AREAS:
		if not new_look.has(area):
			continue
		var c := String(new_look[area])
		if not (CONCEPTS[area] as Array).has(c):
			c = String(DEFAULT_LOOK[area])
		if c != String(look[area]):
			look[area] = c
			changed.append(area)
	if not _built:
		return
	for area in changed:
		_build_group(area)
	if changed.has("floor"):
		_rake_target = float(RAKE[look["floor"]])
	_count()


func set_colors(primary_color: Color, secondary_color: Color) -> void:
	primary = primary_color
	secondary = secondary_color
	_apply_colors()


## "soft" (red), "medium" (yellow), "hard" (white), "inter", "wet".
func set_compound(c: String) -> void:
	compound = c if COMPOUND_COLORS.has(c) else "medium"
	_apply_colors()


## Straight Mode / DRS: the rear-wing flap swings flat.
func set_wing_open(open: bool) -> void:
	wing_open = open


## Short "part fitted" animation on an area: the part pops in with a flash.
func fit_part(area: String, flash: Color = YELLOW) -> void:
	if area == "suspension":
		_bounce = 0.0
	elif area == "power_unit":
		_shake = 0.0
	_fx[area] = {"t": 0.0, "color": flash}


## Tints an area while hovered; "" for none.
func highlight(area: String) -> void:
	_highlight = area


## Where an area sits on the car (local space), e.g. for leader lines.
func area_point(area: String) -> Vector3:
	match area:
		"suspension":
			return Vector3(FRONT_AXLE, 0.4, FRONT_TRACK - 0.2)
		"floor":
			return Vector3(-0.4, 0.06, 0.9)
		"sidepods":
			return Vector3(-0.2, 0.5, 0.7)
	return PIVOTS.get(area, Vector3.ZERO)


# ---- materials ----

func _make_materials() -> void:
	for key: String in ["paint", "accent", "carbon", "carbon_hi", "tyre", "stripe", "rim", "metal", "visor", "dark", "glow", "gold", "light"]:
		var m := ShaderMaterial.new()
		m.shader = TOON
		_mats[key] = m
	_apply_colors()


func _set_mat(key: String, c: Color, gloss: float = 0.0, emit: Color = Color.BLACK, energy: float = 0.0) -> void:
	var m: ShaderMaterial = _mats[key]
	m.set_shader_parameter("albedo", c)
	m.set_shader_parameter("gloss", gloss)
	m.set_shader_parameter("emission", emit)
	m.set_shader_parameter("emission_energy", energy)


func _apply_colors() -> void:
	_set_mat("paint", primary, 0.35)
	_set_mat("accent", secondary, 0.2)
	_set_mat("carbon", CARBON, 0.18)
	_set_mat("carbon_hi", CARBON.lightened(0.1), 0.18)
	_set_mat("tyre", Color("1c1d21"))
	_set_mat("stripe", COMPOUND_COLORS.get(compound, YELLOW), 0.0, COMPOUND_COLORS.get(compound, YELLOW), 0.25)
	_set_mat("rim", Color("3a3e48"), 0.4)
	_set_mat("metal", Color("a3a8b2"), 0.8)
	_set_mat("visor", Color("16181f"), 1.2)
	_set_mat("dark", Color("0d0e12"))
	_set_mat("glow", Color("12313a"), 0.0, BLUE, 1.6)
	_set_mat("gold", Color("e6b440"), 0.9)
	_set_mat("light", Color("2a0a09"), 0.0, RED, 1.4)


# ---- building ----

func _build_all() -> void:
	_chassis = Node3D.new()
	_chassis.name = "Chassis"
	add_child(_chassis)
	_rake = float(RAKE[look["floor"]])
	_rake_target = _rake
	_ride = float(RIDE[look["floor"]])
	_build_group("body")
	for area in AREAS:
		_build_group(area)
	_build_wheels()
	_built = true
	_apply_chassis()
	_count()


func _count() -> void:
	triangles = 0
	for k: String in _tris:
		triangles += int(_tris[k])


func _holder(area: String) -> Node3D:
	if _groups.has(area):
		return _groups[area]
	var h := Node3D.new()
	h.name = area
	h.position = PIVOTS[area]
	# Suspension joins the (pitched) chassis to the (level) wheels, so it lives
	# in the car's own space and is rebuilt when the rake changes.
	if area == "suspension":
		add_child(h)
	else:
		_chassis.add_child(h)
	_groups[area] = h
	return h


func _new_kit(origin: Vector3) -> Kit:
	var k := Kit.new()
	k.xf = Transform3D(Basis.IDENTITY, -origin)
	return k


func _add_mesh(parent: Node3D, k: Kit, name_: String = "Mesh") -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.name = name_
	mi.mesh = k.commit(_mats)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)
	return mi


func _build_group(area: String) -> void:
	var h := _holder(area)
	for c in h.get_children():
		h.remove_child(c)
		c.free()
	var k := _new_kit(PIVOTS[area])
	var style := String(look.get(area, ""))
	match area:
		"body":
			_build_body(k)
		"front_wing":
			_build_front_wing(k, style)
		"rear_wing":
			_flap = null
			_build_rear_wing(k, h, style)
		"sidepods":
			_build_sidepods(k, style)
		"floor":
			_build_floor(k, style)
		"suspension":
			_build_suspension(k, style)
		"power_unit":
			_build_power_unit(k, style)
	_tris[area] = k.triangles
	_add_mesh(h, k)
	_halos.erase(area)
	if _overlays.has(area):
		_set_overlay(area, _overlays[area])


## Superellipse ring across the car (YZ plane) at station x.
static func _ring(x: float, hw: float, y_bot: float, y_top: float, n: int = 12, p: float = 2.6) -> PackedVector3Array:
	var r := PackedVector3Array()
	var mid := (y_bot + y_top) * 0.5
	var hh := (y_top - y_bot) * 0.5
	for i in n:
		var a := TAU * float(i) / n
		var c := cos(a)
		var s := sin(a)
		r.append(Vector3(x, mid + hh * signf(s) * pow(absf(s), 2.0 / p), hw * signf(c) * pow(absf(c), 2.0 / p)))
	return r


static func _mirror() -> Transform3D:
	return Transform3D(Basis.from_scale(Vector3(1, 1, -1)), Vector3.ZERO)


# Engine cover stations: x, half width, bottom, top.
const COVER := [
	[-0.12, 0.16, 0.58, 1.0], [-0.42, 0.30, 0.38, 0.98], [-0.90, 0.36, 0.30, 0.86],
	[-1.40, 0.28, 0.28, 0.70], [-1.85, 0.17, 0.30, 0.56], [-2.25, 0.09, 0.33, 0.46],
]


## Engine cover half width, bottom and top at station x (linear between stations).
static func _cover_at(x: float) -> Vector3:
	for i in COVER.size() - 1:
		var a: Array = COVER[i]
		var b: Array = COVER[i + 1]
		if x <= float(a[0]) and x >= float(b[0]):
			var t := (x - float(a[0])) / (float(b[0]) - float(a[0]))
			return Vector3(lerpf(a[1], b[1], t), lerpf(a[2], b[2], t), lerpf(a[3], b[3], t))
	var e: Array = COVER[0] if x > float(COVER[0][0]) else COVER[COVER.size() - 1]
	return Vector3(e[1], e[2], e[3])


## Height of the engine cover's surface at (x, z).
static func _cover_y(x: float, z: float) -> float:
	var c := _cover_at(x)
	var mid := (c.y + c.z) * 0.5
	var hh := (c.z - c.y) * 0.5
	var u := clampf(absf(z) / c.x, 0.0, 1.0)
	return mid + hh * pow(1.0 - pow(u, 2.6), 1.0 / 2.6)


func _build_body(k: Kit) -> void:
	# Survival cell, from the front bulkhead to behind the driver. The top faces
	# over the cockpit are dark: the opening.
	var st := [[1.30, 0.25, 0.22, 0.60], [0.82, 0.31, 0.12, 0.67], [0.72, 0.32, 0.11, 0.67],
		[0.05, 0.37, 0.10, 0.67], [-0.22, 0.39, 0.10, 0.66], [-0.45, 0.40, 0.10, 0.62]]
	var rings: Array[PackedVector3Array] = []
	for s: Array in st:
		rings.append(_ring(s[0], s[1], s[2], s[3]))
	var cockpit := func(seg: int, side: int) -> String:
		return "dark" if (seg == 2 or seg == 3) and (side == 2 or side == 3) else "paint"
	k.loft(rings, cockpit, "paint", "paint")
	# Cockpit: driver's helmet with visor and a stripe; headrest; halo.
	k.ellipsoid("accent", Vector3(0.07, 0.81, 0), Vector3(0.17, 0.15, 0.14), 8, 6)
	k.box("visor", Vector3(0.18, 0.83, 0), Vector3(0.08, 0.055, 0.22))
	k.box("paint", Vector3(0.05, 0.955, 0), Vector3(0.26, 0.025, 0.06))
	for s: float in [1.0, -1.0]:
		k.box("carbon", Vector3(-0.05, 0.71, 0.17 * s), Vector3(0.32, 0.07, 0.07))
	k.tube("carbon", PackedVector3Array([Vector3(0.84, 0.62, 0), Vector3(0.74, 0.83, 0), Vector3(0.64, 0.92, 0)]), 0.035)
	var halo := PackedVector3Array()
	for s: float in [-1.0, 1.0]:
		var side := [Vector3(-0.26, 0.64, 0.30), Vector3(-0.2, 0.78, 0.30), Vector3(-0.04, 0.89, 0.29),
			Vector3(0.18, 0.925, 0.27), Vector3(0.40, 0.935, 0.22), Vector3(0.56, 0.935, 0.12)]
		if s > 0.0:
			side.reverse()
		for p: Vector3 in side:
			halo.append(Vector3(p.x, p.y, p.z * s))
		if s < 0.0:
			halo.append(Vector3(0.64, 0.93, 0))
	k.tube("carbon", halo, 0.026)
	# Mirrors on stalks.
	for s: float in [1.0, -1.0]:
		k.rod("carbon", Vector3(0.66, 0.6, 0.30 * s), Vector3(0.6, 0.73, 0.52 * s), 0.025, 0.02)
		k.box("paint", Vector3(0.6, 0.75, 0.57 * s), Vector3(0.08, 0.07, 0.16))
		k.box("metal", Vector3(0.555, 0.75, 0.57 * s), Vector3(0.012, 0.05, 0.13))
	# Gearbox and rear crash structure, with the rain light.
	var gb: Array[PackedVector3Array] = [_ring(-1.55, 0.17, 0.16, 0.45, 8), _ring(-2.2, 0.11, 0.24, 0.43, 8), _ring(-2.62, 0.06, 0.30, 0.40, 8)]
	k.loft(gb, "carbon", "carbon", "carbon")
	k.box("light", Vector3(-2.63, 0.35, 0), Vector3(0.03, 0.06, 0.1))


# ---- front wing (and nose) ----

## Aerofoil ring in the XY plane at z. angle is trailing edge up, in degrees.
static func _foil(z: float, x_le: float, y: float, chord: float, angle: float, t: float) -> PackedVector3Array:
	var a := deg_to_rad(angle)
	var d := Vector2(-cos(a), sin(a))
	var nn := Vector2(sin(a), cos(a))
	var le := Vector2(x_le, y)
	var pts := [le, le + d * chord * 0.3 + nn * t * 0.55, le + d * chord, le + d * chord * 0.35 - nn * t * 0.45]
	var r := PackedVector3Array()
	for p: Vector2 in pts:
		r.append(Vector3(p.x, p.y, z))
	return r


## One wing element across the span; fn(u) -> [x_le, y, chord, angle, thickness],
## u = 0 at the centre line and 1 at the tips.
func _element(k: Kit, m: String, half_span: float, fn: Callable, stations: int = 9, z_from: float = -1.0, z_to: float = 1.0) -> void:
	var rings: Array[PackedVector3Array] = []
	for i in stations:
		var z := lerpf(z_from, z_to, float(i) / (stations - 1)) * half_span
		var p: Array = fn.call(absf(z) / half_span)
		rings.append(_foil(z, p[0], p[1], p[2], p[3], p[4]))
	k.loft(rings, m, m, m)


## Endplate lofted bottom to top; rows are [y, x_front, x_back, z].
func _endplate(k: Kit, m: String, rows: Array, t: float) -> void:
	var rings: Array[PackedVector3Array] = []
	for r: Array in rows:
		var y: float = r[0]
		var z: float = r[3]
		rings.append(PackedVector3Array([Vector3(r[1], y, z - t * 0.5), Vector3(r[1], y, z + t * 0.5),
			Vector3(r[2], y, z + t * 0.5), Vector3(r[2], y, z - t * 0.5)]))
	k.loft(rings, m, m, m)


func _build_front_wing(k: Kit, style: String) -> void:
	# Nose
	var nose: Array = []
	match style:
		"highnose":
			nose = [[1.30, 0.25, 0.22, 0.60], [1.80, 0.18, 0.34, 0.57], [2.22, 0.12, 0.38, 0.53], [2.46, 0.07, 0.40, 0.50], [2.5, 0.03, 0.43, 0.48]]
		"inwash":
			nose = [[1.30, 0.25, 0.22, 0.60], [1.80, 0.17, 0.22, 0.50], [2.30, 0.10, 0.13, 0.35], [2.70, 0.05, 0.10, 0.24], [2.76, 0.02, 0.12, 0.21]]
		_:
			nose = [[1.30, 0.25, 0.22, 0.60], [1.80, 0.21, 0.21, 0.51], [2.30, 0.16, 0.13, 0.37], [2.66, 0.12, 0.10, 0.27], [2.72, 0.08, 0.11, 0.24]]
	var rings: Array[PackedVector3Array] = []
	for s: Array in nose:
		rings.append(_ring(s[0], s[1], s[2], s[3], 10))
	var last := nose.size() - 2
	var tip := func(seg: int, _side: int) -> String: return "accent" if seg == last else "paint"
	k.loft(rings, tip, "paint", "accent")
	# Wing elements
	match style:
		"inwash":
			# Three elements swept back toward the tips, dropping outboard: air turned inboard.
			_element(k, "carbon_hi", 0.92, func(u: float) -> Array: return [2.80 - 0.12 * u, 0.075, 0.24, 4.0, 0.035])
			_element(k, "paint", 0.92, func(u: float) -> Array: return [2.60 - 0.22 * u, 0.13 - 0.03 * u, 0.15, 22.0 - 8.0 * u, 0.03])
			_element(k, "paint", 0.92, func(u: float) -> Array: return [2.47 - 0.30 * u, 0.185 - 0.06 * u, 0.12, 34.0 - 12.0 * u, 0.028])
			for s: float in [1.0, -1.0]:
				_endplate(k, "carbon", [[0.03, 2.84, 2.40, 0.93 * s], [0.17, 2.74, 2.36, 0.91 * s]], 0.025)
		"highnose":
			# Flat wing hung under the raised nose on two pylons.
			_element(k, "carbon_hi", 0.94, func(u: float) -> Array: return [2.80 - 0.03 * u, 0.08 + 0.03 * u, 0.25, 3.0, 0.035])
			_element(k, "paint", 0.94, func(u: float) -> Array: return [2.58 - 0.03 * u, 0.13 + 0.05 * u, 0.14, 16.0 + 8.0 * u, 0.03])
			_element(k, "paint", 0.94, func(u: float) -> Array: return [2.46 - 0.03 * u, 0.18 + 0.07 * u, 0.11, 28.0 + 8.0 * u, 0.028])
			for s: float in [1.0, -1.0]:
				k.slab_xy("carbon", PackedVector2Array([Vector2(2.42, 0.44), Vector2(2.30, 0.42), Vector2(2.52, 0.11), Vector2(2.66, 0.11)]), 0.09 * s, 0.03)
				_endplate(k, "paint", [[0.03, 2.86, 2.30, 0.95 * s], [0.28, 2.74, 2.30, 0.95 * s], [0.31, 2.70, 2.34, 0.99 * s]], 0.025)
		_:
			# Outwash: four elements rising steeply outboard, big endplates curling out.
			_element(k, "carbon_hi", 0.93, func(u: float) -> Array: return [2.82 - 0.05 * u, 0.07 + 0.02 * u, 0.25, 4.0, 0.035])
			_element(k, "paint", 0.93, func(u: float) -> Array: return [2.60 - 0.04 * u, 0.11 + 0.07 * u, 0.15, 18.0 + 10.0 * u, 0.03])
			_element(k, "paint", 0.93, func(u: float) -> Array: return [2.47 - 0.04 * u, 0.15 + 0.11 * u, 0.12, 30.0 + 12.0 * u, 0.028])
			_element(k, "paint", 0.93, func(u: float) -> Array: return [2.36 - 0.04 * u, 0.19 + 0.15 * u, 0.10, 42.0 + 12.0 * u, 0.026])
			for s: float in [1.0, -1.0]:
				_endplate(k, "paint", [[0.03, 2.88, 2.22, 0.94 * s], [0.24, 2.82, 2.20, 0.96 * s], [0.38, 2.70, 2.20, 1.02 * s], [0.42, 2.62, 2.26, 1.06 * s]], 0.025)
				k.box("accent", Vector3(2.55, 0.035, 0.94 * s), Vector3(0.64, 0.03, 0.05))


# ---- rear wing ----

func _build_rear_wing(k: Kit, h: Node3D, style: String) -> void:
	var span := 0.5
	var main: Callable
	var flap: Callable
	var angles := Vector2(44.0, 8.0)  # flap angle closed, open (Straight Mode)
	var top := 1.0
	var bottom := 0.44
	match style:
		"spoon":
			# Spoon: the elements dip deep in the middle and stay shallow at the tips.
			main = func(u: float) -> Array:
				var d := 1.0 - u * u
				return [-2.33, 0.90 - 0.18 * d, 0.21 + 0.11 * d, 5.0 + 5.0 * d, 0.045]
			flap = func(u: float) -> Array:
				var d := 1.0 - u * u
				return [-2.53 - 0.08 * d, 0.95 - 0.17 * d, 0.13, 18.0, 0.03]
			angles = Vector2(18.0, 3.0)
			top = 0.95
		"beam":
			# Smaller top wing; the big beam wing below does the work.
			main = func(_u: float) -> Array: return [-2.38, 0.88, 0.18, 6.0, 0.04]
			flap = func(_u: float) -> Array: return [-2.53, 0.93, 0.12, 24.0, 0.028]
			angles = Vector2(24.0, 4.0)
			top = 0.98
			bottom = 0.3
		_:
			# High downforce: deep mainplane, steep flap, tall endplates.
			main = func(_u: float) -> Array: return [-2.27, 0.78, 0.32, 12.0, 0.055]
			flap = func(_u: float) -> Array: return [-2.55, 0.85, 0.27, 46.0, 0.04]
			angles = Vector2(46.0, 8.0)
			top = 1.08
	_element(k, "paint", span, main, 9 if style == "spoon" else 5)
	for s: float in [1.0, -1.0]:
		var pts := PackedVector2Array([Vector2(-2.26, bottom + 0.06), Vector2(-2.26, top - 0.08), Vector2(-2.36, top),
			Vector2(-2.86, top), Vector2(-2.86, bottom + 0.2), Vector2(-2.62, bottom)])
		if style == "spoon":
			pts = PackedVector2Array([Vector2(-2.26, bottom + 0.06), Vector2(-2.26, top - 0.12), Vector2(-2.4, top),
				Vector2(-2.7, top), Vector2(-2.86, top - 0.1), Vector2(-2.86, bottom + 0.2), Vector2(-2.62, bottom)])
		k.slab_xy("carbon", pts, (span + 0.015) * s, 0.03)
		k.box("accent", Vector3(-2.6 if style != "spoon" else -2.56, top - 0.012, (span + 0.015) * s), Vector3(0.5 if style != "spoon" else 0.3, 0.025, 0.04))
		# Central pylons from the crash structure.
		k.slab_xy("carbon", PackedVector2Array([Vector2(-2.38, 0.40), Vector2(-2.30, 0.76), Vector2(-2.40, 0.78), Vector2(-2.52, 0.40)]), 0.05 * s, 0.025)
	if style == "beam":
		# The beam wing: two big painted elements low between the endplates,
		# split around the exhaust.
		for s: float in [1.0, -1.0]:
			var z0 := 0.16 * s
			var z1 := (span - 0.01) * s
			for e: Array in [[-2.38, 0.42, 0.22, 8.0, 0.045], [-2.62, 0.5, 0.17, 30.0, 0.035]]:
				var rings: Array[PackedVector3Array] = [_foil(z0, e[0], e[1], e[2], e[3], e[4]), _foil(z1, e[0], e[1], e[2], e[3], e[4])]
				k.loft(rings, "paint", "paint", "paint")
			k.box("accent", Vector3(-2.8, 0.58, z1 * 0.6), Vector3(0.02, 0.025, 0.3))
	# The flap pivots on its trailing edge (where the DRS actuator hinges), and
	# swings flat in Straight Mode.
	var tip: Array = flap.call(1.0)
	var a := deg_to_rad(float(tip[3]))
	var hinge := Vector3(float(tip[0]) - cos(a) * float(tip[2]), float(tip[1]) + sin(a) * float(tip[2]), 0)
	var fk := _new_kit(hinge)
	_element(fk, "paint", span, flap, 9 if style == "spoon" else 5)
	fk.box("accent", Vector3(hinge.x - 0.005, hinge.y, 0), Vector3(0.02, 0.025, span * 2.0))
	_flap = Node3D.new()
	_flap.name = "Flap"
	_flap.position = hinge - PIVOTS["rear_wing"]
	h.add_child(_flap)
	_add_mesh(_flap, fk)
	_flap_delta = deg_to_rad(angles.x - angles.y)
	_tris["rear_wing_flap"] = fk.triangles

# ---- sidepods ----

## Sidepod section: [x, z_inner, z_outer, y_bottom, y_top, undercut].
static func _pod_ring(s: Array) -> PackedVector3Array:
	var x: float = s[0]
	var zi: float = s[1]
	var zo: float = s[2]
	var yb: float = s[3]
	var yt: float = s[4]
	var under: float = s[5]
	var r := minf(0.09, (yt - yb) * 0.3)
	var pts := [
		Vector2(yt - 0.02, zi), Vector2(yt, zi + (zo - zi) * 0.45), Vector2(yt - r * 0.3, zo - r * 0.6),
		Vector2(yt - r, zo), Vector2(yb + (yt - yb) * 0.45, zo - under * 0.2), Vector2(yb + 0.02, zo - under),
		Vector2(yb, zi + 0.04), Vector2(yb + 0.06, zi),
	]
	var out := PackedVector3Array()
	for p: Vector2 in pts:
		out.append(Vector3(x, p.x, p.y))
	return out


func _build_sidepods(k: Kit, style: String) -> void:
	var st: Array = []
	match style:
		"zeropod":
			# Almost no pod: a narrow slot inlet and bodywork hugging the chassis.
			st = [[0.40, 0.28, 0.44, 0.40, 0.60, 0.0], [0.25, 0.28, 0.46, 0.26, 0.60, 0.02], [-0.4, 0.28, 0.46, 0.18, 0.56, 0.03],
				[-1.1, 0.26, 0.42, 0.14, 0.44, 0.03], [-1.7, 0.2, 0.3, 0.14, 0.24, 0.0]]
		"undercut":
			# Wide letterbox inlet over a deep undercut that feeds the floor edge.
			st = [[0.74, 0.28, 0.90, 0.36, 0.64, 0.3], [0.50, 0.28, 0.92, 0.25, 0.66, 0.42], [-0.05, 0.28, 0.88, 0.2, 0.64, 0.4],
				[-0.6, 0.28, 0.72, 0.16, 0.52, 0.26], [-1.2, 0.26, 0.48, 0.14, 0.34, 0.09], [-1.55, 0.22, 0.32, 0.14, 0.24, 0.02]]
		_:
			# Downwash: a tall inlet, then a long steep ramp down to the floor.
			st = [[0.62, 0.28, 0.74, 0.25, 0.62, 0.1], [0.40, 0.28, 0.80, 0.2, 0.64, 0.14], [0.0, 0.28, 0.78, 0.17, 0.58, 0.16],
				[-0.5, 0.28, 0.66, 0.15, 0.40, 0.13], [-1.0, 0.26, 0.50, 0.14, 0.27, 0.07], [-1.6, 0.2, 0.32, 0.14, 0.19, 0.0]]
	var base := k.xf
	for s: float in [1.0, -1.0]:
		k.xf = base if s > 0.0 else base * _mirror()
		var rings: Array[PackedVector3Array] = []
		for row: Array in st:
			rings.append(_pod_ring(row))
		var stripe := func(_seg: int, side: int) -> String: return "accent" if side == 3 and style != "zeropod" else "paint"
		k.loft(rings, stripe, "", "paint")
		# Inlet: a painted lip around a recessed dark opening.
		var front := rings[0]
		var c := Kit.centroid(front)
		var inner := PackedVector3Array()
		for p: Vector3 in front:
			var q := c + (p - c) * Vector3(0.0, 0.74, 0.8)
			inner.append(Vector3(p.x - 0.04, q.y, q.z))
		k.bridge("paint", front, inner, Vector3.RIGHT)
		k.cap("dark", inner, Vector3.RIGHT)
		match style:
			"undercut":
				# Cooling louvres on top of the pod.
				for i in 4:
					k.box("dark", Vector3(-0.18 - i * 0.1, 0.645 - i * 0.012, 0.62), Vector3(0.035, 0.02, 0.2))
			"zeropod":
				# A small blade of a wing on the flank, where the pod used to be.
				k.slab_xy("carbon", PackedVector2Array([Vector2(0.3, 0.5), Vector2(-0.5, 0.48), Vector2(-0.5, 0.45), Vector2(0.3, 0.46)]), 0.52, 0.02)
	k.xf = base


# ---- floor ----

func _build_floor(k: Kit, style: String) -> void:
	var y := 0.015 if style == "venturi" else 0.03
	var t := 0.035
	var right: Array[Vector2] = [Vector2(1.02, 0.28), Vector2(0.82, 0.56), Vector2(0.55, 0.92), Vector2(-1.25, 0.94), Vector2(-1.5, 0.6), Vector2(-1.62, 0.5)]
	var poly := PackedVector2Array()
	for p: Vector2 in right:
		poly.append(p)
	for i in range(right.size() - 1, -1, -1):
		poly.append(Vector2(right[i].x, -right[i].y))
	k.slab_xz("carbon", poly, y + t * 0.5, t)
	var top := y + t
	# Diffuser: [rear x, rear height, strakes, strake material]
	var dx := -2.36
	var dh := 0.26
	var strakes := [0.2]
	var sm := "carbon_hi"
	match style:
		"high_rake":
			dx = -2.54
			dh = 0.5
			strakes = [0.12, 0.26, 0.4]
			sm = "paint"
		"venturi":
			dx = -2.45
			dh = 0.34
			strakes = [0.16, 0.34]
			sm = "paint"
	var x0 := -1.6
	k.rod("carbon", Vector3(x0, top, 0), Vector3(dx, dh, 0), 1.0, 0.03)
	for s: float in [1.0, -1.0]:
		k.slab_xy("carbon", PackedVector2Array([Vector2(x0, y), Vector2(x0, top + 0.05), Vector2(dx, dh + 0.06), Vector2(dx, dh * 0.3)]), 0.5 * s, 0.025)
		for z: float in strakes:
			k.slab_xy(sm, PackedVector2Array([Vector2(x0 - 0.15, top), Vector2(dx + 0.02, dh), Vector2(dx + 0.02, maxf(top, dh * 0.3))]), z * s, 0.02)
		match style:
			"low_rake":
				# Flat floor with a clean painted edge.
				k.rod("paint", Vector3(0.55, top + 0.015, 0.915 * s), Vector3(-1.25, top + 0.015, 0.93 * s), 0.035, 0.03)
			"high_rake":
				# Edge fins at the front corners and a stepped edge.
				for fx: float in [0.48, 0.2]:
					k.slab_xy("paint", PackedVector2Array([Vector2(fx, top), Vector2(fx - 0.06, top + 0.18), Vector2(fx - 0.22, top + 0.18), Vector2(fx - 0.24, top)]), 0.86 * s, 0.03)
				k.rod("carbon_hi", Vector3(0.0, top + 0.03, 0.93 * s), Vector3(-1.2, top + 0.03, 0.935 * s), 0.03, 0.06)
			"venturi":
				# Tunnel fences at the inlets and a curled edge wing.
				for z0: float in [0.3, 0.42, 0.54, 0.66]:
					var a := Vector3(1.0 - (z0 - 0.3) * 0.5, top + 0.06, z0 * s)
					var b := Vector3(0.62 - (z0 - 0.3) * 0.4, top + 0.07, (z0 + 0.1) * s)
					k.rod("paint", a, b, 0.025, 0.17)
				var scroll: Array[PackedVector3Array] = []
				for e: Array in [[0.5, 0.06], [-0.3, 0.13], [-1.15, 0.08]]:
					var x: float = e[0]
					var hgt: float = e[1]
					scroll.append(PackedVector3Array([Vector3(x, top, 0.925 * s), Vector3(x, top, 0.955 * s),
						Vector3(x, top + hgt, 0.93 * s), Vector3(x, top + hgt * 0.9, 0.88 * s)]))
				k.loft(scroll, "paint", "paint", "paint")


# ---- suspension ----

func _build_suspension(k: Kit, style: String) -> void:
	var cx := _chassis_xf()
	_susp_key = Vector2(_rake, _ride + ride_offset_total())
	var pull := style == "pullrod"
	for s: float in [1.0, -1.0]:
		for front: bool in [true, false]:
			var ax := FRONT_AXLE if front else REAR_AXLE
			var zo := (FRONT_TRACK - FRONT_TYRE_W * 0.5 - 0.05) if front else (REAR_TRACK - REAR_TYRE_W * 0.5 - 0.05)
			var zi := 0.2 if front else 0.13
			var spread := 0.32 if front else 0.28
			var lo := Vector3(ax, 0.17, zo * s)
			var uo := Vector3(ax - 0.03, 0.55, (zo - 0.02) * s)
			var mat := "carbon"
			# Wishbones: two legs each to the chassis (front) or gearbox (rear).
			for leg: float in [1.0, -1.0]:
				k.rod(mat, lo, cx * Vector3(ax + spread * leg, 0.21, zi * s), 0.035, 0.02)
				k.rod(mat, uo, cx * Vector3(ax + spread * leg * 0.85, 0.47, (zi - 0.02) * s), 0.035, 0.02)
			# Steering / toe link.
			k.rod(mat, Vector3(ax + (0.12 if front else -0.18), 0.34, zo * s), cx * Vector3(ax + (0.14 if front else -0.2), 0.34, zi * s), 0.025, 0.02)
			# Upright, inside the wheel.
			k.box("carbon_hi", Vector3(ax, 0.36, (zo + 0.02) * s), Vector3(0.12, 0.42, 0.05))
			# Push rod: low outboard to a rocker high on the chassis. Pull rod: the other way round.
			var a := Vector3(ax - 0.02, 0.2, (zo - 0.04) * s) if not pull else Vector3(ax - 0.02, 0.52, (zo - 0.05) * s)
			var b := cx * (Vector3(ax - 0.16, 0.6 if front else 0.5, (zi - 0.04) * s) if not pull else Vector3(ax - 0.16, 0.16, zi * s))
			k.rod("accent", a, b, 0.055, 0.055)
			if front and not pull:
				# Rocker fairing on top of the chassis.
				k.box("carbon_hi", cx * Vector3(ax - 0.18, 0.585, 0.1 * s), Vector3(0.16, 0.05, 0.1), cx.basis)
			if pull:
				k.box("carbon_hi", cx * Vector3(ax - 0.18, 0.16, (zi - 0.02) * s), Vector3(0.16, 0.06, 0.08), cx.basis)


# ---- power unit ----

func _build_power_unit(k: Kit, style: String) -> void:
	# The engine cover and airbox belong to the power unit, so fitting one
	# flashes the whole cover. Dark intake over the driver's head, T-cam, fin.
	var cover: Array[PackedVector3Array] = []
	for c: Array in COVER:
		cover.append(_ring(c[0], c[1], c[2], c[3]))
	k.loft(cover, "paint", "paint", "carbon")
	var intake := Vector3(0.03, 0.15 if style == "topend" else 0.11, 0.17 if style == "topend" else 0.15)
	k.box("dark", Vector3(-0.115, 0.89, 0), intake)
	k.box("carbon", Vector3(-0.2, 1.01, 0), Vector3(0.07, 0.04, 0.16))
	k.slab_xy("paint", PackedVector2Array([Vector2(-0.42, 0.93), Vector2(-0.80, 1.0), Vector2(-1.98, 0.80),
		Vector2(-2.08, 0.47), Vector2(-1.4, 0.66), Vector2(-0.9, 0.82)]), 0.0, 0.025)
	var r := 0.05
	var length := 0.22
	if style == "torque":
		r = 0.075
		length = 0.3
	var ex := Vector3(-2.22, 0.475, 0)
	k.cyl("metal", ex, ex + Vector3(-length, 0.0, 0), r, 10, "metal")
	k.disc("dark", ex + Vector3(-length - 0.003, 0, 0), Vector3.LEFT, r * 0.7, 10)
	match style:
		"torque":
			# Big exhaust with a heat-tinted collar, twin wastegates and gold heat
			# shielding over the hot end of the engine cover.
			k.cyl("gold", ex + Vector3(-length + 0.08, 0, 0), ex + Vector3(-length + 0.02, 0, 0), r + 0.018, 10, "gold")
			for s: float in [1.0, -1.0]:
				k.cyl("gold", Vector3(-2.18, 0.42, 0.11 * s), Vector3(-2.42, 0.44, 0.13 * s), 0.025, 6, "dark")
				_cover_patch(k, "gold", -1.32, -2.06, 0.04 * s, 0.17 * s)
		"topend":
			# Extra cooling: louvres down the engine cover and "ear" inlets by the airbox.
			for s: float in [1.0, -1.0]:
				for i in 7:
					var x := -0.95 - i * 0.085
					for zz: float in [0.1, 0.2]:
						k.box("dark", Vector3(x, _cover_y(x, zz) + 0.006, zz * s), Vector3(0.04, 0.03, 0.085))
				k.box("paint", Vector3(-0.45, 0.93, 0.25 * s), Vector3(0.22, 0.1, 0.09))
				k.box("dark", Vector3(-0.335, 0.93, 0.25 * s), Vector3(0.012, 0.075, 0.065))
		"efficiency":
			# Glowing battery / ERS vents along the engine cover and behind the airbox.
			for s: float in [1.0, -1.0]:
				for x: float in [-0.9, -1.13, -1.36, -1.59]:
					var c := _cover_at(x)
					k.box("glow", Vector3(x, (c.y + c.z) * 0.5 + 0.03, (c.x - 0.006) * s), Vector3(0.2, 0.06, 0.035), Basis(Vector3.UP, -0.15 * s))
			for i in 4:
				var x := -0.55 - i * 0.075
				k.box("glow", Vector3(x, _cover_y(x, 0.0) + 0.006, 0), Vector3(0.035, 0.025, 0.3))


## A thin panel laid on the engine cover's surface between two stations.
func _cover_patch(k: Kit, m: String, x0: float, x1: float, z0: float, z1: float, lift: float = 0.012) -> void:
	var rows: Array[PackedVector3Array] = []
	for i in 5:
		var x := lerpf(x0, x1, i / 4.0)
		var row := PackedVector3Array()
		for j in 3:
			var z := lerpf(z0, z1, j / 2.0)
			row.append(Vector3(x, _cover_y(x, z) + lift, z))
		rows.append(row)
	k.patch(m, rows, Vector3.UP)


# ---- wheels ----

func _build_wheels() -> void:
	for w in _wheels:
		w.free()
	_wheels.clear()
	for front: bool in [true, false]:
		for s: float in [1.0, -1.0]:
			var n := Node3D.new()
			n.name = ("Front" if front else "Rear") + ("R" if s > 0.0 else "L")
			n.position = Vector3(FRONT_AXLE if front else REAR_AXLE, WHEEL_R, (FRONT_TRACK if front else REAR_TRACK) * s)
			add_child(n)
			var k := Kit.new()
			if s < 0.0:
				k.xf = _mirror()
			_wheel(k, FRONT_TYRE_W if front else REAR_TYRE_W)
			_add_mesh(n, k)
			_tris["wheel%d" % _wheels.size()] = k.triangles
			_wheels.append(n)


## One wheel at the origin, axle along Z, outer face toward +Z.
func _wheel(k: Kit, width: float) -> void:
	var h := width * 0.5
	var r := WHEEL_R
	var prof := PackedVector2Array([Vector2(0.215, -h), Vector2(0.255, -h), Vector2(0.29, -h), Vector2(r, -h + 0.05),
		Vector2(r, h - 0.05), Vector2(0.29, h), Vector2(0.255, h), Vector2(0.215, h)])
	var mats: Array[String] = ["tyre", "stripe", "tyre", "tyre", "tyre", "stripe", "tyre"]
	k.revolve(mats, Vector3.ZERO, Vector3.BACK, prof, 14)
	for side: float in [1.0, -1.0]:
		var n := Vector3(0, 0, side)
		k.disc("rim", Vector3(0, 0, (h - 0.03) * side), n, 0.215, 14)
		k.annulus("metal", Vector3(0, 0, (h - 0.028) * side), n, 0.18, 0.215, 14)
	k.disc("accent", Vector3(0, 0, h - 0.02), Vector3.BACK, 0.06, 8)
	k.box("carbon", Vector3(0, 0, -h - 0.02), Vector3(0.18, 0.18, 0.04))


# ---- animation ----

func _chassis_xf() -> Transform3D:
	var t := Transform3D(Basis.IDENTITY, Vector3(FRONT_AXLE, _ride + ride_offset_total(), 0))
	t = t * Transform3D(Basis(Vector3.BACK, -deg_to_rad(_rake)), Vector3.ZERO)
	return t * Transform3D(Basis.IDENTITY, Vector3(-FRONT_AXLE, 0, 0))


func ride_offset_total() -> float:
	var b := 0.0
	if _bounce >= 0.0:
		b = 0.12 * exp(-_bounce * 5.0) * cos(_bounce * 15.0)
	return ride_offset + b


func _apply_chassis() -> void:
	_chassis.transform = _chassis_xf()
	if _shake >= 0.0:
		var a := 0.006 * clampf(1.0 - _shake / 0.7, 0.0, 1.0)
		_chassis.position += Vector3(sin(_time * 90.0) * a, cos(_time * 77.0) * a, 0)


func _process(delta: float) -> void:
	if not _built:
		return
	_time += delta
	# Rear-wing flap
	_flap_t = move_toward(_flap_t, 1.0 if wing_open else 0.0, delta * 3.5)
	if _flap:
		_flap.rotation.z = _flap_delta * smoothstep(0.0, 1.0, _flap_t)
	# Rake and ride height follow the floor
	var ride_target := float(RIDE[look["floor"]])
	_rake = move_toward(_rake, _rake_target, delta * 3.0)
	_ride = move_toward(_ride, ride_target, delta * 0.08)
	if _bounce >= 0.0:
		_bounce += delta
		if _bounce > 1.2:
			_bounce = -1.0
	if _shake >= 0.0:
		_shake += delta
		if _shake > 0.8:
			_shake = -1.0
	_apply_chassis()
	# The suspension joins the moving chassis to the wheels: rebuild it when the
	# chassis has moved more than a centimetre (rake change, fit bounce; the idle
	# bob is too small to need it).
	var key := Vector2(_rake, _ride + ride_offset_total())
	if absf(key.x - _susp_key.x) > 0.05 or absf(key.y - _susp_key.y) > 0.012:
		_build_group("suspension")
	for i in 2:
		_wheels[i].rotation.y = steer
	# Efficiency power unit glow breathes
	(_mats["glow"] as ShaderMaterial).set_shader_parameter("emission_energy", 1.3 + 0.5 * sin(_time * 3.0) + (1.5 if _fx.has("power_unit") else 0.0))
	_update_fx(delta)


func _update_fx(delta: float) -> void:
	var done: Array[String] = []
	for area: String in _fx:
		var fx: Dictionary = _fx[area]
		var t: float = float(fx["t"]) + delta
		fx["t"] = t
		var h: Node3D = _groups.get(area)
		if h and area != "suspension" and area != "power_unit":
			var s := 1.0 - 0.5 * exp(-t * 7.0) * cos(t * 16.0)
			h.scale = Vector3.ONE * maxf(s, 0.05)
			h.position = PIVOTS[area] + Vector3(0, 0.35 * exp(-t * 9.0) * absf(cos(t * 12.0)), 0)
		if t > 0.9:
			done.append(area)
			if h:
				h.scale = Vector3.ONE
				h.position = PIVOTS[area]
	for a in done:
		_fx.erase(a)
	# Overlays: fit flash wins over hover highlight.
	for area: String in _groups:
		var want := 0.0
		var rim := 0.0
		var col := highlight_color
		if _fx.has(area):
			var t: float = _fx[area]["t"]
			# Two hard blinks, then a stepped fade.
			want = 1.0 if t < 0.07 else (0.15 if t < 0.13 else ceilf((1.0 - clampf((t - 0.13) / 0.7, 0.0, 1.0)) * 4.0) / 4.0 * 0.9)
			rim = 2.5 if want > 0.2 else 0.0
			col = _fx[area]["color"]
		elif area == _highlight:
			want = 0.2 + 0.06 * sin(_time * 6.0)
			rim = 1.5 if sin(_time * 6.0) < 0.0 else 2.5
		if want > 0.0:
			var m := _overlay(area)
			m.set_shader_parameter("amount", want)
			m.set_shader_parameter("color", col)
			var hm := _halo_mat(area)
			hm.set_shader_parameter("color", Color(col, 1.0 if rim > 0.0 else 0.0))
			hm.set_shader_parameter("width_px", rim)
			if not _overlays.has(area):
				_overlays[area] = m
				_set_overlay(area, m)
		elif _overlays.has(area):
			_overlays.erase(area)
			_set_overlay(area, null)


func _overlay(area: String) -> ShaderMaterial:
	if not _overlay_mats.has(area):
		var m := ShaderMaterial.new()
		m.shader = OVERLAY
		m.render_priority = 40
		_overlay_mats[area] = m
	return _overlay_mats[area]


func _halo_mat(area: String) -> ShaderMaterial:
	if not _halo_mats.has(area):
		var m := ShaderMaterial.new()
		m.shader = HALO
		m.render_priority = 50
		_halo_mats[area] = m
	return _halo_mats[area]


## Tint overlay on the group's meshes plus the halo rim (null clears both).
func _set_overlay(area: String, m: Material) -> void:
	var h: Node3D = _groups.get(area)
	if h == null:
		return
	if m != null and not _halos.has(area):
		_halos[area] = _make_halos(h, _halo_mat(area))
	for mi in h.find_children("*", "MeshInstance3D", true, false):
		if not String(mi.name).begins_with("Halo"):
			(mi as MeshInstance3D).material_overlay = m
	for hm: MeshInstance3D in _halos.get(area, []):
		hm.visible = m != null


## Smooth-normal copies of a group's meshes for the halo: flat-shaded faces
## would split apart when pushed outward, so normals are averaged per corner.
func _make_halos(h: Node3D, mat: Material) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	for mi in h.find_children("*", "MeshInstance3D", true, false):
		var src := (mi as MeshInstance3D).mesh as ArrayMesh
		if src == null or String(mi.name).begins_with("Halo"):
			continue
		var verts := PackedVector3Array()
		var norms := PackedVector3Array()
		for i in src.get_surface_count():
			var arr := src.surface_get_arrays(i)
			verts.append_array(arr[Mesh.ARRAY_VERTEX] as PackedVector3Array)
			norms.append_array(arr[Mesh.ARRAY_NORMAL] as PackedVector3Array)
		var acc := {}
		for i in verts.size():
			var key := verts[i].snapped(Vector3.ONE * 0.0005)
			acc[key] = (acc.get(key, Vector3.ZERO) as Vector3) + norms[i]
		for i in verts.size():
			norms[i] = (acc[verts[i].snapped(Vector3.ONE * 0.0005)] as Vector3).normalized()
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = verts
		arrays[Mesh.ARRAY_NORMAL] = norms
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var hm := MeshInstance3D.new()
		hm.name = "Halo"
		hm.mesh = mesh
		hm.material_override = mat
		hm.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		hm.transform = (mi as MeshInstance3D).transform
		mi.get_parent().add_child(hm)
		out.append(hm)
	return out
