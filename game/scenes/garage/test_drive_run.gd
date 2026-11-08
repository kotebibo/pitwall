class_name TestDriveRun
extends RefCounted
## The garage's TEST DRIVE: one autopilot lap of Mtkvari with a car spec, run a
## slice at a time so the screen never freezes. The same SessionSim and
## Autopilot as res://sim/test_drive.gd, with the autopilot's speed profile
## scaled to what this car can do (CarPerf), so a car with more grip also
## corners faster and a car that brakes better brakes later. Display only:
## nothing here is verified or sent anywhere.

const TRACK := "mtkvari"
const MAX_TICKS := 120 * 150
## Track points per mini-sector on the map (about 80 m)
const MINI := 20

## Finished runs by setup, driver stats and spec: {"us", "valid", "sectors", "times", "lap_end"}
static var cache := {}
static var _track: TrackData

var key := ""
var result: Dictionary = {}
var _session: SessionSim
var _pilot: TestPilot
var _times := PackedFloat64Array()


static func track() -> TrackData:
	if _track == null:
		_track = TrackData.load_id(TRACK)
	return _track


func _init(setup: Dictionary, stats: Dictionary, spec: Dictionary) -> void:
	key = "%s|%s|%s" % [setup, stats, spec]
	if cache.has(key):
		result = cache[key]
		return
	var t := track()
	_session = SessionSim.new(t, setup, stats, PackedByteArray([128, 0, 0, 0]), SessionSim.Kind.QUALIFYING, spec)
	_pilot = TestPilot.new(t, CarPerf.car(setup, stats, spec), CarPerf.car(setup, stats, {}))
	_times.resize(t.size())
	_times.fill(-1.0)


func done() -> bool:
	return not result.is_empty()


## Drives for up to budget_usec of real time; returns how far through the lap it is (0..1).
func step(budget_usec: int) -> float:
	if done():
		return 1.0
	var t := track()
	var n := t.size()
	var t0 := Time.get_ticks_usec()
	while Time.get_ticks_usec() - t0 < budget_usec:
		for k in 30:
			var before := _session.car.idx
			var inp := _pilot.drive(_session.car)
			_session.step(inp[0], inp[1], inp[2], inp[3])
			if _session.lap_number == 1:
				_mark(before, _session.car.idx, n)
			if not _session.laps.is_empty() or _session.tick >= MAX_TICKS:
				_finish()
				return 1.0
	if _session.lap_number == 0:
		return 0.03
	return 0.03 + 0.97 * float(_session.car.idx) / n


## When the car passed each track point on its flying lap (seconds, to a fraction of a tick).
func _mark(before: int, after: int, n: int) -> void:
	var d := (after - before + n) % n
	if d == 0 or d > n / 2:
		return
	var speed := maxf(Fx.to_float(_session.car.speed), 1.0)
	var now := _session.tick / 120.0 - Fx.to_float(_session.car.along) / speed
	for j in range(1, d + 1):
		var p := (before + j) % n
		if _times[p] < 0.0:
			_times[p] = now


func _finish() -> void:
	if _session.laps.is_empty():
		result = {"us": -1, "valid": false, "sectors": [], "times": _times, "lap_end": 0.0}
	else:
		var lap: Dictionary = _session.laps[0]
		result = {"us": int(lap["us"]), "valid": bool(lap["valid"]), "sectors": lap["sectors"], "times": _times, "lap_end": _times[0] + int(lap["us"]) / 1000000.0}
	cache[key] = result
	_session = null


## Seconds spent in each mini-sector of a finished run (the last one ends at the line).
static func mini_times(r: Dictionary) -> PackedFloat64Array:
	var times: PackedFloat64Array = r.get("times", PackedFloat64Array())
	var n := times.size()
	var out := PackedFloat64Array()
	var i := 0
	while i < n:
		var j := mini(i + MINI, n)
		var a := times[i]
		var b: float = r.get("lap_end", 0.0) if j == n else times[j]
		out.append(b - a if a >= 0.0 and b >= 0.0 else 0.0)
		i = j
	return out


## The autopilot, driving to what this car can do: its speed profile (made for
## the standard car) scaled in corners by the car's corner speed at that radius,
## and its braking by the car's braking.
class TestPilot:
	extends Autopilot

	var _brake_k := 1.0

	func _init(t: TrackData, car: Dictionary, std: Dictionary) -> void:
		super(t)
		var n := t.size()
		var top := CarPerf.top_speed(std)
		for i in n:
			var r := _radius(t, i)
			var v_std := CarPerf.corner_speed(std, r, top)
			if v_std < top * 0.98:  # a corner the standard car is grip-limited in
				_kmh[i] *= CarPerf.corner_speed(car, r, top * 2.0) / v_std
			else:  # a straight: the car's power and drag decide, not the profile
				_kmh[i] = 400.0
		var v := 50.0
		_brake_k = (CarPerf._brake_force(car, v) / float(car["mass"])) / (CarPerf._brake_force(std, v) / float(std["mass"]))

	## Radius of the centre line at point i (m), from the turn over about 25 m either side.
	static func _radius(t: TrackData, i: int) -> float:
		var n := t.size()
		var a := (i - 6 + n) % n
		var b := (i + 6) % n
		var da := Vector2(t.dir_x[a], t.dir_y[a]) / 65536.0
		var db := Vector2(t.dir_x[b], t.dir_y[b]) / 65536.0
		var turn := absf(da.angle_to(db))
		var length := (Vector2(t.x[b], t.y[b]) - Vector2(t.x[a], t.y[a])).length() / 65536.0
		return length / turn if turn > 0.0005 else 100000.0

	## Autopilot.drive with this car's braking.
	func drive(car: CarSim) -> Array[int]:
		var n := track.size()
		var v := Fx.to_float(car.speed)
		var pos := Vector2(car.px, car.py) / 65536.0
		var ahead := (car.idx + 3 + int(v * 0.09)) % n
		var to := _line[ahead] - pos
		var hx := Fx.to_float(Fx.cos_a(car.heading))
		var hy := Fx.to_float(Fx.sin_a(car.heading))
		var err := atan2(hx * to.y - hy * to.x, hx * to.x + hy * to.y)
		var steer := clampi(roundi(err * 700.0), -127, 127)
		var target := 120.0
		var d := 0.0
		for k in 90:
			var i := (car.idx + k) % n
			var vc := _kmh[i] / 3.6 * pace
			var avg := (v + vc) * 0.5
			var decel := (13.0 + 0.004 * avg * avg) * pace * _brake_k
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
