class_name CarSim
extends RefCounted
## One car's physics, top-down, in whole numbers at 120 ticks per second.
##
## A bicycle model: front and rear tyres build grip with slip up to a peak and
## lose some past it; downforce and drag grow with speed squared; braking and
## acceleration shift weight between the axles; each axle shares its grip
## between cornering and braking or driving. Everything a player owns or picks
## (setup, driver stats) changes a constant here; nothing adds randomness.
## All values are 16.16 fixed point (Fx.ONE = 1.0) unless the name says otherwise.

const ONE := Fx.ONE

# Car (an F1 car at roughly 2026 numbers)
const MASS := 800  # kg, with driver
const INERTIA := 1100  # kg m^2, yaw
const MASS_FRONT := 378  # kg over the front axle
const MASS_REAR := 422
const A_CG := 124518  # 1.9 m, front axle to centre of mass
const B_CG := 111411  # 1.7 m
const WHEELBASE := 235930  # 3.6 m
const CG_HEIGHT := 19661  # 0.3 m
const CAR_RADIUS := 78643  # 1.2 m, for walls
const CAR_HALF_WIDTH := 65536  # 1.0 m, for track limits
const G := 642908  # 9.81 m/s^2

# Tyres
const MU := 131072  # 2.00 peak friction (warm slicks with a modern carcass)
const SLIP_PEAK := 6554  # 0.10, tangent of the slip angle at peak grip (front)
const REAR_SLIP_PEAK := 9830  # 0.15: the rear lets go later, so the car understeers gently instead of snapping
const LONG_SLIDE := 55705  # 0.85 of peak once a wheel locks or spins
const LOCKED_LATERAL := 39322  # 0.60 of lateral grip left on a locked or spinning axle
const V_MIN := 327680  # 5 m/s, slip is measured against at least this speed

# Power and brakes
const P_ICE := 400000  # W, combustion engine
const P_BOOST := 350000  # W, electric Boost (2026 MGU-K)
const P_HARVEST_MAX := 350000  # W
const F_DRIVE_MAX := 557056000  # 8500 N, low-speed drive force
const F_BRAKE_MAX := 3538944000  # 54000 N at full pedal
const F_ENGINE_BRAKE := 78643200  # 1200 N on lift-off
const F_REVERSE := 196608000  # 3000 N
const F_ROLL := 7733248  # 118 N, rolling resistance
const BATTERY_MAX := 4000000  # J
const STEER_LOCK := 23593  # 0.36 rad at the front wheels when stopped
## Lock halves by this speed: at 300 km/h full input is about 0.1 rad, near the
## grip limit, so the car can't be thrown sideways at speed (as in a real F1 car).
const STEER_SPEED := 2097152  # 32 m/s
const YAW_DAMPING := 60  # N m per (rad/s x m/s): aero and tyre damping that settles the car

# Surfaces
const KERB_WIDTH := 104858  # 1.6 m
const MU_KERB := 60948  # 0.93
const MU_GRASS := 36045  # 0.55
const F_GRASS := 117964800  # 1800 N extra rolling drag on grass

# Straight Mode (2026 active aero): wings open on marked straights
const SM_DRAG := 44564  # 0.68 of normal drag
const SM_DOWNFORCE := 36045  # 0.55 of normal downforce

enum Surface { ASPHALT, KERB, GRASS }

# Tyres (races only; qualifying runs on fresh tyres with no wear)
const COMPOUND_GRIP := [68157, 65536, 63570]  # soft 1.04, medium 1.00, hard 0.97
const COMPOUND_WEAR := [55, 34, 22]  # wear (ppm) per metre: about 18%, 11%, 7% a lap
const WEAR_CLIFF := 600000  # past 60% worn, grip falls away fast

# Set by configure() from setup, parts, driver stats and the attempt seed
var k_down := 0  # N per (m/s)^2
var mu_base := MU
var p_ice := P_ICE
var f_drive_max := F_DRIVE_MAX
var k_drag := 0
var front_share := 0  # share of downforce on the front axle
var brake_front := 0  # brake bias
var diff_lock := 0
var brake_grip := ONE  # Braking stat: brake force before front lock-up
var traction_grip := ONE  # Traction stat: throttle before rear wheelspin
var slide_grip := 52429  # Cornering stat: grip kept past the peak (0.80 base)
var harvest_eff := 0  # Energy stat
var grip_mult := ONE  # tiny per-attempt variation
var wind_x := 0
var wind_y := 0
var tyre_model := false
var compound := 1  # 0 soft, 1 medium, 2 hard
var wear := 0  # 0 .. 1,000,000

# State
var track: TrackData
var px := 0
var py := 0
var heading := 0
var vx := 0
var vy := 0
var yaw_rate := 0
var battery := BATTERY_MAX
var accel_long := 0  # last tick's longitudinal acceleration, for weight transfer
var idx := 0  # track segment
var along := 0
var lateral := 0
var surface := Surface.ASPHALT
var off_track := false  # all four wheels past the white line
var wall_hit := 0  # speed into the wall this tick (0 if none)
var in_pit_lane := false

# For the presenter: what the car is doing this tick
var speed := 0
var steer_angle := 0
var boosting := false
var straight_mode := false
var front_locked := false
var rear_sliding := false
var _sm_armed := false
var _was_in_zone := false


## Setup levers are whole numbers on the setup screen's scales; stats are 0 to 100.
## `car` is the sum of the fitted parts (per-mille changes, kW for power), see game/data/parts.json.
func configure(setup: Dictionary, stats: Dictionary, seed: PackedByteArray, car: Dictionary = {}) -> void:
	var fw: int = int(setup.get("front_wing", 6)) - 6
	var rw: int = int(setup.get("rear_wing", 6)) - 6
	k_down = 196608 + fw * 3932 + rw * 6554  # 3.0 + 0.06 fw + 0.10 rw
	k_drag = 52429 + fw * 524 + rw * 2097  # 0.80 + 0.008 fw + 0.032 rw
	front_share = 28836 + fw * 786 - rw * 655  # 0.44 + 0.012 fw - 0.010 rw
	brake_front = clampi(int(setup.get("brake_bias", 57)), 50, 64) * ONE / 100
	diff_lock = (clampi(int(setup.get("differential", 6)), 1, 11) - 1) * ONE / 10

	brake_grip = ONE + clampi(int(stats.get("braking", 50)), 0, 100) * 3932 / 100  # up to +6%
	traction_grip = ONE + clampi(int(stats.get("traction", 50)), 0, 100) * 3932 / 100 + Fx.mul(diff_lock, 3277)
	slide_grip = 57672 + clampi(int(stats.get("cornering", 50)), 0, 100) * 4588 / 100  # 0.88 to 0.95
	harvest_eff = 39322 + clampi(int(stats.get("energy", 50)), 0, 100) * 13107 / 100  # 0.60 to 0.80

	# Parts: each value is clamped so a broken catalogue can never make a rocket
	k_down = k_down * (1000 + clampi(int(car.get("downforce", 0)), -150, 150)) / 1000
	k_drag = k_drag * (1000 + clampi(int(car.get("drag", 0)), -150, 150)) / 1000
	front_share += clampi(int(car.get("balance", 0)), -60, 60) * ONE / 1000
	p_ice = P_ICE + clampi(int(car.get("power", 0)), -40, 40) * 1000
	harvest_eff = harvest_eff * (1000 + clampi(int(car.get("harvest", 0)), -200, 200)) / 1000
	mu_base = MU * (1000 + clampi(int(car.get("grip", 0)), -80, 80)) / 1000
	var traction := clampi(int(car.get("traction", 0)), -120, 120)
	traction_grip = traction_grip * (1000 + traction) / 1000
	f_drive_max = F_DRIVE_MAX / 1000 * (1000 + traction)

	# The attempt seed moves grip by up to 0.4% and adds up to 3 m/s of wind,
	# so a lap recorded for one attempt does not replay cleanly in another.
	var s0 := seed[0] if seed.size() > 2 else 128
	var s1 := seed[1] if seed.size() > 2 else 0
	var s2 := seed[2] if seed.size() > 2 else 0
	grip_mult = ONE + (s0 - 128) * 2
	var wind := s1 * 196608 / 255  # 0 to 3 m/s
	var wind_dir := s2 * Fx.TWO_PI / 256
	wind_x = Fx.mul(wind, Fx.cos_a(wind_dir))
	wind_y = Fx.mul(wind, Fx.sin_a(wind_dir))


## Puts the car on the track at a point, pointing along it, at a speed.
func place(t: TrackData, point: int, start_speed: int) -> void:
	track = t
	idx = point
	px = t.x[point]
	py = t.y[point]
	heading = _angle_of(t.dir_x[point], t.dir_y[point])
	vx = Fx.mul(start_speed, t.dir_x[point])
	vy = Fx.mul(start_speed, t.dir_y[point])
	yaw_rate = 0
	accel_long = 0
	battery = BATTERY_MAX
	speed = absi(start_speed)
	var p := t.project(px, py, idx)
	idx = p[0]
	along = p[1]
	lateral = p[2]


## Heading of a unit vector, by bisection on the sine table (only used when placing).
func _angle_of(dx: int, dy: int) -> int:
	var lo := 0
	var hi := Fx.TWO_PI
	var best := 0
	var best_err := 1 << 62
	# coarse scan then refine: deterministic and cheap enough for a one-off
	for i in 256:
		var a := i * Fx.TWO_PI / 256
		var err := absi(Fx.cos_a(a) - dx) + absi(Fx.sin_a(a) - dy)
		if err < best_err:
			best_err = err
			best = a
	lo = best - Fx.TWO_PI / 256
	hi = best + Fx.TWO_PI / 256
	for i in 512:
		var a := lo + (hi - lo) * i / 512
		var err := absi(Fx.cos_a(a) - dx) + absi(Fx.sin_a(a) - dy)
		if err < best_err:
			best_err = err
			best = a
	return Fx.wrap_angle(best)


## Advances one tick. steer -127..127 (right positive), throttle and brake 0..255.
## The brake only ever brakes; reverse is its own control.
func step(steer: int, throttle: int, brake: int, boost: bool, reverse: bool = false) -> void:
	var c := Fx.cos_a(heading)
	var s := Fx.sin_a(heading)
	var v_long := (vx * c + vy * s) >> 16
	var v_lat := (vy * c - vx * s) >> 16
	speed = Fx.length(vx, vy)

	# Aero, against the air (wind included)
	var in_zone := (track.flags[idx] & TrackData.FLAG_STRAIGHT_MODE) != 0
	if in_zone and not _was_in_zone:
		_sm_armed = true
	_was_in_zone = in_zone
	if brake > 0 or throttle < 128:
		_sm_armed = false
	straight_mode = _sm_armed and in_zone and throttle >= 230
	var air_x := vx - wind_x
	var air_y := vy - wind_y
	var air_speed := Fx.length(air_x, air_y)
	var air_sq := Fx.mul(air_speed, air_speed)
	var downforce := Fx.mul(k_down, air_sq)
	var drag := Fx.mul(k_drag, air_sq)
	if straight_mode:
		downforce = Fx.mul(downforce, SM_DOWNFORCE)
		drag = Fx.mul(drag, SM_DRAG)

	# Loads on each axle: static weight, downforce, weight transfer
	var weight := MASS * G
	var static_f := Fx.mul(weight, Fx.div(B_CG, WHEELBASE))
	var static_r := weight - static_f
	var down_f := Fx.mul(downforce, front_share)
	var transfer := Fx.mul(MASS * accel_long, Fx.div(CG_HEIGHT, WHEELBASE))
	var fz_f := maxi(static_f + down_f - transfer, static_f / 6)
	var fz_r := maxi(static_r + downforce - down_f + transfer, static_r / 6)

	var mu := Fx.mul(mu_base, grip_mult)
	if tyre_model:
		mu = Fx.mul(mu, tyre_grip())
	var roll := F_ROLL
	if surface == Surface.KERB:
		mu = Fx.mul(mu, MU_KERB)
	elif surface == Surface.GRASS:
		mu = Fx.mul(mu, MU_GRASS)
		roll += F_GRASS
	var fmax_f := Fx.mul(mu, fz_f)
	var fmax_r := Fx.mul(mu, fz_r)

	# Steering: less lock at speed, as a real driver uses
	var steer_max := Fx.div(STEER_LOCK, ONE + Fx.div(absi(v_long), STEER_SPEED))
	steer_angle = steer_max * clampi(steer, -127, 127) / 127
	var forward := 1 if v_long >= 0 else -1

	# Lateral: slip of each axle
	var denom := maxi(absi(v_long), V_MIN)
	var lat_f := v_lat + Fx.mul(A_CG, yaw_rate)
	var lat_r := v_lat - Fx.mul(B_CG, yaw_rate)
	var slip_f := Fx.div(lat_f, denom) - steer_angle * forward
	var slip_r := Fx.div(lat_r, denom)
	var fy_f := _lateral(slip_f, fmax_f, SLIP_PEAK)
	var fy_r := _lateral(slip_r, fmax_r, REAR_SLIP_PEAK)

	# Longitudinal: throttle, brakes, lift-off, reverse
	var drive := 0
	var brake_force := 0
	var reversing := reverse and throttle == 0 and v_long < ONE / 2
	boosting = boost and battery > 0 and throttle > 0 and v_long > 0
	if reversing:
		if v_long > -393216:  # up to 6 m/s backwards
			drive = -F_REVERSE
	elif throttle > 0:
		var power := p_ice + (P_BOOST if boosting else 0)
		drive = mini((power << 32) / maxi(v_long, 655360), f_drive_max) * throttle / 255
	elif v_long > ONE:
		drive = -F_ENGINE_BRAKE
	if not reversing and brake > 0:
		brake_force = F_BRAKE_MAX / 255 * brake
		# Never push the car backwards once it has stopped
		brake_force = mini(brake_force, MASS * absi(v_long) * Fx.TICKS)
	var brake_f := Fx.mul(brake_force, brake_front)
	var brake_r := brake_force - brake_f
	var fx_f := -brake_f * forward
	var fx_r := drive - brake_r * forward

	# Each axle shares its grip between the two directions
	var front := _combine(fx_f, fy_f, fmax_f, brake_grip)
	var rear := _combine(fx_r, fy_r, fmax_r, traction_grip if fx_r > 0 else brake_grip)
	fx_f = front[0]
	fy_f = front[1]
	fx_r = rear[0]
	fy_r = rear[1]
	front_locked = front[2] == 1
	rear_sliding = rear[2] == 1 or absi(slip_r) > REAR_SLIP_PEAK * 2

	# A tyre cannot push harder than it takes to stop its own sideways slide in one tick
	var wheel_slip_f := lat_f - Fx.mul(v_long, steer_angle)
	var cap_f := MASS_FRONT * absi(wheel_slip_f) * Fx.TICKS
	var cap_r := MASS_REAR * absi(lat_r) * Fx.TICKS
	fy_f = clampi(fy_f, -cap_f, cap_f)
	fy_r = clampi(fy_r, -cap_r, cap_r)

	# Car-frame forces and yaw torque
	var cd := Fx.cos_a(steer_angle)
	var sd := Fx.sin_a(steer_angle)
	var front_lat := Fx.mul(fy_f, cd) + Fx.mul(fx_f, sd)
	var f_long := fx_r + Fx.mul(fx_f, cd) - Fx.mul(fy_f, sd)
	var f_lat := fy_r + front_lat
	var torque := Fx.mul(A_CG, front_lat) - Fx.mul(B_CG, fy_r)
	torque -= Fx.mul(yaw_rate, speed) * YAW_DAMPING
	if throttle > 0:
		# A locked differential resists rotation under power: stable, but understeer
		torque -= Fx.mul(Fx.mul(diff_lock, 196608000), yaw_rate)  # up to 3000 N m per rad/s

	var fwx := Fx.mul(f_long, c) - Fx.mul(f_lat, s)
	var fwy := Fx.mul(f_long, s) + Fx.mul(f_lat, c)
	if air_speed > 0:
		fwx -= Fx.mul(drag, Fx.div(air_x, air_speed))
		fwy -= Fx.mul(drag, Fx.div(air_y, air_speed))
	if speed > 0:
		var r := mini(roll, MASS * speed * Fx.TICKS)
		fwx -= Fx.mul(r, Fx.div(vx, speed))
		fwy -= Fx.mul(r, Fx.div(vy, speed))

	# Integrate
	vx += fwx / (MASS * Fx.TICKS)
	vy += fwy / (MASS * Fx.TICKS)
	yaw_rate += torque / (INERTIA * Fx.TICKS)
	heading = Fx.wrap_angle(heading + yaw_rate / Fx.TICKS)
	px += vx / Fx.TICKS
	py += vy / Fx.TICKS
	accel_long = f_long / MASS

	# Energy: Boost spends the battery, braking and lifting refill it
	if boosting:
		battery -= P_BOOST * throttle / 255 / Fx.TICKS
	var harvest := 0
	if brake > 0 and v_long > 0:
		harvest = mini(P_HARVEST_MAX, (brake_r * v_long) >> 32)
	elif throttle == 0 and v_long > ONE:
		harvest = mini(P_HARVEST_MAX / 3, (F_ENGINE_BRAKE * v_long) >> 32)
	battery = clampi(battery + Fx.mul(harvest, harvest_eff) / Fx.TICKS, 0, BATTERY_MAX)

	if tyre_model:
		wear = mini(1000000, wear + ((speed / Fx.TICKS) * COMPOUND_WEAR[compound] >> 16) + (40 if front_locked or rear_sliding else 0))

	_track_contact()


## Grip multiplier from compound and wear: a slow fade, then a cliff.
func tyre_grip() -> int:
	var loss := wear * 6554 / 1000000  # up to 10% over the tyre's life
	if wear > WEAR_CLIFF:
		loss += (wear - WEAR_CLIFF) * 22938 / 1000000  # plus up to 14% past the cliff
	return COMPOUND_GRIP[compound] - Fx.mul(COMPOUND_GRIP[compound], loss)


## Puts the car at a point with a sideways offset (fixed point metres), standing still.
func place_at(t: TrackData, point: int, offset: int) -> void:
	place(t, point, 0)
	px += (-t.dir_y[point] * offset) >> 16
	py += (t.dir_x[point] * offset) >> 16
	var p := t.project(px, py, idx)
	idx = p[0]
	along = p[1]
	lateral = p[2]


## Holds the car still (on the grid, in the pit box).
func hold() -> void:
	vx = 0
	vy = 0
	yaw_rate = 0
	accel_long = 0
	speed = 0


## Grip from a slip: rises to the peak, then falls toward the sliding level.
func _lateral(slip: int, fmax: int, peak: int) -> int:
	var a := absi(slip)
	var g: int
	if a <= peak:
		g = Fx.div(a, peak)
	elif a >= peak * 3:
		g = slide_grip
	else:
		g = ONE - Fx.mul(ONE - slide_grip, Fx.div(a - peak, peak * 2))
	var f := Fx.mul(g, fmax)
	return -f if slip > 0 else f


## Friction circle for one axle. Returns [fx, fy, 1 if the wheels lock or spin].
func _combine(fx: int, fy: int, fmax: int, long_limit: int) -> Array[int]:
	if absi(fx) > Fx.mul(fmax, long_limit):
		var slide := Fx.mul(fmax, LONG_SLIDE)
		return [slide if fx > 0 else -slide, Fx.mul(fy, LOCKED_LATERAL), 1]
	var total := Fx.length(fx >> 8, fy >> 8) << 8
	if total > fmax and total > 0:
		var k := Fx.div(fmax, total)
		return [Fx.mul(fx, k), Fx.mul(fy, k), 0]
	return [fx, fy, 0]


## Track position, surface, track limits and walls.
func _track_contact() -> void:
	var p := track.project(px, py, idx)
	idx = p[0]
	along = p[1]
	lateral = p[2]
	wall_hit = 0
	var hw := track.half_width
	var wall := hw + track.runoff - CAR_RADIUS
	if absi(lateral) > wall:
		var side := 1 if lateral > 0 else -1
		var nx := -track.dir_y[idx] * side  # outward normal
		var ny := track.dir_x[idx] * side
		var excess := absi(lateral) - wall
		px -= Fx.mul(excess, nx)
		py -= Fx.mul(excess, ny)
		lateral = wall * side
		var into := (vx * nx + vy * ny) >> 16
		if into > 0:
			wall_hit = into
			vx -= Fx.mul(Fx.mul(into, 81920), nx)  # remove it, plus a 0.25 bounce
			vy -= Fx.mul(Fx.mul(into, 81920), ny)
		vx = Fx.mul(vx, 63570)  # scraping the wall: -3% a tick
		vy = Fx.mul(vy, 63570)
		yaw_rate = Fx.mul(yaw_rate, 52429)
	var out := absi(lateral)
	# the inside run-off along the main straight is the pit lane: asphalt, and no track limits
	in_pit_lane = track.in_pit_zone(idx) and lateral < -hw and lateral > -track.pit_outer - CAR_HALF_WIDTH
	off_track = out > hw + CAR_HALF_WIDTH and not in_pit_lane
	if in_pit_lane:
		surface = Surface.ASPHALT
		return
	if out <= hw:
		surface = Surface.ASPHALT
	elif out <= hw + KERB_WIDTH and (track.flags[idx] & 3) != 0:
		surface = Surface.KERB
	else:
		surface = Surface.GRASS if out > hw + CAR_HALF_WIDTH / 2 else Surface.ASPHALT
