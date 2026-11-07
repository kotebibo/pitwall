"""Night-track backdrops drawn in the exact camera of a 3D car render.

Each render from game/scenes/car3d/render_brand.gd comes with a JSON file
describing its camera. Here every backdrop pixel is cast onto the ground
plane (Y = 0) through that camera, so the asphalt, kerbs and grass sit under
the car in true perspective. Light is quantised to five steps with ordered
dithering, using the colour ramps of the game's menu background
(tools/art/menu_bg.py), so it reads as the same world.
"""
from __future__ import annotations

import json
import math

import numpy as np

import brandkit as bk
from brandkit import BG, INK, RED, bayer, canvas, hx, over

import menu_bg  # tools/art (imported, not modified)

RAMPS = menu_bg.RAMPS


def ramp(*hexes):
    return np.array([hx(h) for h in hexes], np.uint8)


RAMPS = dict(RAMPS)
RAMPS["kerb_red"] = ramp("3a1216", "6a1a1f", "a8242a", "d23129", "e8352b")
RAMPS["kerb_white"] = ramp("2a2b30", "4a4c54", "8a8c94", "c9c7c2", "ebe8e1")
RAMPS["line"] = ramp("2a2b30", "55575f", "9a9ca3", "d6d4cf", "f1efea")


class Cam:
    """Camera of one render, placed on a canvas with the render's top-left at (ox, oy)."""

    def __init__(self, meta: dict, ox: float, oy: float):
        self.m = meta
        self.ox, self.oy = ox, oy
        self.w, self.h = meta["w"], meta["h"]
        self.O = np.array(meta["origin"], float)
        self.r = np.array(meta["right"], float)
        self.u = np.array(meta["up"], float)
        self.b = np.array(meta["back"], float)
        self.ppm = float(meta["ppm"])
        self.persp = bool(meta["persp"])
        self.f = float(meta["f_px"])
        self.fwd = np.array(meta["forward"], float)
        self.right_dir = np.array([-self.fwd[2], 0.0, self.fwd[0]])  # car's right side
        # car's right = Basis(UP, yaw) * Z = (sin yaw, 0, cos yaw); forward = (cos, 0, -sin)
        self.right_dir = np.array([-meta["forward"][2], 0.0, meta["forward"][0]])

    @property
    def cx(self):
        return self.ox + self.w / 2.0

    @property
    def cy(self):
        return self.oy + self.h / 2.0

    def ground(self, W: int, H: int, ss: int = 1):
        """World X, Z of the ground under every canvas pixel centre, and t (distance)."""
        v, u = np.mgrid[0:H, 0:W].astype(float)
        du = u + 0.5 - self.cx
        dv = v + 0.5 - self.cy
        if self.persp:
            D = (-self.b[None, None, :] + self.r[None, None, :] * (du / self.f)[..., None]
                 - self.u[None, None, :] * (dv / self.f)[..., None])
            O = np.broadcast_to(self.O, D.shape)
        else:
            O = (self.O[None, None, :] + self.r[None, None, :] * (du / self.ppm)[..., None]
                 - self.u[None, None, :] * (dv / self.ppm)[..., None])
            D = np.broadcast_to(-self.b, O.shape)
        dy = D[..., 1]
        hit = dy < -1e-6
        t = np.where(hit, -O[..., 1] / np.where(hit, dy, -1), 1e9)
        X = O[..., 0] + t * D[..., 0]
        Z = O[..., 2] + t * D[..., 2]
        return X, Z, t, hit

    def project(self, P):
        P = np.asarray(P, float)
        rel = P - self.O
        x, y, z = rel @ self.r, rel @ self.u, -(rel @ self.b)
        if self.persp:
            return self.cx + self.f * x / z, self.cy - self.f * y / z
        return self.cx + x * self.ppm, self.cy - y * self.ppm

    def car_point(self, local):
        """Car-local point (x forward, y up, z right) to world."""
        lx, ly, lz = local
        return self.fwd * lx + np.array([0, ly, 0]) + self.right_dir * lz


def load_meta(name: str) -> dict:
    return json.loads((bk.RENDERS / f"{name}.json").read_text(encoding="utf-8"))


class Track:
    """A corner (radius R, turning toward `turn` = +1 right / -1 left of the car)
    or a straight (R=None). The car sits `lat` metres right of the centre line."""

    def __init__(self, cam: Cam, R=60.0, turn=-1, lat=0.0, half=7.0, along=0.0):
        self.cam, self.R, self.turn, self.lat, self.half = cam, R, turn, lat, half
        f, rgt = cam.fwd, cam.right_dir
        self.p0 = -rgt * lat + f * along  # centre line point abeam the car
        if R:
            self.C = self.p0 + rgt * (turn * R)

    def coords(self, X, Z):
        """d: signed lateral distance (+ = car's right of the centre line), s: distance along."""
        f, rgt = self.cam.fwd, self.cam.right_dir
        if not self.R:
            dx, dz = X - self.p0[0], Z - self.p0[2]
            return dx * rgt[0] + dz * rgt[2], dx * f[0] + dz * f[2]
        dx, dz = X - self.C[0], Z - self.C[2]
        rad = np.hypot(dx, dz)
        # angle relative to the car's abeam point, measured in the direction of travel
        a0 = math.atan2(self.p0[2] - self.C[2], self.p0[0] - self.C[0])
        ang = np.arctan2(dz, dx) - a0
        ang = (ang + np.pi) % (2 * np.pi) - np.pi
        # travel direction sign: forward vector vs. tangent
        tan = np.array([-(self.p0[2] - self.C[2]), (self.p0[0] - self.C[0])])
        sgn = 1.0 if (tan[0] * f[0] + tan[1] * f[2]) > 0 else -1.0
        s = sgn * ang * self.R
        d = (self.R - rad) * self.turn  # + toward the car's right... normalised below
        # d positive on the car's right side
        d = -(rad - self.R) * (1 if self.turn > 0 else -1)
        return d, s


def light_field(X, Z, pools, base=0.06):
    L = np.full(X.shape, base)
    for (px_, pz), r, a in pools:
        d2 = (X - px_) ** 2 + (Z - pz) ** 2
        L += a * np.exp(-d2 / (r * r))
    return L


def hash01(a, b, seed=0):
    v = (a * 73856093) ^ (b * 19349663) ^ (seed * 83492791)
    v = (v ^ (v >> 13)) * 1274126177
    return ((v ^ (v >> 16)) & 0xFFFF) / 65535.0


def paint_track(W, H, cam: Cam, track: Track, pools, kerb_side=+1, base=0.06, gain=3.2,
                outside="gravel", inside="grass", seed=1, finish=None):
    """The ground: asphalt, racing line, edge lines, kerbs, run-off, grass."""
    X, Z, t, hit = cam.ground(W, H)
    d, s = track.coords(X, Z)
    L = light_field(X, Z, pools, base)
    b = bayer(W, H)
    lv = np.clip(np.floor(L * gain + (b - 0.5) * 0.9).astype(int), 0, 4)
    lv_flat = np.clip(np.floor(L * gain + 0.25).astype(int), 0, 4)
    img = np.zeros((H, W, 4), np.uint8)
    img[..., 3] = 255

    def pnt(mask, name, bias=0, flat=False):
        idx = np.clip((lv_flat if flat else lv) + bias, 0, 4)
        img[mask] = RAMPS[name][idx[mask]]

    half = track.half
    ad = np.abs(d)
    # grass with mowing bands along the track
    band = (np.floor(s / 6.0) % 2) == 0
    pnt(band, "grassA")
    pnt(~band, "grassB")
    # each side: kerb side gets kerb then grass/run-off, other side run-off + gravel
    side = np.sign(d) == kerb_side
    other = ~side
    # run-off on the far side
    ro = other & (ad > half) & (ad <= half + 5.0)
    pnt(ro, "runoff")
    rb = ro & ((np.floor((s + ad * 0.8) / 2.0) % 4) == 0) & (b > 0.45)
    pnt(rb, "runoff", bias=1)
    gr = other & (ad > half + 5.0) & (ad <= half + 12.0)
    pnt(gr, "gravel")
    pnt(gr & (b > 0.82), "gravel", bias=1)
    tw = other & (ad > half + 12.0) & (ad <= half + 13.1)
    pnt(tw, "tyre")
    pnt(tw & ((np.floor(s / 2.2) % 5) == 0), "red", bias=-1)
    # inside: kerb, then a strip of run-off, then grass
    pnt(side & (ad > half + 1.4) & (ad <= half + 4.0), "runoff", bias=-1)
    # asphalt
    trk = ad <= half
    pnt(trk, "asphalt")
    rl = trk & (np.abs(d - kerb_side * (half - 2.4)) < 1.9)
    pnt(rl, "rubber")
    # aggregate grain: per screen pixel, sparse lighter and darker specks
    yy, xx = np.mgrid[0:H, 0:W].astype(np.int64)
    hsh = hash01(xx, yy, seed)
    pnt(trk & (hsh > 0.93) & (lv >= 1), "asphalt", bias=1)
    pnt(trk & (hsh < 0.05), "asphalt", bias=-1)
    pnt(trk & (hsh > 0.995) & (lv >= 2), "asphalt", bias=2)
    edge = trk & (ad > half - 0.35)
    pnt(edge, "line", bias=-1, flat=True)
    if finish is not None:
        # chequered finish line across the track, `finish` metres along (0.75 m squares)
        f0 = finish
        fl = trk & (s >= f0) & (s < f0 + 1.5)
        chk = ((np.floor((s - f0) / 0.75) + np.floor((d + half) / 0.75)) % 2) == 0
        pnt(fl & chk, "kerb_white", flat=True)
        pnt(fl & ~chk, "tyre", flat=True)
    # kerb (sausage-free, flat red/white blocks of 1.5 m)
    km = side & (ad > half) & (ad <= half + 1.4)
    red = km & ((np.floor(s / 1.5) % 2) == 0)
    pnt(red, "kerb_red", flat=True)
    pnt(km & ~red, "kerb_white", bias=-1, flat=True)
    # far-away / non-hit pixels: darkest
    img[~hit] = BG
    return img, dict(X=X, Z=Z, d=d, s=s, L=L, lv=lv, hit=hit)


def darken(img, t, amount=0.62, steps=5):
    """Stepped, dithered darkening by a 0..1 field t."""
    H, W = img.shape[:2]
    b = bayer(W, H)
    lvl = np.clip(np.floor(t * steps + (b - 0.5)), 0, steps) / steps
    k = 1.0 - amount * lvl
    out = img.astype(np.float32)
    out[..., 0] *= k
    out[..., 1] *= k
    out[..., 2] *= np.minimum(1.0, k * 1.08)
    img[..., :3] = np.clip(out[..., :3], 0, 255).astype(np.uint8)
    return img


def darken_left(img, x0, x1, amount=0.62):
    H, W = img.shape[:2]
    x = np.arange(W)[None, :] + 0.0
    t = np.clip((x1 - x) / max(1.0, (x1 - x0)), 0, 1) * np.ones((H, 1))
    return darken(img, t, amount)


def vignette(img, strength=0.55, start=0.75, aspect=0.8):
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    dx = (xx + 0.5 - W / 2) / (W / 2)
    dy = (yy + 0.5 - H / 2) / (H / 2)
    d = np.sqrt(dx * dx * aspect + dy * dy)
    t = np.clip((d - start) / 0.6, 0, 1)
    return darken(img, t, strength, steps=4)


def lighten(img, cx, cy, radius, color, amount=0.12, steps=4):
    """Soft light spill: radial falloff, quantised and dithered (no smooth gradient)."""
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    t = np.clip(1.0 - np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) / radius, 0, 1)
    lvl = np.clip(np.floor(t * steps + (bayer(W, H) - 0.5)), 0, steps) / steps
    col = np.array(color[:3], np.float32)
    out = img[..., :3].astype(np.float32)
    a = (lvl * amount)[..., None]
    img[..., :3] = np.clip(out * (1 - a) + col * a, 0, 255).astype(np.uint8)
    return img


def glow(img, cx, cy, radius, color, levels=((0.3, 0.55), (0.55, 0.32), (0.8, 0.16), (1.0, 0.07))):
    """Stepped radial glow (additive-ish mix), like the menu floodlights."""
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.hypot(xx + 0.5 - cx, (yy + 0.5 - cy)) / max(1e-6, radius)
    col = np.array(color[:3], np.float32)
    out = img[..., :3].astype(np.float32)
    for edge, a in sorted(levels, key=lambda e: -e[0]):
        m = d <= edge
        out[m] = out[m] * (1 - a) + col * a
    img[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return img


def streak(img, p0, p1, color, width=1, fade=True, dither=True, alpha=1.0):
    """A light trail from p0 (bright) to p1 (faded), stepped and dithered."""
    H, W = img.shape[:2]
    x0, y0 = p0
    x1, y1 = p1
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    col = np.array(color[:3], np.float32)
    for i in range(n):
        t = i / max(1, n - 1)
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        a = alpha * ((1 - t) if fade else 1.0)
        # four steps
        a = math.floor(a * 4 + 0.5) / 4
        for w in range(width):
            xi, yi = int(math.floor(x)), int(math.floor(y)) + w
            if 0 <= xi < W and 0 <= yi < H and a > 0:
                if dither and a < 1 and ((xi + yi) % 2 == 1) and a <= 0.5:
                    continue
                img[yi, xi, :3] = (img[yi, xi, :3] * (1 - a) + col * a).astype(np.uint8)
    return img


def scene(W, H, name, cx, cy, R=38.0, turn=-1, lat=None, half=7.0, kerb_side=-1, pools=None, gain=3.0,
          trails=True, speed_lines=True, base=0.05, seed=1, shadow=True, finish=None, sky=None):
    """Ground + car (+ light trails) for render `name`, its centre at canvas (cx, cy).
    Returns (img, cam)."""
    meta = load_meta(name)
    car = bk.render(name)
    ox, oy = int(round(cx - meta["w"] / 2)), int(round(cy - meta["h"] / 2))
    cam = Cam(meta, ox, oy)
    if lat is None:
        lat = kerb_side * (half - 1.7)
    tr = Track(cam, R=R, turn=turn, lat=lat, half=half)
    P = lambda lx, lz: tuple(cam.car_point((lx, 0, lz))[[0, 2]])
    if pools is None:
        pools = [(P(0.4, 0.0), 7.5, 1.05), (P(-16, -3), 9.0, 0.55), (P(14, 4), 8.0, 0.45)]
    else:
        pools = [(P(a, b), r, k) for (a, b), r, k in pools]
    img, info = paint_track(W, H, cam, tr, pools, kerb_side=kerb_side, gain=gain, base=base, seed=seed,
                            finish=finish)
    if sky is not None:
        sky(img, info["hit"])
    if speed_lines:
        rng = np.random.default_rng(seed)
        for i in range(14):
            lz = rng.uniform(-6.5, 6.5)
            if abs(lz) < 1.3:
                continue
            l0 = rng.uniform(-3.0, 4.0)
            ln = rng.uniform(5.0, 16.0)
            a = cam.project(cam.car_point((l0, 0.0, lz)))
            b = cam.project(cam.car_point((l0 - ln, 0.0, lz)))
            streak(img, a, b, (150, 156, 168), alpha=rng.uniform(0.25, 0.5))
    if shadow:
        sp = bk.RENDERS / f"{name}_shadow.png"
        if sp.exists():
            over(img, bk.load(sp), ox, oy)
    if trails:
        # rain light: a soft glow and a two-tone trail; wing tips and front wing tips: thin trails
        rl = cam.project(cam.car_point((-2.62, 0.42, 0.0)))
        glow(img, rl[0], rl[1], 7 * cam.ppm / 40, (255, 70, 56), levels=((0.45, 0.6), (0.8, 0.3), (1.0, 0.12)))
        for (lx, ly, lz), col, alpha, ln, wd in (
                ((-2.62, 0.42, 0.0), (255, 90, 70), 1.0, 34.0, 2),
                ((-2.62, 0.95, -0.52), (232, 53, 43), 0.75, 26.0, 1),
                ((-2.62, 0.95, 0.52), (232, 53, 43), 0.75, 26.0, 1),
                ((2.55, 0.10, -0.98), (94, 200, 229), 0.4, 20.0, 1),
                ((2.55, 0.10, 0.98), (94, 200, 229), 0.4, 20.0, 1)):
            a = cam.project(cam.car_point((lx, ly, lz)))
            b = cam.project(cam.car_point((lx - ln, ly, lz)))
            streak(img, a, b, col, alpha=alpha, width=wd)
    over(img, car, ox, oy)
    return img, cam


def horizon(img, hit, seed=3, towers=((0.62, 30), (0.9, 26)), stand=(0.0, 1.0)):
    """Night sky above the horizon of a perspective scene: a stepped dark
    gradient, a distant floodlit grandstand with crowd specks, and light towers."""
    H, W = img.shape[:2]
    rows = np.nonzero(hit.all(axis=1))[0]
    hy = int(rows.min()) if len(rows) else H
    sky = ~hit
    b = bayer(W, H)
    yy = np.mgrid[0:H, 0:W][0].astype(float)
    t = np.clip(yy / max(1, hy), 0, 1)
    lvl = np.clip(np.floor(t * 4 + (b - 0.5)), 0, 4) / 4
    top, bot = np.array(hx("0f1013")[:3], float), np.array(hx("1b202b")[:3], float)
    col = top[None, None, :] * (1 - lvl[..., None]) + bot[None, None, :] * lvl[..., None]
    img[sky, :3] = col[sky].astype(np.uint8)
    rng = np.random.default_rng(seed)
    x0, x1 = int(stand[0] * W), int(stand[1] * W)
    sh = max(8, H // 14)
    y0 = hy - sh
    img[y0:hy, x0:x1, :3] = hx("0d0e11")[:3]
    crowd = menu_bg.CROWD
    for y in range(y0 + 3, hy - 1):
        for x in range(x0, x1):
            if rng.random() < 0.45:
                c = crowd[rng.integers(len(crowd))]
                k = 0.55 + 0.25 * (y - y0) / sh
                img[y, x, :3] = (np.array(c[:3]) * k).astype(np.uint8)
    img[y0, x0:x1, :3] = hx("2a2c33")[:3]
    img[y0 + 1, x0:x1, :3] = hx("1a1b20")[:3]
    lamps = []
    for x in range(x0 + 4, x1, 11):
        img[y0, x, :3] = (255, 240, 205)
        lamps.append((x, y0))
    for (lx, ly) in lamps:
        glow(img, lx + 0.5, ly + 0.5, 4, (255, 236, 190), levels=((0.5, 0.45), (1.0, 0.12)))
    for fx, th in towers:
        x = int(fx * W)
        top_y = y0 - th
        img[top_y:y0, x, :3] = hx("23252b")[:3]
        img[top_y - 2:top_y, x - 2:x + 3, :3] = hx("3a3d45")[:3]
        img[top_y - 2, x - 2:x + 3, :3] = (255, 244, 214)
        glow(img, x + 0.5, top_y - 1.5, 26, (255, 226, 170))
        img[top_y - 2, x - 2:x + 3, :3] = (255, 250, 235)
    return hy
