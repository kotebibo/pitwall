class_name SessionSim
extends RefCounted
## A driving session: practice, qualifying and race are the same engine with
## different settings. Steps the car, times laps and sectors to the microsecond
## and records every tick's inputs so the server can re-drive the run.

const PHYSICS_VERSION := 5
const US_PER_TICK_FP := 7864320  # 120 << 16: lap time = ticks_fp * 1e6 / this

enum Kind { PRACTICE, QUALIFYING, RACE }

## One finished lap: {"lap": int, "us": int, "valid": bool, "sectors": [us, us, us], "ticks": [start, end]}
var laps: Array[Dictionary] = []
## Events from the last step(), for the presenter: {"type": "lap"|"sector"|"limits"|"wall", ...}
var events: Array[Dictionary] = []

var kind := Kind.QUALIFYING
var track: TrackData
var car := CarSim.new()
var tick := 0
var inputs := PackedByteArray()  # 4 bytes per tick: steer+128, throttle, brake, buttons

var lap_number := 0  # 0 = out-lap
var lap_valid := true
var lap_start_fp := -1  # tick time (16.16) the current lap started
var _next_checkpoint := 0  # index into _checkpoints
var _checkpoints: Array[int] = []
var _sector_start_fp := 0
var _sector_times: Array[int] = []


func _init(t: TrackData, setup: Dictionary, stats: Dictionary, seed: PackedByteArray, session_kind: Kind = Kind.QUALIFYING, car_spec: Dictionary = {}) -> void:
	track = t
	kind = session_kind
	car.configure(setup, stats, seed, car_spec)
	car.place(t, t.spawn_index, t.spawn_speed)
	_checkpoints = [t.sectors[0], t.sectors[1], 0]
	_next_checkpoint = 2  # first crossing of the line starts lap 1


## Steps one tick with the given inputs and records them.
func step(steer: int, throttle: int, brake: int, buttons: int) -> void:
	steer = clampi(steer, -127, 127)
	throttle = clampi(throttle, 0, 255)
	brake = clampi(brake, 0, 255)
	buttons &= 0xFF
	inputs.append(steer + 128)
	inputs.append(throttle)
	inputs.append(brake)
	inputs.append(buttons)
	events.clear()
	var before := car.idx
	car.step(steer, throttle, brake, (buttons & 1) != 0, (buttons & 2) != 0)
	_progress(before, car.idx)
	if car.off_track and lap_valid and lap_number > 0:
		lap_valid = false
		events.append({"type": "limits"})
	if car.wall_hit > 0:
		events.append({"type": "wall", "speed": car.wall_hit})
	tick += 1


func _progress(before: int, after: int) -> void:
	var n := track.size()
	var delta := (after - before + n) % n
	if delta == 0:
		return
	if delta > n / 2:
		# Reversing back over a timing line spoils the lap; a bounce off a wall does not
		var back := n - delta
		for k in back:
			if (before - k + n) % n in _checkpoints and lap_number > 0:
				lap_valid = false
		return
	for k in range(1, delta + 1):
		var point := (before + k) % n
		if point == _checkpoints[_next_checkpoint]:
			_cross(_next_checkpoint, after, point)


## Exact time the car crossed a point this tick, from how far past it the car is.
func _crossing_fp(after: int, point: int) -> int:
	var n := track.size()
	var past := car.along
	var i := point
	while i != after:
		past += track.seg_len[i]
		i = (i + 1) % n
	var moved := maxi(car.speed / Fx.TICKS, 1)
	var frac := clampi(Fx.div(past, moved), 0, Fx.ONE)
	return ((tick + 1) << 16) - frac


func _cross(checkpoint: int, after: int, point: int) -> void:
	var t := _crossing_fp(after, point)
	if checkpoint < 2:
		if lap_number > 0:
			_sector_times.append(_us(t - _sector_start_fp))
			events.append({"type": "sector", "sector": checkpoint + 1, "us": _sector_times[-1]})
		_sector_start_fp = t
		_next_checkpoint = checkpoint + 1
		return
	# Start/finish line
	if lap_number > 0:
		_sector_times.append(_us(t - _sector_start_fp))
		var lap := {
			"lap": lap_number,
			"us": _us(t - lap_start_fp),
			"valid": lap_valid and _sector_times.size() == 3,
			"sectors": _sector_times.duplicate(),
			"ticks": [lap_start_fp, t],
		}
		laps.append(lap)
		events.append({"type": "lap", "lap": lap})
	lap_number += 1
	lap_valid = true
	lap_start_fp = t
	_sector_start_fp = t
	_sector_times.clear()
	_next_checkpoint = 0


static func _us(ticks_fp: int) -> int:
	return ticks_fp * 1000000 / US_PER_TICK_FP


## Time into the current lap in microseconds (0 on the out-lap).
func current_lap_us() -> int:
	if lap_number == 0:
		return 0
	return _us((tick << 16) - lap_start_fp)


func best_lap() -> Dictionary:
	var best := {}
	for lap in laps:
		if lap["valid"] and (best.is_empty() or int(lap["us"]) < int(best["us"])):
			best = lap
	return best


# ---- input log encoding (shared with the server re-drive) ----

## Run-length encoded inputs as base64: repeated [count (1..255), 4 input bytes].
func encoded_inputs() -> String:
	return Marshalls.raw_to_base64(encode_inputs(inputs))


static func encode_inputs(raw: PackedByteArray) -> PackedByteArray:
	var out := PackedByteArray()
	var i := 0
	while i < raw.size():
		var run := 1
		while run < 255 and i + 4 * run + 3 < raw.size() \
				and raw[i + 4 * run] == raw[i] and raw[i + 4 * run + 1] == raw[i + 1] \
				and raw[i + 4 * run + 2] == raw[i + 2] and raw[i + 4 * run + 3] == raw[i + 3]:
			run += 1
		out.append(run)
		out.append_array(raw.slice(i, i + 4))
		i += 4 * run
	return out


static func decode_inputs(rle: PackedByteArray) -> PackedByteArray:
	var out := PackedByteArray()
	var i := 0
	while i + 4 < rle.size():
		var group := rle.slice(i + 1, i + 5)
		for _r in rle[i]:
			out.append_array(group)
		i += 5
	return out


static func hash_inputs(raw: PackedByteArray) -> String:
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	ctx.update(raw)
	return ctx.finish().hex_encode()
