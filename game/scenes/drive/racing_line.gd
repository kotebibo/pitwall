class_name RacingLine
extends Node2D
## Practice aid: the racing line ahead of the car, coloured live from YOUR speed.
## Red where you must already be braking to make the corner from the speed you
## carry now, yellow where to lift, green where it's flat out. Carry more speed
## and the red starts earlier; slow down and it moves back. Qualifying and
## ranked sessions never show it (braking boards only, as at a real track).

const AHEAD := 110  # points drawn ahead of the car (about 440 m)
const GREEN := Color(0.24, 0.81, 0.42)
const YELLOW := Color(0.95, 0.76, 0.19)
const RED := Color(0.91, 0.21, 0.17)

var _render: TrackRender
## Highest speed (m/s) the car can have at each point and still make every corner after it.
var _allowed := PackedFloat32Array()
var _idx := 0
var _v := 0.0


func setup(render: TrackRender) -> void:
	_render = render
	z_index = 1
	var n := render.line_kmh.size()
	_allowed.resize(n)
	for i in n:
		_allowed[i] = render.line_kmh[i] / 3.6


## Call every frame with the car's track point and speed (m/s).
func follow(idx: int, speed_ms: float) -> void:
	_idx = idx
	_v = speed_ms
	queue_redraw()


func _color_at(i: int) -> Color:
	var allowed := _allowed[i]
	if _v > allowed + 1.5:
		return RED
	if _v > allowed * 0.94:
		return YELLOW
	return GREEN


func _draw() -> void:
	if _render == null:
		return
	var line := _render.line
	var n := line.size()
	for k in range(1, AHEAD):
		var i := (_idx + k) % n
		var j := (i + 1) % n
		var fade := 1.0 - float(k) / AHEAD
		var base := _color_at(i)
		var c := base
		c.a = 0.85 * fade + 0.15
		var width := 1.1 if base == GREEN else 1.6
		draw_line(line[i], line[j], Color(0, 0, 0, c.a * 0.5), width + 0.6)
		draw_line(line[i], line[j], c, width)


## True when the car is faster than it can be at a point a little ahead: time to brake.
func brake_warning(idx: int, speed_ms: float) -> bool:
	var n := _allowed.size()
	if n == 0:
		return false
	for k in range(2, 14):
		if speed_ms > _allowed[(idx + k) % n] + 1.5:
			return true
	return false
