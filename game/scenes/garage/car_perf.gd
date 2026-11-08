class_name CarPerf
extends RefCounted
## What a car spec means on track, in numbers a player knows: top speed, corner
## speed, braking distance, 0-200 time, energy recovered and weight.
##
## Display only, in floats: the formulas and constants are CarSim's
## (game/sim/car_sim.gd configure and step), so a part that shows faster here
## is faster in the physics. Nothing here ever reaches the sim.

const KEYS: Array[String] = ["top_speed", "cornering", "braking", "acceleration", "battery", "weight"]
const NAMES := {
	"top_speed": "TOP SPEED", "cornering": "CORNERING", "braking": "BRAKING",
	"acceleration": "ACCELERATION", "battery": "BATTERY", "weight": "WEIGHT",
	"balance": "BALANCE",
}
const HELP := {
	"top_speed": "Top speed: how fast the car goes at the end of a long straight with Boost. Less drag and more power raise it.",
	"cornering": "Cornering: the fastest the car can take a medium corner (60 m radius) before the tyres slide. Grip, downforce and weight decide it.",
	"braking": "Braking: metres to stop from 200 km/h with the tyres at their limit. Shorter is better: you can brake later.",
	"acceleration": "Acceleration: seconds from 0 to 200 km/h with Boost. Power, traction and weight decide it. Lower is better.",
	"battery": "Battery: energy won back for Boost from one heavy stop (300 to 100 km/h). The battery holds 4,000 kJ.",
	"weight": "Weight: the car with its driver. Every kilo makes it accelerate, brake and turn a little worse.",
	"balance": "Balance: the share of the downforce on the front wheels. More front: sharper turn-in, but the rear can slide. Less: a calm rear, but the car runs wide in corners.",
}
## The TUNING tab's bars: what a setup changes. BRAKING there is braking without locking a wheel, so brake bias moves it.
const SETUP_KEYS: Array[String] = ["top_speed", "cornering", "braking", "acceleration", "balance"]
const SETUP_HELP := {
	"top_speed": "Top speed: how fast the car goes at the end of a long straight with Boost. Less wing means less drag and a higher top speed.",
	"cornering": "Cornering: the fastest the car can take a medium corner (60 m radius) before the tyres slide. More wing pushes the tyres down harder.",
	"braking": "Braking: metres to stop from 200 km/h, braking as hard as you can without locking a wheel. Brake bias and wing change it. Shorter is better.",
	"acceleration": "Acceleration: seconds from 0 to 200 km/h with Boost. Drag and grip at the rear decide it. Lower is better.",
	"balance": "Balance: the share of the downforce on the front wheels. More front: sharper turn-in, but the rear can slide. Less: a calm rear, but the car runs wide in corners. Not better or worse: it is how the car feels.",
}
## Bar scale for setups: a setup moves these numbers much more than a part does.
const SETUP_SPAN := {"top_speed": 0.08, "cornering": 0.05, "braking": 0.12, "acceleration": 0.04, "balance": 0.25}
## Neither better nor worse: drawn in yellow.
const NEUTRAL := {"balance": true}
const LOWER_IS_BETTER := {"braking": true, "acceleration": true, "weight": true}
## Bar scale: the standard car sits in the middle and the bar's ends are this
## share better or worse (parts move these numbers by a few percent at most).
const SPAN := {"top_speed": 0.025, "cornering": 0.015, "braking": 0.012, "acceleration": 0.02, "battery": 0.12, "weight": 0.02}
const CORNER_R := 60.0  # m, the CORNERING bar
const SLOW_R := 25.0  # m, a hairpin, for the summary
const FAST_R := 90.0  # m, a fast sweeper, for the summary
const DT := 1.0 / 120.0  # the sim's tick
const ONE := 65536.0


## The car CarSim.configure builds from a setup, driver stats and parts spec.
static func car(setup: Dictionary, stats: Dictionary, spec: Dictionary) -> Dictionary:
	var fw: int = int(setup.get("front_wing", 6)) - 6
	var rw: int = int(setup.get("rear_wing", 6)) - 6
	var diff_lock := (clampi(int(setup.get("differential", 6)), 1, 11) - 1) / 10.0
	var traction := clampi(int(spec.get("traction", 0)), -120, 120)
	return {
		"k_down": (196608 + fw * 3932 + rw * 6554) / ONE * (1000 + clampi(int(spec.get("downforce", 0)), -150, 150)) / 1000.0,
		"k_drag": (52429 + fw * 524 + rw * 2097) / ONE * (1000 + clampi(int(spec.get("drag", 0)), -150, 150)) / 1000.0,
		"front_share": (28836 + fw * 786 - rw * 655) / ONE + clampi(int(spec.get("balance", 0)), -60, 60) / 1000.0,
		"brake_front": clampi(int(setup.get("brake_bias", 57)), 50, 64) / 100.0,
		"brake_grip": 1.0 + clampi(int(stats.get("braking", 50)), 0, 100) * 3932 / 100.0 / ONE,
		"traction_grip": (1.0 + clampi(int(stats.get("traction", 50)), 0, 100) * 3932 / 100.0 / ONE + diff_lock * 3277 / ONE) * (1000 + traction) / 1000.0,
		"harvest_eff": (39322 + clampi(int(stats.get("energy", 50)), 0, 100) * 13107 / 100.0) / ONE * (1000 + clampi(int(spec.get("harvest", 0)), -200, 200)) / 1000.0,
		"p_ice": float(CarSim.P_ICE + clampi(int(spec.get("power", 0)), -40, 40) * 1000),
		"mu": CarSim.MU / ONE * (1000 + clampi(int(spec.get("grip", 0)), -80, 80)) / 1000.0,
		"f_drive_max": CarSim.F_DRIVE_MAX / ONE * (1000 + traction) / 1000.0,
		"mass": float(CarSim.MASS + clampi(int(spec.get("weight", 0)), -30, 30)),
	}


## Every number the garage shows for a car (see KEYS), plus slow and fast corner speeds for the summary.
static func metrics(c: Dictionary) -> Dictionary:
	var top := top_speed(c)
	return {
		"top_speed": top * 3.6,
		"cornering": corner_speed(c, CORNER_R, top) * 3.6,
		"slow_corner": corner_speed(c, SLOW_R, top) * 3.6,
		"fast_corner": corner_speed(c, FAST_R, top) * 3.6,
		"braking": braking_distance(c, 200.0 / 3.6),
		"acceleration": accel_time(c, 200.0 / 3.6),
		"battery": stop_harvest(c, 300.0 / 3.6, 100.0 / 3.6) / 1000.0,
		"weight": float(c["mass"]),
		"balance": float(c["front_share"]),
	}


## metrics() for the TUNING tab: braking without locking a wheel (brake bias counts), which axle locks first and the best bias.
static func setup_metrics(c: Dictionary) -> Dictionary:
	var m := metrics(c)
	m["braking"] = braking_distance(c, 200.0 / 3.6, true)
	m["locks_first"] = "front" if brake_limit(c, 120.0 / 3.6)[1] == 0 else "rear"
	m["best_bias"] = best_bias(c)
	return m


## The hardest braking (N) at speed v before a wheel locks with this brake bias, and which axle
## locks first (0 front, 1 rear). CarSim locks an axle once its share of the brake force passes
## its grip, and weight moves forward as the car slows (more grip at the front).
static func brake_limit(c: Dictionary, v: float) -> Array:
	var m: float = c["mass"]
	var g := CarSim.G / ONE
	var mu: float = float(c["mu"]) * float(c["brake_grip"])
	var down: float = float(c["k_down"]) * v * v
	var fs: float = c["front_share"]
	var bias: float = c["brake_front"]
	var hl := float(CarSim.CG_HEIGHT) / CarSim.WHEELBASE
	var static_f := m * g * float(CarSim.B_CG) / CarSim.WHEELBASE
	var static_r := m * g - static_f
	var front := mu * (static_f + down * fs) / maxf(bias - mu * hl, 0.01)
	var rear := mu * (static_r + down * (1.0 - fs)) / maxf(1.0 - bias + mu * hl, 0.01)
	return [minf(minf(front, rear), CarSim.F_BRAKE_MAX / ONE), 0 if front < rear else 1]


## The brake bias (50..64) that stops this car from 200 km/h in the shortest distance without locking.
static func best_bias(c: Dictionary) -> int:
	var best := 57
	var best_d := INF
	var t := c.duplicate()
	for b in range(50, 65):
		t["brake_front"] = b / 100.0
		var d := braking_distance(t, 200.0 / 3.6, true)
		if d < best_d - 0.001:
			best_d = d
			best = b
	return best


## Where drive power (combustion plus Boost) meets drag and rolling resistance, m/s.
static func top_speed(c: Dictionary) -> float:
	var power: float = float(c["p_ice"]) + CarSim.P_BOOST
	var k: float = c["k_drag"]
	var roll := CarSim.F_ROLL / ONE
	var lo := 0.0
	var hi := 250.0
	for i in 40:
		var v := (lo + hi) / 2.0
		if k * v * v * v + roll * v < power:
			lo = v
		else:
			hi = v
	return lo


## Steady speed round a corner of radius r: the tyres' grip (mass plus downforce) holds the car on the circle, m/s.
static func corner_speed(c: Dictionary, r: float, cap: float) -> float:
	var m: float = c["mass"]
	var mu: float = c["mu"]
	var g := CarSim.G / ONE
	var denom: float = m / r - mu * float(c["k_down"])
	if denom <= 0.0:
		return cap  # downforce grows faster than the corner needs: flat out
	return minf(sqrt(mu * m * g / denom), cap)


## Braking force at speed v: the tyres' limit (mass plus downforce), never more than the brakes give.
static func _brake_force(c: Dictionary, v: float) -> float:
	var m: float = c["mass"]
	var grip: float = float(c["mu"]) * float(c["brake_grip"]) * (m * CarSim.G / ONE + float(c["k_down"]) * v * v)
	return minf(CarSim.F_BRAKE_MAX / ONE, grip)


## Metres from v0 to a stop at the limit, tick by tick. `no_lock`: the limit is where the first wheel locks with this brake bias.
static func braking_distance(c: Dictionary, v0: float, no_lock: bool = false) -> float:
	var m: float = c["mass"]
	var k: float = c["k_drag"]
	var roll := CarSim.F_ROLL / ONE
	var v := v0
	var d := 0.0
	for i in 2400:
		var a := ((float(brake_limit(c, v)[0]) if no_lock else _brake_force(c, v)) + k * v * v + roll) / m
		var nv := v - a * DT
		if nv <= 0.0:
			d += v * v / (2.0 * a)  # the last part of a tick
			break
		d += (v + nv) / 2.0 * DT
		v = nv
	return d


## Seconds from standstill to v1 with Boost: drive force capped by the power, the drive limit and the rear tyres' grip.
static func accel_time(c: Dictionary, v1: float) -> float:
	var m: float = c["mass"]
	var k: float = c["k_drag"]
	var roll := CarSim.F_ROLL / ONE
	var g := CarSim.G / ONE
	var power: float = float(c["p_ice"]) + CarSim.P_BOOST
	var rear_static := m * g * (float(CarSim.A_CG) / CarSim.WHEELBASE)
	var transfer_k := float(CarSim.CG_HEIGHT) / CarSim.WHEELBASE
	var v := 0.0
	var a := 0.0
	var t := 0.0
	for i in 120 * 30:
		var drive := minf(power / maxf(v, 10.0), float(c["f_drive_max"]))
		var fz_r := rear_static + (1.0 - float(c["front_share"])) * float(c["k_down"]) * v * v + m * a * transfer_k
		drive = minf(drive, float(c["mu"]) * float(c["traction_grip"]) * fz_r)
		a = (drive - k * v * v - roll) / m
		var nv := v + a * DT
		if nv >= v1:
			return t + (v1 - v) / maxf(nv - v, 0.000001) * DT
		v = nv
		t += DT
	return t


## Energy the rear axle recovers in one stop from v0 to v1 at the limit, J.
static func stop_harvest(c: Dictionary, v0: float, v1: float) -> float:
	var m: float = c["mass"]
	var k: float = c["k_drag"]
	var roll := CarSim.F_ROLL / ONE
	var rear := 1.0 - float(c["brake_front"])
	var v := v0
	var e := 0.0
	for i in 2400:
		if v <= v1:
			break
		var f := _brake_force(c, v)
		e += minf(CarSim.P_HARVEST_MAX, f * rear * v) * float(c["harvest_eff"]) * DT
		v -= (f + k * v * v + roll) / m * DT
	return e


# ---- specs ----

## A part's wear effect, per mille (the server sends it; fresh parts are 1000).
static func effect_of(p: Dictionary) -> int:
	var d: Variant = p.get("display")
	if d is Dictionary and (d as Dictionary).has("effect"):
		return int(d["effect"])
	return 1000


## A stat scaled by a wear effect, rounded toward the faster side as the server's scaleSpec does.
static func _scale(data: Dictionary, key: String, v: int, effect: int) -> int:
	if effect == 1000:
		return v
	var x := v * effect / 1000.0
	var w := float(((data.get("lapWeights", {}) as Dictionary).get("weights", {}) as Dictionary).get(key, 0))
	if w > 0.0:
		return ceili(x)
	if w < 0.0:
		return floori(x)
	return signi(v) * roundi(absf(x))


static func _family(data: Dictionary, area: String, p: Dictionary) -> String:
	var a: Variant = (data.get("areas", {}) as Dictionary).get(area)
	if not a is Dictionary:
		return ""
	var c: Variant = ((a as Dictionary).get("concepts", {}) as Dictionary).get(String(p.get("concept", "")))
	var f: Variant = (c as Dictionary).get("family") if c is Dictionary else null
	return String(f) if f is String else ""


static func _add(data: Dictionary, spec: Dictionary, delta: Variant, effect: int = 1000) -> void:
	if not delta is Dictionary:
		return
	for k: String in delta:
		spec[k] = int(spec.get(k, 0)) + _scale(data, k, int(delta[k]), effect)


## The car spec for a set of fitted parts (area -> part), summed as the server's
## carDetail does: stats (faded by wear), conditional traits and synergies.
## `data` is the parts catalogue (Catalog.data, game/data/parts.json).
static func spec_of(parts: Dictionary, data: Dictionary) -> Dictionary:
	var spec := {}
	var traits: Dictionary = data.get("traits", {})
	var floor_family := _family(data, "floor", parts.get("floor", {}))
	for area: String in parts:
		var p: Dictionary = parts[area]
		var effect := effect_of(p)
		_add(data, spec, p.get("stats", {}), effect)
		var fam := _family(data, area, p)
		for t: Variant in p.get("traits", []):
			var tid := String((t as Dictionary).get("id", "")) if t is Dictionary else String(t)
			var cond: Variant = (traits.get(tid, {}) as Dictionary).get("conditional")
			if cond is Dictionary and String(cond.get("when", "")) == "floor_family_matches" and area != "floor" and fam != "" and fam == floor_family:
				_add(data, spec, cond.get("delta", {}), effect)
	for s: Variant in data.get("synergies", []):
		if not s is Dictionary:
			continue
		var when: Dictionary = s.get("when", {})
		var on := true
		if when.get("sameFamily") is Array:
			var first := ""
			for i in (when["sameFamily"] as Array).size():
				var a := String(when["sameFamily"][i])
				var f := _family(data, a, parts.get(a, {}))
				if f == "" or (i > 0 and f != first):
					on = false
				if i == 0:
					first = f
		if when.get("concepts") is Dictionary:
			for a: String in when["concepts"]:
				if String((parts.get(a, {}) as Dictionary).get("concept", "")) != String(when["concepts"][a]):
					on = false
		if on:
			_add(data, spec, s.get("delta", {}))
	return spec


# ---- words ----

## One plain sentence on how car b drives against car a (both from metrics()).
static func summary(a: Dictionary, b: Dictionary) -> String:
	# [change (+ is better), noticeable from, better words, worse words]; "~" becomes "a little " for small changes
	var effects := [
		[b["top_speed"] - a["top_speed"], 0.3, "~faster on the straights", "~slower on the straights"],
		[b["fast_corner"] - a["fast_corner"], 0.25, "~more grip in fast corners", "~less grip in fast corners"],
		[b["slow_corner"] - a["slow_corner"], 0.15, "~more grip in slow corners", "~less grip in slow corners"],
		[a["braking"] - b["braking"], 0.2, "brakes ~later", "brakes ~earlier"],
		[a["acceleration"] - b["acceleration"], 0.01, "~quicker to accelerate", "~slower to accelerate"],
		[b["battery"] - a["battery"], 3.0, "~more Boost from braking", "~less Boost from braking"],
	]
	var good := []
	var bad := []
	for e: Array in effects:
		var size := absf(float(e[0])) / float(e[1])
		if size < 1.0:
			continue
		var words := String(e[2] if float(e[0]) > 0 else e[3]).replace("~", "a little " if size < 3.0 else "")
		(good if float(e[0]) > 0 else bad).append([size, words])
	good.sort_custom(func(x: Array, y: Array) -> bool: return x[0] > y[0])
	bad.sort_custom(func(x: Array, y: Array) -> bool: return x[0] > y[0])
	var g: Array[String] = []
	for x: Array in good.slice(0, 2 if bad.size() < 2 else 1):
		g.append(String(x[1]))
	var w: Array[String] = []
	for x: Array in bad.slice(0, 3 - g.size()):
		w.append(String(x[1]))
	# Aero balance does not change these numbers, but it changes how the car feels
	var bal: float = b["balance"] - a["balance"]
	if absf(bal) >= 0.004 and g.size() + w.size() < 3:
		g.append("sharper on turn-in" if bal > 0 else "a more stable rear")
	var dw := roundi(b["weight"] - a["weight"])
	var kg := "" if absi(dw) < 2 else " (%d kg %s)" % [absi(dw), "lighter" if dw < 0 else "heavier"]
	if g.is_empty() and w.is_empty():
		return "Drives almost the same as the car you have now" + kg + "."
	var text := " and ".join(g)
	if not w.is_empty():
		text += (", " if text != "" else "") + " and ".join(w)
	return text.left(1).to_upper() + text.substr(1) + kg + "."
