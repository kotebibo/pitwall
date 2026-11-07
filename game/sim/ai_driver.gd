class_name AiDriver
extends RefCounted
## An AI racing driver in whole numbers, so a race with AI cars re-drives
## exactly on the server. Follows the racing line at a share of the circuit's
## speed profile, moves off line to pass, and takes the pit lane when told.

const ONE := Fx.ONE

## Share of the speed profile it drives at, per mille (950 = 95%).
var pace := 950
## Lap on which it pits (0 = never), and the tyre it fits.
var pit_lap := 0
var pit_compound := 1
var pitted := false

var _track: TrackData
var _lx := PackedInt64Array()  # racing line, fixed point
var _ly := PackedInt64Array()
var _target := PackedInt64Array()  # profile speed, fixed point m/s
var _offset := 0  # current lateral offset from the line, fixed point
var _want_offset := 0


func _init(t: TrackData, pace_pm: int) -> void:
	_track = t
	pace = pace_pm
	var n := t.size()
	_lx.resize(n)
	_ly.resize(n)
	_target.resize(n)
	for i in n:
		var off: int = (t.line_cm[i] if t.line_cm.size() == n else 0) * ONE / 100
		# right-hand normal of the segment direction
		_lx[i] = t.x[i] + ((-t.dir_y[i] * off) >> 16)
		_ly[i] = t.y[i] + ((t.dir_x[i] * off) >> 16)
		var kmh: int = t.line_kmh[i] if t.line_kmh.size() == n else 150
		_target[i] = kmh * ONE * 10 / 36 * pace / 1000


## Inputs for one tick: [steer, throttle, brake, buttons].
## `lane` is a lateral offset from the centreline to drive in (pit lane), or 0 for the racing line.
## `limit` caps the speed (pit limiter, stopping in the box), 0 = none.
func drive(car: CarSim, lane: int, limit: int, blocked_side: int) -> Array[int]:
	var t := _track
	var n := t.size()
	var v := car.speed
	# pass a car that is in the way: move to the side with room
	_want_offset = 0 if blocked_side == 0 else -blocked_side * 229376  # 3.5 m
	_offset += clampi(_want_offset - _offset, -3277, 3277)  # 0.05 m per tick
	var ahead := (car.idx + 3 + ((v >> 16) * 9 / 100)) % n
	var tx: int
	var ty: int
	if lane != 0:
		tx = t.x[ahead] + ((-t.dir_y[ahead] * lane) >> 16)
		ty = t.y[ahead] + ((t.dir_x[ahead] * lane) >> 16)
	else:
		tx = _lx[ahead] + ((-t.dir_y[ahead] * _offset) >> 16)
		ty = _ly[ahead] + ((t.dir_x[ahead] * _offset) >> 16)
	var dx := tx - car.px
	var dy := ty - car.py
	var c := Fx.cos_a(car.heading)
	var s := Fx.sin_a(car.heading)
	var cross := (c * dy - s * dx) >> 16
	var dot := (c * dx + s * dy) >> 16
	var dist := maxi(Fx.length(dx, dy), 1)
	var err := Fx.div(cross, dist)
	if dot < 0:
		err = ONE if cross > 0 else -ONE
	var steer := clampi((err * 700) >> 16, -127, 127)

	var target := _target[(car.idx + 3) % n]
	if _offset != 0:
		target = target * 97 / 100  # off line: a little less grip
	if limit > 0:
		target = mini(target, limit)
	var throttle := 0
	var brake := 0
	var margin := ONE * 8 / 10
	if v < target - margin:
		throttle = 255 if absi(steer) < 60 or v > 35 * ONE else 170
	elif v > target + margin:
		brake = clampi(((v - target) * 45) >> 16, 30, 255)
	else:
		throttle = 140
	var boost := 1 if throttle == 255 and absi(steer) < 15 and car.battery > 500000 and limit == 0 else 0
	return [steer, throttle, brake, boost]
