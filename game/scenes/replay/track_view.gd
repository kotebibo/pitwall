class_name TrackView
extends Control
## Draws the circuit and the cars. Geometry lives in a fixed design space and is
## scaled to fit, so the same lap fraction maps to the same spot at any size.

const DESIGN_SIZE := Vector2(1220, 800)
const L := 120.0
const R := 1100.0
const T := 120.0
const B := 680.0
const CORNER := 180.0
const SFX := 640.0
const PIT_IN := 0.90
const PIT_OUT := 0.995
const PIT_BOX := 0.955
const PIT_OFFSET := -58.0

## Each car: {"dist": float, "pit": float, "color": Color, "you": bool, "tag": String, "out": bool}
var cars: Array[Dictionary] = []

var _pts: PackedVector2Array = PackedVector2Array()
var _cum: PackedFloat32Array = PackedFloat32Array()
var _len := 0.0


func _ready() -> void:
	_build_track()


func _build_track() -> void:
	var pts := PackedVector2Array()
	_line(pts, Vector2(SFX, B), Vector2(R - CORNER, B), 60)
	_arc(pts, Vector2(R - CORNER, B - CORNER), PI / 2, 0.0, 50)
	_line(pts, Vector2(R, B - CORNER), Vector2(R, T + CORNER), 40)
	_arc(pts, Vector2(R - CORNER, T + CORNER), 0.0, -PI / 2, 50)
	for i in 120:  # top straight with a chicane
		var x := R - CORNER - (R - 2 * CORNER - L) * i / 120.0
		var u := (x - 420.0) / 300.0
		var bump := pow(sin(PI * u), 2) if u > 0.0 and u < 1.0 else 0.0
		pts.append(Vector2(x, T + 70.0 * bump))
	_arc(pts, Vector2(L + CORNER, T + CORNER), -PI / 2, -PI, 50)
	_line(pts, Vector2(L, T + CORNER), Vector2(L, B - CORNER), 40)
	_arc(pts, Vector2(L + CORNER, B - CORNER), PI, PI / 2, 50)
	_line(pts, Vector2(L + CORNER, B), Vector2(SFX, B), 40)
	_pts = pts
	_cum = PackedFloat32Array([0.0])
	for i in range(1, pts.size() + 1):
		_cum.append(_cum[i - 1] + pts[i - 1].distance_to(pts[i % pts.size()]))
	_len = _cum[_cum.size() - 1]


func _line(pts: PackedVector2Array, a: Vector2, b: Vector2, n: int) -> void:
	for i in n:
		pts.append(a.lerp(b, float(i) / n))


func _arc(pts: PackedVector2Array, c: Vector2, a0: float, a1: float, n: int) -> void:
	for i in n:
		var a := lerpf(a0, a1, float(i) / n)
		pts.append(c + Vector2(cos(a), sin(a)) * CORNER)


## Position and inward normal at a lap fraction, in design space.
func pos_at(fraction: float) -> Dictionary:
	var f := fposmod(fraction, 1.0)
	var s := f * _len
	var lo := 0
	var hi := _cum.size() - 1
	while hi - lo > 1:
		var m := (lo + hi) >> 1
		if _cum[m] <= s:
			lo = m
		else:
			hi = m
	var a := _pts[lo]
	var b := _pts[(lo + 1) % _pts.size()]
	var t := (s - _cum[lo]) / maxf(_cum[lo + 1] - _cum[lo], 0.0001)
	var d := (b - a).normalized()
	return {"p": a.lerp(b, t), "n": Vector2(-d.y, d.x)}


static func pit_amount(fraction: float) -> float:
	var f := fposmod(fraction, 1.0)
	return smoothstep(PIT_IN, PIT_IN + 0.03, f) * (1.0 - smoothstep(PIT_OUT - 0.025, PIT_OUT, f))


func _xf() -> Transform2D:
	var s := minf(size.x / DESIGN_SIZE.x, size.y / DESIGN_SIZE.y)
	var offset := (size - DESIGN_SIZE * s) / 2.0
	return Transform2D(0.0, Vector2(s, s), 0.0, offset)


func _draw() -> void:
	if _pts.is_empty():
		return
	var xf := _xf()
	var s := xf.get_scale().x
	var loop := xf * _pts
	loop.append(loop[0])
	draw_polyline(loop, Color("3a3c42"), 72.0 * s)
	draw_polyline(loop, Color("2a2c31"), 60.0 * s)
	draw_polyline(loop, Ui.RED.darkened(0.45), 2.0)

	# Pit lane
	var pit := PackedVector2Array()
	for i in 40:
		var f := lerpf(PIT_IN - 0.01, PIT_OUT + 0.005, i / 39.0)
		var at := pos_at(f)
		pit.append(xf * ((at["p"] as Vector2) + (at["n"] as Vector2) * PIT_OFFSET * pit_amount(f)))
	draw_polyline(pit, Color("222328"), 26.0 * s)

	# Start / finish
	var start := xf * Vector2(SFX, B)
	for i in 6:
		draw_rect(Rect2(start + Vector2(0, (i - 3) * 3), Vector2(3, 3)), Ui.INK if i % 2 == 0 else Ui.BG)

	# Cars: everyone else first, then ours on top
	var order := range(cars.size())
	order.sort_custom(func(a: int, b: int) -> bool: return not cars[a]["you"] and cars[b]["you"])
	for i: int in order:
		var car := cars[i]
		var at := pos_at(car["dist"])
		var lane := (i - 2.5) * 4.0 * (1.0 - float(car["pit"]))
		var p: Vector2 = xf * ((at["p"] as Vector2) + (at["n"] as Vector2) * (lane + PIT_OFFSET * float(car["pit"])))
		var color: Color = car["color"]
		if car["out"]:
			color = color.darkened(0.6)
		draw_circle(p, 5.0 if car["you"] else 4.0, Ui.BG)
		draw_circle(p, 4.0 if car["you"] else 3.0, color)
		if car["you"]:
			draw_string(Ui.font, p + Vector2(-8, -8), "YOU", HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_SMALL, Ui.INK)
		if String(car["tag"]) != "":
			draw_string(Ui.font, p + Vector2(-8, 14), car["tag"], HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_SMALL, Ui.YELLOW)
