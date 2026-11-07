"""Track surface textures: grass, asphalt, run-off, gravel, kerbs, barriers, markings.

Tileable textures wrap on a torus (every scatter and noise is periodic), so a
3x3 tiling shows no seams. u runs along the track, v across it.

    python tools/art/track.py
"""

from __future__ import annotations

import math

import numpy as np

from pixel import (
    CLEAR, RED_RAMP, SHADOW, SPRITES, STEEL_RAMP, WHITE_RAMP, blend, canvas, clean_orphans, disc_mask, fbm, hx,
    palette_map, poisson_torus, px, quantize, rect, rng, save, shift, value_noise, with_alpha,
)

OUT = SPRITES / "track"


# --------------------------------------------------------------------------
# Grass
# --------------------------------------------------------------------------

# Tuft stamps: h = blade highlight (warm), m = mid blade, d = blade shadow (cool)
TUFTS = [
    ["h.h",
     "mhm",
     ".dd"],
    [".h..",
     "hmh.",
     ".mmd",
     "..d."],
    ["h..h",
     ".hm.",
     ".md."],
    [".h.",
     "hm.",
     ".d."],
    ["h.h.h",
     "mhmhm",
     ".ddd."],
]


def _stamp(idx, x, y, stamp, codes):
    h, w = idx.shape
    for sy, row in enumerate(stamp):
        for sx, ch in enumerate(row):
            if ch in codes:
                idx[(y + sy) % h, (x + sx) % w] = codes[ch]


def make_grass(seed=7, dark=False):
    W = H = 128
    if not dark:
        pal = [
            hx("223d2e"),  # 0 deep shadow (cool)
            hx("2b4733"),  # 1 patch dark
            hx("30503a"),  # 2 stripe A
            hx("36583c"),  # 3 stripe B
            hx("3f6440"),  # 4 blade mid
            hx("4d7244"),  # 5 blade highlight (warm)
            hx("5f8049"),  # 6 rare bright tip
        ]
    else:
        pal = [
            hx("1a3027"),
            hx("213a2c"),
            hx("274232"),
            hx("294533"),
            hx("335239"),
            hx("3f5f3f"),
            hx("4d6a45"),
            hx("2f4430"),  # 7 dry patch (warmer, barely)
            hx("4a5434"),  # 8 unused
            hx("c2ae62"),  # 9 flower yellow
            hx("c9c6bb"),  # 10 flower white
            hx("8f7fae"),  # 11 flower lilac
            hx("6b5a3a"),  # 12 flower centre / shadow warm
        ]
    g = rng(seed)
    idx = np.full((H, W), 2, int)

    if not dark:
        # Mowing stripes: 16 px bands (4 m), the edge wobbles by a pixel now and then.
        wob = (value_noise(W, H, 16, seed + 3) * 2.2).astype(int)
        xs = np.arange(W)[None, :] + wob - 1
        stripe = ((xs // 16) % 2) == 1
        idx[stripe] = 3
    else:
        # two very close base tones in soft clumps (no hard patchwork)
        base = quantize(fbm(W, H, [32, 16], [1, 0.5], seed + 5), 2, dither=1.0)
        idx = 2 + base

    if dark:
        # Faint dry patches: one warm tone, dithered rim, small.
        dry = fbm(W, H, [32, 16], [1, 0.5], seed + 21)
        dq = quantize(np.clip((dry - 0.74) * 5.0, 0, 1), 2, dither=1.0)
        idx = np.where(dq == 1, 7, idx)
        idx = clean_orphans(idx, passes=2)

    # Tufts: clustered where a noise field is high, sparse elsewhere.
    dens = fbm(W, H, [32, 16], [1, 0.5], seed + 31)
    codes = {"h": 5, "m": 4, "d": 0} if not dark else {"h": 5, "m": 4, "d": 0}
    pts = poisson_torus(W, H, 5.0, seed + 41)
    for (fx, fy) in pts:
        x, y = int(fx), int(fy)
        d = dens[y % H, x % W]
        p = 0.08 + 0.85 * max(0.0, d - 0.45) * 2
        if g.random() < p:
            st = TUFTS[int(g.random() * len(TUFTS))]
            _stamp(idx, x, y, st, codes)
            if g.random() < 0.18:
                idx[y % H, (x + 1) % W] = 6

    # Short grain dashes (mowing direction), very sparse, one shade off the stripe.
    for (fx, fy) in poisson_torus(W, H, 4.0, seed + 51):
        x, y = int(fx), int(fy)
        if idx[y % H, x % W] in (2, 3) and g.random() < 0.35:
            v = idx[y % H, x % W]
            for k in range(2):
                if idx[(y + k) % H, x % W] == v:
                    idx[(y + k) % H, x % W] = v + 1 if v == 2 else v - 1

    if dark:
        # Wildflowers: loose clusters of single blooms, each with a shadow pixel.
        for (fx, fy) in poisson_torus(W, H, 20.0, seed + 61):
            x, y = int(fx), int(fy)
            col = [9, 10, 11, 10][int(g.random() * 4)]
            spots = [(0, 0), (2, 1), (-1, 2), (1, 3), (3, -1)]
            n = 3 + int(g.random() * 3)
            for ox, oy in spots[:n]:
                X, Y = (x + ox) % W, (y + oy) % H
                idx[(Y + 1) % H, (X + 1) % W] = 0
                idx[Y, X] = col

    return palette_map(idx, pal)


# --------------------------------------------------------------------------
# Asphalt
# --------------------------------------------------------------------------


def make_asphalt(seed=3):
    W = H = 128
    pal = [
        hx("222429"),  # 0 deep aggregate shadow
        hx("2d2f34"),  # 1 darker patch
        hx("2f3136"),  # 2 base
        hx("313338"),  # 3 lighter patch
        hx("3a3c42"),  # 4 aggregate lit
        hx("45464b"),  # 5 bright aggregate (warm grey)
        hx("27292e"),  # 6 aggregate mid-shadow
    ]
    g = rng(seed)
    f = fbm(W, H, [64, 32, 16], [1, 0.55, 0.25], seed)
    idx = np.full((H, W), 2, int)
    q = quantize(f, 5, dither=0.9)
    idx = np.where(q == 0, 1, idx)
    idx = np.where(q == 4, 3, idx)
    idx = clean_orphans(idx, passes=3)

    # Aggregate stones: 1-3 px, lit pixel top-left, shadow bottom-right.
    shapes = [
        [(0, 0, "l"), (1, 1, "s")],
        [(0, 0, "l"), (1, 0, "m"), (1, 1, "s"), (2, 1, "s")],
        [(0, 0, "l"), (0, 1, "m"), (1, 1, "s")],
        [(0, 0, "b"), (1, 0, "l"), (1, 1, "s")],
        [(0, 0, "s")],
        [(0, 0, "d"), (1, 0, "d")],
    ]
    for (fx, fy) in poisson_torus(W, H, 3.1, seed + 9):
        x, y = int(fx), int(fy)
        r = g.random()
        if r > 0.78:
            continue
        sh = shapes[int(g.random() * len(shapes))]
        for dx, dy, k in sh:
            code = {"l": 4, "m": 3, "s": 0, "b": 5, "d": 6}[k]
            if k == "b" and g.random() < 0.6:
                code = 4
            idx[(y + dy) % H, (x + dx) % W] = code
    return palette_map(idx, pal)


# --------------------------------------------------------------------------
# Run-off (painted asphalt, blue-grey)
# --------------------------------------------------------------------------


def make_runoff(seed=5):
    W = H = 64
    pal = [
        hx("29323c"),  # 0 shadow speck
        hx("303a45"),  # 1 band dark
        hx("34404b"),  # 2 base
        hx("394651"),  # 3 band light
        hx("43515c"),  # 4 lit speck
    ]
    g = rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    # 45 degree abrasive bands, period 16 px (tiles because 64 % 16 == 0).
    band = ((xx + yy) % 16) < 6
    idx = np.where(band, 3, 2)
    # Thin dark line on the trailing side of each band.
    idx = np.where(((xx + yy) % 16) == 6, 1, idx)
    for (fx, fy) in poisson_torus(W, H, 3.4, seed + 1):
        x, y = int(fx), int(fy)
        if g.random() < 0.55:
            idx[y % H, x % W] = 4
            idx[(y + 1) % H, (x + 1) % W] = 0
        elif g.random() < 0.3:
            idx[y % H, x % W] = 1
    return palette_map(idx, pal)


# --------------------------------------------------------------------------
# Gravel
# --------------------------------------------------------------------------


def make_gravel(seed=11):
    """Pebbles of one warm ramp, low contrast: mid body, lit top-left rim,
    dark bottom-right rim, darker gaps between them."""
    W = H = 64
    gap = hx("5b4d40")
    warm = [hx("66574a"), hx("786754"), hx("8a7861"), hx("a08c70"), hx("b5a083")]
    grey = [hx("635d56"), hx("756e65"), hx("878074"), hx("9c9384"), hx("b0a693")]
    g = rng(seed)
    img = canvas(W, H, gap)
    cover = np.zeros((H, W), bool)
    tone = fbm(W, H, [32, 16], [1, 0.5], seed + 2)
    pts = poisson_torus(W, H, 3.5, seed + 3)
    for (fx, fy) in sorted(pts, key=lambda p: p[1] + p[0] * 0.3):
        greyish = tone[int(fy) % H, int(fx) % W] > 0.66 and g.random() < 0.6
        ramp = grey if greyish or g.random() < 0.06 else warm
        rx = 1.5 + g.random() * 0.8
        ry = 1.2 + g.random() * 0.6
        body = 2 if g.random() < 0.8 else 1
        cx, cy = fx, fy
        x0, y0 = int(math.floor(cx - rx - 1)), int(math.floor(cy - ry - 1))
        cells = []
        for y in range(y0, y0 + int(2 * ry) + 4):
            for x in range(x0, x0 + int(2 * rx) + 4):
                lx = (x + 0.5 - cx) / rx
                ly = (y + 0.5 - cy) / ry
                if lx * lx + ly * ly <= 1.0:
                    cells.append((x, y, lx, ly))
        if not cells:
            continue
        cs = {(x % W, y % H) for x, y, _, _ in cells}
        for x, y, lx, ly in cells:
            X, Y = x % W, y % H
            tl = (X - 1) % W, (Y - 1) % H
            lit = -lx - ly
            k = body
            if lit > 1.0:
                k = body + 2
            elif lit > 0.45:
                k = body + 1
            elif lit < -0.75:
                k = body - 1
            img[Y, X] = ramp[min(k, 4)]
            cover[Y, X] = True
        # contact shadow just below-right of the pebble
        for x, y, _, _ in cells:
            S = ((x + 1) % W, (y + 1) % H)
            if S not in cs and not cover[S[1], S[0]]:
                img[S[1], S[0]] = hx("4e4237")
    return img


# --------------------------------------------------------------------------
# Kerbs
# --------------------------------------------------------------------------


def make_kerb(serrated=False):
    """32 x 12. v=0 is the track side, v=11 the outer (grass) side."""
    W, H = 32, 12
    img = canvas(W, H)
    for u in range(W):
        ramp = RED_RAMP if u < 16 else WHITE_RAMP
        for v in range(H):
            if v == 0:
                c = ramp[2]           # paint edge where it meets the asphalt
            elif v == 1:
                c = ramp[4]           # bevel highlight (lit lip)
            elif v <= 8:
                c = ramp[3]           # flat painted face
            elif v == 9:
                c = ramp[2]
            elif v == 10:
                c = ramp[1]           # outer bevel in shadow
            else:
                c = ramp[0]           # outer drop to the grass
            img[v, u] = c
    # Block ends: paint changes with a 1px softer step so the stripe reads crisply.
    for v in range(1, 9):
        img[v, 15] = RED_RAMP[2]
        img[v, 31] = WHITE_RAMP[2]
    # Rubber wear near the track edge (tyres run over the inner lip)
    wear = [(3, 2), (4, 2), (9, 2), (10, 3), (20, 2), (21, 2), (26, 3), (27, 2), (6, 3), (24, 2)]
    for (u, v) in wear:
        base = RED_RAMP if u < 16 else WHITE_RAMP
        img[v, u] = base[2]
    if serrated:
        # Raised sawtooth band on the outer half: ridges every 4 px across the
        # kerb, each a lit ramp that drops into a dark step.
        for u in range(W):
            ramp = RED_RAMP if u < 16 else WHITE_RAMP
            ph = u % 4
            seq = [ramp[3], ramp[2], ramp[1], ramp[0]] if u < 16 else [ramp[3], ramp[2], ramp[1], ramp[0]]
            img[6, u] = ramp[1]
            for v in range(7, H - 1):
                img[v, u] = seq[ph]
            img[7, u] = ramp[4] if ph == 0 else seq[ph]
            img[H - 1, u] = ramp[0]
    return img


# --------------------------------------------------------------------------
# Barriers
# --------------------------------------------------------------------------

RUBBER = [hx("0d0e10"), hx("17181b"), hx("212226"), hx("2e3035"), hx("43454c"), hx("5c5e66")]


def make_tyre_wall():
    """24 x 10, v=0 = track side conveyor belt, three 8 px tyres behind it."""
    W, H = 24, 10
    img = canvas(W, H)
    # ground gaps between the tyres: the shadow tone
    img[2:, :] = SHADOW
    paint = {2: [hx("5a1820"), hx("8f2027"), hx("c72e28"), hx("e8352b"), hx("f2603f")]}
    yy, xx = np.mgrid[0:H, 0:W]
    for i in range(3):
        cx, cy = 4 + 8 * i, 6.0
        dx = xx + 0.5 - cx
        dy = yy + 0.5 - cy
        d = np.sqrt(dx * dx + dy * dy)
        ring = (d <= 4.0) & (yy >= 2)
        hole = d <= 1.5
        for y, x in zip(*np.nonzero(ring)):
            ang_lit = (-dx[y, x] - dy[y, x]) / max(d[y, x], 0.01)  # +1 at top-left
            if hole[y, x]:
                c = RUBBER[0]
            else:
                ramp = paint.get(i)
                if ramp is not None and 1.5 < d[y, x] <= 3.0:
                    k = 4 if ang_lit > 0.75 else 3 if ang_lit > -0.1 else 2 if ang_lit > -0.75 else 1
                    c = ramp[k]
                else:
                    edge = d[y, x] > 3.2
                    k = 4 if ang_lit > 0.6 else 3 if ang_lit > -0.2 else 2
                    if edge:
                        k = max(1, k - 1)
                    if d[y, x] <= 2.2 and ang_lit < 0:  # inner lip lit on the far side
                        k = 3
                    c = RUBBER[k]
            img[y, x] = c
    # conveyor belt facing the track
    for u in range(W):
        img[0, u] = hx("4a4c54")
        img[1, u] = hx("26272c")
    for u in (3, 11, 19):
        img[1, u] = hx("6e6f78")  # belt bolts
    return img


def make_tecpro():
    """24 x 8, two soft blocks (blue, red); v=0 track side, v=7 drop shadow."""
    W, H = 24, 8
    img = canvas(W, H)
    blue = [hx("1c2f57"), hx("27427a"), hx("3460a6"), hx("4a80c6"), hx("74a6de")]
    red = [hx("5a1820"), hx("8f2027"), hx("c22d28"), hx("e04030"), hx("f2704f")]
    for b, ramp in enumerate([blue, red]):
        x0 = b * 12
        for u in range(12):
            for v in range(7):
                c = ramp[2]
                if v == 0:
                    c = ramp[4]
                elif v == 1:
                    c = ramp[3]
                elif v == 5:
                    c = ramp[1]
                elif v == 6:
                    c = ramp[0]
                if u == 0 and 0 < v < 6:
                    c = ramp[3]
                if u == 11:
                    c = ramp[0] if v > 0 else ramp[1]
                if u == 10 and 0 < v < 6:
                    c = ramp[1]
                img[v, x0 + u] = c
        # printed white label
        for u in range(3, 8):
            img[3, x0 + u] = hx("dcdad4")
        img[3, x0 + 8] = hx("a3a3ad")
        # strap
        img[0, x0 + 11] = hx("17181b")
    # corners rounded
    for x0 in (0, 12):
        img[0, x0] = CLEAR
        img[6, x0] = CLEAR
        img[0, x0 + 11] = CLEAR
        img[6, x0 + 11] = CLEAR
    img[7, :] = SHADOW
    img[6, 0] = SHADOW
    img[6, 12] = SHADOW
    return img


def make_armco():
    """16 x 4 steel guardrail from above; v=0 track side."""
    W, H = 16, 4
    img = canvas(W, H)
    for u in range(W):
        img[0, u] = STEEL_RAMP[3]
        img[1, u] = STEEL_RAMP[2]
        img[2, u] = STEEL_RAMP[1]
        img[3, u] = SHADOW
    img[0, 3] = STEEL_RAMP[4]
    img[0, 11] = STEEL_RAMP[4]
    # bolts at the post every 16 px
    img[1, 7] = STEEL_RAMP[4]
    img[1, 8] = STEEL_RAMP[1]
    # post behind the rail
    for u in (7, 8):
        img[3, u] = STEEL_RAMP[0]
    img[3, 6] = STEEL_RAMP[1]
    return img


def make_fence():
    """16 x 6 catch fence from above (mesh suggested), post every 16 px."""
    W, H = 16, 6
    img = canvas(W, H)
    mesh = with_alpha(hx("9da1a8"), 120)
    for u in range(W):
        img[0, u] = with_alpha(hx("b9bec6"), 235)
        img[5, u] = with_alpha(hx("5d626d"), 235)
        for v in range(1, 5):
            if (u + v) % 4 == 0 or (u - v) % 4 == 0:
                img[v, u] = mesh
    for v in range(H):
        img[v, 0] = hx("c9ccd2") if v < 3 else hx("8a909b")
        img[v, 1] = hx("4f535d")
    return img


# --------------------------------------------------------------------------
# Markings
# --------------------------------------------------------------------------


def make_racing_line(seed=17):
    W = H = 16
    img = canvas(W, H)
    col = (10, 10, 12)
    prof = [0, 0, 0, 1, 2, 2, 3, 3, 3, 3, 2, 2, 1, 0, 0, 0]
    alpha = [0, 30, 50, 66]
    bay = np.array([[0, 2], [3, 1]])
    for v in range(H):
        for u in range(W):
            lv = prof[v]
            # dither the outer step so the band edge feathers without a gradient
            if lv == 0 and v in (2, 13):
                lv = 1 if bay[v % 2, u % 2] in (0, 3) else 0
            if lv:
                img[v, u] = (*col, alpha[lv])
    # longitudinal rubber streaks
    for v, gaps in [(6, {3, 4}), (9, {11, 12, 13}), (7, {14})]:
        for u in range(W):
            if u not in gaps:
                img[v, u] = (*col, 80)
    return img


def make_start_grid():
    """32 x 16; cars drive towards +u. Front line across the lane, short side marks."""
    W, H = 32, 16
    img = canvas(W, H)
    paint = with_alpha(hx("ebe8e1"), 235)
    worn = with_alpha(hx("ebe8e1"), 170)
    for v in range(2, 14):
        img[v, 26] = paint
        img[v, 27] = paint
    for u in range(16, 28):
        img[2, u] = paint
        img[13, u] = paint
    for (u, v) in [(26, 6), (27, 9), (20, 2), (23, 13), (26, 11)]:
        img[v, u] = worn
    return img


def make_start_line():
    W = H = 16
    img = canvas(W, H)
    white = hx("ebe8e1")
    white2 = hx("d2cfc8")
    black = hx("1c1d21")
    black2 = hx("26272c")
    for v in range(H):
        for u in range(W):
            img[v, u] = white if ((u // 4) + (v // 4)) % 2 == 0 else black
    for (u, v) in [(1, 2), (2, 2), (9, 6), (6, 9), (13, 13), (5, 14), (10, 1), (14, 10)]:
        img[v, u] = white2 if ((u // 4) + (v // 4)) % 2 == 0 else black2
    return img


def make_skid():
    a = canvas(4, 4)
    c = (12, 12, 14)
    vals = [[0, 50, 50, 0], [50, 110, 110, 50], [50, 110, 110, 50], [0, 50, 50, 0]]
    for y in range(4):
        for x in range(4):
            if vals[y][x]:
                a[y, x] = (*c, vals[y][x])
    return a


def build():
    out = {
        "grass.png": make_grass(),
        "grass_dark.png": make_grass(seed=19, dark=True),
        "asphalt.png": make_asphalt(),
        "runoff.png": make_runoff(),
        "gravel.png": make_gravel(),
        "kerb.png": make_kerb(),
        "kerb_inside.png": make_kerb(serrated=True),
        "tyre_wall.png": make_tyre_wall(),
        "tecpro.png": make_tecpro(),
        "armco.png": make_armco(),
        "fence.png": make_fence(),
        "racing_line.png": make_racing_line(),
        "start_grid.png": make_start_grid(),
        "start_line.png": make_start_line(),
        "skid.png": make_skid(),
    }
    for name, img in out.items():
        save(img, OUT / name)
    return out


if __name__ == "__main__":
    for k in build():
        print("wrote", OUT / k)
