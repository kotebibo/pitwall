class_name PartCard
extends Control
## A part as a trading card: rarity frame, illustration, name, serial and the
## stats it changes. Also used face down (card back) in pack opening.

signal picked(part: Dictionary)

const SIZE := Vector2(112, 152)
const RARITY_COLORS := {
	"starter": Color("6e6f78"), "common": Color("9aa0aa"), "rare": Color("5ec8e5"),
	"epic": Color("a855f7"), "legendary": Color("f2c230"),
}
const STAT_LABELS := {
	"downforce": "DOWNFORCE", "drag": "DRAG", "balance": "BALANCE", "power": "POWER",
	"harvest": "ENERGY", "grip": "GRIP", "traction": "TRACTION",
}

var part: Dictionary = {}
var face_down := false
var selected := false
var equipped := false
var compact := false  # small list row instead of a full card
var _hover := false
static var _tex := {}


static func texture(path: String) -> Texture2D:
	if not _tex.has(path):
		_tex[path] = load(path) if ResourceLoader.exists(path) else null
	return _tex[path]


static func serial(p: Dictionary) -> String:
	var s: Variant = p.get("serial")
	if s == null or String(s) == "":
		return ""
	var t := String(s)
	return t if t.begins_with("#") else "#" + t


static func rarity_color(rarity: String) -> Color:
	return RARITY_COLORS.get(rarity, Color("9aa0aa"))


static func part_name(p: Dictionary) -> String:
	var display: Variant = p.get("display")
	if display is Dictionary and (display as Dictionary).has("name"):
		return String(display["name"])
	if p.has("name"):
		return String(p["name"])
	return Catalog.concept_name(String(p.get("area", "")), String(p.get("concept", "")))


func _ready() -> void:
	custom_minimum_size = Vector2(220, 34) if compact else SIZE
	mouse_filter = Control.MOUSE_FILTER_STOP
	mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	mouse_entered.connect(func() -> void:
		_hover = true
		queue_redraw())
	mouse_exited.connect(func() -> void:
		_hover = false
		queue_redraw())


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and (event as InputEventMouseButton).pressed and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		picked.emit(part)
		accept_event()


func _draw() -> void:
	if compact:
		_draw_row()
	elif face_down:
		_draw_back()
	else:
		_draw_card()


func _icon() -> Texture2D:
	var t := texture("res://assets/sprites/parts/%s_%s.png" % [part.get("area", ""), part.get("concept", "")])
	if t == null:
		# starter parts show the area's first concept, dimmed by the frame
		t = texture("res://assets/sprites/parts/%s_%s.png" % [part.get("area", ""), {"front_wing": "outwash", "rear_wing": "highdf", "sidepods": "downwash", "floor": "low_rake", "suspension": "pushrod", "power_unit": "torque"}.get(String(part.get("area", "")), "")])
	return t


func _draw_back() -> void:
	var back := texture("res://assets/sprites/cards/back.png")
	if back:
		draw_texture_rect(back, Rect2(Vector2.ZERO, SIZE), false)
	else:
		draw_rect(Rect2(Vector2.ZERO, SIZE), Ui.PANEL)
		draw_rect(Rect2(Vector2.ZERO, SIZE), Ui.RED, false, 2.0)
		draw_string(Ui.font_bold, Vector2(0, SIZE.y / 2 + 6), "PW", HORIZONTAL_ALIGNMENT_CENTER, SIZE.x, Ui.SIZE_TITLE, Ui.RED)
	if _hover:
		draw_rect(Rect2(Vector2.ZERO, SIZE), Color(1, 1, 1, 0.08))


func _draw_card() -> void:
	var rarity := String(part.get("rarity", "common"))
	var rc := rarity_color(rarity)
	var frame := texture("res://assets/sprites/cards/frame_%s.png" % ("common" if rarity == "starter" else rarity))
	if frame:
		draw_texture_rect(frame, Rect2(Vector2.ZERO, SIZE), false)
	else:
		draw_rect(Rect2(Vector2.ZERO, SIZE), Ui.PANEL)
		draw_rect(Rect2(Vector2.ZERO, SIZE), rc, false, 2.0)
	var icon := _icon()
	if icon:
		draw_texture_rect(icon, Rect2(Vector2(24, 18), Vector2(64, 64)), false)
	# Text sits in the frame's slots (see assets/sprites/cards/layout.json)
	draw_string(Ui.font_bold, Vector2(34, 12), rarity.to_upper(), HORIZONTAL_ALIGNMENT_CENTER, 44, 6, rc)
	draw_string(Ui.font_bold, Vector2(8, 97), part_name(part).to_upper(), HORIZONTAL_ALIGNMENT_CENTER, 96, Ui.SIZE_SMALL, Ui.INK)
	var y := 114.0
	for line in Catalog.stat_lines(part, 3):
		draw_string(Ui.font, Vector2(12, y), line[0], HORIZONTAL_ALIGNMENT_LEFT, 56, 7, Ui.INK_2)
		draw_string(Ui.font_bold, Vector2(60, y), line[1], HORIZONTAL_ALIGNMENT_RIGHT, 40, 7, line[2])
		y += 12.0
	var sn := serial(part)
	if sn != "":
		draw_string(Ui.font, Vector2(8, 150), sn, HORIZONTAL_ALIGNMENT_RIGHT, 96, 6, Color(rc, 0.8))
	if equipped:
		draw_rect(Rect2(SIZE.x - 30, 4, 26, 10), Ui.RED)
		draw_string(Ui.font_bold, Vector2(SIZE.x - 30, 12), "ON", HORIZONTAL_ALIGNMENT_CENTER, 26, Ui.SIZE_SMALL, Ui.INK)
	if selected or _hover:
		draw_rect(Rect2(Vector2(-2, -2), SIZE + Vector2(4, 4)), Ui.INK if selected else Color(1, 1, 1, 0.5), false, 1.0)


func _draw_row() -> void:
	var rarity := String(part.get("rarity", "common"))
	var rc := rarity_color(rarity)
	var r := Rect2(Vector2.ZERO, size)
	draw_rect(r, Color("262930") if _hover or selected else Ui.PANEL)
	draw_rect(Rect2(0, 0, 3, size.y), rc)
	if selected:
		draw_rect(r, Ui.INK, false, 1.0)
	var icon := _icon()
	if icon:
		draw_texture_rect(icon, Rect2(Vector2(6, 1), Vector2(32, 32)), false)
	var right := 46.0 if equipped else 6.0
	draw_string(Ui.font_bold, Vector2(42, 14), part_name(part).to_upper(), HORIZONTAL_ALIGNMENT_LEFT, size.x - 42 - right, Ui.SIZE_SMALL, Ui.INK)
	draw_string(Ui.font, Vector2(42, 27), ("%s %s" % [rarity.to_upper(), serial(part)]).strip_edges(), HORIZONTAL_ALIGNMENT_LEFT, 84, Ui.SIZE_SMALL, rc)
	var line: Array = Catalog.stat_lines(part, 1)[0]
	draw_string(Ui.font, Vector2(128, 27), line[0], HORIZONTAL_ALIGNMENT_LEFT, size.x - 176, Ui.SIZE_SMALL, Ui.INK_3)
	draw_string(Ui.font_bold, Vector2(size.x - 48, 27), line[1], HORIZONTAL_ALIGNMENT_RIGHT, 42, Ui.SIZE_SMALL, line[2])
	if equipped:
		draw_rect(Rect2(size.x - 44, 5, 40, 11), Ui.RED)
		draw_string(Ui.font_bold, Vector2(size.x - 44, 14), "FITTED", HORIZONTAL_ALIGNMENT_CENTER, 40, Ui.SIZE_SMALL, Ui.INK)
