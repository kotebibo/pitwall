extends SceneTree
## Headless physics check: an autopilot drives laps, then the recorded inputs
## are re-driven and must give identical times.
##   godot --headless --path game -s res://sim/test_drive.gd

const SETUP := {"front_wing": 6, "rear_wing": 6, "brake_bias": 57, "differential": 6}
var STATS := {"braking": 50, "cornering": 50, "traction": 50, "energy": 50}


func _init() -> void:
	var track := TrackData.load_id("mtkvari")
	var seed := PackedByteArray([128, 0, 0, 0])
	var args := OS.get_cmdline_user_args()
	var laps_wanted := 3
	var out_path := ""
	var car := {}  # parts spec, e.g. --car {"weight":20}
	for i in args.size() - 1:
		if args[i] == "--seed":
			seed = PackedByteArray()
			for k in range(0, args[i + 1].length() - 1, 2):
				seed.append(args[i + 1].substr(k, 2).hex_to_int())
		elif args[i] == "--laps":
			laps_wanted = int(args[i + 1])
		elif args[i] == "--stats":
			var v := args[i + 1].split(",")
			STATS = {"braking": int(v[0]), "cornering": int(v[1]), "traction": int(v[2]), "energy": int(v[3])}
		elif args[i] == "--out":
			out_path = args[i + 1]
		elif args[i] == "--car":
			var parsed: Variant = JSON.parse_string(args[i + 1])
			if parsed is Dictionary:
				car = parsed
	var pilot := Autopilot.new(track)
	var s := SessionSim.new(track, SETUP, STATS, seed, SessionSim.Kind.QUALIFYING, car)
	var top := 0.0
	var walls := 0
	var limits := 0
	var t0 := Time.get_ticks_msec()
	var min_speeds := {}
	while s.laps.size() < laps_wanted and s.tick < 120 * 400:
		var inp := pilot.drive(s.car)
		var was_valid := s.lap_valid
		var idx0 := s.car.idx
		s.step(inp[0], inp[1], inp[2], inp[3])
		if was_valid and not s.lap_valid and s.lap_number > 0:
			print("invalid at tick %d idx %d->%d lat %.1f off %s speed %.0f" % [s.tick, idx0, s.car.idx, s.car.lateral / 65536.0, s.car.off_track, s.car.speed / 65536.0 * 3.6])
		top = maxf(top, Fx.to_float(s.car.speed))
		for e in s.events:
			if e["type"] == "wall":
				walls += 1
			if e["type"] == "limits":
				limits += 1
		var seg := s.car.idx / 25
		var kmh := Fx.to_float(s.car.speed) * 3.6
		min_speeds[seg] = minf(min_speeds.get(seg, 999.0), kmh)
	var ms := Time.get_ticks_msec() - t0
	print("ticks %d in %d ms (%.1f us/tick)" % [s.tick, ms, ms * 1000.0 / maxi(s.tick, 1)])
	print("top speed %.0f km/h, wall ticks %d, limit violations %d, battery %d kJ" % [top * 3.6, walls, limits, s.car.battery / 1000])
	for lap in s.laps:
		print("lap %d: %s valid=%s sectors %s" % [lap["lap"], _fmt(lap["us"]), lap["valid"], lap["sectors"]])
	var mins := []
	for k in min_speeds.keys():
		mins.append("%d:%.0f" % [k * 100, min_speeds[k]])
	print("min km/h by 100 m: ", " ".join(mins))

	if out_path != "":
		var f := FileAccess.open(out_path, FileAccess.WRITE)
		f.store_string(s.encoded_inputs())
		f.close()
	# Re-drive from the recorded inputs
	var rle := SessionSim.encode_inputs(s.inputs)
	var raw := SessionSim.decode_inputs(rle)
	print("inputs %d bytes raw, %d RLE, roundtrip %s, hash %s" % [s.inputs.size(), rle.size(), raw == s.inputs, SessionSim.hash_inputs(raw).substr(0, 16)])
	var r := SessionSim.new(track, SETUP, STATS, seed, SessionSim.Kind.QUALIFYING, car)
	for i in raw.size() / 4:
		r.step(raw[4 * i] - 128, raw[4 * i + 1], raw[4 * i + 2], raw[4 * i + 3])
	var same := r.laps.size() == s.laps.size()
	for i in mini(r.laps.size(), s.laps.size()):
		same = same and r.laps[i]["us"] == s.laps[i]["us"]
	print("re-drive identical: %s (pos %d,%d vs %d,%d)" % [same, r.car.px, r.car.py, s.car.px, s.car.py])
	# A different seed must change the result
	var o := SessionSim.new(track, SETUP, STATS, PackedByteArray([140, 200, 90, 0]))
	for i in raw.size() / 4:
		o.step(raw[4 * i] - 128, raw[4 * i + 1], raw[4 * i + 2], raw[4 * i + 3])
	print("other seed laps: ", o.laps.map(func(l: Dictionary) -> String: return _fmt(l["us"])))
	quit()


func _fmt(us: int) -> String:
	return "%d:%06.3f" % [us / 60000000, (us % 60000000) / 1000000.0]
