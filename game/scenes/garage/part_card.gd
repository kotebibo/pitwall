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


static func _display(p: Dictionary) -> Dictionary:
	var d: Variant = p.get("display")
	return d if d is Dictionary else {}


static func retired(p: Dictionary) -> bool:
	return bool(_display(p).get("retired", false))


## Kilograms against the standard part (parts rolled before weight existed are 0).
static func weight(p: Dictionary) -> int:
	var stats: Variant = p.get("stats")
	return int((stats as Dictionary).get("weight", 0)) if stats is Dictionary else 0


## Durability left (0..1) and its colour: green, yellow once it has started to fade, red near the end. Starters: -1.
static func durability(p: Dictionary) -> Array:
	if String(p.get("rarity", "")) == "starter" or not p.has("km"):
		return [-1.0, Ui.INK_3]
	var d := _display(p)
	var left := 1.0 - clampf(float(d.get("wear", 0.0)), 0.0, 1.0)
	var col := Catalog.GREEN
	if bool(d.get("retired", false)):
		col = Ui.INK_3
	elif left < 0.1:
		col = Ui.RED
	elif int(d.get("effect", 1000)) < 1000:
		col = Ui.YELLOW
	return [left, col]


## A thin durability bar (nothing for starter parts, which never wear).
func _draw_durability(r: Rect2) -> void:
	var dur := durability(part)
	if float(dur[0]) < 0.0:
		return
	draw_rect(r, Color("101114"))
	draw_rect(Rect2(r.position, Vector2(roundf(r.size.x * float(dur[0])), r.size.y)), dur[1])


static func part_name(p: Dictionary) -> String:
	var display: Variant = p.get("display")
	if display is Dictionary and (display as Dictionary).has("name"):
		return String(display["name"])
	if p.has("name"):
		return String(p["name"])
	return Catalog.concept_name(String(p.get("area", "")), String(p.get("concept", "")))


func _ready() -> void:
	custom_minimum_size = Vector2(160, 34) if compact else SIZE
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
	var kg := weight(part)
	if kg != 0:
		# weight chip in the art window's corner
		draw_rect(Rect2(22, 18, 30, 9), Color(Ui.BG, 0.85))
		draw_string(Ui.font_bold, Vector2(22, 25), Catalog.format_stat("weight", kg).to_upper(), HORIZONTAL_ALIGNMENT_CENTER, 30, 6, Catalog.stat_color("weight", kg))
	_draw_durability(Rect2(24, 84, 64, 2))
	if retired(part):
		draw_rect(Rect2(Vector2.ZERO, SIZE), Color(Ui.BG, 0.6))
		draw_rect(Rect2(8, 44, 96, 14), Ui.PANEL)
		draw_string(Ui.font_bold, Vector2(8, 55), "RETIRED", HORIZONTAL_ALIGNMENT_CENTER, 96, Ui.SIZE_SMALL, Ui.INK_2)
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
	var right := 46.0 if equipped or retired(part) else 6.0
	var kg := weight(part)
	if kg != 0:
		draw_string(Ui.font_bold, Vector2(size.x - right - 30, 14), Catalog.format_stat("weight", kg), HORIZONTAL_ALIGNMENT_RIGHT, 28, Ui.SIZE_SMALL, Catalog.stat_color("weight", kg))
		right += 32.0
	draw_string(Ui.font_bold, Vector2(42, 14), part_name(part).to_upper(), HORIZONTAL_ALIGNMENT_LEFT, size.x - 42 - right, Ui.SIZE_SMALL, Ui.INK)
	draw_string(Ui.font, Vector2(42, 27), ("%s %s" % [rarity.to_upper(), serial(part)]).strip_edges(), HORIZONTAL_ALIGNMENT_LEFT, 72, Ui.SIZE_SMALL, rc)
	var line: Array = Catalog.stat_lines(part, 1)[0]
	draw_string(Ui.font, Vector2(116, 27), line[0], HORIZONTAL_ALIGNMENT_RIGHT, size.x - 166, Ui.SIZE_SMALL, Ui.INK_3)
	draw_string(Ui.font_bold, Vector2(size.x - 48, 27), line[1], HORIZONTAL_ALIGNMENT_RIGHT, 42, Ui.SIZE_SMALL, line[2])
	_draw_durability(Rect2(42, size.y - 3, size.x - 48, 2))
	if retired(part):
		draw_rect(r, Color(Ui.BG, 0.55))
		draw_rect(Rect2(size.x - 44, 5, 40, 11), Ui.LINE_STRONG)
		draw_string(Ui.font_bold, Vector2(size.x - 44, 14), "RETIRED", HORIZONTAL_ALIGNMENT_CENTER, 40, Ui.SIZE_SMALL, Ui.INK_2)
	if equipped:
		draw_rect(Rect2(size.x - 44, 5, 40, 11), Ui.RED)
		draw_string(Ui.font_bold, Vector2(size.x - 44, 14), "FITTED", HORIZONTAL_ALIGNMENT_CENTER, 40, Ui.SIZE_SMALL, Ui.INK)
