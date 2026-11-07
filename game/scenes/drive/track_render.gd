class_name TrackRender
extends Node2D
## Draws a circuit, in metres: grass, run-off and gravel, asphalt with a
## rubbered-in racing line, kerbs, white lines, barriers, the start line and grid,
## then places grandstands, trees, billboards and braking boards around it.
## Uses the sprites in assets/sprites/track and deco when they exist, flat colours otherwise.

const TRACK_TEX := "res://assets/sprites/track/%s.png"
const DECO_TEX := "res://assets/sprites/deco/%s.png"
const DECO_M_PER_PX := 0.25
const KERB_WIDTH := 1.4
const BARRIER_WIDTH := 1.3

const GRASS := Color("2b4a2e")
const RUNOFF := Color("3a4448")
const GRAVEL := Color("8a7d63")
const ASPHALT := Color("34363c")
const EDGE := Color("e9e6df")
const WALL := Color("6e6f78")

var track: TrackData
var points := PackedVector2Array()
var normals := PackedVector2Array()  # right-hand normal at each point
var dist := PackedFloat32Array()  # metres from the start line
var line := PackedVector2Array()  # racing line
var line_kmh := PackedInt32Array()
var corner := PackedByteArray()  # 1 where the centreline curves enough to need gravel/tyres
var bounds := Rect2()
var _hw := 0.0
var _wall := 0.0
var _decor: Node2D
## Draw commands only hold texture RIDs, so the textures must stay referenced here.
static var _keep := {}


func setup(t: TrackData) -> void:
	track = t
	texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
	var n := t.size()
	points.resize(n)
	normals.resize(n)
	dist.resize(n)
	corner.resize(n)
	_hw = t.half_width / 65536.0
	_wall = _hw + t.runoff / 65536.0
	for i in n:
		points[i] = Vector2(t.x[i], t.y[i]) / 65536.0
		dist[i] = t.dist[i] / 65536.0
	for i in n:
		var d0 := Vector2(t.dir_x[(i - 1 + n) % n], t.dir_y[(i - 1 + n) % n]) / 65536.0
		var d1 := Vector2(t.dir_x[i], t.dir_y[i]) / 65536.0
		var d := (d0 + d1).normalized()
		normals[i] = Vector2(-d.y, d.x)
	for i in n:
		var a := Vector2(t.dir_x[(i - 3 + n) % n], t.dir_y[(i - 3 + n) % n])
		var b := Vector2(t.dir_x[(i + 3) % n], t.dir_y[(i + 3) % n])
		corner[i] = 1 if absf(a.angle_to(b)) > 0.09 else 0
	# widen corner zones so gravel/tyres run a little before and after
	var wide := corner.duplicate()
	for i in n:
		if corner[i] == 1:
			for k in range(-10, 14):
				wide[(i + k + n) % n] = 1
	corner = wide
	line.resize(n)
	line_kmh.resize(n)
	for i in n:
		var off: float = t.line_cm[i] / 100.0 if t.line_cm.size() == n else 0.0
		line[i] = points[i] + normals[i] * off
		line_kmh[i] = t.line_kmh[i] if t.line_kmh.size() == n else 0
	bounds = Rect2(points[0], Vector2.ZERO)
	for p in points:
		bounds = bounds.expand(p)
	bounds = bounds.grow(220.0)
	_place_decor()
	queue_redraw()


static func tex(name: String) -> Texture2D:
	return _cached(TRACK_TEX % name)


static func deco_tex(name: String) -> Texture2D:
	return _cached(DECO_TEX % name)


static func _cached(path: String) -> Texture2D:
	if not _keep.has(path):
		_keep[path] = load(path) if ResourceLoader.exists(path) else null
	return _keep[path]


## A strip between two offsets from the centreline over the points where keep(i) is true.
## uv "world": texture tiles in world space every `tile` metres; "along": u runs along the track every `tile` metres.
func _strip(a: float, b: float, color: Color, texture: Texture2D, uv_mode: String, tile: float, keep: Callable = Callable(), offsets := PackedFloat32Array()) -> void:
	var n := points.size()
	var verts := PackedVector2Array()
	var uvs := PackedVector2Array()
	var idx := PackedInt32Array()
	for i in n:
		if keep.is_valid() and not keep.call(i):
			continue
		var j := (i + 1) % n
		var base := verts.size()
		var oi := offsets[i] if offsets.size() == n else 0.0
		var oj := offsets[j] if offsets.size() == n else 0.0
		var quad := [
			points[i] + normals[i] * (a + oi), points[j] + normals[j] * (a + oj),
			points[j] + normals[j] * (b + oj), points[i] + normals[i] * (b + oi),
		]
		var dj := dist[j] if j != 0 else float(track.total_len) / 65536.0
		for k in 4:
			var p: Vector2 = quad[k]
			verts.append(p)
			if uv_mode == "along":
				var u := (dist[i] if k == 0 or k == 3 else dj) / tile
				uvs.append(Vector2(u, 0.0 if k < 2 else 1.0))
			else:
				uvs.append(p / tile)
		idx.append_array([base, base + 1, base + 2, base, base + 2, base + 3])
	if verts.is_empty():
		return
	var colors := PackedColorArray()
	colors.resize(verts.size())
	colors.fill(color if texture == null else Color(1, 1, 1, color.a))
	RenderingServer.canvas_item_add_triangle_array(get_canvas_item(), idx, verts, colors, uvs, PackedInt32Array(), PackedFloat32Array(), texture.get_rid() if texture else RID())


func _draw() -> void:
	if track == null:
		return
	var n := points.size()
	# Ground
	var grass := tex("grass")
	var corners := PackedVector2Array([bounds.position, Vector2(bounds.end.x, bounds.position.y), bounds.end, Vector2(bounds.position.x, bounds.end.y)])
	var uv := PackedVector2Array()
	for c in corners:
		uv.append(c / 32.0)
	if grass:
		draw_polygon(corners, PackedColorArray([Color.WHITE]), uv, grass)
	else:
		draw_colored_polygon(corners, GRASS)
	# Run-off: gravel on the outside of corners, painted tarmac elsewhere
	var gravel := tex("gravel")
	var runoff := tex("runoff")
	var outside_right := func(i: int) -> bool: return corner[i] == 1 and _turn(i) < 0.0
	var outside_left := func(i: int) -> bool: return corner[i] == 1 and _turn(i) > 0.0
	_strip(_hw, _wall + 2.0, RUNOFF, runoff, "world", 16.0, func(i: int) -> bool: return not outside_right.call(i))
	_strip(-_wall - 2.0, -_hw, RUNOFF, runoff, "world", 16.0, func(i: int) -> bool: return not outside_left.call(i))
	_strip(_hw + 2.5, _wall + 2.0, GRAVEL, gravel, "world", 16.0, outside_right)
	_strip(-_wall - 2.0, -_hw - 2.5, GRAVEL, gravel, "world", 16.0, outside_left)
	_strip(_hw, _hw + 2.5, RUNOFF, runoff, "world", 16.0, outside_right)
	_strip(-_hw - 2.5, -_hw, RUNOFF, runoff, "world", 16.0, outside_left)
	# Asphalt and the rubbered-in line (real tracks show it; it is not an aid)
	_strip(-_hw, _hw, ASPHALT, tex("asphalt"), "world", 32.0)
	var line_off := PackedFloat32Array()
	line_off.resize(n)
	for i in n:
		line_off[i] = (line[i] - points[i]).dot(normals[i])
	_strip(-1.1, 1.1, Color(0, 0, 0, 0.16), null, "world", 1.0, Callable(), line_off)
	# Kerbs
	var kerb := tex("kerb")
	_strip(_hw - 0.2, _hw + KERB_WIDTH, Ui.RED, kerb, "along", 8.0, func(i: int) -> bool: return (track.flags[i] & 3) != 0)
	_strip(-_hw - KERB_WIDTH, -_hw + 0.2, Ui.RED, kerb, "along", 8.0, func(i: int) -> bool: return (track.flags[i] & 3) != 0)
	# White lines
	_strip(_hw - 0.45, _hw - 0.15, EDGE, null, "world", 1.0, func(i: int) -> bool: return (track.flags[i] & 3) == 0)
	_strip(-_hw + 0.15, -_hw + 0.45, EDGE, null, "world", 1.0, func(i: int) -> bool: return (track.flags[i] & 3) == 0)
	# Barriers: tyre walls in corners, steel elsewhere
	var tyres := tex("tyre_wall")
	var steel := tex("armco")
	for side: float in [-1.0, 1.0]:
		var a := side * (_wall + 0.2)
		var b := side * (_wall + 0.2 + BARRIER_WIDTH)
		_strip(minf(a, b), maxf(a, b), Color("1b1c20"), tyres, "along", 6.0, func(i: int) -> bool: return corner[i] == 1)
		_strip(minf(a, b), maxf(a, b), WALL, steel, "along", 4.0, func(i: int) -> bool: return corner[i] == 0)
	_pit_lane()
	# Straight Mode zones: a thin blue line along the inside edge
	_strip(-_hw + 0.6, -_hw + 0.9, Color("5ec8e5"), null, "world", 1.0, func(i: int) -> bool: return (track.flags[i] & TrackData.FLAG_STRAIGHT_MODE) != 0 and i % 3 != 0)
	_start_line()


## Pit lane on the inside of the main straight: lane, lines, team boxes, limiter boards.
func _pit_lane() -> void:
	var t := track
	var hw := _hw
	var inner := t.pit_inner / 65536.0
	var outer := t.pit_outer / 65536.0
	var zone := func(i: int) -> bool: return t.in_pit_zone(i)
	var lane_body := func(i: int) -> bool: return t.in_pit_zone(i) and t.in_pit_zone((i + 6) % points.size()) and t.in_pit_zone((i - 6 + points.size()) % points.size())
	_strip(-outer - 0.5, -hw, Color(0.17, 0.18, 0.2, 1.0), tex("asphalt"), "world", 32.0, zone)
	_strip(-outer - 0.5, -hw, Color(0, 0, 0, 0.22), null, "world", 1.0, zone)
	# lane edge lines and the pit wall line between track and lane
	_strip(-outer - 0.5, -outer - 0.2, EDGE, null, "world", 1.0, lane_body)
	_strip(-inner + 0.1, -inner + 0.4, Color(EDGE, 0.85), null, "world", 1.0, func(i: int) -> bool: return lane_body.call(i) and i % 2 == 0)
	_strip(-hw - 2.6, -hw - 1.4, Color("2a2c31"), tex("armco"), "along", 4.0, func(i: int) -> bool: return lane_body.call(i) and t.in_pit_zone((i + 10) % points.size()) and t.in_pit_zone((i - 10 + points.size()) % points.size()))
	# entry and exit lines
	for i: int in [t.pit_in, t.pit_out]:
		var a := points[i] + normals[i] * -hw
		var b := points[i] + normals[i] * -outer
		draw_line(a, b, EDGE, 0.4)
	# team boxes
	for slot in 6:
		var i := t.pit_box(slot)
		var c := points[i] + normals[i] * (t.pit_center / 65536.0)
		var d := Vector2(t.dir_x[i], t.dir_y[i]) / 65536.0
		var nrm := normals[i]
		var col := Ui.RED if slot == 0 else Color(1, 1, 1, 0.55)
		var corners := PackedVector2Array([c - d * 3.2 - nrm * 1.9, c + d * 3.2 - nrm * 1.9, c + d * 3.2 + nrm * 1.9, c - d * 3.2 + nrm * 1.9])
		draw_colored_polygon(corners, Color(col, 0.18))
		corners.append(corners[0])
		draw_polyline(corners, col, 0.25)


func _turn(i: int) -> float:
	var n := points.size()
	var a := Vector2(track.dir_x[(i - 6 + n) % n], track.dir_y[(i - 6 + n) % n])
	var b := Vector2(track.dir_x[(i + 6) % n], track.dir_y[(i + 6) % n])
	return a.angle_to(b)  # > 0 turning right (screen), < 0 turning left


func _start_line() -> void:
	var p0 := points[0]
	var dir := Vector2(track.dir_x[0], track.dir_y[0]) / 65536.0
	var nrm := normals[0]
	var cells := int(_hw * 2.0)
	for k in cells:
		for row in 2:
			var c := Color.WHITE if (k + row) % 2 == 0 else Color("101114")
			var base := p0 + nrm * (-_hw + k) + dir * (row - 1.0)
			draw_colored_polygon(PackedVector2Array([base, base + nrm, base + nrm + dir, base + dir]), c)
	# Grid boxes behind the line, staggered like a real grid
	for slot in 10:
		var back := 16.0 + slot * 8.0
		var side := -1.0 if slot % 2 == 0 else 1.0
		var c := p0 - dir * back + nrm * side * 3.2
		var w := 2.4
		draw_line(c + nrm * -w / 2, c + nrm * w / 2, Color(1, 1, 1, 0.75), 0.25)
		draw_line(c + nrm * -w / 2, c + nrm * -w / 2 - dir * 1.2, Color(1, 1, 1, 0.75), 0.25)
		draw_line(c + nrm * w / 2, c + nrm * w / 2 - dir * 1.2, Color(1, 1, 1, 0.75), 0.25)


# ---- decorations ----

func _sprite(name: String, pos: Vector2, rot: float, z: int = 0) -> Sprite2D:
	var t := deco_tex(name)
	if t == null:
		return null
	var shadow := deco_tex(name + "_shadow")
	if shadow:
		var sh := Sprite2D.new()
		sh.texture = shadow
		sh.position = pos
		sh.rotation = rot
		sh.scale = Vector2(DECO_M_PER_PX, DECO_M_PER_PX)
		sh.z_index = z - 1
		_decor.add_child(sh)
	var s := Sprite2D.new()
	s.texture = t
	s.position = pos
	s.rotation = rot
	s.scale = Vector2(DECO_M_PER_PX, DECO_M_PER_PX)
	s.z_index = z
	_decor.add_child(s)
	return s


func _place_decor() -> void:
	if _decor:
		_decor.queue_free()
	_decor = Node2D.new()
	_decor.z_index = 1
	add_child(_decor)
	var n := points.size()
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(track.id)
	var dir_at := func(i: int) -> Vector2: return Vector2(track.dir_x[i], track.dir_y[i]) / 65536.0
	var behind := _wall + BARRIER_WIDTH + 1.5

	# Braking boards on the outside of big stops
	for b: Array in track.boards:
		var i: int = b[0]
		var side: float = b[2]
		var name := "brake_board_%d" % int(b[1])
		_sprite(name, points[i] + normals[i] * side * (_hw + 3.5), (dir_at.call(i) as Vector2).angle() + PI / 2 * side, 2)

	# Main straight: grandstands outside, pit building and paddock inside
	var straight_end := 0
	while straight_end < n and corner[straight_end] == 0:
		straight_end += 1
	var straight_start := n - 1
	while straight_start > 0 and corner[straight_start] == 0:
		straight_start -= 1
	var mid := ((straight_start + straight_end + n) / 2) % n
	var main_rot: float = (dir_at.call(mid) as Vector2).angle()
	for k in range(-2, 3):
		var i := (mid + k * 12 + n) % n
		_sprite("grandstand_long", points[i] + normals[i] * (behind + 7.0), main_rot, 1)
	_sprite("pit_building", points[mid] - normals[mid] * (behind + 14.0), main_rot + PI, 1)
	for k in 4:
		var i := (mid + (k - 2) * 15 + n) % n
		_sprite("tent_%d" % (1 + k % 2), points[i] - normals[i] * (behind + 34.0 + rng.randf_range(0, 6)), main_rot, 1)

	# Start lights gantry across the track at the line
	_sprite("gantry", points[0] + Vector2(track.dir_x[0], track.dir_y[0]) / 65536.0 * 6.0, (dir_at.call(0) as Vector2).angle() + PI / 2, 6)

	# Short grandstands on the outside of the biggest braking zones
	for b: Array in track.boards:
		if int(b[1]) != 50:
			continue
		var i := (int(b[0]) + 12) % n
		var side: float = b[2]
		_sprite("grandstand_short", points[i] + normals[i] * side * (behind + 6.0), (dir_at.call(i) as Vector2).angle() + (0.0 if side > 0 else PI), 1)

	# Billboards along the straights, marshal posts every ~250 m
	var next_board := 0.0
	var next_post := 120.0
	for i in n:
		if corner[i] == 0 and dist[i] > next_board:
			var side := 1.0 if (i / 40) % 2 == 0 else -1.0
			_sprite("billboard_%d" % (1 + (i / 30) % 4), points[i] + normals[i] * side * (behind + 0.6), (dir_at.call(i) as Vector2).angle() + (0.0 if side > 0 else PI), 2)
			next_board = dist[i] + 90.0
		if dist[i] > next_post:
			var side := -1.0 if (i / 50) % 2 == 0 else 1.0
			_sprite("marshal_post", points[i] + normals[i] * side * (behind + 2.0), (dir_at.call(i) as Vector2).angle(), 2)
			next_post = dist[i] + 250.0

	# Trees and bushes in woods around the circuit (only where the camera can see them)
	var trees: Array[String] = ["tree_1", "tree_2", "tree_3", "tree_4", "tree_5", "bush_1", "bush_2", "bush_3"]
	var near := _distance_grid(behind + 9.0, behind + 110.0)
	var spacing := 11.0
	var y := bounds.position.y
	while y < bounds.end.y:
		var x := bounds.position.x
		while x < bounds.end.x:
			var p := Vector2(x + rng.randf_range(-5, 5), y + rng.randf_range(-5, 5))
			var density := 0.5 + 0.5 * sin(p.x * 0.011 + 1.3) * sin(p.y * 0.013 + 0.7)
			if _grid_at(near, p) == 1 and rng.randf() < density * 0.7:
				_sprite(trees[rng.randi() % trees.size()], p, 0.0, 3)
			x += spacing
		y += spacing


const GRID_CELL := 8.0

## Marks grid cells: 2 = too close to the track, 1 = within `far` metres, 0 = beyond.
func _distance_grid(clear: float, far: float) -> Dictionary:
	var cells := {}
	for pass_ in 2:
		var r := far if pass_ == 0 else clear
		var mark := 1 if pass_ == 0 else 2
		var cr := int(ceil(r / GRID_CELL))
		for i in range(0, points.size(), 2):
			var c := Vector2i(floori(points[i].x / GRID_CELL), floori(points[i].y / GRID_CELL))
			for dy in range(-cr, cr + 1):
				for dx in range(-cr, cr + 1):
					if dx * dx + dy * dy <= cr * cr:
						var k := c + Vector2i(dx, dy)
						if mark == 2 or not cells.has(k):
							cells[k] = mark
	return cells


func _grid_at(cells: Dictionary, p: Vector2) -> int:
	return cells.get(Vector2i(floori(p.x / GRID_CELL), floori(p.y / GRID_CELL)), 0)
