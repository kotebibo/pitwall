class_name RaceSim
extends RefCounted
## A driven race: the player and an AI field on one circuit, in whole numbers,
## so the server can re-drive the whole race from the player's inputs.
## Standing start with lights out, tyre wear, a pit lane with a speed limiter,
## pit stops whose length depends on the crew, car-to-car contact, and the
## two-compound rule.

const ONE := Fx.ONE
const TICKS := Fx.TICKS
const LIGHT_GAP := 120  # one red light per second
const PIT_LIMIT := 1456355  # 80 km/h in fixed point m/s
const CONTACT_RADIUS := 85197  # 1.3 m: two cars touch within 2.6 m
const NO_SECOND_COMPOUND_PENALTY := 20  # seconds

enum Pit { NONE, STOPPED, DONE }

var track: TrackData
var laps := 5
var cars: Array[CarSim] = []
var ai: Array = []  # AiDriver or null (the player is car 0)
var crew: Array[int] = []  # pit crew skill 0..100
var tick := 0
var lights_out := 0  # tick the lights go out
var inputs := PackedByteArray()
var events: Array[Dictionary] = []

var crossings: Array[int] = []  # start-line crossings (1 = racing lap 1)
var finish_fp: Array[int] = []  # race time at the flag (16.16 ticks), -1 until finished
var progress: Array[int] = []  # for the running order
var pit_state: Array[int] = []
var pit_ticks_left: Array[int] = []
var pit_stops: Array[int] = []
var compounds_used: Array[int] = []  # bit per compound
var next_compound: Array[int] = []
var penalty_s: Array[int] = []
var _rng_state := 0
var _checkpoint: Array[int] = []  # player only: 0 → passed S1, 1 → passed S2 (no lap without them)


## entries[i] = {"setup", "stats", "car", "pace" (per mille, AI only), "crew" (0..100),
##               "compound" (start tyre), "pit_lap", "pit_compound" (AI)}; entries[0] is the player.
## grid = entry indices in starting order (pole first).
func _init(t: TrackData, entries: Array, seed: PackedByteArray, grid: Array, race_laps: int = 5) -> void:
	track = t
	laps = race_laps
	_rng_state = (seed[0] << 16 | seed[1] << 8 | seed[2]) if seed.size() > 2 else 12345
	var n := t.size()
	for i in entries.size():
		var e: Dictionary = entries[i]
		var car := CarSim.new()
		car.configure(e.get("setup", {}), e.get("stats", {}), seed, e.get("car", {}))
		car.tyre_model = true
		car.compound = int(e.get("compound", 1))
		var slot: int = grid.find(i)
		if slot < 0:
			slot = i
		# grid boxes: 16 m behind the line, then 8 m apart, alternating sides
		var back := 16 + slot * 8
		var point := (n - back / 4) % n
		var side := -1 if slot % 2 == 0 else 1
		car.place_at(t, point, side * 209715)  # 3.2 m
		cars.append(car)
		if i == 0:
			ai.append(null)
		else:
			var d := AiDriver.new(t, int(e.get("pace", 950)))
			d.pit_lap = int(e.get("pit_lap", 2))
			d.pit_compound = int(e.get("pit_compound", 1))
			ai.append(d)
		crew.append(int(e.get("crew", 60)))
		crossings.append(0)
		finish_fp.append(-1)
		progress.append(-n + point)
		pit_state.append(Pit.NONE)
		pit_ticks_left.append(0)
		pit_stops.append(0)
		compounds_used.append(1 << car.compound)
		next_compound.append(1 if car.compound != 1 else 2)
		penalty_s.append(0)
		_checkpoint.append(0)
	# five lights a second apart, then out after 0.2 to 2.5 s
	lights_out = LIGHT_GAP * 5 + 24 + _rand(276)


func _rand(n: int) -> int:
	_rng_state = (_rng_state * 1103515245 + 12345) & 0x7FFFFFFF
	return _rng_state % n


func lights_on() -> int:
	return clampi(tick / LIGHT_GAP + (1 if tick > 0 else 0), 0, 5) if tick < lights_out else 0


func started() -> bool:
	return tick >= lights_out


func finished() -> bool:
	return finish_fp[0] >= 0 and (finish_fp.min() >= 0 or tick > _leader_finish_tick() + TICKS * 30)


func _leader_finish_tick() -> int:
	var best := 1 << 60
	for f in finish_fp:
		if f >= 0:
			best = mini(best, f >> 16)
	return best


## The player's next tyre at a pit stop: 0 soft, 1 medium, 2 hard.
func set_next_compound(c: int) -> void:
	next_compound[0] = clampi(c, 0, 2)


## Steps one tick with the player's inputs and records them.
## buttons: bit 0 Boost, bit 1 reverse, bits 2-3 next pit tyre + 1 (0 = keep).
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
	if (buttons >> 2) & 3 != 0:
		next_compound[0] = ((buttons >> 2) & 3) - 1
	if tick < lights_out:
		if tick % LIGHT_GAP == 0 and tick / LIGHT_GAP < 5:
			events.append({"type": "light", "n": tick / LIGHT_GAP + 1})
		for c in cars:
			c.hold()
		tick += 1
		if tick == lights_out:
			events.append({"type": "go"})
		return
	var n := track.size()
	for i in cars.size():
		var car := cars[i]
		if finish_fp[i] >= 0 and i != 0:
			# finished AI cars cruise and leave the racing line
			pass
		var before := car.idx
		if pit_state[i] == Pit.STOPPED:
			_pit_tick(i)
			continue
		var cmd: Array[int]
		if ai[i] == null:
			cmd = [steer, throttle, brake, buttons]
		else:
			cmd = _ai_inputs(i)
		# pit lane speed limiter
		if car.in_pit_lane and track.in_pit_zone(car.idx) and _past_entry(car):
			if car.speed > PIT_LIMIT:
				cmd[1] = 0
				cmd[2] = maxi(cmd[2], clampi(((car.speed - PIT_LIMIT) * 60) >> 16, 40, 255))
			else:
				cmd[1] = mini(cmd[1], 150)
			cmd[3] &= ~1
		car.step(cmd[0], cmd[1], cmd[2], (cmd[3] & 1) != 0, (cmd[3] & 2) != 0)
		if pit_state[i] == Pit.DONE and not track.in_pit_zone(car.idx):
			pit_state[i] = Pit.NONE
		_check_box(i)
		_progress(i, before, car.idx)
	_contacts()
	tick += 1


## Speed that stops the car in its box: sqrt(2 a d) at a gentle 5 m/s^2, never zero
## (zero would mean "no limit" to the driver), and a crawl once alongside the box.
func box_approach_speed(i: int) -> int:
	var car := cars[i]
	var n := track.size()
	var to_box := (track.pit_box(i) - car.idx + n) % n
	if to_box > n - 3:
		return 1  # just past the mark: stop here
	var dist := to_box * 4 * ONE - car.along
	if dist <= ONE / 2:
		return 1
	if to_box > 14:
		return PIT_LIMIT
	return maxi(1, Fx.isqrt((10 * dist) << 16))


func _past_entry(car: CarSim) -> bool:
	return car.lateral < -track.pit_inner


func _ai_inputs(i: int) -> Array[int]:
	var car := cars[i]
	var d: AiDriver = ai[i]
	var lap := crossings[i]
	var lane := 0
	var limit := 0
	var wants_pit := not d.pitted and d.pit_lap > 0 and lap >= d.pit_lap
	# turn in at the pit entry (or stay in once in the lane), never across the exit
	if wants_pit and track.in_pit_zone(car.idx) and (car.in_pit_lane or car.idx >= track.pit_in):
		lane = track.pit_center
		limit = PIT_LIMIT
		limit = mini(limit, box_approach_speed(i))
	elif d.pitted and car.in_pit_lane and track.in_pit_zone(car.idx):
		lane = track.pit_center
		limit = PIT_LIMIT
	var blocked := _blocked_side(i)
	return d.drive(car, lane, limit, blocked)


## +1 / -1: a car close ahead is on that side of us, so pass on the other. 0: clear.
func _blocked_side(i: int) -> int:
	var me := cars[i]
	var n := track.size()
	for j in cars.size():
		if j == i:
			continue
		var o := cars[j]
		var gap := (o.idx - me.idx + n) % n
		if gap > 0 and gap < 4 and absi(o.lateral - me.lateral) < 163840 and o.speed < me.speed + ONE:
			return 1 if o.lateral >= me.lateral else -1
	return 0


func _check_box(i: int) -> void:
	var car := cars[i]
	if pit_state[i] != Pit.NONE or not car.in_pit_lane:
		return
	var box := track.pit_box(i)
	var n := track.size()
	var d := mini((car.idx - box + n) % n, (box - car.idx + n) % n)
	if d <= 1 and car.speed < ONE and car.lateral < -track.pit_inner:
		pit_state[i] = Pit.STOPPED
		# a good crew is about 2.2 s; a weak one 3.4 s; sometimes a wheel nut sticks
		var stop := TICKS * 22 / 10 + (100 - crew[i]) * TICKS * 12 / 1000
		var fumble := _rand(100) < 8
		if fumble:
			stop += TICKS * 3 / 2
		pit_ticks_left[i] = stop
		events.append({"type": "pit_in", "car": i, "ticks": stop, "fumble": fumble})


func _pit_tick(i: int) -> void:
	var car := cars[i]
	car.hold()
	pit_ticks_left[i] -= 1
	if pit_ticks_left[i] > 0:
		return
	var c: int = next_compound[i] if ai[i] == null else (ai[i] as AiDriver).pit_compound
	car.compound = c
	car.wear = 0
	compounds_used[i] |= 1 << c
	pit_stops[i] += 1
	pit_state[i] = Pit.DONE  # until the car leaves the pit zone
	if ai[i] != null:
		(ai[i] as AiDriver).pitted = true
	events.append({"type": "pit_out", "car": i, "compound": c})


func _progress(i: int, before: int, after: int) -> void:
	var n := track.size()
	var delta := (after - before + n) % n
	if delta == 0 or delta > n / 2:
		return
	progress[i] += delta
	for k in range(1, delta + 1):
		var point := (before + k) % n
		if ai[i] == null:
			if point == track.sectors[0]:
				_checkpoint[i] = 1
			elif point == track.sectors[1] and _checkpoint[i] == 1:
				_checkpoint[i] = 2
		if point == 0 and (ai[i] != null or _checkpoint[i] == 2 or crossings[i] == 0):
			_checkpoint[i] = 0
			crossings[i] += 1
			if finish_fp[i] < 0 and crossings[i] > laps:
				var frac := clampi(Fx.div(car_past(i, point, after), maxi(cars[i].speed / TICKS, 1)), 0, ONE)
				finish_fp[i] = ((tick + 1 - lights_out) << 16) - frac
				if (compounds_used[i] & (compounds_used[i] - 1)) == 0:
					penalty_s[i] = NO_SECOND_COMPOUND_PENALTY
				events.append({"type": "finish", "car": i})
			elif crossings[i] > 1:
				events.append({"type": "lap", "car": i, "lap": crossings[i]})


func car_past(i: int, point: int, after: int) -> int:
	var n := track.size()
	var past := cars[i].along
	var k := point
	while k != after:
		past += track.seg_len[k]
		k = (k + 1) % n
	return past


## Car-to-car contact: push apart and trade a little speed along the contact line.
func _contacts() -> void:
	var r2 := CONTACT_RADIUS * 2
	for a in cars.size():
		for b in range(a + 1, cars.size()):
			var ca := cars[a]
			var cb := cars[b]
			if pit_state[a] == Pit.STOPPED or pit_state[b] == Pit.STOPPED:
				continue
			var dx := cb.px - ca.px
			var dy := cb.py - ca.py
			if absi(dx) > r2 or absi(dy) > r2:
				continue
			var d := Fx.length(dx, dy)
			if d >= r2 or d == 0:
				continue
			var nx := Fx.div(dx, d)
			var ny := Fx.div(dy, d)
			var push := (r2 - d) / 2
			ca.px -= Fx.mul(push, nx)
			ca.py -= Fx.mul(push, ny)
			cb.px += Fx.mul(push, nx)
			cb.py += Fx.mul(push, ny)
			var va := Fx.mul(ca.vx, nx) + Fx.mul(ca.vy, ny)
			var vb := Fx.mul(cb.vx, nx) + Fx.mul(cb.vy, ny)
			var rel := va - vb
			if rel > 0:
				var j := Fx.mul(rel, 42598)  # 0.65: mostly inelastic
				ca.vx -= Fx.mul(j, nx)
				ca.vy -= Fx.mul(j, ny)
				cb.vx += Fx.mul(j, nx)
				cb.vy += Fx.mul(j, ny)
				events.append({"type": "contact", "a": a, "b": b, "speed": rel})


## Running order: finished cars by time, then by distance covered.
func order() -> Array[int]:
	var out: Array[int] = []
	for i in cars.size():
		out.append(i)
	out.sort_custom(func(a: int, b: int) -> bool:
		var fa := finish_fp[a]
		var fb := finish_fp[b]
		if fa >= 0 and fb >= 0:
			return fa + penalty_s[a] * TICKS * ONE < fb + penalty_s[b] * TICKS * ONE
		if fa >= 0 or fb >= 0:
			return fa >= 0
		return progress[a] > progress[b])
	return out


## Microseconds of race time for a finished car, penalties included.
func race_us(i: int) -> int:
	if finish_fp[i] < 0:
		return -1
	return (finish_fp[i] + penalty_s[i] * TICKS * ONE) * 1000000 / SessionSim.US_PER_TICK_FP


func encoded_inputs() -> String:
	return Marshalls.raw_to_base64(SessionSim.encode_inputs(inputs))
