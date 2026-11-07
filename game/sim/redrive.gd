extends SceneTree
## Server-side verification: re-drives a recorded run with the same physics
## the player drove and prints what it produced. The server runs:
##   godot --headless --path game -s res://sim/redrive.gd -- --in run.json --out result.json
## run.json: {"track", "setup", "stats", "car" (parts spec), "seed" (hex), "inputs" (base64 run-length), "kind"}


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var in_path := ""
	var out_path := ""
	for i in args.size() - 1:
		if args[i] == "--in":
			in_path = args[i + 1]
		elif args[i] == "--out":
			out_path = args[i + 1]
	var result := _redrive(in_path)
	var text := JSON.stringify(result)
	if out_path.is_empty():
		print(text)
	else:
		var f := FileAccess.open(out_path, FileAccess.WRITE)
		f.store_string(text)
		f.close()
	quit(0 if not result.has("error") else 1)


func _redrive(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {"error": "cannot read " + path}
	var run: Variant = JSON.parse_string(f.get_as_text())
	if not run is Dictionary:
		return {"error": "bad run file"}
	var r: Dictionary = run
	var track := TrackData.load_id(String(r.get("track", "")))
	if track == null:
		return {"error": "unknown track"}
	var seed := PackedByteArray()
	var seed_hex := String(r.get("seed", ""))
	for i in range(0, seed_hex.length() - 1, 2):
		seed.append(seed_hex.substr(i, 2).hex_to_int())
	if String(r.get("kind", "")) == "race":
		return _redrive_race(r, track, seed)
	var setup: Dictionary = r.get("setup", {})
	var stats: Dictionary = r.get("stats", {})
	var kind := SessionSim.Kind.PRACTICE if r.get("kind", "") == "practice" else SessionSim.Kind.QUALIFYING
	var raw := SessionSim.decode_inputs(Marshalls.base64_to_raw(String(r.get("inputs", ""))))
	if raw.size() % 4 != 0 or raw.size() > 4 * 120 * 1800:
		return {"error": "bad input log"}
	var car: Dictionary = r.get("car", {})
	var s := SessionSim.new(track, setup, stats, seed, kind, car)
	for i in raw.size() / 4:
		s.step(raw[4 * i] - 128, raw[4 * i + 1], raw[4 * i + 2], raw[4 * i + 3])
	return {
		"physicsVersion": SessionSim.PHYSICS_VERSION,
		"ticks": s.tick,
		"laps": s.laps,
		"inputHash": SessionSim.hash_inputs(raw),
	}


## A driven race: run.json also has "entries" (see RaceSim), "grid" and "laps".
func _redrive_race(r: Dictionary, track: TrackData, seed: PackedByteArray) -> Dictionary:
	var raw := SessionSim.decode_inputs(Marshalls.base64_to_raw(String(r.get("inputs", ""))))
	if raw.size() % 4 != 0 or raw.size() > 4 * 120 * 1800:
		return {"error": "bad input log"}
	var grid: Array = []
	for g: Variant in r.get("grid", []):
		grid.append(int(g))
	var race := RaceSim.new(track, r.get("entries", []), seed, grid, int(r.get("laps", 5)))
	for i in raw.size() / 4:
		race.step(raw[4 * i] - 128, raw[4 * i + 1], raw[4 * i + 2], raw[4 * i + 3])
		if race.finished():
			break
	var cars := []
	for i in race.cars.size():
		cars.append({"raceUs": race.race_us(i), "penaltyS": race.penalty_s[i], "pitStops": race.pit_stops[i], "laps": maxi(0, race.crossings[i] - 1)})
	return {
		"physicsVersion": SessionSim.PHYSICS_VERSION,
		"ticks": race.tick,
		"finished": race.finished(),
		"order": race.order(),
		"cars": cars,
		"inputHash": SessionSim.hash_inputs(raw),
	}
