extends SceneTree
## Headless race check: 6 cars, the "player" driven by an AI driver through the
## recorded-input path, then the race is re-driven from those inputs.
##   godot --headless --path game -s res://sim/test_race.gd

const SETUP := {"front_wing": 6, "rear_wing": 6, "brake_bias": 57, "differential": 6}
const STATS := {"braking": 66, "cornering": 66, "traction": 68, "energy": 72}


func _entries() -> Array:
	var out := []
	var paces := [0, 965, 958, 951, 944, 937]
	for i in 6:
		out.append({"setup": SETUP, "stats": STATS, "car": {}, "pace": paces[i], "crew": 40 + i * 10,
			"compound": 0 if i % 2 == 0 else 1, "pit_lap": 2 + i % 2, "pit_compound": 1 if i % 2 == 0 else 2})
	return out


func _init() -> void:
	var track := TrackData.load_id("mtkvari")
	var seed := PackedByteArray([77, 12, 200, 5])
	var grid := [2, 0, 1, 3, 4, 5]
	var race := RaceSim.new(track, _entries(), seed, grid, 5)
	var me := AiDriver.new(track, 950)
	me.pit_lap = 2
	me.pit_compound = 1
	var t0 := Time.get_ticks_msec()
	var pits := 0
	var contacts := 0
	while not race.finished() and race.tick < 120 * 600:
		var car := race.cars[0]
		var lane := 0
		var limit := 0
		if not me.pitted and race.crossings[0] >= me.pit_lap and track.in_pit_zone(car.idx):
			lane = track.pit_center
			limit = RaceSim.PIT_LIMIT
			limit = mini(limit, race.box_approach_speed(0))
		var cmd := me.drive(car, lane, limit, race._blocked_side(0))
		race.step(cmd[0], cmd[1], cmd[2], cmd[3] | (2 << 2))
		for e in race.events:
			if e["type"] == "pit_in":
				pits += 1
				print("pit in: car %d at tick %d, %.2f s%s" % [e["car"], race.tick, e["ticks"] / 120.0, " FUMBLE" if e["fumble"] else ""])
				if e["car"] == 0:
					me.pitted = true
			if e["type"] == "contact":
				contacts += 1
	print("race ticks %d in %d ms, pits %d, contact ticks %d" % [race.tick, Time.get_ticks_msec() - t0, pits, contacts])
	for p in race.order():
		print("P%d car %d  %s  stops %d  wear %d%%  pen %d" % [race.order().find(p) + 1, p, _fmt(race.race_us(p)), race.pit_stops[p], race.cars[p].wear / 10000, race.penalty_s[p]])
	# Re-drive
	var raw := SessionSim.decode_inputs(SessionSim.encode_inputs(race.inputs))
	var again := RaceSim.new(track, _entries(), seed, grid, 5)
	for i in raw.size() / 4:
		again.step(raw[4 * i] - 128, raw[4 * i + 1], raw[4 * i + 2], raw[4 * i + 3])
	var same := again.order() == race.order()
	for i in 6:
		same = same and again.finish_fp[i] == race.finish_fp[i]
	print("re-drive identical: ", same)
	quit()


func _fmt(us: int) -> String:
	if us < 0:
		return "DNF"
	return "%d:%06.3f" % [us / 60000000, (us % 60000000) / 1000000.0]
