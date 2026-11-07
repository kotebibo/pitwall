extends SceneTree
## Measures the car on a huge open circle: acceleration, braking, cornering.
##   godot --headless --path game -s res://sim/test_physics.gd

const SETUP := {"front_wing": 6, "rear_wing": 6, "brake_bias": 57, "differential": 6}
const STATS := {"braking": 50, "cornering": 50, "traction": 50, "energy": 50}


func _init() -> void:
	var t := _open_track()
	# Acceleration
	for boost in [false, true]:
		var car := _car(t, 0)
		var marks := {}
		for i in 120 * 40:
			car.step(0, 255, 0, boost)
			var kmh := Fx.to_float(car.speed) * 3.6
			for m in [100, 200, 300]:
				if kmh >= m and not marks.has(m):
					marks[m] = i / 120.0
		print("accel boost=%s: %s, top after 40 s %.0f km/h, battery %d kJ" % [boost, marks, Fx.to_float(car.speed) * 3.6, car.battery / 1000])
	# Braking from 300 km/h
	for brake in [255, 200, 170]:
		var car := _car(t, Fx.from_float(300 / 3.6))
		var x0 := car.px
		var locked := 0
		var i := 0
		while Fx.to_float(car.speed) * 3.6 > 80.0 and i < 2000:
			car.step(0, 0, brake, false)
			if car.front_locked:
				locked += 1
			i += 1
		print("brake %d: 300->80 km/h in %.0f m, %.2f s, locked %d ticks" % [brake, Fx.to_float(car.px - x0), i / 120.0, locked])
	# Cornering: hold a speed, constant steer
	for kmh in [80, 150, 220, 290]:
		var line := "corner %d km/h:" % kmh
		for steer in [30, 60, 90, 127]:
			var car := _car(t, Fx.from_float(kmh / 3.6))
			var target := Fx.from_float(kmh / 3.6)
			var lat_g := 0.0
			var spun := false
			for i in 120 * 6:
				var thr := 255 if car.speed < target else 0
				car.step(steer, thr, 0, false)
				var c := Fx.cos_a(car.heading)
				var s := Fx.sin_a(car.heading)
				var v_lat := (car.vy * c - car.vx * s) >> 16
				var v_long := (car.vx * c + car.vy * s) >> 16
				if absi(v_lat) > absi(v_long) / 3:
					spun = true
				if i == 120 * 6 - 1:
					# lateral acceleration = v * yaw rate (steady state)
					lat_g = Fx.to_float(car.speed) * Fx.to_float(car.yaw_rate) / 9.81
			line += "  s%d=%.2fg%s(%.0f)" % [steer, lat_g, " SPIN" if spun else "", Fx.to_float(car.speed) * 3.6]
		print(line)
	quit()


func _car(t: TrackData, v: int) -> CarSim:
	var car := CarSim.new()
	car.configure(SETUP, STATS, PackedByteArray([128, 0, 0, 0]))
	car.place(t, 0, v)
	return car


## A circle 4 km round and a kilometre wide: no walls in reach.
func _open_track() -> TrackData:
	var t := TrackData.new()
	var n := 3000
	var r := 3000.0
	t.half_width = Fx.from_float(800.0)
	t.runoff = Fx.from_float(100.0)
	t.sectors = [1000, 2000]
	t.x.resize(n)
	t.y.resize(n)
	t.dir_x.resize(n)
	t.dir_y.resize(n)
	t.seg_len.resize(n)
	t.flags.resize(n)
	t.dist.resize(n)
	for i in n:
		var a := TAU * i / n
		t.x[i] = Fx.from_float(r * sin(a))
		t.y[i] = Fx.from_float(r - r * cos(a))
	for i in n:
		var j := (i + 1) % n
		var dx := float(t.x[j] - t.x[i])
		var dy := float(t.y[j] - t.y[i])
		var ln := sqrt(dx * dx + dy * dy)
		t.dir_x[i] = roundi(dx / ln * 65536.0)
		t.dir_y[i] = roundi(dy / ln * 65536.0)
		t.seg_len[i] = roundi(ln)
	return t
