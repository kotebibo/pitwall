class_name LiveryPanel
extends Control
## The garage's LIVERY tab: pick the car's primary (body) and secondary
## (accents, helmet) colours from the palette in game/data/livery.json and
## see them on the 3D car straight away. SAVE stores them on the server for
## the account; Catalog keeps a copy so they show offline too.
## Colours are presentation only: they never reach the sim.

signal saved

const SWATCH := Vector2(26, 22)

var _show: CarShowcase
var _pick := {"primary": "", "secondary": ""}
var _names := {}
var _swatches: Array[Swatch] = []
var _save: Button
var _status: Label


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_show = CarShowcase.new()
	_show.anchor_right = 0.62
	_show.anchor_bottom = 1.0
	_show.offset_left = 10
	_show.offset_top = 8
	_show.offset_right = -6
	_show.offset_bottom = -24
	add_child(_show)
	var panel := Ui.panel()
	panel.anchor_left = 0.62
	panel.anchor_right = 1.0
	panel.anchor_bottom = 1.0
	panel.offset_left = 6
	panel.offset_right = -8
	panel.offset_top = 4
	panel.offset_bottom = -8
	add_child(panel)
	# scrolls if a short window cannot fit it all
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	panel.add_child(scroll)
	var v := Ui.vbox(5)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(v)
	v.add_child(Ui.label("LIVERY", Ui.SIZE_HEADING, Ui.INK, true))
	var hint := Ui.label("Your colours on track, in races and in the garage. Looks only: paint never changes how the car drives.", Ui.SIZE_SMALL, Ui.INK_2)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(hint)
	_slot(v, "primary", "PRIMARY  ·  BODY")
	_slot(v, "secondary", "SECONDARY  ·  ACCENTS, HELMET")
	_save = Ui.button("SAVE LIVERY", true)
	_save.custom_minimum_size = Vector2(0, 22)
	_save.pressed.connect(_save_livery)
	v.add_child(_save)
	_status = Ui.label("", Ui.SIZE_SMALL, Ui.INK_2)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(_status)
	reset()


## Back to the saved livery (or the cached one when offline).
func reset() -> void:
	for slot: String in _pick:
		_pick[slot] = Catalog.livery_hex(slot)
	_show.set_parts(_full_look())
	_refresh()


func _full_look() -> Dictionary:
	var look := Catalog.car_look()
	for area: String in ["suspension", "power_unit"]:
		look[area] = String(Catalog.equipped_part(area).get("concept", ""))
	return look


func _slot(parent: VBoxContainer, slot: String, title: String) -> void:
	var head := Ui.hbox(6)
	head.add_child(Ui.label(title, Ui.SIZE_SMALL, Ui.INK_2, true))
	var name_label := Ui.label("", Ui.SIZE_SMALL, Ui.INK, true)
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	head.add_child(name_label)
	_names[slot] = name_label
	parent.add_child(head)
	var grid := GridContainer.new()
	grid.columns = 6
	grid.add_theme_constant_override("h_separation", 4)
	grid.add_theme_constant_override("v_separation", 4)
	parent.add_child(grid)
	var group := ButtonGroup.new()
	for o: Variant in Catalog.livery_options(slot):
		if not o is Dictionary:
			continue
		var hex := String((o as Dictionary).get("hex", ""))
		var sw := Swatch.new()
		sw.color = Color(hex)
		sw.hex = hex
		sw.slot = slot
		sw.button_group = group
		sw.tooltip_text = String((o as Dictionary).get("name", hex))
		sw.custom_minimum_size = SWATCH
		sw.pressed.connect(_choose.bind(slot, hex))
		grid.add_child(sw)
		_swatches.append(sw)


func _choose(slot: String, hex: String) -> void:
	_pick[slot] = hex
	Sfx.play("ui_click")
	_refresh()


func _refresh() -> void:
	_show.set_colors(Color(_pick["primary"]), Color(_pick["secondary"]))
	for slot: String in _names:
		(_names[slot] as Label).text = _colour_name(slot, _pick[slot]).to_upper()
	for sw in _swatches:
		sw.set_pressed_no_signal(sw.hex == _pick[sw.slot])
		sw.queue_redraw()
	var changed: bool = _pick["primary"] != Catalog.livery_hex("primary") or _pick["secondary"] != Catalog.livery_hex("secondary")
	_save.disabled = not changed
	_save.text = "SAVE LIVERY" if changed else "SAVED"
	if changed:
		_status.text = "Not saved yet."
		_status.add_theme_color_override("font_color", Ui.INK_2)


func _colour_name(slot: String, hex: String) -> String:
	for o: Variant in Catalog.livery_options(slot):
		if o is Dictionary and String((o as Dictionary).get("hex", "")) == hex:
			return String((o as Dictionary).get("name", hex))
	return hex


func _save_livery() -> void:
	_save.disabled = true
	_status.text = "Saving…"
	var res: Variant = await Api.post_json("/api/garage/livery", {"player": Profile.id, "primary": _pick["primary"], "secondary": _pick["secondary"]})
	if res is Dictionary and (res as Dictionary).get("livery") is Dictionary:
		Catalog.cache_livery(res["livery"])
		Sfx.play("equip")
		_refresh()
		_status.text = "Saved. Your car wears it on track and in races."
		_status.add_theme_color_override("font_color", Catalog.GREEN)
		saved.emit()
	else:
		_status.text = ("Could not save the livery: " + Api.last_error) if Api.last_error != "" else "Could not save the livery (server offline)."
		_status.add_theme_color_override("font_color", Ui.RED)
		_save.disabled = false


## A colour chip drawn as pixel art: dark outline, a lit top edge, a shaded
## bottom edge and a glint. Selected: a chalk ring around it.
class Swatch extends Button:
	var color := Color.WHITE
	var hex := ""
	var slot := ""

	func _init() -> void:
		toggle_mode = true
		focus_mode = Control.FOCUS_NONE
		for st: String in ["normal", "hover", "pressed", "hover_pressed", "focus", "disabled"]:
			add_theme_stylebox_override(st, StyleBoxEmpty.new())

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var chip := r.grow(-2)
		if button_pressed:
			draw_rect(r, Ui.INK)
			draw_rect(r.grow(-1), Ui.BG)
		elif is_hovered():
			draw_rect(r, Ui.INK_3)
			draw_rect(r.grow(-1), Ui.BG)
		draw_rect(chip, Color("0d0e12"))
		var c := chip.grow(-1)
		draw_rect(c, color)
		draw_rect(Rect2(c.position, Vector2(c.size.x, 2)), color.lightened(0.25))
		draw_rect(Rect2(c.position + Vector2(0, c.size.y - 2), Vector2(c.size.x, 2)), color.darkened(0.3))
		draw_rect(Rect2(c.position + Vector2(2, 3), Vector2(2, 2)), Color(1, 1, 1, 0.55))
