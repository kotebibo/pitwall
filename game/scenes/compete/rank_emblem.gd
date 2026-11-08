class_name RankEmblem
extends Control
## A ranked tier emblem: the pixel-art sprite from assets/sprites/ranked when it is there
## (emblem_<tier>.png, 64 px; badge_<tier>.png, 32 px, for lists), else a pixel shield drawn in
## code in the tier colour. The division numeral (IV..I) sits in the emblem's plain centre;
## badges are too small for it, so lists print the tier beside them.
## Sizes are in UI units (640x360 canvas): 64 = the 64 px emblem at 2x on 1280x720, 16 = the
## 32 px badge at 1x.

const TIERS: Array[String] = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"]
const COLORS := {
	"IRON": Color("6e6f78"), "BRONZE": Color("c98a5a"), "SILVER": Color("c6c8d0"), "GOLD": Color("f2c230"),
	"PLATINUM": Color("5ec8b0"), "EMERALD": Color("3ecf6a"), "DIAMOND": Color("5ec8e5"),
	"MASTER": Color("a855f7"), "GRANDMASTER": Color("e8352b"), "CHALLENGER": Color("f1efea"),
	"UNRANKED": Color("4a4c54"),
}
const MEDAL_COLORS := {"bronze": Color("c98a5a"), "silver": Color("c6c8d0"), "gold": Color("f2c230")}
## Half-widths of the 16x16 shield, row by row (centred on x = 8).
const SHAPE: Array[int] = [6, 7, 8, 8, 8, 8, 8, 8, 8, 7, 7, 6, 5, 4, 3, 2]
## The small badge for lists (under 24 px): an 8x8 shield, half-widths per row (centred on x = 4).
const SMALL: Array[int] = [3, 4, 4, 4, 4, 3, 2, 1]

var tier := "UNRANKED"
var division := ""
## Draw the numeral (off for the small list badges, where the text sits beside it).
var numeral := true


static func color(t: String) -> Color:
	return COLORS.get(t.to_upper(), Color("4a4c54"))


static func medal_color(m: String) -> Color:
	return MEDAL_COLORS.get(m.to_lower(), Ui.INK_3)


## "GOLD II", "MASTER", "UNRANKED".
static func label_for(t: String, div: Variant) -> String:
	var d := String(div) if div != null else ""
	return t.to_upper() if d == "" or TIERS.find(t.to_upper()) >= 7 or t.to_upper() == "UNRANKED" else "%s %s" % [t.to_upper(), d]


static func make(t: String, div: Variant, px: int, with_numeral: bool = true) -> RankEmblem:
	var e := RankEmblem.new()
	e.tier = t.to_upper() if t != "" else "UNRANKED"
	e.division = String(div) if div != null else ""
	e.numeral = with_numeral
	e.custom_minimum_size = Vector2(px, px)
	e.size = Vector2(px, px)
	e.mouse_filter = Control.MOUSE_FILTER_IGNORE
	e.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	return e


## A 24x24 medal sprite, or null (the caller then draws a disc).
static func medal_texture(m: String) -> Texture2D:
	return PartCard.texture("res://assets/sprites/ranked/medal_%s.png" % m.to_lower())


func _ready() -> void:
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST


func _draw() -> void:
	var s := minf(size.x, size.y)
	var origin := (size - Vector2(s, s)) / 2
	if s < 24.0:
		var badge := PartCard.texture("res://assets/sprites/ranked/badge_%s.png" % tier.to_lower())
		if badge:
			draw_texture_rect(badge, Rect2(origin, Vector2(s, s)), false)
		else:
			_draw_small(origin, s / 8.0)
		return
	var tex := PartCard.texture("res://assets/sprites/ranked/emblem_%s.png" % tier.to_lower())
	if tex:
		draw_texture_rect(tex, Rect2(origin, Vector2(s, s)), false)
	else:
		_draw_shield(origin, s / 16.0)
	if numeral and division != "" and TIERS.find(tier) < 7 and tier != "UNRANKED":
		# inside the art's safe box (22, 24, 20 x 17 of 64), ink with a 1 px dark drop shadow
		var fs := maxi(8, roundi(s * 0.22))
		var font := Ui.font_bold
		var w := font.get_string_size(division, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
		var p := origin + Vector2(s / 2 - w / 2, s * 0.5 + fs * 0.36)
		var px := maxf(1.0, s / 64.0)
		draw_string(font, p + Vector2(px, px), division, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color("08090b"))
		draw_string(font, p, division, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Ui.INK)
	elif numeral and tier == "UNRANKED" and s >= 32:
		var fs := roundi(s * 0.3)
		var w := Ui.font_bold.get_string_size("?", HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
		draw_string(Ui.font_bold, origin + Vector2(s / 2 - w / 2, s * 0.47 + fs * 0.36), "?", HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Ui.INK_2)


func _in(x: int, y: int) -> bool:
	if y < 0 or y >= SHAPE.size():
		return false
	var hw := SHAPE[y]
	return x >= 8 - hw and x < 8 + hw


## The pixel shield: dark outline, tier fill with a lit top edge and a shaded right side,
## and a dark plate in the middle for the numeral. Higher tiers get crown pips on top.
func _draw_shield(o: Vector2, px: float) -> void:
	var c := color(tier)
	var dark := c.darkened(0.62)
	var plate := Color(0.06, 0.065, 0.075, 0.92)
	var t := TIERS.find(tier)
	for y in SHAPE.size():
		for x in 16:
			if not _in(x, y):
				continue
			var edge := not (_in(x - 1, y) and _in(x + 1, y) and _in(x, y - 1) and _in(x, y + 1))
			var col := dark if edge else c
			if not edge:
				if not _in(x, y - 2) or not _in(x - 2, y):
					col = c.lightened(0.28)  # lit from the top left
				elif not _in(x + 2, y) or not _in(x, y + 2):
					col = c.darkened(0.22)
				# the plate: a smaller shield inside
				if y >= 4 and y <= 10 and absf(x + 0.5 - 8.0) < SHAPE[y] - 3.0:
					col = plate
			draw_rect(Rect2(o + Vector2(x, y) * px, Vector2(px, px)), col)
	# pips over the top edge: one per two tiers above iron, a crown from MASTER
	var pips := 0 if t < 0 else clampi(t / 2, 0, 3)
	if t >= 7:
		pips = 3
	for i in pips:
		var x := 8 - pips + i * 2
		draw_rect(Rect2(o + Vector2(x, -1) * px, Vector2(px, px)), c.lightened(0.3) if t < 7 else Ui.INK)


## A list badge: a flat 8x8 shield with a dark rim and a lit top row.
func _draw_small(o: Vector2, px: float) -> void:
	var c := color(tier)
	for y in SMALL.size():
		var hw := SMALL[y]
		for x in range(4 - hw, 4 + hw):
			var rim := y == SMALL.size() - 1 or x == 4 - hw or x == 3 + hw
			var col := c.darkened(0.55) if rim else (c.lightened(0.25) if y <= 1 else c)
			draw_rect(Rect2(o + Vector2(x, y) * px, Vector2(px, px)), col)
