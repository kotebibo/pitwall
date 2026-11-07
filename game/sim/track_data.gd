class_name TrackData
extends RefCounted
## A circuit as the physics sees it: a closed centreline of points about 4 m
## apart, written as fixed-point integers by tools/make_track.py.

const FLAG_KERB_RIGHT := 1
const FLAG_KERB_LEFT := 2
const FLAG_STRAIGHT_MODE := 4

var id := ""
var name := ""
var length_m := 0
var half_width := 0
var runoff := 0
var sectors: Array[int] = []
var spawn_index := 0
var spawn_speed := 0
var x := PackedInt64Array()
var y := PackedInt64Array()
var dir_x := PackedInt64Array()
var dir_y := PackedInt64Array()
var seg_len := PackedInt64Array()
var flags := PackedByteArray()
## Presentation only (never read by the physics): racing line offset (cm),
## its speed profile (km/h), and braking boards [point, metres, side].
var line_cm := PackedInt32Array()
var line_kmh := PackedInt32Array()
var boards: Array = []
## Pit lane alongside the main straight, on the inside (negative lateral side).
var pit_in := 0  # first point of the pit zone (before the line)
var pit_out := 0  # last point of the pit zone (after the line)
var pit_inner := 0  # lateral distance where the lane starts (fixed point)
var pit_outer := 0
var pit_center := 0
var pit_box0 := 0  # point of the first team box
const PIT_BOX_GAP := 4  # points between boxes (16 m)
## Distance from the start line to each point, fixed point.
var dist := PackedInt64Array()
var total_len := 0


static func load_id(track_id: String) -> TrackData:
	var file := FileAccess.open("res://tracks/%s.json" % track_id, FileAccess.READ)
	if file == null:
		push_error("missing track " + track_id)
		return null
	var raw: Dictionary = JSON.parse_string(file.get_as_text())
	var t := TrackData.new()
	t.id = raw["id"]
	t.name = raw["name"]
	t.length_m = int(raw["length_m"])
	t.half_width = int(raw["half_width"])
	t.runoff = int(raw["runoff"])
	for s: float in raw["sectors"]:
		t.sectors.append(int(s))
	t.spawn_index = int(raw["spawn_index"])
	t.spawn_speed = int(raw["spawn_speed"])
	var xs: Array = raw["x"]
	var ys: Array = raw["y"]
	var dirs: Array = raw["dir"]
	var lens: Array = raw["len"]
	var fl: Array = raw["flags"]
	var n := xs.size()
	t.x.resize(n)
	t.y.resize(n)
	t.dir_x.resize(n)
	t.dir_y.resize(n)
	t.seg_len.resize(n)
	t.flags.resize(n)
	t.dist.resize(n)
	var acc := 0
	for i in n:
		t.x[i] = int(xs[i])
		t.y[i] = int(ys[i])
		t.dir_x[i] = int(dirs[2 * i])
		t.dir_y[i] = int(dirs[2 * i + 1])
		t.seg_len[i] = int(lens[i])
		t.flags[i] = int(fl[i])
		t.dist[i] = acc
		acc += t.seg_len[i]
	t.total_len = acc
	for v: float in raw.get("line_cm", []):
		t.line_cm.append(int(v))
	for v: float in raw.get("line_kmh", []):
		t.line_kmh.append(int(v))
	t.boards = raw.get("boards", [])
	t.pit_in = n - 36
	t.pit_out = 28
	t.pit_inner = t.half_width + 3 * 65536
	t.pit_outer = t.half_width + 10 * 65536
	t.pit_center = -(t.half_width + 13 * 32768)
	t.pit_box0 = n - 18
	return t


func in_pit_zone(i: int) -> bool:
	return i >= pit_in or i <= pit_out


func pit_box(slot: int) -> int:
	return (pit_box0 + slot * PIT_BOX_GAP) % x.size()


func size() -> int:
	return x.size()


## Where a point is relative to the centreline, starting the search at `hint`.
## Returns [segment index, distance along the segment, lateral offset (+ = right)].
func project(px: int, py: int, hint: int) -> Array[int]:
	var n := x.size()
	var i := hint
	var moved := 0  # -1 stepped back, +1 stepped forward
	for _step in 64:
		var rx := px - x[i]
		var ry := py - y[i]
		var along := (rx * dir_x[i] + ry * dir_y[i]) >> 16
		# On the outside of a corner a point can sit between two segments;
		# stepping back and forth means it is at the joint.
		if along < 0 and moved != 1:
			i = (i - 1 + n) % n
			moved = -1
			continue
		if along > seg_len[i] and moved != -1:
			i = (i + 1) % n
			moved = 1
			continue
		along = clampi(along, 0, seg_len[i])
		var lateral := (ry * dir_x[i] - rx * dir_y[i]) >> 16
		return [i, along, lateral]
	# Far from where we looked (only after a reset): scan for the nearest point.
	var best := 0
	var best_d := 1 << 62
	for j in n:
		var dx := (px - x[j]) >> 8
		var dy := (py - y[j]) >> 8
		var d := dx * dx + dy * dy
		if d < best_d:
			best_d = d
			best = j
	var bx := px - x[best]
	var by := py - y[best]
	return [best, clampi((bx * dir_x[best] + by * dir_y[best]) >> 16, 0, seg_len[best]), (by * dir_x[best] - bx * dir_y[best]) >> 16]
