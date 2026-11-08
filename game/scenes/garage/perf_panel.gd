class_name PerfPanel
extends VBoxContainer
## How a part changes the driving: pixel bars for top speed, cornering, braking,
## acceleration, battery and weight (CarPerf), the car with the part against the
## car as it is now, plus one plain sentence. Hover a stat for what it means.

var _caption: Label
var _bars: PerfBars
var _summary: Label
## metrics() by setup, driver stats and spec: hovering the list asks for the same cars again and again
static var _cache := {}


func _init() -> void:
	add_theme_constant_override("separation", 2)
	var head := Ui.hbox(6)
	head.add_child(Ui.label("PERFORMANCE", Ui.SIZE_SMALL, Ui.INK_2, true))
	_caption = Ui.label("", Ui.SIZE_SMALL, Ui.INK_3)
	_caption.clip_text = true
	_caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(_caption)
	add_child(head)
	_bars = PerfBars.new()
	_bars.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(_bars)
	_summary = Ui.label("", Ui.SIZE_SMALL, Ui.INK)
	_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_summary.add_theme_constant_override("line_spacing", -3)
	_summary.custom_minimum_size = Vector2(60, 0)
	add_child(_summary)


## Shows the car with `part` fitted in its area against the car as fitted now.
## For the fitted part itself, against the standard part in that area: what it gives you.
func show_part(part: Dictionary, hovered: bool = false) -> void:
	var area := String(part.get("area", ""))
	if area == "":
		return
	var fitted := Catalog.equipped_part(area)
	var is_fitted := String(part.get("id", "")) == String(fitted.get("id", "-")) or (String(part.get("rarity", "")) == "starter" and String(fitted.get("rarity", "")) == "starter")
	var now := _metrics(fitted_with())
	var std := _metrics({})
	if is_fitted:
		var without := _metrics(fitted_with(area, {"area": area, "concept": "baseline", "rarity": "starter", "stats": {}}))
		_caption.text = "on your car, vs the standard part" if String(part.get("rarity", "")) != "starter" else "your car now"
		_bars.show_cars(without, now, std)
		_summary.text = CarPerf.summary(without, now) if String(part.get("rarity", "")) != "starter" else "The standard part: no strengths, no weaknesses."
	else:
		var cand := _metrics(fitted_with(area, part))
		_caption.text = ("with %s %s" % [PartCard.part_name(part).to_upper(), PartCard.serial(part)]).strip_edges() if hovered else "with this part vs your car now"
		_bars.show_cars(now, cand, std)
		_summary.text = CarPerf.summary(now, cand)


## One plain sentence on what fitting `part` would do to the car as it is now (pack opening).
static func one_liner(part: Dictionary) -> String:
	var area := String(part.get("area", ""))
	if area == "":
		return ""
	return CarPerf.summary(_metrics(fitted_with()), _metrics(fitted_with(area, part)))


## CarPerf.metrics for a set of fitted parts (area -> part) with today's setup and driver.
static func _metrics(parts: Dictionary) -> Dictionary:
	var spec := CarPerf.spec_of(parts, Catalog.data)
	var stats := Profile.stats()
	var key := "%s|%s|%s" % [Profile.setup, stats, spec]
	if not _cache.has(key):
		if _cache.size() > 200:
			_cache.clear()
		_cache[key] = CarPerf.metrics(CarPerf.car(Profile.setup, stats, spec))
	return _cache[key]


## The fitted parts by area, with one part swapped in.
static func fitted_with(area: String = "", part: Variant = null) -> Dictionary:
	var parts := {}
	for a: String in Catalog.AREAS:
		parts[a] = Catalog.equipped_part(a)
	if area != "" and part is Dictionary:
		parts[area] = part
	return parts


## The rows of bars, drawn by hand so they stay crisp pixel art.
class PerfBars:
	extends Control

	const ROW_H := 10
	const NAME_W := 58
	const VALUE_W := 44
	const DELTA_W := 30
	const TRACK := Color("24262c")
	const FILL := Color("7d808a")

	var _from: Dictionary = {}
	var _to: Dictionary = {}
	var _std: Dictionary = {}

	func _init() -> void:
		custom_minimum_size = Vector2(0, ROW_H * CarPerf.KEYS.size())
		mouse_filter = Control.MOUSE_FILTER_PASS
		tooltip_text = "Hover a stat to see what it means."

	func show_cars(from: Dictionary, to: Dictionary, std: Dictionary) -> void:
		_from = from
		_to = to
		_std = std
		queue_redraw()

	func _get_tooltip(at_position: Vector2) -> String:
		var row := int(at_position.y) / ROW_H
		if row < 0 or row >= CarPerf.KEYS.size():
			return ""
		return CarPerf.HELP[CarPerf.KEYS[row]]

	## 0..1 along the bar: the standard car in the middle, better to the right.
	func _frac(key: String, v: float) -> float:
		var s: float = _std.get(key, v)
		if s == 0.0:
			return 0.5
		var rel := (v - s) / absf(s) / float(CarPerf.SPAN[key])
		if CarPerf.LOWER_IS_BETTER.has(key):
			rel = -rel
		return clampf(0.5 + rel * 0.5, 0.03, 1.0)

	static func _value(key: String, v: float) -> String:
		match key:
			"top_speed", "cornering":
				return "%d km/h" % roundi(v)
			"braking":
				return "%.1f m" % v
			"acceleration":
				return "%.2f s" % v
			"battery":
				return "%d kJ" % roundi(v)
			"weight":
				return "%d kg" % roundi(v)
		return "%.1f" % v

	static func _delta(key: String, d: float) -> String:
		match key:
			"acceleration":
				return "%+.2f" % d
			"battery", "weight":
				return "%+d" % roundi(d)
		return "%+.1f" % d

	## Changes smaller than the last digit shown are not worth a colour.
	static func _shown(key: String, d: float) -> bool:
		match key:
			"acceleration":
				return absf(d) >= 0.005
			"battery", "weight":
				return absf(d) >= 0.5
		return absf(d) >= 0.05

	func _draw() -> void:
		if _to.is_empty():
			return
		var bar_x := float(NAME_W)
		var bar_w := maxf(20.0, size.x - NAME_W - VALUE_W - DELTA_W - 4)
		for i in CarPerf.KEYS.size():
			var key: String = CarPerf.KEYS[i]
			var y := float(i * ROW_H)
			draw_string(Ui.font, Vector2(0, y + 8), CarPerf.NAMES[key], HORIZONTAL_ALIGNMENT_LEFT, NAME_W - 2, Ui.SIZE_SMALL, Ui.INK_2)
			var a: float = _from.get(key, 0.0)
			var b: float = _to.get(key, 0.0)
			var d := b - a
			var better := (d < 0.0) if CarPerf.LOWER_IS_BETTER.has(key) else (d > 0.0)
			var shown := _shown(key, d)
			# track, then the car now, then what changes: green gained, red lost
			var by := y + 3
			draw_rect(Rect2(bar_x, by, bar_w, 5), TRACK)
			var fa := roundf(_frac(key, a) * bar_w)
			var fb := roundf(_frac(key, b) * bar_w)
			if shown and fa == fb:
				fb = fa + (1.0 if better else -1.0)  # always at least a pixel
			draw_rect(Rect2(bar_x, by, minf(fa, fb), 5), FILL)
			if shown:
				var lo := minf(fa, fb)
				draw_rect(Rect2(bar_x + lo, by, absf(fb - fa), 5), Catalog.GREEN if better else Ui.RED)
			# segment the bar every 4 px, pixel-art style
			var x := 4.0
			while x < bar_w:
				draw_rect(Rect2(bar_x + x - 1, by, 1, 5), Color(TRACK, 0.85))
				x += 4.0
			# the standard car
			draw_rect(Rect2(bar_x + roundf(bar_w * 0.5), by - 1, 1, 7), Ui.INK_3)
			draw_string(Ui.font_bold, Vector2(bar_x + bar_w + 2, y + 8), _value(key, b), HORIZONTAL_ALIGNMENT_RIGHT, VALUE_W, Ui.SIZE_SMALL, Ui.INK)
			if shown:
				draw_string(Ui.font_bold, Vector2(bar_x + bar_w + 4 + VALUE_W, y + 8), _delta(key, d), HORIZONTAL_ALIGNMENT_RIGHT, DELTA_W - 2, Ui.SIZE_SMALL, Catalog.GREEN if better else Ui.RED)
