extends RefCounted
## Flat-shaded mesh builder for the procedural 3D car (car_model.gd).
## Triangles are grouped by material key and every face keeps its own normal, so
## shapes read as faceted low-poly under the toon shader. Each face is turned to
## point along an "outward" hint, so callers never have to think about winding.

## Applied to every point added (part pivots, left/right mirroring).
var xf := Transform3D.IDENTITY
var triangles := 0
var _surfs := {}


class Surf:
	var v := PackedVector3Array()
	var n := PackedVector3Array()

	func add(a: Vector3, b: Vector3, c: Vector3, nn: Vector3) -> void:
		v.append(a)
		v.append(b)
		v.append(c)
		n.append(nn)
		n.append(nn)
		n.append(nn)


func _surf(m: String) -> Surf:
	if not _surfs.has(m):
		_surfs[m] = Surf.new()
	return _surfs[m]


func is_empty() -> bool:
	return _surfs.is_empty()


## One triangle, turned so its normal points along `out` (local space).
func tri(m: String, a: Vector3, b: Vector3, c: Vector3, out: Vector3) -> void:
	var pa := xf * a
	var pb := xf * b
	var pc := xf * c
	var n := (pb - pa).cross(pc - pa)
	if n.length_squared() < 1e-14:
		return
	n = n.normalized()
	if n.dot(xf.basis * out) < 0.0:
		n = -n
		var t := pb
		pb = pc
		pc = t
	# a, b, c is now counter-clockwise seen from outside; Godot's front faces are clockwise.
	_surf(m).add(pa, pc, pb, n)
	triangles += 1


func quad(m: String, a: Vector3, b: Vector3, c: Vector3, d: Vector3, out: Vector3) -> void:
	tri(m, a, b, c, out)
	tri(m, a, c, d, out)


## A quad facing away from `inside`.
func quad_in(m: String, a: Vector3, b: Vector3, c: Vector3, d: Vector3, inside: Vector3) -> void:
	var out := (a + b + c + d) * 0.25 - inside
	tri(m, a, b, c, out)
	tri(m, a, c, d, out)


static func centroid(r: PackedVector3Array) -> Vector3:
	var c := Vector3.ZERO
	for p in r:
		c += p
	return c / maxf(1.0, r.size())


## Stitches closed rings (same point count) into a tube and caps the ends.
## `mat` is a material key, or a Callable(segment: int, side: int) -> String.
func loft(rings: Array[PackedVector3Array], mat: Variant, cap_a: String = "", cap_b: String = "") -> void:
	var n := rings[0].size()
	var cs: Array[Vector3] = []
	for r in rings:
		cs.append(centroid(r))
	for i in rings.size() - 1:
		var r0 := rings[i]
		var r1 := rings[i + 1]
		var inside := (cs[i] + cs[i + 1]) * 0.5
		for j in n:
			var j2 := (j + 1) % n
			var m: String = mat if mat is String else String((mat as Callable).call(i, j))
			quad_in(m, r0[j], r0[j2], r1[j2], r1[j], inside)
	if cap_a != "":
		_cap(cap_a, rings[0], cs[0] - cs[1])
	if cap_b != "":
		_cap(cap_b, rings[rings.size() - 1], cs[cs.size() - 1] - cs[cs.size() - 2])


## Fan-fills a ring, facing `out`.
func cap(m: String, r: PackedVector3Array, out: Vector3) -> void:
	_cap(m, r, out)


## Quads between two rings with the same point count, all facing `out`
## (lips, frames around openings).
func bridge(m: String, r0: PackedVector3Array, r1: PackedVector3Array, out: Vector3) -> void:
	for j in r0.size():
		var j2 := (j + 1) % r0.size()
		quad(m, r0[j], r0[j2], r1[j2], r1[j], out)


## A grid of quads through rows of points (same count per row), facing `out`.
func patch(m: String, rows: Array[PackedVector3Array], out: Vector3) -> void:
	for i in rows.size() - 1:
		for j in rows[i].size() - 1:
			quad(m, rows[i][j], rows[i][j + 1], rows[i + 1][j + 1], rows[i + 1][j], out)


func _cap(m: String, r: PackedVector3Array, out: Vector3) -> void:
	var c := centroid(r)
	for j in r.size():
		tri(m, c, r[j], r[(j + 1) % r.size()], out)


func box(m: String, center: Vector3, size: Vector3, basis: Basis = Basis.IDENTITY) -> void:
	var h := size * 0.5
	var c: Array[Vector3] = []
	for i in 8:
		var p := Vector3(h.x if i & 1 else -h.x, h.y if i & 2 else -h.y, h.z if i & 4 else -h.z)
		c.append(center + basis * p)
	for f: Array in [[0, 2, 6, 4], [1, 3, 7, 5], [0, 1, 5, 4], [2, 3, 7, 6], [0, 1, 3, 2], [4, 5, 7, 6]]:
		quad_in(m, c[f[0]], c[f[1]], c[f[2]], c[f[3]], center)


## A box stretched from a to b: w across (horizontal), h up.
func rod(m: String, a: Vector3, b: Vector3, w: float, h: float, up: Vector3 = Vector3.UP) -> void:
	var d := b - a
	var length := d.length()
	if length < 1e-5:
		return
	var x := d / length
	if absf(x.dot(up)) > 0.98:
		up = Vector3.FORWARD
	var z := x.cross(up).normalized()
	var y := z.cross(x).normalized()
	box(m, (a + b) * 0.5, Vector3(length, h, w), Basis(x, y, z))


static func _perp(axis: Vector3) -> Array[Vector3]:
	var ref := Vector3.UP if absf(axis.dot(Vector3.UP)) < 0.9 else Vector3.RIGHT
	var u := axis.cross(ref).normalized()
	var v := axis.cross(u).normalized()
	return [u, v]


static func circle(center: Vector3, axis: Vector3, r: float, segs: int, phase: float = 0.0) -> PackedVector3Array:
	var uv := _perp(axis.normalized())
	var out := PackedVector3Array()
	for i in segs:
		var a := TAU * (float(i) + phase) / segs
		out.append(center + (uv[0] * cos(a) + uv[1] * sin(a)) * r)
	return out


## A cylinder from a to b.
func cyl(m: String, a: Vector3, b: Vector3, r: float, segs: int = 8, cap_m: String = "") -> void:
	var axis := (b - a).normalized()
	var rings: Array[PackedVector3Array] = [circle(a, axis, r, segs, 0.5), circle(b, axis, r, segs, 0.5)]
	var cap := m if cap_m == "" else cap_m
	loft(rings, m, cap, cap)


## Flat disc facing `normal`.
func disc(m: String, center: Vector3, normal: Vector3, r: float, segs: int = 12) -> void:
	_cap(m, circle(center, normal, r, segs, 0.5), normal)


## Flat ring facing `normal`.
func annulus(m: String, center: Vector3, normal: Vector3, r0: float, r1: float, segs: int = 12) -> void:
	var a := circle(center, normal, r0, segs, 0.5)
	var b := circle(center, normal, r1, segs, 0.5)
	for j in segs:
		var j2 := (j + 1) % segs
		quad(m, a[j], a[j2], b[j2], b[j], normal)


## Surface of revolution around `axis` through `center`. Profile points are
## (radius, offset along the axis); `mats[k]` paints the band from point k to k+1.
func revolve(mats: Array[String], center: Vector3, axis: Vector3, profile: PackedVector2Array, segs: int) -> void:
	axis = axis.normalized()
	var uv := _perp(axis)
	var pc := Vector2.ZERO
	for p in profile:
		pc += p
	pc /= profile.size()
	for i in segs:
		var a0 := TAU * (float(i) + 0.5) / segs
		var a1 := TAU * (float(i) + 1.5) / segs
		var r0 := uv[0] * cos(a0) + uv[1] * sin(a0)
		var r1 := uv[0] * cos(a1) + uv[1] * sin(a1)
		var am := (a0 + a1) * 0.5
		var inside := center + axis * pc.y + (uv[0] * cos(am) + uv[1] * sin(am)) * pc.x
		for k in profile.size() - 1:
			var p := profile[k]
			var q := profile[k + 1]
			quad_in(mats[mini(k, mats.size() - 1)],
				center + r0 * p.x + axis * p.y, center + r1 * p.x + axis * p.y,
				center + r1 * q.x + axis * q.y, center + r0 * q.x + axis * q.y, inside)


## Low-poly ellipsoid.
func ellipsoid(m: String, center: Vector3, radii: Vector3, lon: int = 8, lat: int = 6) -> void:
	var rings: Array[PackedVector3Array] = []
	for i in lat + 1:
		var t := PI * float(i) / lat
		var ring := PackedVector3Array()
		for j in lon:
			var a := TAU * (float(j) + 0.5) / lon
			ring.append(center + Vector3(cos(a) * sin(t) * radii.x, -cos(t) * radii.y, sin(a) * sin(t) * radii.z))
		rings.append(ring)
	loft(rings, m)


## A tube with a few sides following a path (halo, curved rods).
func tube(m: String, path: PackedVector3Array, r: float, sides: int = 4) -> void:
	var rings: Array[PackedVector3Array] = []
	for i in path.size():
		var t := path[mini(i + 1, path.size() - 1)] - path[maxi(i - 1, 0)]
		rings.append(circle(path[i], t.normalized(), r, sides, 0.5))
	loft(rings, m, m, m)


static func _signed_area(pts: PackedVector2Array) -> float:
	var s := 0.0
	for i in pts.size():
		var p := pts[i]
		var q := pts[(i + 1) % pts.size()]
		s += p.x * q.y - q.x * p.y
	return s * 0.5


## A flat plate (any simple polygon) given in 2D and placed by `to3d(p, offset)`;
## `normal` is the plate's facing.
func _slab(m: String, pts: PackedVector2Array, t: float, normal: Vector3, to3d: Callable, edge_m: String = "") -> void:
	var idx := Geometry2D.triangulate_polygon(pts)
	var h := t * 0.5
	for i in range(0, idx.size(), 3):
		var a: Vector2 = pts[idx[i]]
		var b: Vector2 = pts[idx[i + 1]]
		var c: Vector2 = pts[idx[i + 2]]
		tri(m, to3d.call(a, h), to3d.call(b, h), to3d.call(c, h), normal)
		tri(m, to3d.call(a, -h), to3d.call(b, -h), to3d.call(c, -h), -normal)
	var ccw := _signed_area(pts) > 0.0
	var em := m if edge_m == "" else edge_m
	for i in pts.size():
		var p := pts[i]
		var q := pts[(i + 1) % pts.size()]
		var e := q - p
		var o2 := Vector2(e.y, -e.x) if ccw else Vector2(-e.y, e.x)
		var mid: Vector3 = to3d.call((p + q) * 0.5, 0.0)
		var o3: Vector3 = to3d.call((p + q) * 0.5 + o2.normalized() * 0.01, 0.0) - mid
		quad(em, to3d.call(p, -h), to3d.call(q, -h), to3d.call(q, h), to3d.call(p, h), o3)


## Plate in the XY plane (side view outline) at z, thickness t.
func slab_xy(m: String, pts: PackedVector2Array, z: float, t: float, edge_m: String = "") -> void:
	_slab(m, pts, t, Vector3.BACK, func(p: Vector2, o: float) -> Vector3: return Vector3(p.x, p.y, z + o), edge_m)


## Plate in the XZ plane (plan view outline, points are (x, z)) at height y.
func slab_xz(m: String, pts: PackedVector2Array, y: float, t: float, edge_m: String = "") -> void:
	_slab(m, pts, t, Vector3.UP, func(p: Vector2, o: float) -> Vector3: return Vector3(p.x, y + o, p.y), edge_m)


func commit(mats: Dictionary) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	for m: String in _surfs:
		var s: Surf = _surfs[m]
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = s.v
		arr[Mesh.ARRAY_NORMAL] = s.n
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		mesh.surface_set_material(mesh.get_surface_count() - 1, mats.get(m) as Material)
	return mesh
