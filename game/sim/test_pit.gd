extends SceneTree

func _init() -> void:
	var track := TrackData.load_id("mtkvari")
	var e := {"setup": {}, "stats": {}, "car": {}, "pace": 950, "crew": 60, "compound": 0, "pit_lap": 1, "pit_compound": 1}
	var race := RaceSim.new(track, [e, e.duplicate(), e.duplicate()], PackedByteArray([1, 2, 3]), [0, 1, 2], 3)
	var n := track.size()
	print("n %d pit_in %d pit_out %d box1 %d center %.1f inner %.1f outer %.1f hw %.1f" % [n, track.pit_in, track.pit_out, track.pit_box(1), track.pit_center / 65536.0, track.pit_inner / 65536.0, track.pit_outer / 65536.0, track.half_width / 65536.0])
	var last := -1
	while race.tick < 120 * 120:
		race.step(0, 0, 255, 0)
		var c := race.cars[1]
		if track.in_pit_zone(c.idx) and race.crossings[1] >= 1 and race.tick % 30 == 0:
			print("t %d idx %d lat %.1f v %.1f inlane %s state %d cross %d" % [race.tick, c.idx, c.lateral / 65536.0, c.speed / 65536.0, c.in_pit_lane, race.pit_state[1], race.crossings[1]])
		for ev in race.events:
			if ev["type"] in ["pit_in", "pit_out"]:
				print(ev)
	quit()
