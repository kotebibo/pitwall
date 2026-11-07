"""Minimal flat-shaded 3D -> pixel-art rasteriser for the part illustrations.

Models are lists of convex polygons in world space (X right, Y up, Z toward
the front of the part). An orthographic 3/4 camera projects them, a z-buffer
resolves overlap, each face gets a quantised ramp level from its normal, and
a post pass adds selective outlines and removes orphan pixels so the result
reads as hand-placed pixel art rather than a render.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from pxl import CARBON, hx, ramp

# --------------------------------------------------------------------------
# materials: ramp (dark -> light), and the outline colour used next to them
# --------------------------------------------------------------------------

MATERIALS = {
    # brand red, hue-shifted: shadows toward crimson/violet, lights toward orange
    "paint": ramp("#2a0b14", "#5a1220", "#931b26", "#c4282a", "#e8352b", "#ff6440", "#ffb08a"),
    "lamp": ramp("#3a0806", "#6e0f0a", "#a8170f", "#e02a1c", "#ff4a30", "#ff9a7a", "#ffe2d6"),
    "carbon": ramp("#0b0c0e", "#111317", "#171a1f", "#1f2329", "#292e36", "#363c47", "#56606e"),
    "metal": ramp("#23262d", "#3c414b", "#59606d", "#7d8593", "#a6aebb", "#ccd3dc", "#f1f4f8"),
    "dark": ramp("#050506", "#08090b", "#0c0d10", "#101216", "#15181d", "#1b1f25", "#232830"),
    "tyre": ramp("#08080a", "#0e0e10", "#141417", "#1b1b1f", "#242428", "#2e2e33", "#3c3c42"),
    "gold": ramp("#3d2410", "#6a3f17", "#9a611f", "#c98a2a", "#e8b23a", "#f6d36a", "#fff0b0"),
    "glow": ramp("#0f3a4c", "#16607a", "#2394b3", "#3fbcdc", "#5ec8e5", "#a6ecfb", "#e6fbff"),
    "plank": ramp("#2c1d12", "#4a3020", "#6b472c", "#8b5f3a", "#a87a4c", "#c79b66", "#e2bf8a"),
    "white": ramp("#3a3b42", "#6b6c74", "#9a9ba2", "#c6c6c9", "#e3e2de", "#f4f2ec", "#ffffff"),
    "yellow": ramp("#3a2a08", "#6e4f0e", "#a87a14", "#d9a21f", "#f2c230", "#ffdc6a", "#fff1b0"),
    "copper": ramp("#2a120a", "#4e2312", "#7a3a1c", "#a8552a", "#cf7a3e", "#eaa15f", "#ffd09a"),
}
# outline colour per material (darkened hue rather than flat black)
OUTLINE = {
    "paint": hx("#1c070d"),
    "carbon": hx("#07080a"),
    "metal": hx("#14161b"),
    "dark": hx("#040405"),
    "tyre": hx("#050506"),
    "gold": hx("#24140a"),
    "glow": hx("#0a2733"),
    "plank": hx("#1d130c"),
    "white": hx("#24252b"),
    "yellow": hx("#2a1d06"),
    "copper": hx("#1d0c06"),
    "lamp": hx("#2a0605"),
}
MAT_IDS = {k: i + 1 for i, k in enumerate(MATERIALS)}
MAT_NAMES = {v: k for k, v in MAT_IDS.items()}


def norm(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


# --------------------------------------------------------------------------
# geometry building
# --------------------------------------------------------------------------

@dataclass
class Face:
    pts: np.ndarray            # (n, 3) world
    mat: str
    obj: int = 0
    bias: int = 0              # added to the shade level (manual tweak)
    flat: int | None = None    # force a ramp level
    spec: bool = True


@dataclass
class Model:
    faces: list = field(default_factory=list)
    _obj: int = 0

    def new_obj(self) -> int:
        self._obj += 1
        return self._obj

    def add(self, pts, mat, obj=None, **kw):
        self.faces.append(Face(np.asarray(pts, float), mat, self._obj if obj is None else obj, **kw))

    def extend(self, other: "Model"):
        base = self._obj
        for f in other.faces:
            self.faces.append(Face(f.pts.copy(), f.mat, f.obj + base, f.bias, f.flat, f.spec))
        self._obj = base + other._obj

    def transformed(self, fn) -> "Model":
        m = Model()
        m._obj = self._obj
        for f in self.faces:
            m.faces.append(Face(np.array([fn(p) for p in f.pts]), f.mat, f.obj, f.bias, f.flat, f.spec))
        return m


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def ring_normal(r):
    nrm = np.zeros(3)
    for i in range(len(r)):
        a, b = r[i], r[(i + 1) % len(r)]
        nrm[0] += (a[1] - b[1]) * (a[2] + b[2])
        nrm[1] += (a[2] - b[2]) * (a[0] + b[0])
        nrm[2] += (a[0] - b[0]) * (a[1] + b[1])
    return nrm


def loft(m: Model, sections: list, mat: str, cap0=True, cap1=True, obj=None, **kw):
    """Connect consecutive rings (each (n,3), same n, consistent order).
    Ring orientation is fixed up automatically so normals face outward."""
    o = m.new_obj() if obj is None else obj
    secs = [np.asarray(s, float) for s in sections]
    n = len(secs[0])
    if len(secs) > 1:
        dirv = secs[-1].mean(axis=0) - secs[0].mean(axis=0)
        if np.dot(ring_normal(secs[0]), dirv) < 0:
            secs = [s[::-1].copy() for s in secs]
    for a, b in zip(secs[:-1], secs[1:]):
        for i in range(n):
            j = (i + 1) % n
            m.add([a[i], a[j], b[j], b[i]], mat, o, **kw)
    if cap0:
        m.add(secs[0][::-1], mat, o, **kw)
    if cap1:
        m.add(secs[-1], mat, o, **kw)
    return o


def prism(m: Model, profile2d, axis: str, a0: float, a1: float, mat: str, obj=None, **kw):
    """Extrude a 2D profile. axis 'x': profile is (z, y) extruded along x from
    a0 to a1. axis 'z': profile (x, y) along z. axis 'y': profile (x, z)."""
    p = np.asarray(profile2d, float)
    if axis == "x":
        s0 = [(a0, y, z) for z, y in p]
        s1 = [(a1, y, z) for z, y in p]
    elif axis == "z":
        s0 = [(x, y, a0) for x, y in p]
        s1 = [(x, y, a1) for x, y in p]
    else:
        s0 = [(x, a0, z) for x, z in p]
        s1 = [(x, a1, z) for x, z in p]
    return loft(m, [s0, s1], mat, obj=obj, **kw)


def box(m: Model, c, size, mat: str, R=None, obj=None, **kw):
    cx, cy, cz = c
    sx, sy, sz = (s / 2 for s in size)
    v = np.array([[x, y, z] for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)])
    if R is not None:
        v = v @ np.asarray(R).T
    v = v + np.array([cx, cy, cz])
    # index: x*4 + y*2 + z
    q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    o = m.new_obj() if obj is None else obj
    for f in q:
        m.add(v[list(f)], mat, o, **kw)
    return o


def ring(center, axis, radius, n, start=0.0, ry=None):
    """Circle points around axis ('x','y','z') through center."""
    cx, cy, cz = center
    ry = radius if ry is None else ry
    pts = []
    for i in range(n):
        a = start + 2 * math.pi * i / n
        u, v = math.cos(a) * radius, math.sin(a) * ry
        if axis == "x":      # (y, z) plane
            pts.append((cx, cy + u, cz + v))
        elif axis == "y":    # (z, x) plane
            pts.append((cx + v, cy, cz + u))
        else:                # (x, y) plane
            pts.append((cx + u, cy + v, cz))
    return pts


def cylinder(m: Model, c0, c1, radius, mat, n=16, axis=None, obj=None, r1=None, **kw):
    """Cylinder between two points along a principal axis."""
    c0, c1 = np.asarray(c0, float), np.asarray(c1, float)
    d = c1 - c0
    if axis is None:
        axis = "xyz"[int(np.argmax(np.abs(d)))]
    r1 = radius if r1 is None else r1
    s0 = ring(c0, axis, radius, n)
    s1 = ring(c1, axis, r1, n)
    return loft(m, [s0, s1], mat, obj=obj, **kw)


def tube(m: Model, p0, p1, r, mat, n=6, obj=None, **kw):
    """Arbitrary-direction thin tube."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = norm(p1 - p0)
    a = np.array([0, 1, 0]) if abs(d[1]) < 0.9 else np.array([1, 0, 0])
    u = norm(np.cross(d, a))
    v = np.cross(d, u)
    s0, s1 = [], []
    for i in range(n):
        t = 2 * math.pi * i / n
        off = (math.cos(t) * u + math.sin(t) * v) * r
        s0.append(p0 + off)
        s1.append(p1 + off)
    return loft(m, [s0[::-1], s1[::-1]], mat, obj=obj, **kw)


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

@dataclass
class Camera:
    yaw: float = -35.0       # degrees, rotation around Y
    pitch: float = 28.0      # degrees, tilt so we see the top
    scale: float = 1.0
    cx: float = 32.0
    cy: float = 32.0
    light: tuple = (-0.55, 0.75, 0.45)   # camera space, toward the light

    def view(self, p):
        R = rot_x(math.radians(self.pitch)) @ rot_y(math.radians(self.yaw))
        return np.asarray(p) @ R.T


def shade_level(mat: str, inten: float, spec: float, n_levels: int) -> int:
    # intensity -1..1 -> ramp index 1..n-2, top index reserved for specular
    t = (inten + 0.25) / 1.3
    t = min(max(t, 0.0), 0.999)
    lvl = 1 + int(t * (n_levels - 2))
    if spec > 0.965:
        lvl = n_levels - 1
    return lvl


def render(model: Model, cam: Camera, w=64, h=64, outline=True, interior=True,
           cleanup=True, ssaa=1, twill=True):
    zb = np.full((h, w), -1e9)
    mat_b = np.zeros((h, w), np.int16)
    lvl_b = np.zeros((h, w), np.int16)
    obj_b = np.zeros((h, w), np.int32)
    L = norm(cam.light)
    Hv = norm(L + np.array([0, 0, 1.0]))
    R = rot_x(math.radians(cam.pitch)) @ rot_y(math.radians(cam.yaw))
    ys, xs = np.mgrid[0:h, 0:w]
    pxc = xs + 0.5
    pyc = ys + 0.5
    for f in model.faces:
        v = f.pts @ R.T
        sx = v[:, 0] * cam.scale + cam.cx
        sy = -v[:, 1] * cam.scale + cam.cy
        sz = v[:, 2]
        # normal (camera space) via Newell's method
        nrm = np.zeros(3)
        for i in range(len(v)):
            a, b = v[i], v[(i + 1) % len(v)]
            nrm[0] += (a[1] - b[1]) * (a[2] + b[2])
            nrm[1] += (a[2] - b[2]) * (a[0] + b[0])
            nrm[2] += (a[0] - b[0]) * (a[1] + b[1])
        if np.linalg.norm(nrm) < 1e-9:
            continue
        nrm = norm(nrm)
        if nrm[2] <= 1e-4:
            continue  # back face
        inten = float(np.dot(nrm, L))
        sp = float(np.dot(nrm, Hv)) if f.spec else 0.0
        ramp_ = MATERIALS[f.mat]
        if f.flat is not None:
            lvl = f.flat
        else:
            lvl = shade_level(f.mat, inten, sp, len(ramp_)) + f.bias
            lvl = max(0, min(len(ramp_) - 1, lvl))
        x0, x1 = int(max(0, math.floor(sx.min()))), int(min(w - 1, math.ceil(sx.max())))
        y0, y1 = int(max(0, math.floor(sy.min()))), int(min(h - 1, math.ceil(sy.max())))
        if x0 > x1 or y0 > y1:
            continue
        px = pxc[y0:y1 + 1, x0:x1 + 1]
        py = pyc[y0:y1 + 1, x0:x1 + 1]
        inside = np.ones_like(px, bool)
        n = len(sx)
        # screen winding: front faces are counter-clockwise in y-down => sign
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += sx[i] * sy[j] - sx[j] * sy[i]
        sgn = 1.0 if area > 0 else -1.0
        for i in range(n):
            j = (i + 1) % n
            e = (sx[j] - sx[i]) * (py - sy[i]) - (sy[j] - sy[i]) * (px - sx[i])
            inside &= (e * sgn) >= -1e-6
        if not inside.any():
            continue
        # depth plane from normal: z = z0 - (nx*(x-x0) + ny*(y-y0))/nz in screen
        # (screen y is flipped, scale applied)
        nx, ny, nz = nrm
        xw = (px - cam.cx) / cam.scale
        yw = -(py - cam.cy) / cam.scale
        z = v[0, 2] - (nx * (xw - v[0, 0]) + ny * (yw - v[0, 1])) / nz
        sub_z = zb[y0:y1 + 1, x0:x1 + 1]
        upd = inside & (z > sub_z + 1e-6)
        sub_z[upd] = z[upd]
        mat_b[y0:y1 + 1, x0:x1 + 1][upd] = MAT_IDS[f.mat]
        lvl_b[y0:y1 + 1, x0:x1 + 1][upd] = lvl
        obj_b[y0:y1 + 1, x0:x1 + 1][upd] = f.obj
    return finish(zb, mat_b, lvl_b, obj_b, outline, interior, cleanup, twill)


def finish(zb, mat_b, lvl_b, obj_b, outline=True, interior=True, cleanup=True, twill=False):
    h, w = mat_b.shape
    occ = mat_b > 0
    if cleanup:
        # orphan pixels: a pixel whose 4 neighbours all share one other
        # (material, level) gets that value
        for _ in range(2):
            key = mat_b.astype(np.int32) * 64 + lvl_b
            p = np.pad(key, 1, constant_values=-1)
            nb = [p[1:-1, 2:], p[1:-1, :-2], p[2:, 1:-1], p[:-2, 1:-1]]
            same = (nb[0] == nb[1]) & (nb[1] == nb[2]) & (nb[2] == nb[3]) & (nb[0] != key) & (nb[0] > 0)
            same &= occ
            if not same.any():
                break
            mat_b = np.where(same, nb[0] // 64, mat_b).astype(np.int16)
            lvl_b = np.where(same, nb[0] % 64, lvl_b).astype(np.int16)
    if twill:
        # carbon twill: faint regular diagonal weave on flat interior areas
        cid = MAT_IDS["carbon"]
        key = mat_b.astype(np.int32) * 64 + lvl_b
        p = np.pad(key, 1, constant_values=-1)
        flat = (p[1:-1, 2:] == key) & (p[1:-1, :-2] == key) & (p[2:, 1:-1] == key) & (p[:-2, 1:-1] == key)
        ys, xs = np.mgrid[0:h, 0:w]
        patt = ((xs - ys) % 4 == 0) & ((xs + ys) // 4 % 2 == 0)
        sel = flat & (mat_b == cid) & (lvl_b >= 3) & (lvl_b <= 5) & patt
        lvl_b = np.where(sel, lvl_b - 1, lvl_b).astype(np.int16)
    img = np.zeros((h, w, 4), np.uint8)
    for mid, name in MAT_NAMES.items():
        rp = MATERIALS[name]
        sel = mat_b == mid
        if not sel.any():
            continue
        for li, c in enumerate(rp):
            img[sel & (lvl_b == li)] = c
    if interior:
        # depth / object discontinuities: darken the nearer-side pixel's
        # neighbour that is farther away (draws contour lines behind edges)
        pz = np.pad(zb, 1, constant_values=-1e9)
        po = np.pad(obj_b, 1, constant_values=0)
        edge = np.zeros((h, w), bool)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nz = pz[1 + dy:h + 1 + dy, 1 + dx:w + 1 + dx]
            no = po[1 + dy:h + 1 + dy, 1 + dx:w + 1 + dx]
            edge |= occ & (no > 0) & (no != obj_b) & (nz > zb + 0.75)
        for mid, name in MAT_NAMES.items():
            sel = edge & (mat_b == mid)
            if sel.any():
                rp = MATERIALS[name]
                lv = np.clip(lvl_b - 2, 0, len(rp) - 1)
                for li, c in enumerate(rp):
                    img[sel & (lv == li)] = c
    if outline:
        ring_ = np.zeros((h, w), bool)
        p = np.pad(occ, 1)
        nbr = p[1:-1, 2:] | p[1:-1, :-2] | p[2:, 1:-1] | p[:-2, 1:-1]
        ring_ = nbr & ~occ
        # outline colour from the adjacent material
        pm = np.pad(mat_b, 1)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nm = pm[1 + dy:h + 1 + dy, 1 + dx:w + 1 + dx]
            for mid, name in MAT_NAMES.items():
                sel = ring_ & (nm == mid) & (img[..., 3] == 0)
                img[sel] = OUTLINE[name]
    return img


def floor_shadow(w, h, cx, cy, rx, ry, alpha=70) -> np.ndarray:
    img = np.zeros((h, w, 4), np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    e = ((xx + 0.5 - cx) / rx) ** 2 + ((yy + 0.5 - cy) / ry) ** 2
    img[e <= 1.0] = (8, 9, 12, alpha)
    img[e <= 0.55] = (8, 9, 12, int(alpha * 1.45))
    return img
