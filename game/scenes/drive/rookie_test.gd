class_name RookieTest
extends RefCounted
## The first-time tutorial: four steps checked by what the car actually does,
## in the order the circuit presents them.

signal step_changed(step: int, title: String, text: String)
signal feedback(text: String, good: bool)
signal passed

## {drive_brake} and the like are filled in with the keys bound now (Settings).
const STEPS := [
	["THROTTLE", "Hold {drive_throttle} (or {pad_throttle}) to accelerate. Reach 180 km/h."],
	["BRAKING", "Turn 1 is coming. Brake with {drive_brake} (or {pad_brake}) when the line turns red, around the 100 m board, then turn in."],
	["STRAIGHT MODE + BOOST", "On the long back straight the wings open by themselves. Hold {drive_boost} (or {pad_boost}) to Boost."],
	["CLEAN LAP", "Finish the lap with two wheels inside the white lines. Then you're race ready."],
]

var step := -1
var _track: TrackData
var _zone_start := 0
var _zone_end := 0
var _hit_wall := false
var _boost_ticks := 0
var _saw_sm := false
var _lap_seen := 0


func _init(t: TrackData) -> void:
	_track = t
	# the first braking zone after the start line is Turn 1
	var n := t.size()
	var i := 0
	while i < n and (t.flags[i] & 8) == 0:
		i += 1
	_zone_start = i
	while i < n and (t.flags[i] & 8) != 0:
		i += 1
	_zone_end = i


func start() -> void:
	_go(0)


func _go(i: int) -> void:
	step = i
	if step >= STEPS.size():
		passed.emit()
		return
	step_changed.emit(step, STEPS[step][0], text())


## The current step's instructions, with the keys bound now.
func text() -> String:
	if step < 0 or step >= STEPS.size():
		return ""
	var keys := {}
	for a: String in ["drive_throttle", "drive_brake", "drive_boost"]:
		keys[a] = Settings.keys_text(a)
		keys[a.replace("drive_", "pad_")] = Settings.pad_text(a)
	return String(STEPS[step][1]).format(keys)


## Called every physics tick with the session (after it stepped).
func tick(s: SessionSim) -> void:
	var car := s.car
	var kmh := car.speed / 65536.0 * 3.6
	match step:
		0:
			if kmh >= 180.0:
				feedback.emit("GOOD. NOW LOOK AHEAD FOR THE BOARDS", true)
				_go(1)
		1:
			if car.wall_hit > 0:
				_hit_wall = true
			var past := car.idx > _zone_end + 12 and car.idx < _zone_end + 120
			if past:
				if _hit_wall:
					feedback.emit("TOO LATE: BRAKE EARLIER, AT THE 150 BOARD", false)
				else:
					feedback.emit("NICE BRAKING", true)
				_go(2)
		2:
			if car.boosting:
				_boost_ticks += 1
			if car.straight_mode:
				_saw_sm = true
			if _boost_ticks > 120 and _saw_sm:
				feedback.emit("THAT'S 350 KW OF ELECTRIC BOOST", true)
				_go(3)
		3:
			if s.laps.size() > _lap_seen:
				_lap_seen = s.laps.size()
				var lap: Dictionary = s.laps[-1]
				if lap["valid"]:
					_go(4)
				else:
					feedback.emit("LAP DELETED: STAY INSIDE THE WHITE LINES. GO AGAIN", false)
