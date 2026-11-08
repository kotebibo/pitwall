class_name RankedView
extends Control
## The RANKED tab of the COMPETE screen, from GET /api/ranked: your rank (emblem, RP bar,
## placements, recent results), today's medals and the rules on the left; the daily board or
## the ladder and the RANKED RACE button on the right.

signal race

const GREEN := Color("3ecf6a")

## The last ranked info fetched: the ranked race reads the rank you started from.
static var last_info: Dictionary = {}

var _info: Dictionary = {}
var _left: VBoxContainer
var _right: VBoxContainer
var _status: Label
var _show_ladder := false


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var lp := _glass()
	lp.position = Vector2(14, 0)
	lp.anchor_bottom = 1.0
	lp.offset_top = 0
	lp.offset_bottom = -10
	lp.offset_left = 14
	lp.offset_right = 250
	add_child(lp)
	_left = Ui.vbox(4)
	lp.add_child(_left)
	var rp := _glass()
	rp.anchor_left = 0.0
	rp.anchor_right = 1.0
	rp.anchor_bottom = 1.0
	rp.offset_left = 258
	rp.offset_right = -12
	rp.offset_top = 0
	rp.offset_bottom = -10
	add_child(rp)
	_right = Ui.vbox(3)
	rp.add_child(_right)
	_status = Ui.label("Loading ranked…", Ui.SIZE_SMALL, Ui.INK_2)
	_left.add_child(_status)
	load_info()


func _glass() -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.085, 0.1, 0.9)
	sb.border_color = Color(1, 1, 1, 0.08)
	sb.set_border_width_all(1)
	sb.border_width_top = 2
	sb.set_content_margin_all(8)
	p.add_theme_stylebox_override("panel", sb)
	return p


func load_info() -> void:
	var res: Variant = RankedMock.info() if RankedMock.enabled() else await Api.get_json("/api/ranked?player=" + Profile.id)
	if not is_inside_tree():
		return
	if not res is Dictionary:
		_status.text = "Can't reach the server. Ranked needs it."
		return
	_info = res
	last_info = _info
	_render()


func _clear(box: Container) -> void:
	for c in box.get_children():
		box.remove_child(c)
		c.queue_free()


func _render() -> void:
	_clear(_left)
	_clear(_right)
	_render_rank()
	_render_medals()
	_render_lists()


static func _rp_text(v: int) -> String:
	return ("+%d RP" % v) if v >= 0 else ("−%d RP" % -v)


# ---- left: your rank ----

func _render_rank() -> void:
	var you: Variant = _info.get("you")
	var y: Dictionary = you if you is Dictionary else {}
	var tier := String(y.get("tier", "UNRANKED"))
	var div: Variant = y.get("division")
	var left := int(y.get("placementsLeft", 5)) if not y.is_empty() else 5
	var placing := left > 0 or tier == "UNRANKED"
	var season: Dictionary = _info.get("season", {}) if _info.get("season") is Dictionary else {}

	var head := Ui.hbox(6)
	head.add_child(Ui.label("YOUR RANK", Ui.SIZE_SMALL, Ui.INK_2, true))
	var s := Ui.label(_season_text(season), Ui.SIZE_SMALL, Ui.INK_3)
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	head.add_child(s)
	_left.add_child(head)

	var row := Ui.hbox(8)
	row.add_child(RankEmblem.make(tier, div, 64))
	var col := Ui.vbox(2)
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(col)
	_left.add_child(row)
	if placing:
		col.add_child(Ui.label("PLACEMENTS", Ui.SIZE_HEADING, Ui.INK, true))
		col.add_child(Ui.label("PLACEMENTS: %d LEFT" % left, Ui.SIZE_SMALL, Ui.YELLOW, true))
		var pips := Ui.hbox(3)
		for i in 5:
			var pip := ColorRect.new()
			pip.custom_minimum_size = Vector2(22, 5)
			pip.color = Ui.YELLOW if i < 5 - left else Color(1, 1, 1, 0.1)
			pips.add_child(pip)
		col.add_child(pips)
		var hint := Ui.label("Your rank shows after 5 races.", Ui.SIZE_SMALL, Ui.INK_3)
		col.add_child(hint)
	else:
		col.add_child(Ui.label(RankEmblem.label_for(tier, div), Ui.SIZE_HEADING, RankEmblem.color(tier), true))
		var rp := int(y.get("rp", 0))
		var bar_row := Ui.hbox(6)
		var bar := Ui.stat_bar(clampi(rp, 0, 100), 100)
		bar.custom_minimum_size = Vector2(0, 6)
		_tint_bar(bar, RankEmblem.color(tier))
		bar_row.add_child(bar)
		bar_row.add_child(Ui.label("%d / 100 RP" % rp if RankEmblem.TIERS.find(tier) < 7 else "%d RP" % rp, Ui.SIZE_SMALL, Ui.INK, true))
		col.add_child(bar_row)
		col.add_child(Ui.label("100 RP PROMOTES  ·  BELOW 0 DEMOTES", Ui.SIZE_SMALL, Ui.INK_3))

	var wl := Ui.hbox(8)
	if int(y.get("races", 0)) > 0:
		wl.add_child(Ui.label("W %d" % int(y.get("wins", 0)), Ui.SIZE_BODY, GREEN, true))
		wl.add_child(Ui.label("L %d" % int(y.get("losses", 0)), Ui.SIZE_BODY, Ui.RED, true))
		wl.add_child(Ui.label("%d RACES" % int(y.get("races", 0)), Ui.SIZE_SMALL, Ui.INK_2))
	else:
		wl.add_child(Ui.label("No ranked races yet. Five placement races set your rank.", Ui.SIZE_SMALL, Ui.INK_2))
	_left.add_child(wl)

	var recent: Array = y.get("recent", []) if y.get("recent") is Array else []
	if not recent.is_empty():
		_left.add_child(Ui.label("LAST 5", Ui.SIZE_SMALL, Ui.INK_2, true))
		var chips := Ui.hbox(3)
		for r: Variant in recent.slice(0, 5):
			chips.add_child(_result_chip(r as Dictionary))
		_left.add_child(chips)


func _season_text(season: Dictionary) -> String:
	var name := String(season.get("name", "SEASON"))
	var ms := int(float(season.get("endsAt", 0))) - int(Time.get_unix_time_from_system() * 1000.0)
	if ms <= 0:
		return name
	var h := ms / 3_600_000
	return "%s · ENDS IN %dD" % [name, h / 24] if h >= 24 else "%s · ENDS IN %dH" % [name, h]


func _tint_bar(bar: ProgressBar, c: Color) -> void:
	var fill := StyleBoxFlat.new()
	fill.bg_color = c
	bar.add_theme_stylebox_override("fill", fill)
	var bg := StyleBoxFlat.new()
	bg.bg_color = Color(1, 1, 1, 0.08)
	bar.add_theme_stylebox_override("background", bg)


func _result_chip(r: Dictionary) -> Control:
	var forfeit := bool(r.get("forfeit", false))
	var change := int(r.get("rpChange", 0))
	var won := int(r.get("wins", 0)) >= 3  # a race is won by beating 3 or more of the 5
	var c := (GREEN if change > 0 else Ui.RED) if change != 0 else (GREEN if won else Ui.RED)
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(c, 0.12)
	sb.border_color = Color(c, 0.6)
	sb.border_width_top = 2
	sb.set_content_margin_all(2)
	sb.content_margin_left = 3
	sb.content_margin_right = 3
	p.add_theme_stylebox_override("panel", sb)
	p.custom_minimum_size = Vector2(41, 0)
	p.tooltip_text = ("Forfeit" if forfeit else "Lap %s" % Ui.format_time(int(float(r.get("us", 0))) / 1000)) + ": beat %d of %d" % [int(r.get("wins", 0)), int(r.get("of", 5))]
	var v := Ui.vbox(0)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.add_child(v)
	var a := Ui.label(_rp_text(change) if change != 0 else ("WIN" if won else "LOSS"), Ui.SIZE_SMALL, c, true)
	a.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(a)
	var b := Ui.label("FORFEIT" if forfeit else "%d OF %d" % [int(r.get("wins", 0)), int(r.get("of", 5))], Ui.SIZE_SMALL, Ui.INK_2)
	b.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(b)
	return p


func _ladder_row(r: Dictionary) -> Control:
	var me := bool(r.get("you", false))
	var row := Ui.hbox(4)
	var n := Ui.label(str(int(r.get("rank", 0))), Ui.SIZE_SMALL, Ui.RED if me else Ui.INK_3, true)
	n.custom_minimum_size = Vector2(14, 0)
	row.add_child(n)
	var tier := String(r.get("tier", ""))
	row.add_child(RankEmblem.make(tier, r.get("division"), 16, false))
	var name := Ui.label(String(r.get("name", "")).to_upper(), Ui.SIZE_SMALL, Ui.RED if me else Ui.INK)
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name.clip_text = true
	row.add_child(name)
	var t := Ui.label(RankEmblem.label_for(tier, r.get("division")), Ui.SIZE_SMALL, RankEmblem.color(tier))
	t.custom_minimum_size = Vector2(72, 0)
	t.clip_text = true
	row.add_child(t)
	var rp := Ui.label("%d RP" % int(r.get("rp", 0)), Ui.SIZE_SMALL, Ui.INK_2)
	rp.custom_minimum_size = Vector2(36, 0)
	rp.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(rp)
	return row


# ---- left, under your rank: today's medals ----

func _render_medals() -> void:
	var daily: Dictionary = _info.get("daily", {}) if _info.get("daily") is Dictionary else {}
	var medals: Dictionary = daily.get("medals", {}) if daily.get("medals") is Dictionary else {}
	var head := Ui.hbox(6)
	head.add_child(Ui.label("TODAY'S MEDALS", Ui.SIZE_SMALL, Ui.INK_2, true))
	var closes := int(float(daily.get("closesAt", 0))) - int(Time.get_unix_time_from_system() * 1000.0)
	var cl := Ui.label("NEW DAY IN %dH %02dM" % [closes / 3_600_000, (closes % 3_600_000) / 60_000] if closes > 0 else "", Ui.SIZE_SMALL, Ui.INK_3)
	cl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	head.add_child(cl)
	_left.add_child(head)
	var row := Ui.hbox(3)
	for m: String in ["gold", "silver", "bronze"]:
		row.add_child(_medal_chip(m, int(float(medals.get(m, 0)))))
	_left.add_child(row)
	var dy: Variant = daily.get("you")
	if dy is Dictionary:
		var d: Dictionary = dy
		var medal := String(d.get("medal")) if d.get("medal") is String else ""
		var line := Ui.hbox(4)
		line.add_child(Ui.label("YOUR BEST", Ui.SIZE_SMALL, Ui.INK_2, true))
		line.add_child(Ui.label(Ui.format_time(int(float(d.get("us", 0))) / 1000), Ui.SIZE_SMALL, Ui.INK, true))
		line.add_child(Ui.label(("·  %s MEDAL" % medal.to_upper()) if medal != "" else "·  NO MEDAL YET", Ui.SIZE_SMALL, RankEmblem.medal_color(medal) if medal != "" else Ui.INK_3, true))
		_left.add_child(line)
		var drivers := int(daily.get("drivers", 0))
		var laps := int(d.get("laps", 0))
		_left.add_child(Ui.label("P%d TODAY" % int(d.get("rank", 0)) + (" OF %d" % drivers if drivers > 0 else "") + ("  ·  %d LAP%s" % [laps, "" if laps == 1 else "S"] if laps > 0 else ""), Ui.SIZE_SMALL, Ui.INK_2))
	else:
		var none := Ui.label("No ranked lap today. Your best lap of the day earns its medal pack.", Ui.SIZE_SMALL, Ui.INK_3)
		none.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		none.custom_minimum_size = Vector2(220, 0)
		_left.add_child(none)


# ---- right: the daily board or the ladder, RANKED RACE ----

func _render_lists() -> void:
	var daily: Dictionary = _info.get("daily", {}) if _info.get("daily") is Dictionary else {}
	var tabs := Ui.hbox(4)
	var today := Ui.button("TODAY  ·  TOP 10")
	var ladder := Ui.button("LADDER  ·  TOP 10")
	for b: Button in [today, ladder]:
		b.toggle_mode = true
		b.add_theme_font_size_override("font_size", Ui.SIZE_SMALL)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	today.set_pressed_no_signal(not _show_ladder)
	ladder.set_pressed_no_signal(_show_ladder)
	for st: String in ["font_color", "font_pressed_color", "font_hover_pressed_color", "font_hover_color"]:
		(ladder if _show_ladder else today).add_theme_color_override(st, Ui.RED)
	today.pressed.connect(func() -> void:
		_show_ladder = false
		_render())
	ladder.pressed.connect(func() -> void:
		_show_ladder = true
		_render())
	tabs.add_child(today)
	tabs.add_child(ladder)
	_right.add_child(tabs)
	var list := Ui.vbox(0)
	if _show_ladder:
		var lad: Array = _info.get("ladder", []) if _info.get("ladder") is Array else []
		if lad.is_empty():
			list.add_child(Ui.label("Nobody is ranked yet.", Ui.SIZE_SMALL, Ui.INK_3))
		for r: Variant in lad.slice(0, 10):
			list.add_child(_ladder_row(r as Dictionary))
	else:
		var board: Array = daily.get("leaderboard", []) if daily.get("leaderboard") is Array else []
		if board.is_empty():
			list.add_child(Ui.label("No ranked laps today. Be the first.", Ui.SIZE_SMALL, Ui.INK_3))
		for r: Variant in board.slice(0, 10):
			list.add_child(_board_row(r as Dictionary))
	_right.add_child(list)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_right.add_child(spacer)
	# the rules, at the foot of the left column
	var lspace := Control.new()
	lspace.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_left.add_child(lspace)
	_left.add_child(Ui.label("HOW RANKED WORKS", Ui.SIZE_SMALL, Ui.INK_2, true))
	var rules := Ui.label("One lap counts: your first lap is your result.\nBeat the 5 drivers nearest your rank.\nRestarting or quitting forfeits.\nMedals earn medal packs.", Ui.SIZE_SMALL, Ui.INK)
	rules.add_theme_constant_override("line_spacing", -2)
	_left.add_child(rules)
	var go := Ui.button("RANKED RACE  >", true)
	go.custom_minimum_size = Vector2(0, 30)
	go.add_theme_font_size_override("font_size", Ui.SIZE_HEADING)
	go.tooltip_text = "Standard car, your own setup. Driving stops after your first lap: that lap is your result."
	go.pressed.connect(func() -> void:
		Sfx.play("ui_confirm")
		race.emit())
	_right.add_child(go)


func _medal_chip(m: String, us: int) -> Control:
	var c := RankEmblem.medal_color(m)
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(c, 0.1)
	sb.border_color = Color(c, 0.55)
	sb.set_border_width_all(1)
	sb.set_content_margin_all(3)
	p.add_theme_stylebox_override("panel", sb)
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var row := Ui.hbox(3)
	p.add_child(row)
	row.add_child(medal_icon(m, 12))
	var v := Ui.vbox(0)
	v.add_child(Ui.label(m.to_upper(), Ui.SIZE_SMALL, c, true))
	v.add_child(Ui.label("≤ " + Ui.format_time(us / 1000), Ui.SIZE_SMALL, Ui.INK))
	row.add_child(v)
	return p


## The medal sprite when it is there, else a pixel disc on a ribbon.
static func medal_icon(m: String, px: int) -> Control:
	var tex := RankEmblem.medal_texture(m)
	if tex:
		var t := TextureRect.new()
		t.texture = tex
		t.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		t.stretch_mode = TextureRect.STRETCH_SCALE
		t.custom_minimum_size = Vector2(px, px)
		t.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		t.mouse_filter = Control.MOUSE_FILTER_IGNORE
		return t
	var d := Control.new()
	d.custom_minimum_size = Vector2(px, px)
	d.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	d.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var c := RankEmblem.medal_color(m)
	d.draw.connect(func() -> void:
		var u := px / 8.0
		d.draw_rect(Rect2(Vector2(2, 0) * u, Vector2(1, 3) * u), Ui.RED)
		d.draw_rect(Rect2(Vector2(5, 0) * u, Vector2(1, 3) * u), Ui.RED_DARK)
		d.draw_rect(Rect2(Vector2(2, 3) * u, Vector2(4, 5) * u), c.darkened(0.5))
		d.draw_rect(Rect2(Vector2(1, 4) * u, Vector2(6, 3) * u), c.darkened(0.5))
		d.draw_rect(Rect2(Vector2(2, 4) * u, Vector2(4, 3) * u), c)
		d.draw_rect(Rect2(Vector2(2, 4) * u, Vector2(2, 1) * u), c.lightened(0.35)))
	return d


func _board_row(r: Dictionary) -> Control:
	var me := bool(r.get("you", false))
	var row := Ui.hbox(4)
	var n := Ui.label(str(int(r.get("rank", 0))), Ui.SIZE_SMALL, Ui.RED if me else Ui.INK_3, true)
	n.custom_minimum_size = Vector2(14, 0)
	row.add_child(n)
	var medal := String(r.get("medal")) if r.get("medal") is String else ""
	var dot := ColorRect.new()
	dot.custom_minimum_size = Vector2(5, 5)
	dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	dot.color = RankEmblem.medal_color(medal) if medal != "" else Color(1, 1, 1, 0.08)
	row.add_child(dot)
	var name := Ui.label(String(r.get("name", "")).to_upper(), Ui.SIZE_SMALL, Ui.RED if me else Ui.INK, me)
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name.clip_text = true
	row.add_child(name)
	var m := Ui.label(medal.to_upper(), Ui.SIZE_SMALL, RankEmblem.medal_color(medal) if medal != "" else Ui.INK_3)
	m.custom_minimum_size = Vector2(44, 0)
	row.add_child(m)
	var t := Ui.label(Ui.format_time(int(float(r.get("us", 0))) / 1000), Ui.SIZE_SMALL, Ui.INK, me)
	t.custom_minimum_size = Vector2(52, 0)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(t)
	return row
