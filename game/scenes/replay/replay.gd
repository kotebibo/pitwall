class_name ReplayScreen
extends Control
## Plays a race replay produced by the server-side sim. Positions come straight
## from the sim's cumulative lap times; nothing here decides an outcome.

signal done(race: Dictionary)

const PIT_LOSS_MS := 21000.0
const FAST := 75.0  # race ms per real ms on quiet laps
const SLOW := 20.0  # start, pit windows and the final lap

var race: Dictionary
var _replay: Dictionary
var _laps: Array = []
var _pit_laps: Array = []
var _teams: Array = []
var _lap_count := 24
var _base_lap_ms := 90000.0
var _finish_ms := 0.0
var _ms := 0.0
var _rate := SLOW
var _event_index := 0
var _ended := false

var _track: CircuitView
var _lap_label: Label
var _rows: Array[Label] = []
var _swatches: Array[ColorRect] = []
var _ticker: Label


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_replay = race["replay"]
	_laps = _replay["laps"]
	_pit_laps = _replay["pitLaps"]
	_teams = _replay["teams"]
	var track: Dictionary = _replay["track"]
	_lap_count = int(track["laps"])
	_base_lap_ms = float(track["baseLapMs"])
	for team_laps: Array in _laps:
		for t: Variant in team_laps:
			if t != null:
				_finish_ms = maxf(_finish_ms, float(t))
	_build()


func _build() -> void:
	# Full-screen circuit, broadcast graphics on top
	_track = CircuitView.new()
	_track.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_track.follow = int(race.get("playerSlot", 0))
	add_child(_track)

	var head := _glass()
	head.position = Vector2(10, 10)
	add_child(head)
	var hv := Ui.vbox(1)
	head.add_child(hv)
	hv.add_child(Ui.label(String(race.get("trackName", "")).to_upper() + "  ·  RACE", Ui.SIZE_SMALL, Ui.INK_2))
	_lap_label = Ui.label("", Ui.SIZE_TITLE, Ui.INK, true)
	hv.add_child(_lap_label)

	var tower := _glass()
	tower.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	tower.position = Vector2(-182, 10)
	tower.custom_minimum_size = Vector2(172, 0)
	add_child(tower)
	var right := Ui.vbox(2)
	tower.add_child(right)
	right.add_child(Ui.label("POSITIONS", Ui.SIZE_SMALL, Ui.RED, true))
	for i in _teams.size():
		var row := Ui.hbox(4)
		var sw := ColorRect.new()
		sw.custom_minimum_size = Vector2(3, 12)
		row.add_child(sw)
		var l := Ui.label("", Ui.SIZE_BODY)
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(l)
		right.add_child(row)
		_rows.append(l)
		_swatches.append(sw)

	var bar := _glass()
	bar.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	bar.offset_left = 10
	bar.offset_right = -10
	bar.offset_top = -34
	bar.offset_bottom = -10
	add_child(bar)
	var bh := Ui.hbox(8)
	bar.add_child(bh)
	var live := Ui.label("LIVE", Ui.SIZE_SMALL, Ui.INK, true)
	live.add_theme_color_override("font_color", Ui.RED)
	bh.add_child(live)
	_ticker = Ui.label("LIGHTS OUT AND AWAY WE GO", Ui.SIZE_BODY, Ui.INK, true)
	_ticker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bh.add_child(_ticker)
	var skip := Ui.button("SKIP TO RESULTS  >")
	skip.pressed.connect(func() -> void: _end())
	bh.add_child(skip)


func _glass() -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.075, 0.09, 0.86)
	sb.border_color = Color(1, 1, 1, 0.08)
	sb.set_border_width_all(1)
	sb.border_width_top = 2
	sb.border_color = Color(1, 1, 1, 0.08)
	sb.set_content_margin_all(6)
	p.add_theme_stylebox_override("panel", sb)
	return p


func _short(team: int) -> String:
	var name := String(_teams[team])
	return "YOU" if team == int(race.get("playerSlot", 0)) else name.get_slice(" ", 0).to_upper()


## Where a car is at race time ms: laps completed plus fraction, how far into the
## pit lane it is, and whether it has stopped, finished or retired.
func _car_at(c: int, ms: float) -> Dictionary:
	var laps: Array = _laps[c]
	if ms <= 0.0:
		return {"dist": 0.0, "pit": 0.0, "stopped": false, "out": false}
	var retired_on := laps.find(null)
	if retired_on != -1:
		var since := 0.0 if retired_on == 0 else float(laps[retired_on - 1])
		if ms >= since + _base_lap_ms * 0.5:
			return {"dist": retired_on + 0.5, "pit": 0.0, "stopped": true, "out": true}
	var last: Variant = laps[_lap_count - 1]
	if last != null and ms >= float(last):
		var over := ms - float(last)
		return {"dist": _lap_count + 0.07 * (1.0 - exp(-over / 9000.0)), "pit": 0.0, "stopped": false, "out": false}
	var k := 0
	while k < _lap_count and laps[k] != null and float(laps[k]) <= ms:
		k += 1
	var start := 0.0 if k == 0 else float(laps[k - 1])
	if laps[k] == null:  # the lap it retired on
		return {"dist": k + clampf((ms - start) / _base_lap_ms, 0.0, 0.5), "pit": 0.0, "stopped": false, "out": false}
	var lap_time := float(laps[k]) - start
	var elapsed := ms - start
	var is_pit := (_pit_laps[c] as Array).has(k + 1)
	var f := 0.0
	var stopped := false
	if is_pit:
		var driving := lap_time - PIT_LOSS_MS
		if elapsed < CircuitView.PIT_BOX * driving:
			f = elapsed / driving
		elif elapsed < CircuitView.PIT_BOX * driving + PIT_LOSS_MS:
			f = CircuitView.PIT_BOX
			stopped = true
		else:
			f = (elapsed - PIT_LOSS_MS) / driving
	else:
		f = elapsed / lap_time
	var pit := TrackView.pit_amount(f) if is_pit else 0.0
	return {"dist": k + f, "pit": pit, "stopped": stopped, "out": false}


func _process(delta: float) -> void:
	if _ended:
		return
	var states: Array[Dictionary] = []
	var leader := 0.0
	var pit_window := false
	for c in _teams.size():
		var s := _car_at(c, _ms)
		states.append(s)
		if not s["out"]:
			leader = maxf(leader, s["dist"])
		if float(s["pit"]) > 0.05 or s["stopped"] and not s["out"]:
			pit_window = true
	var target := SLOW if leader < 1.0 or leader > _lap_count - 1 or pit_window else FAST
	_rate = lerpf(_rate, target, clampf(delta * 4.0, 0.0, 1.0))
	_ms += delta * 1000.0 * _rate

	var cars: Array[Dictionary] = []
	for c in _teams.size():
		var s := states[c]
		var tag := "OUT" if s["out"] else ("PIT" if s["stopped"] else "")
		cars.append({"dist": s["dist"], "pit": s["pit"], "color": Ui.TEAM_COLORS[c % Ui.TEAM_COLORS.size()],
			"you": c == int(race.get("playerSlot", 0)), "tag": tag, "out": s["out"]})
	_track.set_cars(cars)

	_lap_label.text = "LAP %d/%d" % [mini(int(leader) + 1, _lap_count), _lap_count]
	var order := range(_teams.size())
	order.sort_custom(func(a: int, b: int) -> bool:
		if states[a]["out"] != states[b]["out"]:
			return not states[a]["out"]
		return float(states[a]["dist"]) > float(states[b]["dist"]))
	for pos in order.size():
		var c: int = order[pos]
		var tag := "  OUT" if states[c]["out"] else ("  PIT" if states[c]["stopped"] else "")
		_rows[pos].text = "P%d  %s%s" % [pos + 1, _short(c), tag]
		_rows[pos].add_theme_color_override("font_color", Ui.RED if c == int(race.get("playerSlot", 0)) else Ui.INK)
		_swatches[pos].color = Ui.TEAM_COLORS[c % Ui.TEAM_COLORS.size()]

	_update_ticker(leader)
	if _ms > _finish_ms + 4000.0:
		_end()


func _update_ticker(leader: float) -> void:
	var events: Array = _replay["events"]
	while _event_index < events.size() and leader >= float((events[_event_index] as Dictionary)["lap"]) - 0.05:
		var e: Dictionary = events[_event_index]
		match String(e["type"]):
			"pit":
				_ticker.text = "LAP %d · %s PITS" % [e["lap"], _short(int(e["team"]))]
			"overtake":
				_ticker.text = "LAP %d · %s PASSES %s" % [e["lap"], _short(int(e["team"])), _short(int(e["passed"]))]
			"retired":
				_ticker.text = "LAP %d · %s IS OUT" % [e["lap"], _short(int(e["team"]))]
		_event_index += 1
	if leader >= _lap_count:
		var winner: int = (_replay["order"] as Array)[0]
		_ticker.text = "CHEQUERED FLAG · %s WINS" % _short(winner)


func _end() -> void:
	if _ended:
		return
	_ended = true
	done.emit(race)
