class_name Autopilot
extends RefCounted
## A driver for tests, AI ghosts and the attract mode: follows the racing line
## from the track file and brakes for its speed profile, with a margin.
## Produces inputs only; it never touches the physics, so its floats do not
## matter for verification.

var track: TrackData
## 1.0 drives the profile; lower is more cautious.
var pace := 0.94
var _line := PackedVector2Array()
var _kmh := PackedFloat32Array()


func _init(t: TrackData) -> void:
	track = t
	var n := t.size()
	_line.resize(n)
	_kmh.resize(n)
	for i in n:
		var p := Vector2(t.x[i], t.y[i]) / 65536.0
		var d := Vector2(t.dir_x[i], t.dir_y[i]) / 65536.0
		var off: float = t.line_cm[i] / 100.0 if t.line_cm.size() == n else 0.0
		_line[i] = p + Vector2(-d.y, d.x) * off
		_kmh[i] = t.line_kmh[i] if t.line_kmh.size() == n else 150.0


func drive(car: CarSim) -> Array[int]:
	var n := track.size()
	var v := Fx.to_float(car.speed)
	var pos := Vector2(car.px, car.py) / 65536.0
	# steer at a point on the line ahead, further ahead the faster we go
	var ahead := (car.idx + 3 + int(v * 0.09)) % n
	var to := _line[ahead] - pos
	var hx := Fx.to_float(Fx.cos_a(car.heading))
	var hy := Fx.to_float(Fx.sin_a(car.heading))
	var err := atan2(hx * to.y - hy * to.x, hx * to.x + hy * to.y)
	var steer := clampi(roundi(err * 700.0), -127, 127)
	# target speed: the profile ahead, minus what braking can take off in the distance left
	var target := 120.0
	var d := 0.0
	for k in 90:
		var i := (car.idx + k) % n
		var vc := _kmh[i] / 3.6 * pace
		var avg := (v + vc) * 0.5
		var decel := (13.0 + 0.004 * avg * avg) * pace
		target = minf(target, sqrt(vc * vc + 2.0 * decel * maxf(d - 6.0, 0.0)))
		d += 4.0
	var throttle := 0
	var brake := 0
	if v < target - 0.8:
		throttle = 255 if absi(steer) < 60 or v > 35.0 else 170
	elif v > target + 0.8:
		brake = clampi(roundi((v - target) * 45.0), 30, 255)
	else:
		throttle = 140
	var boost := 1 if throttle == 255 and absi(steer) < 15 and car.battery > 500000 else 0
	return [steer, throttle, brake, boost]
