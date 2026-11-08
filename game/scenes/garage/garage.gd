class_name GarageScreen
extends Control
## The garage: fit parts to the car (it changes how the car drives and looks),
## tune the setup, and open development packs.

signal done

const TABS: Array[String] = ["PARTS", "TUNING", "PACKS"]
const SLOT_SIZE := Vector2(132, 38)

var _tab := 0
var _tab_buttons: Array[Button] = []
var _pages: Array[Control] = []
var _preview: CarPreview
var _slots := {}
var _area := "front_wing"
var _list: VBoxContainer
var _list_title: Label
var _detail: RichTextLabel
var _perf: PerfPanel
var _detail_more: RichTextLabel
var _desc: Label
var _fit: Button
var _scrap: Button
var _test: Button
var _scrap_armed := false
var _selected: Dictionary = {}
var _spec_box: VBoxContainer
var _status: Label
var _packs_page: Control
var _parts_panel: Control


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_background()
	_top_bar()
	var body := Control.new()
	body.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	body.offset_top = 34
	add_child(body)
	_pages = [_parts_page(), _tuning_page(), _make_packs_page()]
	for p in _pages:
		body.add_child(p)
	_status = Ui.label("", Ui.SIZE_SMALL, Ui.INK_2)
	_status.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_status.position = Vector2(12, -16)
	add_child(_status)
	_show_tab(0)
	_load()


func _background() -> void:
	var bg := ColorRect.new()
	bg.color = Ui.BG
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	var floor_tex := PartCard.texture("res://assets/sprites/ui/garage_floor.png")
	if floor_tex:
		var f := TextureRect.new()
		f.texture = floor_tex
		f.stretch_mode = TextureRect.STRETCH_TILE
		f.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		f.modulate = Color(0.32, 0.33, 0.36)
		f.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		add_child(f)
	var wall := PartCard.texture("res://assets/sprites/ui/garage_wall.png")
	if wall:
		var w := TextureRect.new()
		w.texture = wall
		w.stretch_mode = TextureRect.STRETCH_TILE
		w.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
		w.custom_minimum_size = Vector2(0, 64)
		w.size.y = 64
		w.modulate = Color(0.55, 0.55, 0.6)
		w.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		add_child(w)
	var vignette := PartCard.texture("res://assets/sprites/ui/vignette.png")
	if vignette:
		var v := TextureRect.new()
		v.texture = vignette
		v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		v.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		v.stretch_mode = TextureRect.STRETCH_SCALE
		v.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(v)


func _top_bar() -> void:
	var bar := ColorRect.new()
	bar.color = Color(0.06, 0.065, 0.075, 0.92)
	bar.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	bar.size.y = 30
	add_child(bar)
	var row := Ui.hbox(6)
	row.position = Vector2(10, 5)
	add_child(row)
	var back := Ui.button("<  WEEKEND")
	back.pressed.connect(func() -> void:
		Profile.save()
		done.emit())
	row.add_child(back)
	var title := Ui.label("  GARAGE  ", Ui.SIZE_HEADING, Ui.INK, true)
	row.add_child(title)
	var tips := [
		"Fit parts to the car. Every part changes how it drives and how it looks.",
		"Set up the car: wing flap angles, brake bias and differential.",
		"Development packs: three unique parts each, earned by driving.",
	]
	for i in TABS.size():
		var b := Ui.button(TABS[i])
		b.toggle_mode = true
		b.custom_minimum_size = Vector2(70, 0)
		b.tooltip_text = tips[i]
		b.pressed.connect(_show_tab.bind(i))
		row.add_child(b)
		_tab_buttons.append(b)
	var help := Ui.button("?")
	help.custom_minimum_size = Vector2(22, 0)
	help.tooltip_text = "Garage tour: what everything here does."
	help.pressed.connect(_start_tour)
	row.add_child(help)


func _show_tab(i: int) -> void:
	_tab = i
	for k in _pages.size():
		_pages[k].visible = k == i
		_tab_buttons[k].set_pressed_no_signal(k == i)
	if i == 2:
		_refresh_packs()


# ---- PARTS ----

func _parts_page() -> Control:
	var page := Control.new()
	page.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_preview = CarPreview.new()
	_preview.color = Ui.RED
	_preview.look = Catalog.car_look()
	_preview.anchor_right = 0.64
	_preview.anchor_bottom = 0.78
	_preview.offset_top = 46
	_preview.offset_bottom = -42
	_preview.offset_left = 10
	_preview.offset_right = -10
	page.add_child(_preview)
	for area: String in Catalog.AREAS:
		var s := _slot(area)
		page.add_child(s)
		_slots[area] = s
	page.resized.connect(_place_slots.bind(page))
	# Inventory for the chosen area
	var panel := Ui.panel()
	_parts_panel = panel
	panel.anchor_left = 0.64
	panel.anchor_right = 1.0
	panel.anchor_bottom = 1.0
	panel.offset_left = 6
	panel.offset_right = -8
	panel.offset_top = 4
	panel.offset_bottom = -8
	page.add_child(panel)
	var v := Ui.vbox(4)
	panel.add_child(v)
	_list_title = Ui.label("", Ui.SIZE_SMALL, Ui.INK_2, true)
	v.add_child(_list_title)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	v.add_child(scroll)
	_list = Ui.vbox(3)
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_list)
	_detail = _detail_label()
	v.add_child(_detail)
	# two lines of the concept's story; all of it on hover
	_desc = Ui.label("", Ui.SIZE_SMALL, Ui.INK_2)
	_desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_desc.max_lines_visible = 2
	_desc.add_theme_constant_override("line_spacing", -3)
	_desc.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_desc.custom_minimum_size = Vector2(60, 0)
	_desc.mouse_filter = Control.MOUSE_FILTER_PASS
	v.add_child(_desc)
	# How the part changes the driving, against the car as it is now
	_perf = PerfPanel.new()
	v.add_child(_perf)
	_detail_more = _detail_label()
	v.add_child(_detail_more)
	var buttons := Ui.hbox(4)
	v.add_child(buttons)
	_fit = Ui.button("FIT PART", true)
	_fit.tooltip_text = "Swap this part onto the car. Try it in Practice straight away.\nQualifying keeps the car you first qualified with (parc ferme)."
	_fit.custom_minimum_size = Vector2(0, 22)
	_fit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_fit.pressed.connect(_equip_selected)
	buttons.add_child(_fit)
	_test = Ui.button("TEST DRIVE")
	_test.tooltip_text = "The autopilot drives a lap of Mtkvari with your car now and with this part, and shows where it gains or loses time."
	_test.custom_minimum_size = Vector2(0, 22)
	_test.pressed.connect(_test_drive)
	buttons.add_child(_test)
	_scrap = Ui.button("SCRAP")
	_scrap.tooltip_text = "Scrap this part for R&D credits (more for rarer parts). It leaves your garage for good."
	_scrap.custom_minimum_size = Vector2(0, 22)
	_scrap.pressed.connect(_scrap_selected)
	buttons.add_child(_scrap)
	# Car spec summary
	_spec_box = Ui.vbox(2)
	_spec_box.anchor_top = 0.78
	_spec_box.anchor_bottom = 1.0
	_spec_box.anchor_right = 0.64
	_spec_box.offset_left = 14
	_spec_box.offset_right = -10
	_spec_box.offset_bottom = -22
	page.add_child(_spec_box)
	return page


func _detail_label() -> RichTextLabel:
	var l := RichTextLabel.new()
	l.bbcode_enabled = true
	l.fit_content = true
	l.scroll_active = false
	l.add_theme_font_size_override("normal_font_size", Ui.SIZE_SMALL)
	l.add_theme_font_size_override("bold_font_size", Ui.SIZE_SMALL)
	l.add_theme_font_override("bold_font", Ui.font_bold)
	return l


func _slot(area: String) -> Control:
	var b := Button.new()
	b.focus_mode = Control.FOCUS_NONE
	b.custom_minimum_size = SLOT_SIZE
	b.size = SLOT_SIZE
	b.toggle_mode = true
	b.tooltip_text = Catalog.AREA_HELP.get(area, "") + "\n\nClick to see the parts you own for it."
	b.pressed.connect(_select_area.bind(area))
	b.mouse_entered.connect(func() -> void:
		_preview.highlight = area)
	b.mouse_exited.connect(func() -> void:
		_preview.highlight = _area)
	var icon := TextureRect.new()
	icon.name = "Icon"
	icon.position = Vector2(3, 3)
	icon.size = Vector2(32, 32)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(icon)
	var a := Ui.label(Catalog.AREA_NAMES[area], Ui.SIZE_SMALL, Ui.INK_2)
	a.position = Vector2(38, 4)
	a.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(a)
	var n := Ui.label("", Ui.SIZE_SMALL, Ui.INK, true)
	n.name = "PartName"
	n.position = Vector2(38, 18)
	n.size = Vector2(72, 14)
	n.clip_text = true
	n.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(n)
	return b


func _place_slots(page: Control) -> void:
	var w := page.size.x * 0.64
	var h := page.size.y * 0.78
	# two rows: aero above the car, mechanical below; rear on the left like the car
	var gap := (w - 3 * SLOT_SIZE.x) / 4.0
	var col := func(i: int) -> float: return gap + i * (SLOT_SIZE.x + gap)
	var pos := {
		"rear_wing": Vector2(col.call(0), 4), "sidepods": Vector2(col.call(1), 4), "front_wing": Vector2(col.call(2), 4),
		"power_unit": Vector2(col.call(0), h - SLOT_SIZE.y + 2), "floor": Vector2(col.call(1), h - SLOT_SIZE.y + 2), "suspension": Vector2(col.call(2), h - SLOT_SIZE.y + 2),
	}
	var leaders := {}
	for area: String in _slots:
		var s: Control = _slots[area]
		s.position = pos[area]
		var top: bool = area in ["rear_wing", "sidepods", "front_wing"]
		var anchor: Vector2 = s.position + Vector2(SLOT_SIZE.x / 2, SLOT_SIZE.y if top else 0.0) - _preview.position
		leaders[area] = anchor
	_preview.leaders = leaders


func _refresh_slots() -> void:
	for area: String in _slots:
		var b: Button = _slots[area]
		var p := Catalog.equipped_part(area)
		var icon := b.get_node("Icon") as TextureRect
		icon.texture = PartCard.texture("res://assets/sprites/parts/%s_%s.png" % [area, p.get("concept", "")])
		if icon.texture == null:
			icon.texture = PartCard.texture("res://assets/sprites/parts/%s_%s.png" % [area, {"front_wing": "outwash", "rear_wing": "highdf", "sidepods": "downwash", "floor": "low_rake", "suspension": "pushrod", "power_unit": "torque"}[area]])
		icon.modulate = Color(1, 1, 1, 1.0 if String(p.get("rarity", "")) != "starter" else 0.45)
		var n := b.get_node("PartName") as Label
		n.text = PartCard.part_name(p).to_upper()
		n.add_theme_color_override("font_color", PartCard.rarity_color(String(p.get("rarity", "starter"))))
		b.set_pressed_no_signal(area == _area)


func _select_area(area: String) -> void:
	_area = area
	_preview.highlight = area
	_preview.focus(area)
	_refresh_slots()
	_fill_list()


func _fill_list() -> void:
	for c in _list.get_children():
		c.queue_free()
	var parts := Catalog.inventory().filter(func(p: Dictionary) -> bool: return String(p.get("area", "")) == _area)
	_list_title.text = "%s · %d PART%s" % [Catalog.AREA_NAMES[_area], parts.size(), "" if parts.size() == 1 else "S"]
	var fitted := Catalog.equipped_id(_area)
	parts.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return String(a.get("id", "")) == fitted)
	for p: Dictionary in parts:
		var row := PartCard.new()
		row.compact = true
		row.part = p
		row.equipped = String(p.get("id", "")) == fitted
		row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.picked.connect(_pick)
		row.mouse_entered.connect(_try_on.bind(p))
		row.mouse_exited.connect(_try_on.bind({}))
		_list.add_child(row)
	if parts.is_empty():
		var l := Ui.label("No parts for this area yet. Open packs to find some.", Ui.SIZE_SMALL, Ui.INK_3)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_list.add_child(l)
	_pick(Catalog.equipped_part(_area))


func _try_on(p: Dictionary) -> void:
	var look := Catalog.car_look()
	if not p.is_empty() and look.has(String(p.get("area", ""))):
		var c := String(p.get("concept", ""))
		if c != "baseline":
			look[String(p["area"])] = c
	if look != _preview.look:
		_preview.look = look
		_preview.rebuild()
	# the bars follow the hover, and go back to the picked part after
	if not p.is_empty():
		_perf.show_part(p, true)
	elif not _selected.is_empty():
		_perf.show_part(_selected)


func _pick(p: Dictionary) -> void:
	_selected = p
	_scrap_armed = false
	for row in _list.get_children():
		if row is PartCard:
			(row as PartCard).selected = (row as PartCard).part.get("id") == p.get("id")
			row.queue_redraw()
	var area := String(p.get("area", _area))
	var concept := String(p.get("concept", ""))
	var display: Dictionary = p.get("display") if p.get("display") is Dictionary else {}
	var rarity := String(p.get("rarity", ""))
	var retired := bool(display.get("retired", false))
	var kg := PartCard.weight(p)
	var kg_text := "  [color=#%s]%s[/color]" % [Catalog.stat_color("weight", kg).to_html(false), Catalog.format_stat("weight", kg)] if kg != 0 else ""
	_detail.text = "[b]%s[/b]  [color=#%s]%s[/color]%s%s" % [PartCard.part_name(p).to_upper(), PartCard.rarity_color(rarity).to_html(false), rarity.to_upper(), kg_text, "  [color=#6e6f78]RETIRED[/color]" if retired else ""]
	var desc := Catalog.concept_description(area, concept)
	if desc == "":
		desc = String(display.get("description", ""))
	_desc.text = desc
	_desc.tooltip_text = desc
	_desc.visible = desc != ""
	_perf.show_part(p)
	# The part's own numbers, for those who want them, on hover: the bars say what they do
	var more := ""
	var stats: Dictionary = p.get("stats", {})
	var bits: Array[String] = []
	for k: String in Catalog.STAT_ORDER + ["weight"]:
		var v := int(stats.get(k, 0))
		if v != 0:
			bits.append("%s %s" % [Catalog.STAT_NAMES.get(k, k.to_upper()), Catalog.format_stat(k, v)])
	_detail.tooltip_text = ("The part's own numbers (against the standard part):\n" + "\n".join(bits)) if not bits.is_empty() else ""
	var traits: Array = p.get("traits", [])
	if display.get("traits") is Array:
		traits = display["traits"]
	if not traits.is_empty():
		var names := traits.map(func(t: Variant) -> String: return String(t.get("name", t.get("id", ""))) if t is Dictionary else String(t))
		more += "[color=#f2c230]%s[/color]\n" % "  ·  ".join(names)
	if rarity == "starter":
		more += "[color=#6e6f78]Starter part: it never wears out.[/color]"
	elif p.has("km"):
		var km := float(p.get("km", 0))
		var left := float(display.get("kmLeft", maxf(0.0, float(display.get("lifeKm", 0)) - km)))
		var effect := int(display.get("effect", 1000))
		more += "[color=#a3a3ad]%s km driven · %s km left[/color] [color=#6e6f78]· %d races · %d wins[/color]" % [_km(km), _km(left), int(p.get("races", 0)), int(p.get("wins", 0))]
		if retired:
			more += "\n[color=#e8352b]RETIRED: worn out. Scrap it for R&D credits.[/color]"
		elif effect < 1000:
			more += "\n[color=#f2c230]WORN: %d%% effect[/color] [color=#6e6f78]its changes fade as it wears[/color]" % roundi(effect / 10.0)
	_detail_more.text = more
	var is_fitted: bool = String(p.get("id", "")) == Catalog.equipped_id(area) or (p.get("rarity") == "starter" and Catalog.equipped_id(area) == "")
	_fit.disabled = is_fitted or not p.has("id") or retired
	_fit.text = "FITTED" if is_fitted else ("RETIRED" if retired else "FIT PART")
	_test.visible = p.has("id") and not retired and not (is_fitted and rarity == "starter")
	var credits := _scrap_credits(rarity)
	_scrap.visible = not is_fitted and p.has("id") and rarity != "starter"
	_scrap.disabled = false
	_scrap.text = "SCRAP +%d" % credits
	_scrap.tooltip_text = "Scrap this part for %d R&D credits. It leaves your garage for good." % credits
	if Profile.setup_locked() and not is_fitted:
		_status.text = "Parc ferme: today's qualifying keeps the car you first qualified with. New parts count in practice now and in qualifying tomorrow."


## TEST DRIVE: autopilot laps with the car now and with the picked part (or, for
## the fitted part, with the standard part instead), then where it gains and loses.
func _test_drive() -> void:
	if _selected.is_empty():
		return
	var area := String(_selected.get("area", _area))
	var standard := {"area": area, "concept": "baseline", "rarity": "starter", "stats": {}}
	var is_fitted := String(_selected.get("id", "")) == Catalog.equipped_id(area)
	var panel := TestDrivePanel.new()
	panel.title = ("%s %s" % [PartCard.part_name(_selected).to_upper(), PartCard.serial(_selected)]).strip_edges()
	if is_fitted:
		panel.base_spec = CarPerf.spec_of(PerfPanel.fitted_with(area, standard), Catalog.data)
		panel.part_spec = CarPerf.spec_of(PerfPanel.fitted_with(), Catalog.data)
		panel.caption = "Fitted now: against the standard part in its place."
	else:
		panel.base_spec = CarPerf.spec_of(PerfPanel.fitted_with(), Catalog.data)
		panel.part_spec = CarPerf.spec_of(PerfPanel.fitted_with(area, _selected), Catalog.data)
		panel.caption = "Against your car as it is now."
	add_child(panel)
	await panel.closed
	panel.queue_free()


static func _km(km: float) -> String:
	return "%d" % roundi(km) if km >= 100.0 or is_equal_approx(km, roundf(km)) else "%.1f" % km


func _scrap_credits(rarity: String) -> int:
	var r: Variant = (Catalog.data.get("rarities", {}) as Dictionary).get(rarity)
	return int((r as Dictionary).get("scrapCredits", 0)) if r is Dictionary else 0


## Scrapping takes two clicks: the first asks, the second scraps.
func _scrap_selected() -> void:
	if _selected.is_empty():
		return
	if not _scrap_armed:
		_scrap_armed = true
		_scrap.text = "SURE? +%d" % _scrap_credits(String(_selected.get("rarity", "")))
		return
	_scrap_armed = false
	_scrap.disabled = true
	var res: Variant = await Api.post_json("/api/garage/scrap", {"player": Profile.id, "partId": _selected.get("id", "")})
	if res is Dictionary and (res as Dictionary).has("scrapped"):
		var credits := int((res["scrapped"] as Dictionary).get("credits", 0))
		res.erase("scrapped")
		Catalog.garage = res
		if has_node("/root/Sfx"):
			get_node("/root/Sfx").call("play", "equip")
		_refresh_slots()
		_fill_list()
		_refresh_spec()
		_status.text = "Scrapped: +%d R&D credits (%d in total)." % [credits, int(Catalog.garage.get("credits", 0))]
	else:
		_status.text = ("Could not scrap the part: " + Api.last_error) if Api.last_error != "" else "Could not scrap the part (server offline)."
		_scrap.disabled = false


func _equip_selected() -> void:
	if _selected.is_empty():
		return
	_fit.disabled = true
	var res: Variant = await Api.post_json("/api/garage/equip", {"player": Profile.id, "partId": _selected.get("id", "")})
	if res is Dictionary and (res as Dictionary).has("equipped"):
		Catalog.garage = res
		if has_node("/root/Sfx"):
			get_node("/root/Sfx").call("play", "equip")
		_preview.look = Catalog.car_look()
		_preview.rebuild()
		_preview.fitted(String(_selected.get("area", "")))
		_refresh_slots()
		_fill_list()
		_refresh_spec()
	else:
		_status.text = ("Could not fit the part: " + Api.last_error) if Api.last_error != "" else "Could not fit the part (server offline)."
		_fit.disabled = false


func _refresh_spec() -> void:
	for c in _spec_box.get_children():
		c.queue_free()
	var spec := Catalog.car_spec()
	var head := Ui.hbox(8)
	head.add_child(Ui.label("CAR SPEC", Ui.SIZE_SMALL, Ui.INK_2, true))
	head.add_child(Ui.label("changes from your parts vs a baseline car", Ui.SIZE_SMALL, Ui.INK_3))
	_spec_box.add_child(head)
	var grid := GridContainer.new()
	grid.columns = 6
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 1)
	_spec_box.add_child(grid)
	for k: String in ["downforce", "drag", "power", "grip", "traction", "harvest", "weight"]:
		var v := int(spec.get(k, 0))
		var name_label := Ui.label(Catalog.STAT_NAMES[k], Ui.SIZE_SMALL, Ui.INK_2)
		name_label.tooltip_text = Catalog.STAT_HELP.get(k, "")
		name_label.mouse_filter = Control.MOUSE_FILTER_PASS
		grid.add_child(name_label)
		grid.add_child(Ui.label(Catalog.format_stat(k, v) if v != 0 else "0", Ui.SIZE_SMALL, Catalog.stat_color(k, v) if v != 0 else Ui.INK_3, true))


# ---- TUNING ----

func _tuning_page() -> Control:
	var page := Control.new()
	page.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var t := TuningPanel.new()
	t.locked = Profile.setup_locked()
	t.changed.connect(Profile.save)
	page.add_child(t)
	t.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	t.offset_top = 6
	t.offset_left = 8
	t.offset_right = -8
	t.offset_bottom = -20
	return page


# ---- PACKS ----

func _make_packs_page() -> Control:
	_packs_page = Control.new()
	_packs_page.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return _packs_page


func _refresh_packs() -> void:
	for c in _packs_page.get_children():
		c.queue_free()
	var count := Catalog.unopened_packs()
	var art := TextureRect.new()
	art.texture = PartCard.texture("res://assets/sprites/packs/pack_closed.png")
	art.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	art.size = Vector2(96, 112) * 1.7
	art.position = Vector2(60, 24)
	art.modulate = Color.WHITE if count > 0 else Color(0.45, 0.45, 0.5)
	_packs_page.add_child(art)
	var badge := Ui.label("x%d" % count, Ui.SIZE_TITLE, Ui.INK if count > 0 else Ui.INK_3, true)
	badge.position = Vector2(60 + art.size.x - 20, 24)
	_packs_page.add_child(badge)
	if count > 0:
		var bob := create_tween().set_loops()
		bob.tween_property(art, "position:y", 18.0, 0.8).set_trans(Tween.TRANS_SINE)
		bob.tween_property(art, "position:y", 24.0, 0.8).set_trans(Tween.TRANS_SINE)
	var open := Ui.button("OPEN PACK" if count > 0 else "NO PACKS YET", true)
	open.disabled = count == 0
	open.custom_minimum_size = Vector2(150, 26)
	open.position = Vector2(66, 230)
	open.pressed.connect(_open_pack)
	_packs_page.add_child(open)

	var info := Ui.vbox(4)
	info.position = Vector2(300, 20)
	info.custom_minimum_size = Vector2(300, 0)
	_packs_page.add_child(info)
	info.add_child(Ui.label("DEVELOPMENT PACKS", Ui.SIZE_HEADING, Ui.INK, true))
	info.add_child(Ui.label("Three unique parts each. Earned on track, never sold.", Ui.SIZE_SMALL, Ui.INK_2))
	for line: String in ["First qualifying run of the day", "Top 3 in qualifying", "Every race you finish"]:
		var r := Ui.hbox(6)
		var dot := ColorRect.new()
		dot.color = Ui.RED
		dot.custom_minimum_size = Vector2(4, 4)
		dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		r.add_child(dot)
		r.add_child(Ui.label(line, Ui.SIZE_SMALL, Ui.INK))
		info.add_child(r)
	var packs: Dictionary = Catalog.garage.get("packs", {})
	if packs.has("weeklyCap"):
		info.add_child(Ui.label("You have earned %d of %d packs this week." % [int(packs.get("earnedThisWeek", 0)), int(packs.get("weeklyCap", 0))], Ui.SIZE_SMALL, Ui.INK_2))
	var supply: Dictionary = Catalog.garage.get("supply", {})
	if supply.has("cap"):
		var cap := int(supply.get("cap", 1))
		var minted := int(supply.get("minted", 0))
		info.add_child(Ui.label("WEEKLY PART SUPPLY", Ui.SIZE_SMALL, Ui.INK_2, true))
		var bar := Ui.stat_bar(minted, maxi(cap, 1))
		bar.custom_minimum_size = Vector2(280, 6)
		info.add_child(bar)
		info.add_child(Ui.label("%d of %d parts released this week. Scarce by design." % [minted, cap], Ui.SIZE_SMALL, Ui.INK))
	var note := Ui.label("Parts live in your garage for free. They are minted on Solana only when you choose to trade one, and the trader pays the mint.", Ui.SIZE_SMALL, Ui.INK_3)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.custom_minimum_size = Vector2(300, 0)
	info.add_child(note)


func _open_pack() -> void:
	var res: Variant = await Api.post_json("/api/packs/open", {"player": Profile.id})
	if not res is Dictionary or not (res as Dictionary).get("parts") is Array:
		_status.text = ("Could not open the pack: " + Api.last_error) if Api.last_error != "" else "Could not open the pack (server offline)."
		return
	var overlay := PackOpening.new()
	overlay.parts = res["parts"]
	add_child(overlay)
	await overlay.closed
	overlay.queue_free()
	await Catalog.load_garage()
	_refresh_all()
	_show_tab(0)


# ---- data ----

func _load() -> void:
	var ok: bool = await Catalog.load_garage()
	if not ok:
		_status.text = "Offline: parts and packs need the server. Tuning still works."
	_refresh_all()
	if not Profile.garage_tour_done:
		await get_tree().create_timer(0.4).timeout
		_start_tour()


func _start_tour() -> void:
	_show_tab(0)
	var tour := CoachTour.new()
	tour.steps = [
		{"target": func() -> Control: return _preview, "title": "YOUR CAR",
			"text": "Every part you fit changes how the car drives and how it looks. Watch it change here."},
		{"target": func() -> Control: return _slots["front_wing"], "title": "SIX PART SLOTS",
			"text": "Front wing, rear wing, sidepods, floor, suspension and power unit. Click a slot to see the parts you own for it."},
		{"target": func() -> Control: return _parts_panel, "title": "PART CARDS",
			"text": "Each part is unique: a real engineering concept with rolled stats. Green helps lap time, red costs it. Every part is a trade-off: more downforce means more drag."},
		{"target": func() -> Control: return _fit, "title": "FIT A PART",
			"text": "Hover a card to preview it on the car, then FIT PART. Test it in Practice. Qualifying keeps the car you first qualified with (parc ferme)."},
		{"target": func() -> Control: return _spec_box, "title": "CAR SPEC",
			"text": "The sum of your fitted parts against a baseline car. No part is best everywhere: match the car to the track."},
		{"target": func() -> Control: return _tab_buttons[1], "title": "TUNING",
			"before": func() -> void: _show_tab(1),
			"text": "Set the car like an engineer: wing flap angles in side view, brake bias and differential on steering-wheel dials."},
		{"target": func() -> Control: return _tab_buttons[2], "title": "DEVELOPMENT PACKS",
			"before": func() -> void: _show_tab(2),
			"text": "Earned by driving: your first qualifying lap of the day, a top 3 time, every race you finish. Three unique parts each, from a capped weekly supply."},
	]
	tour.finished.connect(func() -> void:
		Profile.garage_tour_done = true
		Profile.save()
		_show_tab(0))
	add_child(tour)


func _refresh_all() -> void:
	_preview.look = Catalog.car_look()
	_preview.rebuild()
	_refresh_slots()
	_fill_list()
	_refresh_spec()
	_tab_buttons[2].text = "PACKS (%d)" % Catalog.unopened_packs() if Catalog.unopened_packs() > 0 else "PACKS"
