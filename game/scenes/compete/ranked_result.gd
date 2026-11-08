class_name RankedResult
extends Control
## The result of a ranked race, over the frozen track: WIN or LOSS against each of the five
## opponents, the RP change with an animated bar, PROMOTED / DEMOTED / PLACED banners, the
## day's medal and any medal packs. Built from the `ranked` block of the run response.

signal again
signal back

const GREEN := Color("3ecf6a")
const DIVS: Array[String] = ["IV", "III", "II", "I"]

## The run response (POST /api/attempts/:id/run), or null when it could not be verified.
var response: Variant = null
## rankedMatch.opponents from the attempt (for their tiers).
var match_opponents: Array = []
## Your rank before the race (GET /api/ranked "you"), if known.
var before: Dictionary = {}
var lap_us := 0
var lap_valid := true

var _bar: ProgressBar
var _bar_text: Label
var _emblem: RankEmblem
var _tier_label: Label
var _banner: Label
var _change_label: Label


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	theme = Ui.theme
	var dim := ColorRect.new()
	dim.color = Color(0.03, 0.035, 0.045, 0.8)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	var panel := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.075, 0.09, 0.97)
	sb.border_color = Ui.RED
	sb.border_width_top = 3
	sb.set_content_margin_all(10)
	panel.add_theme_stylebox_override("panel", sb)
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(470, 0)
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	add_child(panel)
	var box := Ui.vbox(5)
	panel.add_child(box)
	var r: Dictionary = {}
	if response is Dictionary and (response as Dictionary).get("ranked") is Dictionary:
		r = (response as Dictionary)["ranked"]
	if r.is_empty():
		_build_unverified(box)
	else:
		_build(box, r)
	modulate.a = 0.0
	create_tween().tween_property(self, "modulate:a", 1.0, 0.25)


func _build_unverified(box: VBoxContainer) -> void:
	box.add_child(Ui.label("RANKED RACE", Ui.SIZE_SMALL, Ui.RED, true))
	box.add_child(Ui.label("NOT COUNTED", Ui.SIZE_TITLE, Ui.YELLOW, true))
	var why := "The server could not verify this lap (it is unreachable, or the re-drive did not match). It did not count."
	if lap_us > 0:
		why = "Your lap: %s. " % Ui.format_time(lap_us / 1000) + why
	var l := Ui.label(why, Ui.SIZE_SMALL, Ui.INK_2)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(450, 0)
	box.add_child(l)
	box.add_child(_buttons())


func _build(box: VBoxContainer, r: Dictionary) -> void:
	var forfeit := bool(r.get("forfeit", false))
	var wins := int(r.get("wins", 0))
	var of := int(r.get("of", 5))
	var change := int(r.get("rpChange", 0))
	var rank: Dictionary = r.get("rank", {}) if r.get("rank") is Dictionary else {}
	var daily: Dictionary = r.get("daily", {}) if r.get("daily") is Dictionary else {}
	var us := int(float(r.get("us"))) if r.get("us") != null else 0

	var head := Ui.hbox(6)
	head.add_child(Ui.label("RANKED RACE  ·  RESULT", Ui.SIZE_SMALL, Ui.RED, true))
	var d := Ui.label("DAILY P%d OF %d" % [int(daily.get("rank", 0)), int(daily.get("of", 0))] if not daily.is_empty() and not forfeit else "", Ui.SIZE_SMALL, Ui.INK_2, true)
	d.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	d.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	head.add_child(d)
	box.add_child(head)

	# your lap and the day's medal
	var top := Ui.hbox(8)
	if forfeit:
		top.add_child(Ui.label("FORFEIT", Ui.SIZE_TITLE, Ui.RED, true))
		var why := "LAP DELETED: TRACK LIMITS" if lap_us > 0 and not lap_valid else "NO LAP COMPLETED"
		var w := Ui.label(why + "  ·  LOSES TO ALL 5", Ui.SIZE_SMALL, Ui.INK_2, true)
		w.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		top.add_child(w)
	else:
		top.add_child(Ui.label(Ui.format_time(us / 1000), Ui.SIZE_TITLE, Ui.INK, true))
		var medal := String(r.get("medal")) if r.get("medal") is String else ""
		if medal != "":
			top.add_child(RankedView.medal_icon(medal, 24))
			var m := Ui.label("TODAY: %s MEDAL" % medal.to_upper(), Ui.SIZE_SMALL, RankEmblem.medal_color(medal), true)
			m.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			top.add_child(m)
		else:
			var m := Ui.label("NO MEDAL TODAY YET  ·  BRONZE AT 1:08.500", Ui.SIZE_SMALL, Ui.INK_3)
			m.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			top.add_child(m)
	box.add_child(top)

	var mid := Ui.hbox(12)
	box.add_child(mid)
	# left: each opponent, your time against theirs
	var opp_box := Ui.vbox(2)
	opp_box.custom_minimum_size = Vector2(290, 0)
	mid.add_child(opp_box)
	opp_box.add_child(Ui.label("YOUR 5 OPPONENTS", Ui.SIZE_SMALL, Ui.INK_2, true))
	var opps: Array = r.get("opponents", []) if r.get("opponents") is Array else []
	for i in opps.size():
		var o: Dictionary = opps[i]
		opp_box.add_child(_opp_row(o, _match_for(o, i), us, forfeit))
	# right: the score and your rank
	var score := Ui.vbox(3)
	score.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mid.add_child(score)
	score.add_child(Ui.label("BEAT %d OF %d" % [wins, of], Ui.SIZE_HEADING, GREEN if wins * 2 > of else (Ui.INK if wins > 0 else Ui.RED), true))
	var placing := int(rank.get("placementsLeft", 0)) > 0
	var placement := placing or bool(r.get("placed", false))  # no RP during placements
	_change_label = Ui.label(RankedView._rp_text(change) if not placement else "PLACEMENT %d/5" % (5 - int(rank.get("placementsLeft", 0))), Ui.SIZE_TITLE, GREEN if change >= 0 else Ui.RED, true)
	if placement:
		_change_label.add_theme_color_override("font_color", Ui.YELLOW)
		_change_label.add_theme_font_size_override("font_size", 20)
	score.add_child(_change_label)
	var rank_row := Ui.hbox(8)
	score.add_child(rank_row)
	var tier := String(rank.get("tier", "UNRANKED"))
	var div: Variant = rank.get("division")
	var promoted := bool(r.get("promoted", false))
	var demoted := bool(r.get("demoted", false))
	var placed := bool(r.get("placed", false))
	var start_tier := tier
	var start_div: Variant = div
	if promoted or demoted:
		var prev := _step(tier, String(div) if div != null else "", -1 if promoted else 1)
		start_tier = prev[0]
		start_div = prev[1]
	_emblem = RankEmblem.make(start_tier if not placed else "UNRANKED", start_div, 64)
	rank_row.add_child(_emblem)
	var rcol := Ui.vbox(2)
	rcol.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rcol.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	rank_row.add_child(rcol)
	_tier_label = Ui.label("", Ui.SIZE_BODY, Ui.INK, true)
	rcol.add_child(_tier_label)
	_bar = Ui.stat_bar(0, 100)
	_bar.custom_minimum_size = Vector2(0, 7)
	rcol.add_child(_bar)
	_bar_text = Ui.label("", Ui.SIZE_SMALL, Ui.INK_2)
	rcol.add_child(_bar_text)
	_banner = Ui.label("", Ui.SIZE_HEADING, Ui.YELLOW, true)
	_banner.custom_minimum_size = Vector2(0, 18)
	score.add_child(_banner)

	# medal packs earned
	var packs: Array = r.get("packsEarned", []) if r.get("packsEarned") is Array else []
	if not packs.is_empty():
		var pr := Ui.hbox(5)
		pr.add_child(Ui.label("MEDAL PACK%s EARNED:" % ("" if packs.size() == 1 else "S"), Ui.SIZE_SMALL, Ui.YELLOW, true))
		for p: Variant in packs:
			var medal := String((p as Dictionary).get("medal", "")) if p is Dictionary else ""
			if medal != "":
				pr.add_child(RankedView.medal_icon(medal, 12))  # the 24 px medal at 1x
			pr.add_child(Ui.label(("%s MEDAL PACK" % medal.to_upper()) if medal != "" else "DEVELOPMENT PACK", Ui.SIZE_SMALL, RankEmblem.medal_color(medal) if medal != "" else Ui.INK, true))
		pr.add_child(Ui.label("·  OPEN IN THE GARAGE", Ui.SIZE_SMALL, Ui.INK_2))
		box.add_child(pr)
	box.add_child(_buttons())

	# the animation: the RP bar fills (or drains) to the new value; banners on rank changes
	if placing:
		_tier_label.text = "PLACEMENTS: %d LEFT" % int(rank.get("placementsLeft", 0))
		_tier_label.add_theme_color_override("font_color", Ui.YELLOW)
		_bar.max_value = 5
		_bar.value = 5 - int(rank.get("placementsLeft", 0))
		_tint(Ui.YELLOW)
		_bar_text.text = "Your rank shows after 5 races."
		Sfx.play("verified" if wins * 2 > of else "ui_confirm")
	else:
		_animate(start_tier, start_div, tier, div, int(rank.get("rp", 0)), change, promoted, demoted, placed)
	if not packs.is_empty():
		get_tree().create_timer(1.6).timeout.connect(func() -> void:
			if is_inside_tree():
				Sfx.play("coins"))


func _buttons() -> Control:
	var row := Ui.hbox(6)
	var go := Ui.button("RANKED RACE AGAIN  >", true)
	go.custom_minimum_size = Vector2(180, 26)
	go.pressed.connect(func() -> void: again.emit())
	row.add_child(go)
	var b := Ui.button("BACK")
	b.custom_minimum_size = Vector2(90, 26)
	b.pressed.connect(func() -> void: back.emit())
	row.add_child(b)
	return row


## The attempt's opponent for a result row (same name, else the same place).
func _match_for(o: Dictionary, i: int) -> Dictionary:
	for m: Variant in match_opponents:
		if m is Dictionary and String((m as Dictionary).get("name", "")) == String(o.get("name", "")):
			return m
	return match_opponents[i] if i < match_opponents.size() and match_opponents[i] is Dictionary else {}


func _opp_row(o: Dictionary, m: Dictionary, us: int, forfeit: bool) -> Control:
	var beat := bool(o.get("beat", false))
	var row := Ui.hbox(4)
	var chip := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = GREEN.darkened(0.45) if beat else Ui.RED_DARK
	sb.border_color = GREEN if beat else Ui.RED
	sb.border_width_left = 2
	sb.content_margin_left = 3
	sb.content_margin_right = 2
	chip.add_theme_stylebox_override("panel", sb)
	chip.custom_minimum_size = Vector2(34, 0)
	var cl := Ui.label("WIN" if beat else "LOSS", Ui.SIZE_SMALL, Ui.INK, true)
	cl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	chip.add_child(cl)
	row.add_child(chip)
	var tier := String(o.get("tier", m.get("tier", "")))
	if tier != "":
		var dv: Variant = o.get("division", m.get("division", ""))
		row.add_child(RankEmblem.make(tier, dv, 16, false))
		var tl := Ui.label(RankEmblem.label_for(tier, dv), Ui.SIZE_SMALL, RankEmblem.color(tier))
		tl.custom_minimum_size = Vector2(50, 0)
		tl.clip_text = true
		row.add_child(tl)
	var name := Ui.label(String(o.get("name", "")).to_upper() + ("  AI" if bool(o.get("ai", false)) else ""), Ui.SIZE_SMALL, Ui.INK)
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name.clip_text = true
	row.add_child(name)
	var their := int(float(o.get("us", 0)))
	var t := Ui.label(Ui.format_time(their / 1000), Ui.SIZE_SMALL, Ui.INK_2)
	t.custom_minimum_size = Vector2(46, 0)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(t)
	var gap := ""
	if not forfeit and us > 0 and their > 0:
		var dd := (us - their) / 1000000.0
		gap = ("-%.3f" % -dd) if dd < 0 else ("+%.3f" % dd)
	var g := Ui.label(gap, Ui.SIZE_SMALL, GREEN if beat else Ui.RED, true)
	g.custom_minimum_size = Vector2(40, 0)
	g.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(g)
	return row


## The division `steps` below (-1) or above (+1) a rank: ["GOLD", "II"].
static func _step(tier: String, div: String, steps: int) -> Array:
	var ti := RankEmblem.TIERS.find(tier)
	if ti < 0 or ti >= 7:
		return [tier, div]  # MASTER and up have no divisions
	var di := DIVS.find(div)
	var at := ti * 4 + maxi(di, 0) + steps
	at = clampi(at, 0, 27)
	return [RankEmblem.TIERS[at / 4], DIVS[at % 4]]


func _tint(c: Color) -> void:
	var fill := StyleBoxFlat.new()
	fill.bg_color = c
	_bar.add_theme_stylebox_override("fill", fill)
	var bg := StyleBoxFlat.new()
	bg.bg_color = Color(1, 1, 1, 0.08)
	_bar.add_theme_stylebox_override("background", bg)


func _show_rank(tier: String, div: Variant) -> void:
	_emblem.tier = tier
	_emblem.division = String(div) if div != null else ""
	_emblem.queue_redraw()
	_tier_label.text = RankEmblem.label_for(tier, div)
	_tier_label.add_theme_color_override("font_color", RankEmblem.color(tier))
	_tint(RankEmblem.color(tier))


func _set_rp(v: float) -> void:
	_bar.value = clampf(v, 0.0, 100.0)
	_bar_text.text = "%d / 100 RP" % roundi(v)


func _animate(from_tier: String, from_div: Variant, tier: String, div: Variant, rp: int, change: int, promoted: bool, demoted: bool, placed: bool) -> void:
	var tw := create_tween()
	tw.tween_interval(0.5)
	if placed:
		_show_rank("UNRANKED", null)
		_tier_label.text = "PLACEMENTS DONE"
		_set_rp(0)
		tw.tween_callback(func() -> void:
			_show_rank(tier, div)
			_banner.text = "PLACED: " + RankEmblem.label_for(tier, div)
			_banner.add_theme_color_override("font_color", RankEmblem.color(tier))
			_pop(_emblem)
			Sfx.play("lap_purple"))
		tw.tween_method(_set_rp, 0.0, float(rp), 0.8).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		return
	_show_rank(from_tier, from_div)
	var start := float(rp - change)
	if promoted:
		start = float(rp - change + 100)
	elif demoted:
		start = float(before.get("rp", maxi(-change - 4, 0))) if not before.is_empty() else float(maxi(-change - 4, 0))
	_set_rp(start)
	Sfx.play("verified" if change >= 0 else "ui_error")
	if promoted:
		tw.tween_method(_set_rp, start, 100.0, 0.7).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
		tw.tween_callback(func() -> void:
			_show_rank(tier, div)
			_set_rp(0)
			_banner.text = "PROMOTED TO " + RankEmblem.label_for(tier, div)
			_banner.add_theme_color_override("font_color", RankEmblem.color(tier))
			_ribbon()
			_pop(_emblem)
			Sfx.play("lap_purple"))
		tw.tween_method(_set_rp, 0.0, float(rp), 0.5).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	elif demoted:
		tw.tween_method(_set_rp, start, 0.0, 0.6).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
		tw.tween_callback(func() -> void:
			_show_rank(tier, div)
			_banner.text = "DEMOTED TO " + RankEmblem.label_for(tier, div)
			_banner.add_theme_color_override("font_color", Ui.RED)
			Sfx.play("lap_deleted"))
		tw.tween_method(_set_rp, 100.0, float(rp), 0.5).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	else:
		tw.tween_method(_set_rp, start, float(rp), 0.9).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)


func _pop(c: Control) -> void:
	c.pivot_offset = c.size / 2
	var t := create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	t.tween_property(c, "scale", Vector2(1.25, 1.25), 0.12)
	t.tween_property(c, "scale", Vector2.ONE, 0.25)


## The "PROMOTED" ribbon sprite over the emblem, when the art is there.
func _ribbon() -> void:
	var tex := PartCard.texture("res://assets/sprites/ranked/rank_up.png")
	if tex == null:
		return
	var t := TextureRect.new()
	t.texture = tex
	t.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	t.size = tex.get_size() / 2  # 1x on a 1280x720 screen: as wide as the emblem
	t.position = _emblem.get_global_rect().get_center() - get_global_rect().position - t.size / 2 + Vector2(0, 27)
	add_child(t)
	t.modulate.a = 0.0
	create_tween().tween_property(t, "modulate:a", 1.0, 0.2)
