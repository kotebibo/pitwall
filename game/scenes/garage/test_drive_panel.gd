class_name TestDrivePanel
extends Control
## TEST DRIVE: the autopilot drives a lap of Mtkvari with the car as it is and
## again with the part (TestDriveRun, a slice per frame), then shows the lap
## and sector deltas, and on a track map where the part gains (green) and
## loses (red) time.

signal closed

## The two cars: [setup, stats, spec] for the car now and the car with the part
var base_spec: Dictionary = {}
var part_spec: Dictionary = {}
var title := ""
var caption := ""
## The two setups (empty: Profile.setup for both), for a setup test from the TUNING tab
var base_setup: Dictionary = {}
var part_setup: Dictionary = {}
## How the two cars are named on screen
var base_name := "your car now"
var part_name := "with the part"
var change_name := "the part"

var _runs: Array[TestDriveRun] = []
var _run := 0
var _bar: ProgressBar
var _status: Label
var _map: TrackMap
var _results: VBoxContainer


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	var dim := ColorRect.new()
	dim.color = Color(0.03, 0.03, 0.04, 0.82)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	var panel := Ui.panel(true)
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(400, 236)
	panel.position = -panel.custom_minimum_size / 2
	add_child(panel)
	var row := Ui.hbox(10)
	panel.add_child(row)
	_map = TrackMap.new()
	_map.custom_minimum_size = Vector2(170, 210)
	row.add_child(_map)
	var v := Ui.vbox(4)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(v)
	v.add_child(Ui.label("TEST DRIVE · MTKVARI", Ui.SIZE_HEADING, Ui.INK, true))
	var t := Ui.label(title, Ui.SIZE_SMALL, Ui.INK, true)
	t.clip_text = true
	t.custom_minimum_size = Vector2(200, 0)
	v.add_child(t)
	var c := Ui.label(caption, Ui.SIZE_SMALL, Ui.INK_3)
	c.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	c.custom_minimum_size = Vector2(200, 0)
	v.add_child(c)
	_status = Ui.label("", Ui.SIZE_SMALL, Ui.INK_2)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.custom_minimum_size = Vector2(200, 0)
	v.add_child(_status)
	_bar = Ui.stat_bar(0, 1000)
	_bar.custom_minimum_size = Vector2(200, 6)
	v.add_child(_bar)
	_results = Ui.vbox(2)
	_results.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(_results)
	var close := Ui.button("CLOSE")
	close.custom_minimum_size = Vector2(90, 20)
	close.size_flags_horizontal = Control.SIZE_SHRINK_END
	close.pressed.connect(func() -> void: closed.emit())
	v.add_child(close)
	var stats := Profile.stats()
	var a: Dictionary = base_setup if not base_setup.is_empty() else Profile.setup
	var b: Dictionary = part_setup if not part_setup.is_empty() else Profile.setup
	_runs = [TestDriveRun.new(a, stats, base_spec), TestDriveRun.new(b, stats, part_spec)]


func _process(_delta: float) -> void:
	if _run >= _runs.size():
		return
	# a few milliseconds of driving a frame keeps the screen moving, on the web too
	var p := _runs[_run].step(8000)
	_bar.value = (_run + p) * 500.0
	_status.text = "Autopilot lap %d of 2: %s" % [_run + 1, base_name if _run == 0 else part_name]
	if _runs[_run].done():
		_run += 1
		if _run == _runs.size():
			_show()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		closed.emit()
		accept_event()


func _show() -> void:
	_bar.visible = false
	var a := _runs[0].result
	var b := _runs[1].result
	if int(a.get("us", -1)) < 0 or int(b.get("us", -1)) < 0:
		_status.text = "The autopilot could not complete a clean lap with one of the cars. Try it yourself in Practice."
		return
	var d := (int(b["us"]) - int(a["us"])) / 1000000.0
	var good := Catalog.GREEN if d < 0.0 else Ui.RED
	_status.text = "Autopilot laps with your setup. Your own laps may gain more, or less."
	var big := Ui.label("%+.3f s a lap" % d, Ui.SIZE_HEADING, good if absf(d) >= 0.0005 else Ui.INK_2, true)
	_results.add_child(big)
	var short_a := "now" if base_name == "your car now" else base_name
	_results.add_child(Ui.label("%s %s  >  %s %s" % [_fmt(int(a["us"])), short_a, _fmt(int(b["us"])), part_name], Ui.SIZE_SMALL, Ui.INK_2))
	var sa: Array = a.get("sectors", [])
	var sb: Array = b.get("sectors", [])
	var srow := Ui.hbox(12)
	for i in mini(sa.size(), sb.size()):
		var ds := (int(sb[i]) - int(sa[i])) / 1000000.0
		var l := Ui.label("S%d %+.3f" % [i + 1, ds], Ui.SIZE_SMALL, (Catalog.GREEN if ds < 0.0 else Ui.RED) if absf(ds) >= 0.0005 else Ui.INK_2, true)
		srow.add_child(l)
	_results.add_child(srow)
	var legend := Ui.label("On the map: green where %s gains time, red where it loses it." % change_name, Ui.SIZE_SMALL, Ui.INK_3)
	legend.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	legend.custom_minimum_size = Vector2(200, 0)
	_results.add_child(legend)
	_map.show_deltas(TestDriveRun.mini_times(a), TestDriveRun.mini_times(b))
	if has_node("/root/Sfx"):
		get_node("/root/Sfx").call("play", "verified" if d < 0.0 else "equip")


static func _fmt(us: int) -> String:
	return "%d:%06.3f" % [us / 60000000, (us % 60000000) / 1000000.0]


## Mtkvari from above, each mini-sector coloured by the time the part gains or loses there.
class TrackMap:
	extends Control

	var _deltas := PackedFloat64Array()
	var _pts := PackedVector2Array()

	func show_deltas(a: PackedFloat64Array, b: PackedFloat64Array) -> void:
		_deltas.resize(mini(a.size(), b.size()))
		for i in _deltas.size():
			_deltas[i] = b[i] - a[i]
		queue_redraw()

	func _points() -> PackedVector2Array:
		var t := TestDriveRun.track()
		var raw := PackedVector2Array()
		var lo := Vector2(INF, INF)
		var hi := Vector2(-INF, -INF)
		for i in t.size():
			var p := Vector2(t.x[i], t.y[i]) / 65536.0
			raw.append(p)
			lo = Vector2(minf(lo.x, p.x), minf(lo.y, p.y))
			hi = Vector2(maxf(hi.x, p.x), maxf(hi.y, p.y))
		var box := size - Vector2(16, 16)
		var k := minf(box.x / maxf(hi.x - lo.x, 1.0), box.y / maxf(hi.y - lo.y, 1.0))
		var off := (size - (hi - lo) * k) / 2.0
		var out := PackedVector2Array()
		for p in raw:
			out.append(((p - lo) * k + off).round())
		return out

	func _draw() -> void:
		if _pts.is_empty() or size != get_meta("drawn_size", Vector2.ZERO):
			_pts = _points()
			set_meta("drawn_size", size)
		var n := _pts.size()
		var biggest := 0.0
		for d in _deltas:
			biggest = maxf(biggest, absf(d))
		# the track in grey, then the coloured mini-sectors over it
		for i in n:
			draw_line(_pts[i], _pts[(i + 1) % n], Ui.LINE_STRONG, 5.0)
		for s in _deltas.size():
			var d := _deltas[s]
			var col := Ui.INK_3
			if absf(d) >= 0.001:
				var strength := clampf(absf(d) / maxf(biggest, 0.001), 0.35, 1.0)
				col = Color(Catalog.GREEN if d < 0.0 else Ui.RED, strength)
			for i in range(s * TestDriveRun.MINI, mini((s + 1) * TestDriveRun.MINI, n)):
				draw_line(_pts[i], _pts[(i + 1) % n], col, 3.0)
		# start line and sector marks
		var t := TestDriveRun.track()
		draw_circle(_pts[0], 3.0, Ui.INK)
		for i in t.sectors.size():
			var p := _pts[t.sectors[i] % n]
			draw_rect(Rect2(p - Vector2(2, 2), Vector2(4, 4)), Ui.YELLOW)
			draw_string(Ui.font_bold, p + Vector2(4, -3), "S%d" % (i + 2), HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_SMALL, Ui.YELLOW)
