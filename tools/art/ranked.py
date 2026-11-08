"""Ranked art: tier emblems, medal icons, medal pack variants, PROMOTED banner.

Run:  python tools/art/ranked.py
Writes game/assets/sprites/ranked/*.png and ranked/preview_ranked.png

Emblems are built from layered masks (back to front): tyre ring, wing blades,
laurel, shield (raised rim + recessed enamel field), chequered band, helmet or
crystal or crown, gems. Each tier switches layers on and grows the shield, so the ten
tiers read as one family that gets more ornate. Light from the top-left, every
part gets a 1 px outline in the darkest step of its own ramp.
"""
from __future__ import annotations

import colorsys
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import packs  # noqa: E402
from pxl import (FONT5, alpha_over, canvas, draw_text, ellipse_mask, hx,  # noqa: E402
                 poly_mask, put, rect, save, scale, text_width)

S = 64                    # emblem canvas
CX = 32.0                 # mirror axis (between columns 31 and 32)
BG = hx("#141518")
INK = hx("#f1efea")
INK2 = hx("#a3a3ad")
BRAND = hx("#e8352b")
CLEAR = (0, 0, 0, 0)
# FONT5 plus the one letter it lacks (for BRONZE)
F5 = dict(FONT5, Z=["11111", "00001", "00010", "00100", "01000", "10000", "11111"])

# --------------------------------------------------------------------------
# ramps: 6 steps, 0 = outline ... 5 = highlight. Shadows drift to blue-violet,
# lights drift to warm yellow.
# --------------------------------------------------------------------------

COOL_H, WARM_H = 0.68, 0.13


def _toward(h, target, f):
    d = (target - h + 0.5) % 1.0 - 0.5
    return (h + d * f) % 1.0


def tramp(base: str, sat_floor=0.10) -> list:
    r, g, b = (int(base.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    grey = s < 0.15
    steps = [  # (lightness, hue target, shift, sat mul)
        (l * 0.26, COOL_H, 0.30, 1.05),
        (l * 0.50, COOL_H, 0.18, 1.0),
        (l * 0.74, COOL_H, 0.08, 1.0),
        (l, None, 0, 1.0),
        (l + (1 - l) * 0.38, WARM_H, 0.07, 0.95),
        (l + (1 - l) * 0.74, WARM_H, 0.14, 0.85),
    ]
    out = []
    for (ll, tgt, f, sm) in steps:
        hh, ss = h, s * sm
        if tgt is not None:
            if grey:
                hh, ss = (0.63 if tgt == COOL_H else 0.11), max(ss, sat_floor)
            else:
                hh = _toward(h, tgt, f)
        rr, gg, bb = colorsys.hls_to_rgb(hh, min(ll, 0.97), min(ss, 1.0))
        out.append((int(rr * 255 + .5), int(gg * 255 + .5), int(bb * 255 + .5), 255))
    return out


GOLD_TRIM = tramp("#f2c230")
GEM = {
    "green": tramp("#3ecf6a"),
    "ice": tramp("#5ec8e5"),
    "violet": tramp("#c084fc"),
    "ruby": tramp("#ff5a4a"),
    "blue": tramp("#3f8cff"),
}
RUBBER = [hx("#101114"), hx("#1e2026"), hx("#2b2e35"), hx("#3a3d46"), hx("#4d515b"), hx("#636874")]
VISOR = [hx("#0c1420"), hx("#163049"), hx("#2a5f8f"), hx("#4f9ad0"), hx("#9fd4f2"), hx("#e6f6ff")]

# tier table. size grows, layers switch on. field = enamel ramp for the centre.
TIERS = [
    dict(name="iron", col="#6e6f78", sw=28, sh=33, top=17, rough=True, rivets=True),
    dict(name="bronze", col="#c98a5a", sw=30, sh=35, top=16, tyre=True, rivets=True, field="#b07448"),
    dict(name="silver", col="#c6c8d0", sw=31, sh=36, top=15, tyre=True, cheq=True, peak=2),
    dict(name="gold", col="#f2c230", sw=32, sh=37, top=15, tyre=True, cheq=True, peak=2, laurel=3,
         helmet=True),
    dict(name="platinum", col="#5ec8b0", sw=33, sh=38, top=15, tyre=True, cheq=True, peak=3, laurel=4,
         helmet=True, wings=2),
    dict(name="emerald", col="#3ecf6a", sw=34, sh=38, top=15, tyre=True, cheq=True, peak=3, laurel=4,
         topgem=True, wings=3, gem="green", sidegems=True),
    dict(name="diamond", col="#5ec8e5", sw=34, sh=39, top=15, tyre=True, cheq=True, peak=3, laurel=5,
         topgem=True, wings=4, gem="ice", facets=True, sidegems=True),
    dict(name="master", col="#a855f7", sw=35, sh=40, top=17, tyre=True, cheq=True, peak=2, laurel=5,
         crown=3, wings=4, gem="violet", sidegems=True),
    dict(name="grandmaster", col="#e8352b", sw=36, sh=40, top=17, tyre=True, cheq=True, peak=2, laurel=5,
         crown=5, wings=4, gem="ruby", sidegems=True, trim=True),
    dict(name="challenger", col="#f1efea", sw=37, sh=41, top=17, tyre=True, cheq=True, peak=2, laurel=6,
         crown=5, wings=5, gem="blue", sidegems=True, trim=True, field="#2a4f9a"),
]


# --------------------------------------------------------------------------
# mask helpers
# --------------------------------------------------------------------------

def nb(m, dx, dy):
    """m shifted so out[y, x] = m[y+dy, x+dx] (False outside)."""
    k = max(abs(dx), abs(dy), 1)
    p = np.pad(m, k)
    h, w = m.shape
    return p[k + dy:k + dy + h, k + dx:k + dx + w]


def ring_of(m, diag=False):
    r = nb(m, 1, 0) | nb(m, -1, 0) | nb(m, 0, 1) | nb(m, 0, -1)
    if diag:
        r = r | nb(m, 1, 1) | nb(m, -1, -1) | nb(m, 1, -1) | nb(m, -1, 1)
    return r & ~m


def erode(m, r=1):
    for _ in range(r):
        m = m & nb(m, 1, 0) & nb(m, -1, 0) & nb(m, 0, 1) & nb(m, 0, -1)
    return m


def mirror_mask(m):
    return m | m[:, ::-1]


def bevel(img, m, ramp, base=3, outline=True, diag_outline=False):
    """Fill a part: base tone, top-left edge lit, bottom-right edge shaded,
    1 px outline in ramp[0] outside the mask."""
    if outline:
        img[ring_of(m, diag_outline)] = ramp[0]
    img[m] = ramp[base]
    tl = m & (~nb(m, 0, -1) | ~nb(m, -1, 0))
    br = m & (~nb(m, 0, 1) | ~nb(m, 1, 0))
    img[br] = ramp[max(base - 2, 1)]
    img[tl & ~br] = ramp[min(base + 2, 5)]
    # second step of light just inside the lit edge
    tl2 = m & ~tl & ~br & (~nb(m, 0, -2) | ~nb(m, -2, 0))
    img[tl2] = ramp[min(base + 1, 5)]


def leaf_mask(cx, cy, ang, L, W):
    yy, xx = np.mgrid[0:S, 0:S]
    dx, dy = xx + 0.5 - cx, yy + 0.5 - cy
    ca, sa = math.cos(ang), math.sin(ang)
    u = dx * ca + dy * sa
    v = -dx * sa + dy * ca
    return (u / (L / 2)) ** 2 + (v / (W / 2)) ** 2 <= 1.0


# --------------------------------------------------------------------------
# emblem parts
# --------------------------------------------------------------------------

def shield_pts(t):
    """Heater shield, optional centre peak, mirror-symmetric about CX."""
    sw, sh, top = t["sw"], t["sh"], t["top"]
    x0 = CX - sw / 2
    c = 3
    pk = t.get("peak", 0)
    left = [(CX, top - pk), (CX - 5, top)] if pk else [(CX, top)]
    left += [(x0 + c, top), (x0, top + c), (x0, top + sh * 0.46)]
    p0, p1, p2 = (x0, top + sh * 0.46), (x0, top + sh * 0.80), (CX, top + sh)
    for i in range(1, 8):
        u = i / 8
        left.append(((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0],
                     (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1]))
    right = [(2 * CX - x, y) for (x, y) in reversed(left[1:])]
    return left + [p2] + right


def draw_tyre(img, t, ramp):
    sw, sh, top = t["sw"], t["sh"], t["top"]
    cy = top + sh * 0.40
    ro = sw / 2 + 6.5
    ri = ro - 4.2
    yy, xx = np.mgrid[0:S, 0:S]
    d = np.hypot(xx + 0.5 - CX, yy + 0.5 - cy)
    ring = (d <= ro) & (d > ri)
    img[ring_of(ring)] = RUBBER[0]
    img[ring] = RUBBER[2]
    ang = np.degrees(np.arctan2(yy + 0.5 - cy, xx + 0.5 - CX))
    # lit upper-left arc, darker lower-right
    lit = ring & (((ang < -100) & (ang > -170)) | (ang > 170))
    dark = ring & (ang > -10) & (ang < 80)
    img[lit] = RUBBER[3]
    img[dark] = RUBBER[1]
    # tread blocks on the outer edge
    outer = ring & (d > ro - 1.2)
    tread = outer & ((np.floor((ang + 180) / 9) % 2) == 0)
    img[tread] = RUBBER[1]
    img[outer & lit & ~tread] = RUBBER[4]
    # sidewall stripe in the tier colour (like a compound stripe)
    stripe = ring & (np.abs(d - (ri + 1.3)) < 0.55)
    img[stripe] = ramp[3]
    img[stripe & lit] = ramp[4]
    img[stripe & dark] = ramp[2]


def draw_wings(img, t, ramp):
    """Fan of tapered feathers (read as stacked aerofoil blades) spreading from
    behind the shield's upper half. Lower feathers first; each upper feather's
    outline separates it from the one below."""
    n = t["wings"]
    sw, top = t["sw"], t["top"]
    x0 = CX - sw / 2
    rx = x0 + 3.0
    for i in reversed(range(n)):
        ry = top + 3.0 + i * 4.2
        th = math.radians(52 - i * (62 / max(n - 1, 1)) if n > 1 else 45)
        L = min(17.0 + n * 1.0 - i * 1.0, (rx - 1.5) / max(math.cos(th), 0.3))
        dx, dy = -math.cos(th), -math.sin(th)
        nx, ny = -dy, dx
        w = 7.0
        pts = [(rx + nx * w / 2, ry + ny * w / 2),
               (rx + dx * L * 0.62 + nx * w * 0.42, ry + dy * L * 0.62 + ny * w * 0.42),
               (rx + dx * L, ry + dy * L),
               (rx + dx * L * 0.62 - nx * w * 0.42, ry + dy * L * 0.62 - ny * w * 0.42),
               (rx - nx * w / 2, ry - ny * w / 2)]
        m = mirror_mask(poly_mask(S, S, pts))
        bevel(img, m, ramp, base=3)


def draw_laurel(img, t, ramp):
    """Two laurel branches hugging the lower shield; leaves drawn one by one
    from the top down so every leaf keeps its own outline."""
    n = t["laurel"]
    sw, sh, top = t["sw"], t["sh"], t["top"]
    ecx, ecy = CX, top + sh * 0.40
    rx, ry = sw / 2 + 4.6, sh * 0.62 + 1.0
    a0, a1 = 100, 192
    stem = np.zeros((S, S), bool)
    for k in range(120):
        a = math.radians(a0 + k * (a1 - a0) / 120)
        x, y = ecx + math.cos(a) * rx, ecy + math.sin(a) * ry
        if 0 <= int(y) < S:
            stem[int(y), int(x)] = True
    stem = mirror_mask(stem)
    img[ring_of(stem)] = ramp[0]
    img[stem] = ramp[1]
    for i in reversed(range(n)):
        a = math.radians(a0 + 6 + i * ((a1 - a0 - 6) / max(n - 1, 1)))
        x, y = ecx + math.cos(a) * rx, ecy + math.sin(a) * ry
        # unit tangent pointing up the branch (direction of growth)
        tx_, ty_ = -math.sin(a) * rx, math.cos(a) * ry
        tl_ = math.hypot(tx_, ty_)
        tx_, ty_ = tx_ / tl_, ty_ / tl_
        nx_, ny_ = math.cos(a), math.sin(a)  # outward normal (approx)
        for side in (1, -1):
            lx = x + nx_ * 1.9 * side + tx_ * 2.4
            ly = y + ny_ * 1.9 * side + ty_ * 2.4
            ang = math.atan2(ty_, tx_) - side * 0.42
            m = mirror_mask(leaf_mask(lx, ly, ang, 8.0, 3.2))
            bevel(img, m, ramp, base=3 if side > 0 else 2)


def draw_shield(img, t, ramp, field_ramp):
    pts = shield_pts(t)
    sm = poly_mask(S, S, pts)
    rim_w = 3
    fm = erode(sm, rim_w)
    yy, xx = np.mgrid[0:S, 0:S]
    sw, sh, top = t["sw"], t["sh"], t["top"]
    u = (xx + 0.5 - CX) / sw
    v = (yy + 0.5 - (top + sh / 2)) / sh
    diag = u + v
    rim = sm & ~fm
    img[ring_of(sm)] = ramp[0]
    img[rim] = ramp[3]
    img[rim & (diag < -0.22)] = ramp[4]
    img[rim & (diag > 0.30)] = ramp[2]
    if t.get("facets"):
        ang = np.degrees(np.arctan2(v, u))
        sector = np.floor((ang + 180 + 11.25) / 22.5).astype(int) % 16
        img[rim & (sector % 2 == 0) & (diag < 0.1)] = ramp[5]
        img[rim & (sector % 2 == 0) & (diag >= 0.1)] = ramp[3]
        img[rim & (sector % 2 == 1) & (diag >= 0.1)] = ramp[2]
    # crisp outer edge: lit top/left, shaded bottom/right
    tl = sm & (~nb(sm, 0, -1) | ~nb(sm, -1, 0))
    br = sm & (~nb(sm, 0, 1) | ~nb(sm, 1, 0))
    img[tl & (diag < 0.25)] = ramp[5]
    img[br & (diag > -0.25)] = ramp[1]
    # inner bevel of the rim (facing the field): lit on the bottom-right side
    rin = rim & ring_of(fm, True)
    img[rin & (diag > 0.0)] = ramp[4]
    img[rin & (diag <= 0.0)] = ramp[1]
    # recessed enamel field
    img[fm] = field_ramp[2]
    ftl = fm & (~nb(fm, 0, -1) | ~nb(fm, -1, 0))
    img[ftl] = field_ramp[1]
    fbr = fm & (~nb(fm, 0, 1) | ~nb(fm, 1, 0)) & ~ftl
    img[fbr] = field_ramp[3]
    # one diagonal glint band in the upper-left of the field (kept out of the
    # numeral zone in the middle)
    d2 = (xx - (CX - sw / 2)) + (yy - top)
    band = fm & ~ftl & (d2 >= 9) & (d2 <= 10)
    img[band] = field_ramp[3]
    if t.get("rough"):
        # chipped edge + a crack and a few dents
        chips = [(-1, 0.30), (1, 0.62), (-1, 0.78), (1, 0.12)]
        for (sd, fy) in chips:
            y = int(top + sh * fy)
            row = np.where(sm[y])[0]
            if len(row):
                x = row[0] if sd < 0 else row[-1]
                img[y, x] = CLEAR
                img[y, x - sd] = ramp[0]
                img[y + 1, x] = ramp[0] if img[y + 1, x, 3] else CLEAR
        for (x, y) in ((int(CX + 6), top + 1), (int(CX + 7), top + 2), (int(CX + 7), top + 3)):
            img[y, x] = ramp[1]
        img[top + sh - 9, int(CX - 9)] = ramp[1]
    return sm, fm


def draw_cheq(img, t, fm):
    """Two rows of 2x2 checks across the top of the field."""
    top = t["top"]
    rows = [r for r in range(S) if fm[r].any()]
    y0 = rows[0] + 1
    for y in range(y0, y0 + 4):
        xs = np.where(fm[y])[0]
        for x in xs[1:-1]:
            on = ((x // 2) + ((y - y0) // 2)) % 2 == 0
            img[y, x] = INK if on else hx("#16171b")
    xs = np.where(fm[y0 + 4])[0]
    for x in xs[1:-1]:
        img[y0 + 4, x] = hx("#0d0e10")
    return y0 + 4


def draw_gem(img, cx, cy, r, gramp):
    """Rhombus cut gem: light top-left facet, dark bottom-right, glint."""
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    m = poly_mask(S, S, pts)
    img[ring_of(m)] = gramp[0]
    yy, xx = np.mgrid[0:S, 0:S]
    u, v = xx + 0.5 - cx, yy + 0.5 - cy
    img[m] = gramp[3]
    img[m & (u < 0) & (v < 0)] = gramp[4]
    img[m & (u >= 0) & (v >= 0)] = gramp[2]
    img[m & (u >= 0) & (v < 0)] = gramp[3]
    img[m & (u < 0) & (v >= 0)] = gramp[3]
    put(img, int(cx - r / 2.5), int(cy - r / 2.5), gramp[5])
    return m


def draw_helmet(img, t, ramp):
    top = t["top"] - t.get("peak", 0)
    cy = top + 2
    dome = ellipse_mask(S, S, CX, cy, 8.5, 8.0) & (np.mgrid[0:S, 0:S][0] < cy)
    bevel(img, dome, ramp, base=3)
    # visor slit
    vis = dome & (np.mgrid[0:S, 0:S][0] >= cy - 4) & (np.mgrid[0:S, 0:S][0] <= cy - 2)
    vis &= np.abs(np.mgrid[0:S, 0:S][1] + 0.5 - CX) < 6.5
    img[vis] = VISOR[2]
    yy = np.mgrid[0:S, 0:S][0]
    img[vis & (yy == cy - 4)] = VISOR[3]
    img[vis & (yy == cy - 2)] = VISOR[1]
    put(img, int(CX - 5), cy - 4, VISOR[5])
    put(img, int(CX - 4), cy - 4, VISOR[4])
    # crest stripe over the top (brand red)
    for y in range(cy - 8, cy - 4):
        for x in (int(CX) - 1, int(CX)):
            if dome[y, x]:
                img[y, x] = BRAND if x == int(CX) - 1 else hx("#b82a26")


def draw_top_crystal(img, t, ramp, gramp):
    """Big cut crystal set in a small metal mount on the shield's peak."""
    top = t["top"] - t.get("peak", 0)
    # mount: short bar in the tier metal
    mt = np.zeros((S, S), bool)
    mt[top - 1:top + 2, int(CX - 6):int(CX + 6)] = True
    bevel(img, mt, ramp, base=3)
    cy = top - 5
    hw, hh = 5.0, 7.5
    pts = [(CX, cy - hh), (CX + hw, cy - hh * 0.35), (CX + hw, cy + hh * 0.30), (CX, cy + hh * 0.85),
           (CX - hw, cy + hh * 0.30), (CX - hw, cy - hh * 0.35)]
    m = poly_mask(S, S, pts)
    img[ring_of(m)] = gramp[0]
    yy, xx = np.mgrid[0:S, 0:S]
    u = xx + 0.5 - CX
    img[m] = gramp[3]
    img[m & (u < -1.5)] = gramp[4]
    img[m & (u > 1.5)] = gramp[2]
    upper = m & (yy + 0.5 < cy - hh * 0.35 + 1)
    img[upper & (u < 0)] = gramp[5]
    img[upper & (u >= 0)] = gramp[3]
    lower = m & (yy + 0.5 > cy + hh * 0.30)
    img[lower & (u < 0)] = gramp[2]
    img[lower & (u >= 0)] = gramp[1]
    put(img, int(CX) - 3, int(cy - 2), gramp[5])
    put(img, int(CX) - 3, int(cy - 1), gramp[5])


def draw_crown(img, t, ramp, gramp):
    n = t["crown"]
    top = t["top"] - t.get("peak", 0)
    by0, by1 = top - 3, top + 1
    hw = 11 if n == 5 else 9
    m = np.zeros((S, S), bool)
    m[by0:by1 + 1, int(CX - hw):int(CX + hw)] = True
    xs = np.linspace(CX - hw + 1.5, CX + hw - 1.5, n)
    tips = []
    for i, x in enumerate(xs):
        hgt = 8 if i == n // 2 else (6 if abs(i - n // 2) == 1 else 4)
        pts = [(x - 2.6, by0 + 0.5), (x, by0 - hgt), (x + 2.6, by0 + 0.5)]
        m |= poly_mask(S, S, pts)
        tips.append((x, by0 - hgt))
    m = mirror_mask(m)
    bevel(img, m, ramp, base=3)
    # band jewels + rim line
    yy, xx = np.mgrid[0:S, 0:S]
    img[m & (yy == by1)] = ramp[1]
    for (x, y) in tips:
        b = ellipse_mask(S, S, x, y, 1.6, 1.6)
        img[ring_of(b) & ~m] = ramp[0]
        img[b] = ramp[5]
    for i in range(n):
        x = xs[i]
        if i != n // 2:
            put(img, int(x), by0 + 2, gramp[3])
            put(img, int(2 * CX - 1 - int(x)), by0 + 2, gramp[3])


def clean(img):
    """Drop isolated opaque pixels (no 4-neighbour)."""
    a = img[..., 3] > 0
    lone = a & ~(nb(a, 1, 0) | nb(a, -1, 0) | nb(a, 0, 1) | nb(a, 0, -1))
    img[lone] = CLEAR
    return img


def make_emblem(t):
    img = canvas(S, S)
    ramp = tramp(t["col"])
    trim = GOLD_TRIM if t.get("trim") else ramp
    field = tramp(t["field"]) if t.get("field") else ramp
    field_ramp = [field[0], field[0], field[1], field[2], field[3], field[4]]
    if t["name"] == "challenger":
        field_ramp = field
    if t.get("tyre"):
        draw_tyre(img, t, ramp)
    if t.get("wings"):
        draw_wings(img, t, trim if t["name"] == "challenger" else ramp)
    if t.get("laurel"):
        draw_laurel(img, t, GOLD_TRIM if t.get("trim") or t["name"] == "gold" else ramp)
    sm, fm = draw_shield(img, t, ramp, field_ramp)
    if t.get("cheq"):
        draw_cheq(img, t, fm)
    gramp = GEM.get(t.get("gem", ""), ramp)
    if t.get("helmet"):
        draw_helmet(img, t, ramp)
    if t.get("topgem"):
        draw_top_crystal(img, t, ramp, gramp)
    if t.get("crown"):
        draw_crown(img, t, trim, gramp)
    if t.get("gem"):
        bottom = max(r for r in range(S) if fm[r].any())
        draw_gem(img, CX, bottom - 4, 2.6, gramp)
    if t.get("sidegems"):
        y = t["top"] + int(t["sh"] * 0.40)
        x = CX - t["sw"] / 2 + 1.5
        draw_gem(img, x, y, 2.0, gramp)
        draw_gem(img, 2 * CX - x, y, 2.0, gramp)
    if t.get("rivets"):
        top, sw, sh = t["top"], t["sw"], t["sh"]
        for (x, y) in ((CX - sw / 2 + 1.5, top + 1.5), (CX + sw / 2 - 2.5, top + 1.5),
                       (CX - 0.5, top + sh - 2.5)):
            put(img, int(x), int(y), ramp[5])
            put(img, int(x) + 1, int(y) + 1, ramp[1])
    return clean(img)


def make_unranked():
    t = dict(sw=30, sh=35, top=16, peak=2)
    img = canvas(S, S)
    g = tramp("#6e6f78")
    sm = poly_mask(S, S, shield_pts(t))
    inner = erode(sm, 2)
    img[ring_of(sm)] = g[0]
    img[sm & ~inner] = g[3]
    tl = sm & (~nb(sm, 0, -1) | ~nb(sm, -1, 0))
    img[tl] = g[4]
    img[inner] = (29, 31, 35, 200)
    img[inner & ring_of(erode(sm, 3), True) & ~erode(sm, 3)] = g[0]
    # big "?" (2x pixels)
    q = ["01110", "10001", "00001", "00110", "00100", "00000", "00100"]
    x0, y0 = int(CX) - 5, 22
    for j, row in enumerate(q):
        for i, b in enumerate(row):
            if b == "1":
                rect(img, x0 + i * 2 + 1, y0 + j * 2 + 1, x0 + i * 2 + 2, y0 + j * 2 + 2, g[0])
    for j, row in enumerate(q):
        for i, b in enumerate(row):
            if b == "1":
                rect(img, x0 + i * 2, y0 + j * 2, x0 + i * 2 + 1, y0 + j * 2 + 1, g[4])
    return clean(img)


# --------------------------------------------------------------------------
# medals
# --------------------------------------------------------------------------

MEDALS = {
    "bronze": tramp("#c98a5a"),
    "silver": tramp("#c6c8d0"),
    "gold": tramp("#f2c230"),
}
RIB = [hx("#3a0c10"), hx("#7a1a1d"), hx("#b82a26"), hx("#e8352b"), hx("#ff6a4a")]


def draw_medal(img, cx, top, r, ramp, rib_h, star=True):
    """Ribbon (brand red V with a chequered centre stripe) + disc medal.
    cx is the mirror axis (between pixels), top the ribbon's top row."""
    H, W = img.shape[:2]
    rw = max(4, int(r * 0.9))
    yy, xx = np.mgrid[0:H, 0:W]
    # ribbon: one band in brand red, notched V at the bottom (behind the disc)
    pts = [(cx - rw, top), (cx + rw, top), (cx + rw - 1, top + rib_h + 1), (cx, top + rib_h + 3),
           (cx - rw + 1, top + rib_h + 1)]
    rm = poly_mask(W, H, pts)
    img[ring_of(rm)] = RIB[0]
    img[rm] = RIB[3]
    img[rm & (xx + 0.5 < cx - rw + 1.5)] = RIB[4]
    img[rm & (xx + 0.5 > cx + rw - 1.5)] = RIB[2]
    # fold shadow where the band tucks behind the disc
    img[rm & (yy == top + rib_h)] = RIB[2]
    # chequered stripe down the middle: 2 px wide, 1 px checks
    for y in range(top, top + rib_h + 1):
        for x in (int(cx) - 1, int(cx)):
            if rm[y, x]:
                img[y, x] = INK if (x + y) % 2 == 0 else hx("#16171b")
    # ring (loop) + disc
    cy = top + rib_h + r - 0.5
    disc = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) <= r
    img[ring_of(disc, True) & ~rm] = ramp[0]
    img[ring_of(disc)] = ramp[0]
    img[disc] = ramp[3]
    d = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy)
    u, v = (xx + 0.5 - cx) / r, (yy + 0.5 - cy) / r
    rimm = disc & (d > r - 1.6)
    img[rimm & (u + v < -0.3)] = ramp[5]
    img[rimm & (u + v > 0.3)] = ramp[1]
    face = disc & (d <= r - 1.6)
    img[face] = ramp[3]
    img[face & (u + v < -0.7)] = ramp[4]
    img[face & (u + v > 0.55)] = ramp[2]
    if star:
        # engraved star from a hand-set 5x5 glyph: dark recess, lit lower-right lip
        g = ["00100", "11111", "01110", "01010", "10001"]
        sx, sy = int(cx) - 2, int(round(cy)) - 2
        for j, row in enumerate(g):
            for i, b in enumerate(row):
                if b == "1":
                    put(img, sx + i + 1, sy + j + 1, ramp[5])
        for j, row in enumerate(g):
            for i, b in enumerate(row):
                if b == "1":
                    put(img, sx + i, sy + j, ramp[1])
    return img


def make_medal_icon(name):
    img = canvas(24, 24)
    draw_medal(img, 12.0, 1, 7.0, MEDALS[name], 7)
    return clean(img)


# --------------------------------------------------------------------------
# medal packs: same pouch from packs.py, re-foiled, with a medal on the plate
# --------------------------------------------------------------------------

FOILS = {
    "bronze": [hx("#2a1610"), hx("#4a2a1c"), hx("#6e4029"), hx("#93593a"), hx("#c98a5a"), hx("#f0c49a")],
    "silver": [hx("#2c2f38"), hx("#454955"), hx("#626775"), hx("#868b98"), hx("#c6c8d0"), hx("#f4f3ee")],
    "gold": [hx("#3d2a08"), hx("#6e4f0e"), hx("#9a7214"), hx("#c99a1e"), hx("#f2c230"), hx("#fff0a8")],
}


def make_medal_pouch(name, open_top=False):
    old = packs.FOIL
    packs.FOIL = FOILS[name]
    try:
        img = packs.make_pouch(open_top=False)
        # repaint the DEV/PACK plate: medal on the left, tier word + PACK right
        rect(img, 18, 39, 77, 73, packs.OUT)
        rect(img, 19, 40, 76, 72, hx("#15161a"))
        rect(img, 19, 40, 76, 40, FOILS[name][3])
        m = canvas(96, 112)
        draw_medal(m, 30.0, 41, 9.0, MEDALS[name], 9)
        alpha_over(img, m)
        word = name.upper()
        ramp = MEDALS[name]
        wx = 58 - text_width(word, F5) // 2
        draw_text(img, wx + 1, 48, word, ramp[0], F5)
        draw_text(img, wx, 47, word, ramp[4], F5)
        wx2 = 58 - text_width("PACK", F5) // 2
        draw_text(img, wx2 + 1, 58, "PACK", packs.RED[0], FONT5)
        draw_text(img, wx2, 57, "PACK", INK, FONT5)
        for (bx, by) in ((21, 42), (74, 42), (21, 70), (74, 70)):
            put(img, bx, by, FOILS[name][4])
        if open_top:
            img = packs.tear_open(img)
        return img
    finally:
        packs.FOIL = old


# --------------------------------------------------------------------------
# PROMOTED banner
# --------------------------------------------------------------------------

def make_rank_up():
    W, H = 128, 32
    img = canvas(W, H)
    R = [hx("#3a0c10"), hx("#7a1a1d"), hx("#b82a26"), hx("#e8352b"), hx("#ff6a4a"), hx("#ffb39a")]
    # tails (folded back, darker) behind the main band
    for side in (-1, 1):
        pts = [(64 + side * 50, 11), (64 + side * 63.5, 11), (64 + side * 58, 18.5),
               (64 + side * 63.5, 26), (64 + side * 50, 26)]
        m = poly_mask(W, H, pts)
        img[ring_of(m)] = R[0]
        img[m] = R[2]
        yy = np.mgrid[0:H, 0:W][0]
        img[m & (yy == 11)] = R[3]
        img[m & (yy == 26)] = R[1]
        # fold shadow triangle
        fp = [(64 + side * 50, 22), (64 + side * 56, 26), (64 + side * 50, 26)]
        fm = poly_mask(W, H, fp)
        img[fm] = R[0]
    # main band
    band = np.zeros((H, W), bool)
    band[5:23, 12:116] = True
    img[ring_of(band)] = R[0]
    img[band] = R[3]
    yy, xx = np.mgrid[0:H, 0:W]
    img[band & (yy == 5)] = R[5]
    img[band & (yy == 6)] = R[4]
    img[band & (yy == 22)] = R[1]
    img[band & (yy == 21)] = R[2]
    img[band & (xx == 12)] = R[4]
    img[band & (xx == 115)] = R[2]
    # chequered edge strips
    for x in range(14, 114):
        for y in (8, 9):
            img[y, x] = INK if ((x // 2 + (y - 8) // 2) % 2 == 0) else hx("#16171b")
        for y in (18, 19):
            img[y, x] = INK if ((x // 2 + (y - 18) // 2) % 2 == 0) else hx("#16171b")
    # wipe a plate for the text
    rect(img, 18, 8, 109, 19, R[3])
    rect(img, 18, 8, 109, 8, R[4])
    # text: 1x FONT5 is 7 px tall, plate is 12 px -> centred at y=10
    word = "PROMOTED"
    tw = text_width(word, FONT5, gap=2)
    x0 = 64 - tw // 2
    draw_text(img, x0 + 1, 11, word, R[0], FONT5, gap=2)
    draw_text(img, x0, 10, word, INK, FONT5, gap=2)
    # chevrons pointing up at both ends of the plate
    for (cx_, col) in ((22, GOLD_TRIM[4]), (105, GOLD_TRIM[4])):
        for k, y in enumerate((11, 12, 13)):
            put(img, cx_ - k, y + 2, col)
            put(img, cx_ + k, y + 2, col)
        for k, y in enumerate((14, 15, 16)):
            put(img, cx_ - k, y, GOLD_TRIM[2])
            put(img, cx_ + k, y, GOLD_TRIM[2])
    return clean(img)


# --------------------------------------------------------------------------
# contact sheet
# --------------------------------------------------------------------------

def label(text, col=INK2):
    t = canvas(text_width(text.upper()) + 2, 6)
    draw_text(t, 0, 0, text.upper(), col)
    return t


def badge32(img):
    """64 -> 32 px badge: each 2x2 block takes its most common colour
    (transparent only when 3+ of the 4 pixels are). Keeps outlines and gems
    that a plain nearest 1/2 would drop."""
    h, w = img.shape[:2]
    out = canvas(w // 2, h // 2)
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            blk = [tuple(int(v) for v in img[y + j, x + i]) for j in (0, 1) for i in (0, 1)]
            opaque = [c for c in blk if c[3] > 0]
            if len(opaque) < 2:
                continue
            best = max(opaque, key=lambda c: (opaque.count(c), -sum(c[:3])))
            out[y // 2, x // 2] = best
    return clean(out)


def build_sheet(emblems, medals, pouches, banner):
    """Everything at 3x on the UI background, plus a true 1x strip at the end."""
    K = 3
    names = [t["name"] for t in TIERS] + ["unranked"]
    W = 12 + 11 * (64 + 8)
    sheet = canvas(W, 600)
    sheet[...] = BG
    y = 4
    draw_text(sheet, 4, y, "RANKED - TIER EMBLEMS 64PX", INK)
    y += 8
    for i, n in enumerate(names):
        x = 6 + i * 72
        alpha_over(sheet, emblems[n], x, y)
        draw_text(sheet, x, y + 66, n.upper()[:11], INK2)
    y += 76
    draw_text(sheet, 4, y, "BADGE_ 32PX AND A 32PX CENTRE CROP WITH A MOCK NUMERAL", INK)
    y += 8
    for i, n in enumerate(names):
        x = 6 + i * 72
        alpha_over(sheet, badge32(emblems[n]), x, y)
        e = emblems[n].copy()
        if n != "unranked":
            mock_numeral(e, ["IV", "III", "II", "I"][i % 4])
        alpha_over(sheet, e[16:48, 16:48].copy(), x + 34, y)
    y += 36
    draw_text(sheet, 4, y, "NUMERAL ZONE MOCK - THE UI DRAWS THE NUMERAL", INK)
    y += 8
    for i, n in enumerate(names[:10]):
        x = 6 + i * 72
        e = emblems[n].copy()
        mock_numeral(e, ["IV", "III", "II", "I"][i % 4])
        alpha_over(sheet, e, x, y)
    y += 70
    draw_text(sheet, 4, y, "MEDALS 24PX AND PROMOTED BANNER 128X32", INK)
    y += 8
    for i, n in enumerate(["bronze", "silver", "gold"]):
        alpha_over(sheet, medals[n], 6 + i * 30, y)
    alpha_over(sheet, banner, 110, y)
    y += 40
    draw_text(sheet, 4, y, "MEDAL PACKS 96X112 - CLOSED  SHAKE 1  SHAKE 2  OPEN", INK)
    y += 8
    for i, n in enumerate(["bronze", "silver", "gold"]):
        for j, k in enumerate(["closed", "shake_1", "shake_2", "open"]):
            alpha_over(sheet, pouches[(n, k)], 6 + j * 100 + (i % 2) * 400, y + (i // 2) * 116)
    y += 2 * 116
    big = scale(sheet[:y], K)
    # 1x strip so the real size can be judged on the same sheet
    strip = canvas(big.shape[1], 64 + 30)
    strip[...] = BG
    t = canvas(200, 6)
    draw_text(t, 0, 0, "ACTUAL SIZE 1X", INK)
    alpha_over(strip, scale(t, 2), 12, 4)
    for i, n in enumerate(names):
        alpha_over(strip, emblems[n], 12 + i * 70, 22)
        alpha_over(strip, badge32(emblems[n]), 800 + i * 36, 22)
    for i, n in enumerate(["bronze", "silver", "gold"]):
        alpha_over(strip, medals[n], 1210 + i * 28, 22)
    alpha_over(strip, banner, 1300, 22)
    return np.concatenate([big, strip], axis=0)


def mock_numeral(img, s):
    """Mock the UI's division numeral in the field centre (sheet only)."""
    w = text_width(s, FONT5, gap=1)
    x0 = 32 - (w + 1) // 2
    y0 = 31
    draw_text(img, x0 + 1, y0 + 1, s, (8, 9, 11, 255), FONT5)
    draw_text(img, x0, y0, s, INK, FONT5)


def build():
    """Write every ranked sprite and the contact sheet; return the paths."""
    paths = []
    out = {}
    for t in TIERS:
        img = make_emblem(t)
        out[t["name"]] = img
        paths.append(save(img, "ranked", f"emblem_{t['name']}.png"))
    out["unranked"] = make_unranked()
    paths.append(save(out["unranked"], "ranked", "emblem_unranked.png"))
    for n, img in out.items():
        paths.append(save(badge32(img), "ranked", f"badge_{n}.png"))
    medals = {}
    for n in MEDALS:
        medals[n] = make_medal_icon(n)
        paths.append(save(medals[n], "ranked", f"medal_{n}.png"))
    pouches = {}
    for n in MEDALS:
        closed = make_medal_pouch(n)
        pouches[(n, "closed")] = closed
        pouches[(n, "shake_1")] = packs.skew(closed, 0.035, squash=3)
        pouches[(n, "shake_2")] = packs.skew(closed, -0.035, squash=1)
        pouches[(n, "open")] = make_medal_pouch(n, open_top=True)
        paths.append(save(closed, "ranked", f"pack_closed_{n}.png"))
        paths.append(save(pouches[(n, "shake_1")], "ranked", f"pack_shake_1_{n}.png"))
        paths.append(save(pouches[(n, "shake_2")], "ranked", f"pack_shake_2_{n}.png"))
        paths.append(save(pouches[(n, "open")], "ranked", f"pack_open_{n}.png"))
    banner = make_rank_up()
    paths.append(save(banner, "ranked", "rank_up.png"))
    sheet = build_sheet(out, medals, pouches, banner)
    paths.append(save(sheet, "ranked", "preview_ranked.png"))
    return paths


if __name__ == "__main__":
    written = build()
    print(f"wrote {len(written)} files, sheet: {written[-1]}")
