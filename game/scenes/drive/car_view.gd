class_name CarView
extends Node2D
## A top-down F1 car built from layered pixel-art sprites, one layer per part,
## so the fitted parts change how the car looks. Paint layers are greyscale and
## tinted with the team colour. Falls back to a drawn car if the sprites are missing.

const DIR := "res://assets/sprites/car/%s.png"
const M_PER_PX := 0.1
## Cars are drawn a little larger than life so they read at racing zoom.
const VISUAL_SCALE := 1.25

var body := Ui.RED
var secondary := Color("f1efea")
## Visual concept per area, as in game/data/parts.json.
var parts := {"front_wing": "outwash", "rear_wing": "highdf", "sidepods": "downwash", "floor": "low_rake"}
var steer := 0.0  # radians
var braking := false
var boosting := false
var straight_mode := false
var ghost := false

var _sprites := false
var _rig: Node2D
var _front_tyres: Array[Sprite2D] = []
var _wing_closed: Array[Sprite2D] = []
var _wing_open: Array[Sprite2D] = []
var _glow: Sprite2D
var _light: Sprite2D
var _blink := 0.0


func _ready() -> void:
	build()


static func has_sprites() -> bool:
	return ResourceLoader.exists(DIR % "body_paint")


## (Re)creates the layers for the current parts and colours.
func build() -> void:
	if _rig:
		_rig.queue_free()
	_front_tyres.clear()
	_wing_closed.clear()
	_wing_open.clear()
	_glow = null
	_light = null
	_sprites = has_sprites()
	if not _sprites:
		queue_redraw()
		return
	_rig = Node2D.new()
	var s := M_PER_PX * VISUAL_SCALE
	_rig.scale = Vector2(s, s)
	add_child(_rig)
	var anchors := _anchors()
	var alpha := 0.42 if ghost else 1.0
	_layer("shadow", Color(1, 1, 1, 0.0 if ghost else 1.0))
	_layer("floor_" + String(parts.get("floor", "low_rake")), Color(1, 1, 1, alpha))
	_layer("tyre_rear", Color(1, 1, 1, alpha))
	for w: Array in anchors.get("front_wheels", [[17.5, -8.0], [17.5, 8.0]]):
		var t := _layer("tyre_front", Color(1, 1, 1, alpha))
		if t:
			t.centered = true
			t.position = Vector2(w[0], w[1])
			t.flip_v = float(w[1]) > 0.0  # compound stripe on the outside of both wheels
			_front_tyres.append(t)
	_pair("sidepods_" + String(parts.get("sidepods", "downwash")), alpha)
	_pair("body", alpha)
	_pair("front_wing_" + String(parts.get("front_wing", "outwash")), alpha)
	var rw := "rear_wing_" + String(parts.get("rear_wing", "highdf"))
	_wing_closed.append_array(_pair(rw, alpha))
	_wing_open.append_array(_pair(rw + "_open", alpha))
	for o in _wing_open:
		o.visible = false
	_layer("halo_detail", Color(1, 1, 1, alpha))
	var helmet := _layer("helmet_paint", Color(secondary, alpha))
	if helmet == null:
		pass
	if not ghost:
		_glow = _layer("brake_disc_glow", Color(1, 1, 1, 0.0))
		_light = _layer("lights", Color(1, 1, 1, 0.0))


func _anchors() -> Dictionary:
	var path := "res://assets/sprites/car/anchors.json"
	if not FileAccess.file_exists(path):
		return {}
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return data if data is Dictionary else {}


func _layer(name: String, tint: Color) -> Sprite2D:
	var path := DIR % name
	if not ResourceLoader.exists(path):
		return null
	var sp := Sprite2D.new()
	sp.texture = load(path)
	sp.modulate = tint
	_rig.add_child(sp)
	return sp


## Paint (tinted with the team colour) and detail layers of one part.
func _pair(name: String, alpha: float) -> Array[Sprite2D]:
	var out: Array[Sprite2D] = []
	var paint := _layer(name + "_paint", Color(body, alpha))
	if paint:
		out.append(paint)
	var detail := _layer(name + "_detail", Color(1, 1, 1, alpha))
	if detail:
		out.append(detail)
	return out


func _process(delta: float) -> void:
	if not _sprites:
		queue_redraw()
		return
	for t in _front_tyres:
		t.rotation = steer
	for w in _wing_closed:
		w.visible = not straight_mode
	for w in _wing_open:
		w.visible = straight_mode
	if _glow:
		_glow.modulate.a = move_toward(_glow.modulate.a, 0.9 if braking else 0.0, delta * (6.0 if braking else 1.5))
	if _light:
		_blink += delta
		_light.modulate.a = 1.0 if boosting and fmod(_blink, 0.25) < 0.125 else 0.0


func _draw() -> void:
	if _sprites:
		return
	var a := 0.45 if ghost else 1.0
	var tyre := Color(0.07, 0.07, 0.08, a)
	var dark := body.darkened(0.45)
	dark.a = a
	var main := body
	main.a = a
	draw_rect(Rect2(-2.85, -0.8, 0.4, 1.6), dark)
	draw_rect(Rect2(-2.35, -1.0, 0.75, 0.38), tyre)
	draw_rect(Rect2(-2.35, 0.62, 0.75, 0.38), tyre)
	for side: float in [-1.0, 1.0]:
		draw_set_transform(Vector2(1.7, side * 0.81), steer, Vector2.ONE)
		draw_rect(Rect2(-0.32, -0.17, 0.64, 0.34), tyre)
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	draw_colored_polygon(PackedVector2Array([
		Vector2(-2.4, -0.55), Vector2(-1.1, -0.85), Vector2(0.5, -0.8), Vector2(1.0, -0.35),
		Vector2(2.55, -0.16), Vector2(2.55, 0.16), Vector2(1.0, 0.35), Vector2(0.5, 0.8),
		Vector2(-1.1, 0.85), Vector2(-2.4, 0.55),
	]), main)
	draw_rect(Rect2(-0.1, -0.22, 0.7, 0.44), Color(0.05, 0.05, 0.06, a))
	draw_rect(Rect2(2.45, -0.98, 0.38, 1.96), dark)
	if braking and not ghost:
		draw_rect(Rect2(-2.95, -0.15, 0.12, 0.3), Color(1.0, 0.25, 0.2))
	if boosting and not ghost:
		draw_rect(Rect2(-3.0, -0.08, 0.16, 0.16), Color("5ec8e5"))
