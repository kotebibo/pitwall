"""Menu background (640 x 360): a floodlit corner at night, seen from above at
a slight angle, with a red car streaking through. The left half is kept dark
and quiet for menu text.

A tiny pinhole camera maps every screen pixel to the ground plane (metres), so
stripes, kerbs and light pools all sit in proper perspective. Light levels are
quantised to five steps with ordered dithering: no smooth gradients.

    python tools/art/menu_bg.py
"""

from __future__ import annotations

import math

import numpy as np

from pixel import SPRITES, UI, bayer, blend, canvas, hx, load, save

OUT = SPRITES / "ui" / "bg_menu.png"
W, H = 640, 360

# camera: height h (m), pitch phi below the horizon, focal f (px)
CAM_H = 98.0
PHI = math.radians(55)
F = 600.0
CX, CY = W / 2, H / 2

# the corner: arc centre C, radius R; the car runs from theta=180 deg towards 90 deg
C = np.array([85.0, 20.0])
R = 70.0
HALF = 7.0


def ground_coords():
    v, u = np.mgrid[0:H, 0:W].astype(float)
    u = u + 0.5 - CX
    v = v + 0.5 - CY
    t = CAM_H / (v * math.cos(PHI) + F * math.sin(PHI))
    X = u * t
    Z = t * (F * math.cos(PHI) - v * math.sin(PHI))
    return X, Z, t


def project(X, Y, Z):
    """World (X right, Y up, Z forward) -> screen (x, y)."""
    yc = -(Y - CAM_H) * math.cos(PHI) - Z * math.sin(PHI)
    zc = -(Y - CAM_H) * math.sin(PHI) + Z * math.cos(PHI)
    return CX + F * X / zc, CY + F * yc / zc


def arc_point(theta_deg, d=0.0):
    th = math.radians(theta_deg)
    return C[0] + (R + d) * math.cos(th), C[1] + (R + d) * math.sin(th)


def ramp(*hexes):
    return np.array([hx(h) for h in hexes], np.uint8)


RAMPS = {
    "asphalt": ramp("0f1013", "15171a", "1c1e22", "26292e", "33363c"),
    "rubber": ramp("0d0e10", "121316", "18191d", "202226", "2a2c31"),
    "runoff": ramp("0e1318", "131a21", "1a232c", "223039", "2d3c47"),
    "gravel": ramp("16130f", "1f1b15", "2b251d", "3b3327", "504535"),
    "grassA": ramp("08120d", "0c1812", "102017", "172b1e", "203a27"),
    "grassB": ramp("09140f", "0e1b14", "13241a", "1a3121", "24402b"),
    "red": ramp("35101a", "5e161c", "8f2027", "c22d28", "e8352b"),
    "white": ramp("26272c", "45474e", "777982", "b3b2b0", "e6e3dc"),
    "tyre": ramp("08090a", "0d0e10", "141518", "1c1d21", "26282c"),
    "board": ramp("1a1c22", "24324a", "2b4a78", "3d68b0", "5a8ad0"),
}


def light_field(X, Z):
    L = np.full(X.shape, 0.06)  # moonlight
    pools = [((27.0, 54.0), 18.0, 1.25), ((44.0, 92.0), 21.0, 1.25), ((74.0, 94.0), 16.0, 0.8),
             ((8.0, 76.0), 15.0, 0.9), ((18.0, 34.0), 13.0, 0.55)]
    for (px_, pz), r, a in pools:
        d2 = (X - px_) ** 2 + (Z - pz) ** 2
        L += a * np.exp(-d2 / (r * r))
    return L


def hash01(a, b, seed=0):
    v = (a * 73856093) ^ (b * 19349663) ^ (seed * 83492791)
    v = (v ^ (v >> 13)) * 1274126177
    return ((v ^ (v >> 16)) & 0xFFFF) / 65535.0


def render_ground():
    X, Z, t = ground_coords()
    dx, dz = X - C[0], Z - C[1]
    rad = np.hypot(dx, dz)
    th = np.degrees(np.arctan2(dz, dx))
    d = rad - R                       # + outside, - inside
    s = R * np.radians(180 - th)      # arc length along the lap direction
    L = light_field(X, Z)
    lv = np.floor(L * 3.2 + (bayer(W, H) - 0.5) * 0.9).astype(int)
    lv = np.clip(lv, 0, 4)
    lv_flat = np.clip(np.floor(L * 3.2 + 0.25).astype(int), 0, 4)  # paint stays solid: no dither

    img = np.zeros((H, W, 4), np.uint8)
    img[..., 3] = 255

    def paint(mask, name, bias=0, flat=False):
        idx = np.clip((lv_flat if flat else lv) + bias, 0, 4)
        img[mask] = RAMPS[name][idx[mask]]

    # grass: mowing stripes in world space (5 m bands)
    stripe = (np.floor(X / 5.0) % 2) == 0
    paint(stripe, "grassA")
    paint(~stripe, "grassB")
    corner = (th > 92) & (th < 178)
    # outside: run-off, gravel, tyre wall, boards
    paint((d > 8.4) & (d <= 17.0), "runoff")
    band = (d > 8.4) & (d <= 17.0) & ((np.floor((s + d * 0.8) / 2.0) % 4) == 0) & (bayer(W, H) > 0.45)
    paint(band, "runoff", bias=1)
    paint((d > 17.0) & (d <= 25.5), "gravel")
    pebble = (d > 17.0) & (d <= 25.5) & (bayer(W, H) > 0.82)
    paint(pebble, "gravel", bias=1)
    tyre = (d > 25.5) & (d <= 26.6)
    paint(tyre, "tyre")
    red_t = tyre & ((np.floor(s / 2.2) % 5) == 0)
    paint(red_t, "red", bias=-1)
    boards = (d > 26.6) & (d <= 27.2)
    paint(boards, "board")
    yel = boards & ((np.floor(s / 9.0) % 3) == 1)
    img[yel] = RAMPS["red"][np.clip(lv[yel] + 1, 0, 4)] * 0 + np.array(hx("c49a1e"), np.uint8)
    redb = boards & ((np.floor(s / 9.0) % 3) == 2)
    img[redb] = np.array(hx("a8242a"), np.uint8)
    # inside run-off strip
    paint((d < -8.4) & (d >= -11.5), "runoff", bias=-1)
    # track
    track = np.abs(d) <= HALF
    paint(track, "asphalt")
    # racing line: outside at entry, apex inside, out again
    rl = 4.5 * np.cos(np.radians((th - 135) * 2.2)) - 0.5
    rl = np.where(th > 177, 4.0, rl)
    rub = track & (np.abs(d - rl) < 2.0)
    paint(rub, "rubber")
    # white edge lines
    edge = track & (np.abs(d) > HALF - 0.35)
    paint(edge, "white", bias=-1, flat=True)
    # kerbs through the corner, 3 m blocks
    kerb_o = (d > HALF) & (d <= HALF + 1.4) & corner & (th < 168)
    kerb_i = (d < -HALF) & (d >= -HALF - 1.4) & (th > 108) & (th < 160)
    for km in (kerb_o, kerb_i):
        red = km & ((np.floor(s / 3.0) % 2) == 0)
        paint(red, "red", flat=True)
        paint(km & ~red, "white", bias=-1, flat=True)
    # aggregate glints on the lit asphalt (sparse, structured by a hash grid)
    gx, gz = np.floor(X / 0.6).astype(np.int64), np.floor(Z / 0.6).astype(np.int64)
    glint = track & (hash01(gx, gz, 3) > 0.985) & (lv >= 2) & ~edge
    paint(glint, "asphalt", bias=1)
    return img, X, Z, d, th, s, lv


# --------------------------------------------------------------------------
# 3D props: grandstand, floodlight towers, trees
# --------------------------------------------------------------------------

CROWD = [hx(c) for c in ["c9342b", "d8d4cc", "d9ad2f", "4fa9c4", "37a85c", "8f4fd0", "d06a2c", "3d68b0",
                         "b5466d", "e8e2d0", "e8352b", "f2c230", "34363c", "4a4c54", "26282d", "6e6f78"]]
CROWD = [tuple(int(c[i] * 0.62 + 0x2a * 0.38) for i in range(3)) + (255,) for c in CROWD]


def draw_grandstand(img):
    """Seating ramp outside the corner, rising away from the track, under a lit roof."""
    th0, th1 = 104.0, 138.0
    d0, d1 = 30.0, 44.0
    rows = 16
    depth = np.full((H, W), -1e9)
    # front wall with sponsor boards
    for th in np.arange(th0, th1, 0.04):
        seg = int((th - th0) / 3.4) % 4
        board = [hx("c22d28"), hx("d9ad2f"), hx("2b4a78"), hx("17261c")][seg]
        mark = [hx("f1efea"), hx("17181b"), hx("7fd6ee"), hx("3ecf6a")][seg]
        fs = ((th - th0) / 3.4) % 1
        for y3 in np.arange(0.0, 1.7, 0.08):
            x, z = arc_point(th, d0)
            sx, sy = project(x, y3, z)
            ix, iy = int(sx), int(sy)
            if 0 <= ix < W and 0 <= iy < H:
                if y3 > 1.45:
                    col = hx("6e6f78")
                elif y3 > 0.35:
                    col = mark if (0.3 < fs < 0.7 and 0.75 < y3 < 1.1 and int(fs * 40) % 3) else board
                else:
                    col = hx("17181b")
                img[iy, ix] = col
    # seating: stepped rows, one spectator per 0.3 deg seat, lit from the roof
    for r in range(rows):
        dd0 = d0 + r * (d1 - d0) / rows
        dd1 = dd0 + (d1 - d0) / rows
        hgt = 1.7 + r * 0.75
        lit = 0.55 + 0.45 * max(0.0, 1.0 - abs(r - 8) / 8.0)
        for th in np.arange(th0, th1, 0.03):
            sf = (th - th0) / 0.3
            seat = int(sf)
            fs = sf - seat
            hv = hash01(seat, r, 7)
            for dd in np.arange(dd0, dd1, 0.1):
                frac = (dd - dd0) / (dd1 - dd0)
                x, z = arc_point(th, dd)
                y3 = hgt if frac > 0.3 else hgt - 0.75 + frac * 2.5
                sx, sy = project(x, y3, z)
                ix, iy = int(sx), int(sy)
                if not (0 <= ix < W and 0 <= iy < H):
                    continue
                if frac <= 0.3:
                    col = hx("3a3c43") if frac > 0.2 else hx("1d1f23")  # step edge + riser
                elif hv < 0.12 or fs > 0.72:
                    col = hx("1f2d48")  # seat
                else:
                    c = CROWD[int(hv * 997) % len(CROWD)]
                    if frac > 0.68 and 0.15 < fs < 0.55:
                        c = hx("d8ae8a") if hv > 0.55 else hx("3a2a20") if hv > 0.3 else hx("e8c040")
                    col = (int(c[0] * lit), int(c[1] * lit), int(min(255, c[2] * lit * 1.05)), 255)
                img[iy, ix] = col
    # aisles
    for th in np.arange(th0 + 8.5, th1, 8.5):
        for dd in np.arange(d0, d1, 0.08):
            r = int((dd - d0) / ((d1 - d0) / rows))
            x, z = arc_point(th, dd)
            for k in range(2):
                x2, z2 = arc_point(th + k * 0.18, dd)
                sx, sy = project(x2, 1.7 + r * 0.75, z2)
                ix, iy = int(sx), int(sy)
                if 0 <= ix < W and 0 <= iy < H:
                    img[iy, ix] = hx("4a4c54") if (int(dd * 4) % 2) else hx("3a3c43")
    # roof: dark slab over the back rows with a bright light rig along its front edge
    roof_y = 1.7 + rows * 0.75 + 3.5
    for th in np.arange(th0, th1 + 1.0, 0.04):
        for dd in np.arange(d0 + 7.5, d1 + 3.0, 0.15):
            x, z = arc_point(th, dd)
            sx, sy = project(x, roof_y, z)
            ix, iy = int(sx), int(sy)
            if 0 <= ix < W and 0 <= iy < H:
                img[iy, ix] = hx("16171a") if dd > d0 + 8.2 else hx("4a4c54")
        x, z = arc_point(th, d0 + 7.5)
        sx, sy = project(x, roof_y - 0.3, z)
        ix, iy = int(sx), int(sy)
        if 0 <= ix < W and 0 <= iy < H:
            img[iy, ix] = hx("a8242a")
    lamps = []
    for th in np.arange(th0 + 1.5, th1, 3.2):
        x, z = arc_point(th, d0 + 7.6)
        sx, sy = project(x, roof_y - 0.6, z)
        lamps.append((sx, sy))
    return lamps


def glow(img, cx, cy, radius, color, levels=((0.3, 0.55), (0.55, 0.32), (0.8, 0.16), (1.0, 0.07))):
    """Additive stepped glow with a 1 px dithered rim per step."""
    b = bayer(W, H)
    x0, x1 = int(max(0, cx - radius - 1)), int(min(W, cx + radius + 2))
    y0, y1 = int(max(0, cy - radius - 1)), int(min(H, cy + radius + 2))
    for y in range(y0, y1):
        for x in range(x0, x1):
            dn = math.hypot(x + 0.5 - cx, y + 0.5 - cy) / radius
            a = 0.0
            for i, (r, al) in enumerate(levels):
                if dn <= r:
                    a = al
                    if dn > r - 0.06 and b[y, x] > 0.5:
                        a = levels[i + 1][1] if i + 1 < len(levels) else 0.0
                    break
            if a > 0:
                for ch in range(3):
                    img[y, x, ch] = min(255, int(img[y, x, ch] + color[ch] * a))


def draw_tower(img, gx, gz, height=26.0):
    bx, by = project(gx, 0, gz)
    tx, ty = project(gx, height, gz)
    n = int(abs(by - ty)) + 1
    for i in range(n):
        f = i / max(1, n - 1)
        x = bx + (tx - bx) * f
        y = by + (ty - by) * f
        ix, iy = int(x), int(y)
        if 0 <= iy < H:
            if 0 <= ix < W:
                img[iy, ix] = hx("5d626d")
            if 0 <= ix + 1 < W:
                img[iy, ix + 1] = hx("26282d")
    # lamp head: 2 rows of 4 lamps
    hx0, hy0 = int(tx) - 6, int(ty) - 5
    for y in range(hy0, hy0 + 6):
        for x in range(hx0, hx0 + 13):
            if 0 <= x < W and 0 <= y < H:
                img[y, x] = hx("1d1f23")
    for r in range(2):
        for c in range(4):
            x, y = hx0 + 1 + c * 3, hy0 + 1 + r * 2
            for (ddx, ddy, col) in [(0, 0, "fffbe8"), (1, 0, "ffe9a8")]:
                if 0 <= x + ddx < W and 0 <= y + ddy < H:
                    img[y + ddy, x + ddx] = hx(col)
    return tx, ty - 2


def place_sprite(img, spr, gx, gz, dark=0.45):
    sx, sy = project(gx, 0, gz)
    s = spr.copy().astype(np.float32)
    opaque = s[..., 3] > 200
    s[opaque, 0] *= dark
    s[opaque, 1] *= dark
    s[opaque, 2] *= min(1.0, dark * 1.25)
    blend(img, s.astype(np.uint8), int(sx - spr.shape[1] / 2), int(sy - spr.shape[0] / 2))


# --------------------------------------------------------------------------
# The car and its motion blur
# --------------------------------------------------------------------------


def car_parts(fw, rt):
    """Return (mask, colour) layers in the car frame: fw forward (m), rt right (m)."""
    a = np.abs(rt)
    body = ((fw <= 2.8) & (fw >= -2.5) & (a <= np.interp(fw, [-2.5, -1.6, 0.6, 0.9, 2.8], [0.35, 0.8, 0.8, 0.45, 0.16])))
    fwing = (fw >= 2.45) & (fw <= 2.9) & (a <= 1.0)
    rwing = (fw >= -2.85) & (fw <= -2.4) & (a <= 0.78)
    tyre_f = (fw >= 1.25) & (fw <= 2.0) & (a >= 0.62) & (a <= 1.0)
    tyre_r = (fw >= -2.2) & (fw <= -1.25) & (a >= 0.6) & (a <= 1.05)
    cockpit = (fw >= 0.05) & (fw <= 0.85) & (a <= 0.24)
    helmet = (fw >= 0.3) & (fw <= 0.62) & (a <= 0.14)
    spine = body & (a <= 0.12) & (fw > -2.2) & (fw < 2.4)
    return [
        (body, hx("c22d28")),
        (body & (rt < -0.25), hx("e8352b")),
        (spine, hx("f2603f")),
        (fwing, hx("1d1f23")),
        (fwing & (a > 0.85), hx("e8352b")),
        (rwing, hx("17181b")),
        (rwing & (a > 0.62), hx("e8352b")),
        (tyre_f | tyre_r, hx("101113")),
        ((tyre_f | tyre_r) & (rt < 0) & (a < 0.72), hx("2c2e34")),
        (cockpit, hx("141518")),
        (helmet, hx("f2c230")),
    ]


CAR_SCALE = 1.35


def draw_car(img, X, Z, theta, dcar, ghosts=True):
    th = math.radians(theta)
    px_, pz = C[0] + (R + dcar) * math.cos(th), C[1] + (R + dcar) * math.sin(th)
    fx, fz = math.sin(th), -math.cos(th)  # direction of travel (theta decreasing)
    rx, rz = fz, -fx                        # right-hand side
    rel_x, rel_z = X - px_, Z - pz
    k = 1.0 / CAR_SCALE  # hero car drawn a little larger than life
    fw = (rel_x * fx + rel_z * fz) * k
    rt = (rel_x * rx + rel_z * rz) * k
    near = (np.abs(fw) < 3.2) & (np.abs(rt) < 1.3)
    if ghosts:
        # ghost silhouettes behind the car, stepped alpha
        for k, alpha in [(5, 0.12), (4, 0.18), (3, 0.26), (2, 0.36), (1, 0.48)]:
            back = k * 0.9
            gm = (np.abs(fw + back) < 2.9) & (np.abs(rt) < np.interp(fw + back, [-2.5, 0, 2.8], [0.8, 0.85, 0.3]))
            col = np.array(hx("e8352b")[:3], np.float32)
            sub = img[gm][:, :3].astype(np.float32)
            img[gm, :3] = (sub * (1 - alpha) + col * alpha).astype(np.uint8)
    layers = car_parts(fw, rt)
    sil = near & layers[0][0] | near & layers[3][0] | near & layers[5][0] | near & layers[7][0]
    # 1 px dark outline around the car silhouette
    ring = np.zeros_like(sil)
    for ddx, ddy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        ring |= np.roll(np.roll(sil, ddy, 0), ddx, 1)
    ring &= ~sil
    img[ring] = hx("0b0c0e")
    for m, col in layers:
        img[near & m] = col
    return px_, pz, (fx, fz), (rx, rz)


def draw_streaks(img, theta_car, dcar):
    """Speed streaks following the arc behind the car (stepped alpha by distance)."""
    lines = [(-1.0, hx("e8352b"), 34.0), (1.0, hx("e8352b"), 34.0), (-0.55, hx("f2603f"), 22.0),
             (0.55, hx("f2603f"), 22.0), (0.0, hx("ff8a6a"), 46.0), (-1.9, hx("c22d28"), 16.0),
             (1.9, hx("c22d28"), 14.0)]
    for off, col, length in lines:
        for i in range(int(length * 12)):
            back = 2.7 * CAR_SCALE + i / 12.0
            dth = math.degrees(back / (R + dcar))
            x, z = arc_point(theta_car + dth, dcar + off * CAR_SCALE)
            sx, sy = project(x, 0.0, z)
            ix, iy = int(sx), int(sy)
            if not (0 <= ix < W and 0 <= iy < H):
                continue
            f = back / (length + 2.7)
            a = 0.75 if f < 0.25 else 0.5 if f < 0.5 else 0.28 if f < 0.75 else 0.12
            if f >= 0.75 and (ix + iy) % 2:
                continue
            c = np.array(col[:3], np.float32)
            img[iy, ix, :3] = (img[iy, ix, :3] * (1 - a) + c * a).astype(np.uint8)


# --------------------------------------------------------------------------


def darken_left(img):
    """Quiet the left half for menu text: stepped darkening, dithered at each step."""
    b = bayer(W, H)
    x = np.arange(W)[None, :] + 0.0
    t = np.clip((330 - x) / 300.0, 0, 1)  # 0 at x>=330, 1 at x=30
    steps = 5
    lvl = np.floor(t * steps + (b - 0.5))
    lvl = np.clip(lvl, 0, steps) / steps
    k = 1.0 - 0.62 * lvl
    out = img.astype(np.float32)
    out[..., 0] *= k
    out[..., 1] *= k
    out[..., 2] *= np.minimum(1.0, k * 1.08)
    return np.clip(out, 0, 255).astype(np.uint8)


def vignette(img):
    b = bayer(W, H)
    yy, xx = np.mgrid[0:H, 0:W]
    dx = (xx + 0.5 - W / 2) / (W / 2)
    dy = (yy + 0.5 - H / 2) / (H / 2)
    d = np.sqrt(dx * dx * 0.8 + dy * dy)
    t = np.clip((d - 0.75) / 0.6, 0, 1)
    lvl = np.clip(np.floor(t * 4 + (b - 0.5)), 0, 4) / 4
    k = 1.0 - 0.55 * lvl
    out = img.astype(np.float32)
    out[..., :3] *= k[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def build():
    img, X, Z, d, th, s, lv = render_ground()
    # trees in the dark outfield
    deco = SPRITES / "deco"
    trees = [(-38, 44, "tree_3.png"), (-46, 70, "tree_1.png"), (-30, 92, "tree_5.png"), (-58, 104, "tree_3.png"),
             (-12, 112, "tree_4.png"), (-55, 40, "tree_2.png"), (-20, 58, "bush_1.png"), (-34, 120, "tree_1.png"),
             (-70, 82, "tree_5.png"), (100, 40, "tree_1.png"), (92, 58, "tree_4.png"), (-6, 36, "bush_2.png"),
             (-64, 60, "tree_4.png")]
    for gx, gz, name in sorted(trees, key=lambda t: -t[1]):
        place_sprite(img, load(deco / name), gx, gz, dark=0.42 if gx < 0 else 0.6)
    lamps = draw_grandstand(img)
    theta_car, dcar = 141.0, -1.2
    draw_streaks(img, theta_car, dcar)
    draw_car(img, X, Z, theta_car, dcar)
    heads = []
    for (gx, gz) in [(40, 44), (-2, 72)]:
        heads.append(draw_tower(img, gx, gz, height=18.0))
    img = darken_left(img)
    for (sx, sy) in lamps:
        glow(img, sx, sy, 6, (255, 236, 190), levels=((0.35, 0.8), (0.7, 0.3), (1.0, 0.1)))
        ix, iy = int(sx), int(sy)
        if 0 <= ix < W and 0 <= iy < H:
            img[iy, ix, :3] = (255, 250, 235)
    for (sx, sy), r in zip(heads, (26, 20)):
        glow(img, sx, sy, r, (255, 226, 170))
    # tail light glow on the car
    th_r = math.radians(theta_car)
    fx, fz = math.sin(th_r), -math.cos(th_r)
    cx_, cz_ = arc_point(theta_car, dcar)
    sx, sy = project(cx_ - fx * 2.9 * CAR_SCALE, 0, cz_ - fz * 2.9 * CAR_SCALE)
    glow(img, sx, sy, 5, (255, 60, 50), levels=((0.4, 0.7), (1.0, 0.25)))
    img = vignette(img)
    img[..., 3] = 255
    save(img, OUT)
    return img


if __name__ == "__main__":
    build()
    print("wrote", OUT)
