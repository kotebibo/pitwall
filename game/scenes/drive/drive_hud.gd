class_name DriveHud
extends Control
## The driving HUD, drawn directly in the style of a TV graphic: timing tower
## with sectors, live delta, a steering-wheel dash (speed, gear, rev lights,
## battery, Boost and Straight Mode), messages and a track map.

const PURPLE := Color("a855f7")
const GREEN := Color("3ecf6a")
const SM_COLOR := Color("5ec8e5")
const GLASS := Color(0.07, 0.075, 0.09, 0.86)
const GLASS_LINE := Color(1, 1, 1, 0.08)

var title := ""
var lap := 0
var lap_us := 0
var lap_valid := true
var best_us := 0
var last_us := 0
var delta_us := 0
var has_delta := false
var sectors: Array[int] = []  # this lap
var best_sectors: Array[int] = []  # personal best per sector
var speed_kmh := 0
var gear := 1
var rpm := 0.0
var throttle := 0
var brake := 0
var battery := 1.0
var boosting := false
var straight_mode := false
var straight_zone := false
var device := "KEYBOARD"
var waiting := false
## Race mode: positions tower instead of the lap timer
var race_mode := false
var race_lap := 0
var race_laps := 5
## each: {"pos", "name", "gap" (text), "color", "you", "pit"}
var race_rows: Array = []
var tyre_compound := 1
var tyre_wear := 0.0
var next_tyre := 1
var pit_text := ""
var lights := -1  # -1 hidden, 0..5 red lights on
var map_others: Array = []  # {"p": Vector2, "c": Color}
## Rookie test panel (empty title = hidden)
var tut_title := ""
var tut_text := ""
var tut_step := 0
var tut_total := 4
var show_fps := false
var brake_warning := false
var message := ""
var message_color := Ui.INK
var _message_left := 0.0
var _message_age := 0.0

var map_points := PackedVector2Array()
var map_car := Vector2.ZERO
var map_ghost := Vector2(-1, -1)
var _map_rect := Rect2()
var _map_xf := Transform2D()


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func set_track(points: PackedVector2Array) -> void:
	map_points = points
	var lo := points[0]
	var hi := points[0]
	for p in points:
		lo = lo.min(p)
		hi = hi.max(p)
	var box := Vector2(104, 72)
	var s := minf(box.x / (hi - lo).x, box.y / (hi - lo).y)
	_map_xf = Transform2D(0.0, Vector2(s, s), 0.0, -lo * s)
	_map_rect = Rect2(Vector2.ZERO, (hi - lo) * s)


func flash(text: String, color: Color = Ui.INK, seconds: float = 2.5) -> void:
	message = text
	message_color = color
	_message_left = seconds
	_message_age = 0.0


func _process(delta: float) -> void:
	if _message_left > 0.0:
		_message_left -= delta
		_message_age += delta
		if _message_left <= 0.0:
			message = ""
	queue_redraw()


func _text(pos: Vector2, text: String, size: int, color: Color = Ui.INK, bold: bool = false, align := HORIZONTAL_ALIGNMENT_LEFT, width := -1.0) -> void:
	draw_string(Ui.font_bold if bold else Ui.font, pos, text, align, width, size, color)


func _glass(r: Rect2, accent: Color = Color.TRANSPARENT) -> void:
	draw_rect(r, GLASS)
	draw_rect(r, GLASS_LINE, false, 1.0)
	if accent.a > 0.0:
		draw_rect(Rect2(r.position, Vector2(r.size.x, 2)), accent)


func _draw() -> void:
	var w := size.x
	var h := size.y
	if race_mode:
		_draw_race_tower(w)
	else:
		_draw_tower()
	_draw_delta(w)
	_draw_dash(w, h)
	_draw_map(w, h)
	if show_fps:
		_text(Vector2(w - 60, 14), "%d FPS" % Engine.get_frames_per_second(), Ui.SIZE_SMALL, Ui.INK_2)
	if tut_title != "":
		_draw_tutorial(w)
	if lights >= 0:
		_draw_lights(w, h)
	if pit_text != "":
		var pr := Rect2(w / 2 - 150, h - 86, 300, 30)
		_glass(pr, Ui.YELLOW)
		_text(pr.position + Vector2(0, 13), pit_text, Ui.SIZE_SMALL, Ui.YELLOW, true, HORIZONTAL_ALIGNMENT_CENTER, pr.size.x)
		var names := ["SOFT", "MEDIUM", "HARD"]
		var cols := [Ui.RED, Ui.YELLOW, Ui.INK]
		for k in 3:
			var x := pr.position.x + 40 + k * 76
			var on := k == next_tyre
			_text(Vector2(x, pr.position.y + 25), "%d %s" % [k + 1, names[k]], Ui.SIZE_SMALL, cols[k] if on else Ui.INK_3, on)
	if brake_warning and not waiting:
		var blink := fmod(Time.get_ticks_msec() / 1000.0, 0.3) < 0.18
		var r := Rect2(w / 2 - 36, h * 0.30, 72, 20)
		draw_rect(r, Ui.RED if blink else Ui.RED_DARK)
		_text(r.position + Vector2(0, 15), "BRAKE", Ui.SIZE_HEADING, Ui.INK, true, HORIZONTAL_ALIGNMENT_CENTER, r.size.x)
	if waiting:
		var r := Rect2(w / 2 - 130, h / 2 - 34, 260, 52)
		_glass(r, Ui.RED)
		_text(r.position + Vector2(0, 22), "PRESS THROTTLE TO START", Ui.SIZE_HEADING, Ui.INK, true, HORIZONTAL_ALIGNMENT_CENTER, r.size.x)
		_text(r.position + Vector2(0, 38), "THROTTLE W  ·  BRAKE SPACE  ·  BOOST SHIFT  ·  R RESTART  ·  ESC PAUSE", Ui.SIZE_SMALL, Ui.INK_2, false, HORIZONTAL_ALIGNMENT_CENTER, r.size.x)
	elif message != "":
		# slides in, holds, fades
		var a := clampf(_message_left / 0.4, 0.0, 1.0)
		var slide := (1.0 - clampf(_message_age / 0.15, 0.0, 1.0)) * 20.0
		var mw := maxf(200.0, Ui.font_bold.get_string_size(message, HORIZONTAL_ALIGNMENT_LEFT, -1, Ui.SIZE_HEADING).x + 34.0)
		var r := Rect2(w / 2 - mw / 2 + slide, h * (0.33 if tut_title != "" else 0.24), mw, 22)
		draw_rect(r, Color(GLASS, GLASS.a * a))
		draw_rect(Rect2(r.position, Vector2(3, r.size.y)), Color(message_color, a))
		_text(r.position + Vector2(0, 16), message, Ui.SIZE_HEADING, Color(message_color, a), true, HORIZONTAL_ALIGNMENT_CENTER, r.size.x)


func _draw_tutorial(w: float) -> void:
	var pw := 300.0
	var r := Rect2(w / 2 - pw / 2, 38, pw, 60)
	_glass(r, Ui.YELLOW)
	_text(r.position + Vector2(8, 14), "ROOKIE TEST  ·  STEP %d / %d" % [tut_step + 1, tut_total], Ui.SIZE_SMALL, Ui.YELLOW, true)
	for i in tut_total:
		var c := Ui.YELLOW if i < tut_step else (Ui.INK if i == tut_step else Color(1, 1, 1, 0.15))
		draw_rect(Rect2(r.end.x - 8 - (tut_total - i) * 14, r.position.y + 7, 10, 4), c)
	_text(r.position + Vector2(8, 28), tut_title, Ui.SIZE_BODY, Ui.INK, true)
	draw_multiline_string(Ui.font, r.position + Vector2(8, 41), tut_text, HORIZONTAL_ALIGNMENT_LEFT, pw - 16, Ui.SIZE_SMALL, 2, Ui.INK_2)


func _draw_lights(w: float, _h: float) -> void:
	var gantry := PartCard.texture("res://assets/sprites/race/start_lights.png")
	var lamp := PartCard.texture("res://assets/sprites/race/start_light_on.png")
	if gantry and lamp:
		var pos := Vector2(w / 2 - 80, 40)
		draw_texture(gantry, pos)
		for k in mini(lights, 5):
			draw_texture(lamp, pos + Vector2(19 + k * 24, 5))
		return
	var r := Rect2(w / 2 - 92, 44, 184, 40)
	_glass(r)
	for k in 5:
		var c := r.position + Vector2(24 + k * 34, 20)
		draw_circle(c, 12.0, Color(0.05, 0.05, 0.06))
		draw_circle(c, 9.0, Color("ff2a1f") if k < lights else Color(0.18, 0.06, 0.06))
		if k < lights:
			draw_circle(c, 13.0, Color(1, 0.15, 0.1, 0.18))


func _draw_race_tower(_w: float) -> void:
	var rows := race_rows.size()
	var r := Rect2(8, 8, 150, 26 + rows * 12 + 22)
	_glass(r, Ui.RED)
	_text(Vector2(14, 21), "LAP %d / %d" % [clampi(race_lap, 1, race_laps), race_laps] if race_lap > 0 else "FORMATION", Ui.SIZE_BODY, Ui.INK, true)
	var y := 36.0
	for row: Dictionary in race_rows:
		var you: bool = row.get("you", false)
		if you:
			draw_rect(Rect2(9, y - 9, 148, 12), Color(Ui.RED, 0.25))
		draw_rect(Rect2(12, y - 8, 2, 10), row.get("color", Ui.INK))
		_text(Vector2(17, y), str(row.get("pos", 0)), Ui.SIZE_SMALL, Ui.INK_2, true)
		_text(Vector2(30, y), String(row.get("name", "")).to_upper(), Ui.SIZE_SMALL, Ui.INK if you else Ui.INK_2, you)
		_text(Vector2(100, y), "PIT" if row.get("pit", false) else String(row.get("gap", "")), Ui.SIZE_SMALL, Ui.YELLOW if row.get("pit", false) else Ui.INK_3, false, HORIZONTAL_ALIGNMENT_RIGHT, 52)
		y += 12.0
	# tyre
	var cols := [Ui.RED, Ui.YELLOW, Ui.INK]
	var names := ["SOFT", "MEDIUM", "HARD"]
	var ty := r.end.y - 9
	draw_circle(Vector2(18, ty - 3), 5.0, Color(0.06, 0.06, 0.07))
	draw_arc(Vector2(18, ty - 3), 4.0, 0, TAU, 16, cols[tyre_compound], 1.5)
	_text(Vector2(27, ty), names[tyre_compound], Ui.SIZE_SMALL, cols[tyre_compound], true)
	draw_rect(Rect2(76, ty - 7, 60, 5), Color(1, 1, 1, 0.08))
	var life := clampf(1.0 - tyre_wear, 0.0, 1.0)
	draw_rect(Rect2(76, ty - 7, 60 * life, 5), GREEN if life > 0.5 else (Ui.YELLOW if life > 0.3 else Ui.RED))
	_text(Vector2(138, ty), "%d%%" % roundi(life * 100), 6, Ui.INK_3)


func _draw_tower() -> void:
	var r := Rect2(8, 8, 156, 58)
	_glass(r, Ui.RED)
	_text(Vector2(14, 20), title, Ui.SIZE_SMALL, Ui.INK_2)
	_text(Vector2(14, 31), "OUT LAP" if lap == 0 else "LAP %d" % lap, Ui.SIZE_SMALL, Ui.INK, true)
	if not lap_valid and lap > 0:
		draw_rect(Rect2(104, 23, 54, 10), Ui.RED)
		_text(Vector2(104, 31), "DELETED", Ui.SIZE_SMALL, Ui.INK, true, HORIZONTAL_ALIGNMENT_CENTER, 54)
	var time_color := Ui.INK if lap_valid else Ui.INK_3
	_text(Vector2(14, 50), "-:--.---" if lap == 0 else Ui.format_time(lap_us / 1000), 18, time_color, true)
	_text(Vector2(14, 62), "BEST", Ui.SIZE_SMALL, Ui.INK_3)
	_text(Vector2(36, 62), Ui.format_time(best_us / 1000) if best_us > 0 else "-", Ui.SIZE_SMALL, PURPLE if best_us > 0 else Ui.INK_2, true)
	_text(Vector2(90, 62), "LAST", Ui.SIZE_SMALL, Ui.INK_3)
	_text(Vector2(112, 62), Ui.format_time(last_us / 1000) if last_us > 0 else "-", Ui.SIZE_SMALL, Ui.INK_2)
	# Sector strip
	for i in 3:
		var x := 8.0 + i * 52.0
		var sr := Rect2(x, 68, 50, 15)
		var has := i < sectors.size()
		var c := Color(0.12, 0.125, 0.14, 0.86)
		if has:
			c = Ui.YELLOW.darkened(0.25)
			if i < best_sectors.size() and sectors[i] <= best_sectors[i]:
				c = GREEN.darkened(0.25)
		draw_rect(sr, c)
		_text(sr.position + Vector2(0, 11), ("%.3f" % (sectors[i] / 1000000.0)) if has else "S%d" % (i + 1), Ui.SIZE_SMALL, Ui.INK if has else Ui.INK_3, has, HORIZONTAL_ALIGNMENT_CENTER, sr.size.x)


func _draw_delta(w: float) -> void:
	if not has_delta or lap == 0:
		return
	var ahead := delta_us <= 0
	var dc := GREEN if ahead else Ui.RED
	var r := Rect2(w / 2 - 44, 8, 88, 24)
	_glass(r)
	draw_rect(Rect2(r.position.x, r.end.y - 3, r.size.x, 3), dc)
	_text(r.position + Vector2(0, 17), "%s%.3f" % ["-" if ahead else "+", absi(delta_us) / 1000000.0], Ui.SIZE_HEADING, dc, true, HORIZONTAL_ALIGNMENT_CENTER, r.size.x)


## A round speedometer: speed needle on a 0-360 km/h dial, rev lights on the
## inner ring, gear in the middle, battery and Boost / Straight Mode beside it.
func _draw_dash(_w: float, h: float) -> void:
	var c := Vector2(76, h - 70)
	var r := 56.0
	var a0 := deg_to_rad(135.0)
	var sweep := deg_to_rad(270.0)
	draw_circle(c, r + 6, Color(0.05, 0.055, 0.065, 0.9))
	draw_arc(c, r + 6, 0, TAU, 64, GLASS_LINE, 1.0)
	# speed scale
	for k in 19:
		var t := k / 18.0
		var ang := a0 + sweep * t
		var major := k % 3 == 0
		var dir := Vector2.from_angle(ang)
		draw_line(c + dir * (r - (7.0 if major else 4.0)), c + dir * r, Ui.INK_2 if major else Ui.INK_3, 1.5 if major else 1.0)
		if major:
			var label := str(k * 20)
			var lp := c + dir * (r - 15.0)
			_text(lp + Vector2(-10, 3), label, 6, Ui.INK_3, false, HORIZONTAL_ALIGNMENT_CENTER, 20)
	# redline zone of the speed dial
	draw_arc(c, r - 1.5, a0 + sweep * (300.0 / 360.0), a0 + sweep, 12, Color(Ui.RED, 0.7), 2.0)
	# rev lights on an inner ring
	var leds := 15
	var lit := clampi(roundi(clampf((rpm - 6500.0) / 4800.0, 0.0, 1.0) * leds), 0, leds)
	var flash_all := rpm > 11200.0 and fmod(Time.get_ticks_msec() / 1000.0, 0.12) < 0.06
	var ra := deg_to_rad(205.0)
	var rsweep := deg_to_rad(130.0)
	for i in leds:
		var col := GREEN if i < 5 else (Ui.RED if i < 10 else SM_COLOR)
		var on := i < lit or flash_all
		var t0 := ra + rsweep * i / leds
		draw_arc(c, r - 24.0, t0, t0 + rsweep / leds * 0.75, 3, col if on else Color(col, 0.12), 3.0)
	# needle
	var speed_t := clampf(speed_kmh / 360.0, 0.0, 1.0)
	var na := a0 + sweep * speed_t
	draw_line(c, c + Vector2.from_angle(na) * (r - 3.0), Ui.RED, 2.0)
	draw_line(c - Vector2.from_angle(na) * 8.0, c, Ui.RED, 2.0)
	draw_circle(c, 9.0, Color(0.09, 0.095, 0.11))
	draw_arc(c, 9.0, 0, TAU, 24, Color(1, 1, 1, 0.15), 1.0)
	_text(c + Vector2(-12, 6), "N" if speed_kmh < 2 else str(gear), Ui.SIZE_HEADING, Ui.YELLOW, true, HORIZONTAL_ALIGNMENT_CENTER, 24)
	# digital speed under the hub
	_text(c + Vector2(-30, 32), str(speed_kmh), Ui.SIZE_HEADING, Ui.INK, true, HORIZONTAL_ALIGNMENT_CENTER, 60)
	_text(c + Vector2(-30, 41), "KM/H", 6, Ui.INK_3, false, HORIZONTAL_ALIGNMENT_CENTER, 60)
	# pedals left of the dial
	var px := c.x - r - 16
	var ph := r * 1.4
	var py := c.y - ph / 2
	draw_rect(Rect2(px, py, 4, ph), Color(1, 1, 1, 0.06))
	draw_rect(Rect2(px, py + ph * (1.0 - brake / 255.0), 4, ph * brake / 255.0), Ui.RED)
	draw_rect(Rect2(px - 6, py, 4, ph), Color(1, 1, 1, 0.06))
	draw_rect(Rect2(px - 6, py + ph * (1.0 - throttle / 255.0), 4, ph * throttle / 255.0), GREEN)
	# battery and the two lamps right of the dial
	var bx := c.x + r + 12
	var bh := r * 1.3
	var by := c.y - bh / 2 - 6
	draw_rect(Rect2(bx, by, 9, bh), Color(1, 1, 1, 0.06))
	draw_rect(Rect2(bx, by + bh * (1.0 - battery), 9, bh * battery), SM_COLOR if boosting else Ui.YELLOW)
	draw_rect(Rect2(bx, by, 9, bh), GLASS_LINE, false, 1.0)
	_text(Vector2(bx - 6, by + bh + 9), "BATT", 6, Ui.INK_3, false, HORIZONTAL_ALIGNMENT_CENTER, 21)
	var lamp := func(pos: Vector2, label: String, on: bool, dim: bool) -> void:
		draw_rect(Rect2(pos, Vector2(22, 10)), SM_COLOR if on else (Color(SM_COLOR, 0.25) if dim else Color(1, 1, 1, 0.06)))
		_text(pos + Vector2(0, 8), label, 6, Ui.BG if on else Ui.INK_3, true, HORIZONTAL_ALIGNMENT_CENTER, 22)
	lamp.call(Vector2(bx + 14, by + 8), "BST", boosting, false)
	lamp.call(Vector2(bx + 14, by + 22), "SM", straight_mode, straight_zone)


func _draw_map(w: float, h: float) -> void:
	if map_points.size() < 2:
		return
	var origin := Vector2(w - _map_rect.size.x - 16, h - _map_rect.size.y - 16)
	_glass(Rect2(origin - Vector2(8, 8), _map_rect.size + Vector2(16, 16)))
	var xf := Transform2D(0.0, origin) * _map_xf
	var line := xf * map_points
	line.append(line[0])
	draw_polyline(line, Color(1, 1, 1, 0.12), 4.0)
	draw_polyline(line, Ui.INK_2, 1.5)
	draw_rect(Rect2(xf * map_points[0] - Vector2(1.5, 3), Vector2(3, 6)), Ui.INK)
	if map_ghost.x > -1.0:
		draw_circle(xf * map_ghost, 2.5, Color(1, 1, 1, 0.55))
	for o: Dictionary in map_others:
		draw_circle(xf * (o["p"] as Vector2), 2.2, o["c"])
	draw_circle(xf * map_car, 3.5, Ui.BG)
	draw_circle(xf * map_car, 2.5, Ui.RED)
	_text(origin + Vector2(-6, -12), device, Ui.SIZE_SMALL, Ui.INK_3)
