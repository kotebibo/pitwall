"""Trackside decorations seen from above (1 px = 0.25 m), light from the top-left.

Trees, bushes, tents and small props have their shadow baked in (offset to
the bottom-right). Big rotatable props (grandstands, pit building, billboards,
gantry) get a separate *_shadow.png silhouette of the same size, meant to be
drawn under the sprite at a fixed world offset of (+1 m, +1 m).

    python tools/art/deco.py
"""

from __future__ import annotations

import math

import numpy as np

from pixel import (
    CLEAR, CONCRETE, RED_RAMP, SHADOW, SPRITES, STEEL_RAMP, UI, WHITE_RAMP, alpha_mask, blend, canvas,
    clean_orphans, dilate, disc_mask, draw_text, erode, hx, mix, outline, palette_map, poisson_torus, px,
    quantize, rect, rng, save, shade_height, shadow_only, shift, text_width, with_alpha,
)

OUT = SPRITES / "deco"


# --------------------------------------------------------------------------
# Trees and bushes
# --------------------------------------------------------------------------

TREE_RAMPS = {
    "green": ["16271f", "1d3427", "27452d", "335a33", "44703a", "5d8a45", "7aa252"],
    "olive": ["1f2a1c", "2a3a22", "37502a", "476632", "5a7d3a", "759748", "93b05a"],
    "deep": ["111f1b", "172a22", "1f3a2b", "294b32", "365e3a", "4a7645", "64904f"],
    "pine": ["0f201d", "142a24", "1b382c", "244834", "2f5a3c", "3f6f47", "578a55"],
    "pine2": ["0e1c1c", "132623", "19332b", "214131", "2b5139", "3a6443", "4f7d4e"],
}


def _ramp(name):
    return [hx(c) for c in TREE_RAMPS[name]]


def _shade_to_ramp(lit, mask, ramp, thresholds):
    idx = np.zeros(lit.shape, int)
    for t in thresholds:
        idx += (lit > t).astype(int)
    idx = np.clip(idx + 1, 1, len(ramp) - 1)
    idx[~mask] = 0
    return idx


def _finish_canopy(idx, mask, ramp, offset):
    idx = clean_orphans(np.where(mask, idx, -1), wrap=False, passes=2)
    mask = idx >= 0
    img = canvas(*mask.shape[::-1])
    img[mask] = np.array(ramp, np.uint8)[np.clip(idx[mask], 0, len(ramp) - 1)]
    edge = mask & ~erode(mask)
    lit_side = edge & (~shift(mask, 1, 0) | ~shift(mask, 0, 1)) & shift(mask, -1, 0) & shift(mask, 0, -1)
    img[edge & ~lit_side] = ramp[0]
    img[lit_side & (idx <= 1)] = ramp[1]
    sm = shift(mask, offset[0], offset[1]) & ~mask
    img[sm] = SHADOW
    return img


def _lit(nx, ny, nz):
    ln = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-9
    L = np.array([-0.62, -0.62, 0.48])
    L = L / np.linalg.norm(L)
    return (nx * L[0] + ny * L[1] + nz * L[2]) / ln


def tree_canopy(size, clumps, ramp_name, seed, leaf_r=3.0, leaf_n=3.4, offset=(3, 4)):
    """Deciduous canopy: big clump spheres give the form, leaf clusters (small
    spheres) give the texture; light mixes both, then snaps to the ramp."""
    g = rng(seed)
    S = size
    yy, xx = np.mgrid[0:S, 0:S].astype(float)
    macro = np.full((S, S), -1e9)
    for (cx, cy, r) in clumps:
        d2 = (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2
        macro = np.maximum(macro, np.where(d2 <= r * r, np.sqrt(np.maximum(r * r - d2, 0)) + r * 0.4, -1e9))
    inside = macro > -1e8
    mh = np.where(inside, macro, 0)
    gy, gx = np.gradient(mh)
    macro_lit = _lit(-gx, -gy, np.ones_like(mh) * 1.2)
    # leaf clusters
    best = np.full((S, S), -1e9)
    micro = np.zeros((S, S))
    ring = np.zeros((S, S))
    pts = poisson_torus(S, S, leaf_n, seed + 1)
    g.shuffle(pts)
    for (px_, py_) in pts:
        ix, iy = min(S - 1, int(px_)), min(S - 1, int(py_))
        if not inside[iy, ix]:
            continue
        r = leaf_r * (0.85 + g.random() * 0.35)
        dx = xx + 0.5 - px_
        dy = yy + 0.5 - py_
        d2 = dx * dx + dy * dy
        cap = np.sqrt(np.maximum(r * r - d2, 0))
        h = np.where(d2 <= r * r, mh[iy, ix] + cap * 0.8, -1e9)
        win = h > best
        best = np.where(win, h, best)
        micro = np.where(win, _lit(dx, dy, cap + 0.6), micro)
        ring = np.where(win, np.sqrt(d2) / r, ring)
    mask = best > -1e8
    lit = 0.6 * np.where(inside, macro_lit, macro_lit.min()) + 0.55 * micro
    # cluster rims on the shadow side read as the gaps between leaf clumps
    lit = lit - 0.18 * (ring > 0.82) * (micro < 0.45)
    ramp = _ramp(ramp_name)
    q = np.zeros((S, S), int)
    for t in [0.05, 0.3, 0.5, 0.68, 0.84]:
        q += (lit > t).astype(int)
    q = np.clip(q + 1, 1, len(ramp) - 1)
    return _finish_canopy(q, mask, ramp, offset)


def pine_canopy(size, R, branches, ramp_name, seed, tiers=3, offset=(4, 5)):
    """Conifer from above: tiers of pointed branches, each a ridge lit on the
    side facing the top-left."""
    g = rng(seed)
    S = size
    yy, xx = np.mgrid[0:S, 0:S].astype(float)
    cx = cy = (S - offset[0]) / 2
    dx, dy = xx + 0.5 - cx, yy + 0.5 - cy
    d = np.sqrt(dx * dx + dy * dy) + 1e-6
    th = np.arctan2(dy, dx)
    best = np.full((S, S), -1e9)
    lit = np.zeros((S, S))
    for t in range(tiers):
        Rt = R * (1 - 0.3 * t)
        n = max(5, branches - 2 * t)
        off = g.random() * 2 * math.pi
        for k in range(n):
            a = off + 2 * math.pi * k / n + (g.random() - 0.5) * 0.25
            L = Rt * (0.88 + g.random() * 0.14)
            da = np.angle(np.exp(1j * (th - a)))
            perp = d * np.sin(da)
            along = d * np.cos(da)
            width = np.clip(1 - along / L, 0, 1) ** 0.8 * (Rt * 2.1 * math.pi / n) + 0.5
            cov = (along > -1) & (along <= L) & (np.abs(perp) <= width)
            h = 3.0 * t + (L - along) * 0.5 + (width - np.abs(perp)) * 0.7
            win = cov & (h > best)
            best = np.where(win, h, best)
            rx, ry = math.cos(a), math.sin(a)
            side = np.sign(perp)
            nx = rx * 0.55 + (-ry) * side * 0.9
            ny = ry * 0.55 + (rx) * side * 0.9
            lit = np.where(win, _lit(nx, ny, 1.0) + 0.06 * t, lit)
        core = d <= Rt * 0.32
        h = 3.0 * t + Rt
        win = core & (h > best)
        best = np.where(win, h, best)
        lit = np.where(win, _lit(dx / d * 0.4, dy / d * 0.4, 1.0) + 0.06 * t, lit)
    mask = best > -1e8
    ramp = _ramp(ramp_name)
    q = np.zeros((S, S), int)
    for t in [-0.05, 0.25, 0.5, 0.7, 0.86]:
        q += (lit > t).astype(int)
    q = np.clip(q + 1, 1, len(ramp) - 1)
    q = np.where(d < 1.2, len(ramp) - 1, q)
    return _finish_canopy(q, mask, ramp, offset)


def make_trees():
    out = {}
    # tree_1: classic round deciduous, 40 px
    out["tree_1.png"] = tree_canopy(40, [(17, 17, 12), (12, 21, 8), (22, 12, 8), (21, 22, 8)], "green", 101)
    # tree_2: lighter olive, irregular, 34 px
    out["tree_2.png"] = tree_canopy(34, [(14, 15, 9), (20, 12, 7), (10, 20, 6), (19, 20, 7)], "olive", 202,
                                    leaf_r=2.7, leaf_n=3.0)
    # tree_3: big dark oak, 48 px
    out["tree_3.png"] = tree_canopy(48, [(21, 21, 15), (13, 25, 9), (27, 13, 9), (29, 27, 9), (16, 13, 8), (22, 31, 8)],
                                    "deep", 303, leaf_r=3.6, leaf_n=4.0, offset=(4, 5))
    # tree_4: pine, 32 px
    out["tree_4.png"] = pine_canopy(32, 12.5, 12, "pine", 404, tiers=3, offset=(4, 5))
    # tree_5: tall dark pine, 44 px
    out["tree_5.png"] = pine_canopy(44, 17.5, 15, "pine2", 505, tiers=4, offset=(5, 6))
    # bushes
    out["bush_1.png"] = tree_canopy(14, [(6, 6.5, 4.6), (8.5, 7.5, 3.5)], "green", 601, leaf_r=2.0, leaf_n=2.4,
                                    offset=(2, 2))
    out["bush_2.png"] = tree_canopy(16, [(6, 7, 4.2), (9.5, 6, 3.6), (8, 9.5, 3.5)], "olive", 602, leaf_r=2.0,
                                    leaf_n=2.5, offset=(2, 2))
    out["bush_3.png"] = tree_canopy(12, [(5, 5.5, 3.6), (6.5, 5, 3.4)], "deep", 603, leaf_r=2.1, leaf_n=2.2, offset=(2, 2))
    return out


# --------------------------------------------------------------------------
# Crowd helpers
# --------------------------------------------------------------------------

SHIRTS = [hx(c) for c in ["c9342b", "d8d4cc", "d9ad2f", "4fa9c4", "37a85c", "8f4fd0", "d06a2c", "34363c",
                          "3d68b0", "b5466d", "e8e2d0", "6a6f7a", "e8352b", "f2c230"]]
SKIN = [hx(c) for c in ["e0b48f", "c99470", "9c6644", "6b4430"]]
HAIR = [hx(c) for c in ["2a2420", "4a3424", "1c1d21", "8a6a3a"]]
CAPS = [hx(c) for c in ["e8352b", "f2c230", "f1efea", "1d1f23", "5ec8e5"]]
# mute the crowd so it reads as texture, not confetti (dusk light)
SHIRTS = [mix(c, hx("3a3c46"), 0.32) for c in SHIRTS]
CAPS = [mix(c, hx("3a3c46"), 0.25) for c in CAPS]


def _dark(c, k=0.72):
    return (int(c[0] * k), int(c[1] * k * 1.02), int(min(255, c[2] * k * 1.1)), c[3])


def _light(c, k=1.18):
    return (min(255, int(c[0] * k + 8)), min(255, int(c[1] * k + 6)), min(255, int(c[2] * k)), c[3])


def person(img, x, y, g, wrap=False):
    """3 x 2 spectator from above: shirt shoulders, head in the middle."""
    shirt = SHIRTS[int(g.random() * len(SHIRTS))]
    r = g.random()
    if r < 0.25:
        head = CAPS[int(g.random() * len(CAPS))]
    elif r < 0.7:
        head = HAIR[int(g.random() * len(HAIR))]
    else:
        head = SKIN[int(g.random() * len(SKIN))]
    px(img, x, y, _light(shirt), wrap)
    px(img, x + 1, y, head, wrap)
    px(img, x + 2, y, shirt, wrap)
    px(img, x, y + 1, shirt, wrap)
    px(img, x + 1, y + 1, shirt, wrap)
    px(img, x + 2, y + 1, _dark(shirt), wrap)
    if g.random() < 0.12:  # a raised arm
        px(img, x + 3, y - 1, SKIN[int(g.random() * 4)], wrap)


def darken_region(img, x0, y0, x1, y1, k=0.62):
    sub = img[y0:y1, x0:x1].astype(np.float32)
    sub[..., 0] *= k
    sub[..., 1] *= k
    sub[..., 2] *= min(1.0, k * 1.12)
    img[y0:y1, x0:x1] = sub.astype(np.uint8)


def drop_shadow_baked(img, dx, dy):
    m = alpha_mask(img, 127)
    sm = shift(m, dx, dy) & ~m
    out = img.copy()
    out[sm] = SHADOW
    return out


# --------------------------------------------------------------------------
# Sponsor strips (fictional sponsors only)
# --------------------------------------------------------------------------

SPONSORS = {
    "pitwall": dict(text="PIT WALL", bg=[hx("a8242a"), hx("d23129"), hx("e8463a")], fg=hx("f8f5ec"), mark="chq"),
    "kura": dict(text="KURA ENERGY", bg=[hx("b8861e"), hx("e0b02a"), hx("f2c64a")], fg=hx("17181b"), mark="bolt"),
    "mtkvari": dict(text="MTKVARI TELECOM", bg=[hx("15304f"), hx("1f4470"), hx("2b5a8c")], fg=hx("7fd6ee"),
                    mark="wave"),
    "geofuel": dict(text="GEO FUEL", bg=[hx("101a14"), hx("17261c"), hx("1f3326")], fg=hx("3ecf6a"), mark="drop"),
}

MARKS = {
    "bolt": ["..#", ".#.", "###", ".#.", "#.."],
    "drop": [".#.", ".#.", "###", "###", ".#."],
    "wave": [".....", ".#...", "#.#.#", "...#.", "....."],
}


def sponsor_panel(w, key, h=5):
    """A w x h sponsor face: logo mark + name centred, no frame."""
    sp = SPONSORS[key]
    img = canvas(w, h, sp["bg"][1])
    tw = text_width(sp["text"])
    mark = sp["mark"]
    mw = 0 if mark == "chq" else len(MARKS[mark][0]) + 2
    x = (w - tw - mw) // 2
    if mark != "chq":
        for yy, row in enumerate(MARKS[mark]):
            for xx, ch in enumerate(row):
                if ch == "#":
                    px(img, x + xx, yy + (h - 5) // 2, sp["fg"])
        x += mw
    draw_text(img, x, (h - 5) // 2, sp["text"], sp["fg"])
    if mark == "chq" and w >= tw + 20:
        for cx0 in (2, w - 8):
            for yy in range(h):
                for xx in range(6):
                    px(img, cx0 + xx, yy, hx("f8f5ec") if (xx + yy) % 2 == 0 else hx("17181b"))
    return img


# --------------------------------------------------------------------------
# Grandstands
# --------------------------------------------------------------------------


def make_grandstand(W, seed, sponsors):
    """Top = back of the stand (under the roof), bottom = the track side."""
    H = 56
    g = rng(seed)
    img = canvas(W, H)
    c_step = hx("6f727a")
    c_floor = hx("2c2e34")
    seat = hx("2c4f8a")
    for r in range(11):
        y0 = 2 + r * 4
        rect(img, 2, y0, W - 2, y0 + 1, c_step)
        rect(img, 2, y0 + 1, W - 2, y0 + 3, seat)
        rect(img, 2, y0 + 3, W - 2, y0 + 4, c_floor)
        for x in range(3, W - 5, 3):
            if g.random() < 0.88:
                person(img, x + (1 if r % 2 else 0), y0 + 1, g)
            else:
                px(img, x + 1, y0 + 1, hx("4a72b0"))
    # aisles with stairs
    aisles = list(range(46, W - 8, 48))
    for ax in aisles:
        for y in range(2, 46):
            for x in range(ax, ax + 4):
                img[y, x] = hx("8d8f94") if y % 2 == 0 else hx("6f727a")
            img[y, ax] = hx("a9a8a5") if y % 2 == 0 else hx("8d8f94")
            img[y, ax + 3] = hx("555960")
    # end walls
    for y in range(0, 46):
        img[y, 0] = hx("8d8f94")
        img[y, 1] = hx("6f727a")
        img[y, W - 2] = hx("555960")
        img[y, W - 1] = hx("3e4148")
    # roof over the top rows, and the shadow it throws on the seats below
    roof_h = 15
    darken_region(img, 2, roof_h, W - 2, roof_h + 2, 0.6)
    darken_region(img, 2, roof_h + 2, W - 2, roof_h + 3, 0.8)
    roof = [hx("4c505a"), hx("5d626d"), hx("737885"), hx("8a909b"), hx("a7acb5")]
    for y in range(0, roof_h):
        for x in range(0, W):
            rib = x % 8
            c = roof[2]
            if rib == 0:
                c = roof[3]
            elif rib == 1:
                c = roof[4] if y < roof_h - 3 else roof[3]
            elif rib == 7:
                c = roof[1]
            img[y, x] = c
    rect(img, 0, 0, W, 1, roof[4])
    for y in range(roof_h):
        img[y, 0] = roof[4]
        img[y, W - 1] = roof[0]
    rect(img, 0, roof_h - 3, W, roof_h - 2, hx("e8352b"))
    rect(img, 0, roof_h - 2, W, roof_h - 1, hx("a8242a"))
    rect(img, 0, roof_h - 1, W, roof_h, hx("26272c"))
    # floodlight rigs on the roof
    for x in range(12, W - 8, 24):
        rect(img, x, 4, x + 4, 7, hx("3e4148"))
        rect(img, x, 4, x + 4, 5, hx("8d8f94"))
        px(img, x + 1, 5, hx("fff3cf"))
        px(img, x + 2, 5, hx("fff3cf"))
    # sponsor banner on the front wall
    y_b = 46
    rect(img, 0, y_b, W, y_b + 1, hx("17181b"))
    seg = W // len(sponsors)
    for i, key in enumerate(sponsors):
        blend(img, sponsor_panel(seg, key), i * seg, y_b + 1)
        if i:
            rect(img, i * seg, y_b + 1, i * seg + 1, y_b + 6, hx("17181b"))
    rect(img, 0, y_b + 6, W, y_b + 7, hx("17181b"))
    rect(img, 0, y_b + 7, W, y_b + 8, hx("a9a8a5"))
    rect(img, 0, y_b + 8, W, y_b + 9, hx("6f727a"))
    rect(img, 0, y_b + 9, W, H, hx("4a4c54"))
    for x in range(4, W, 16):
        px(img, x, y_b + 9, hx("6f727a"))
    rect(img, 0, H - 1, W, H, hx("2c2e34"))
    return img


# --------------------------------------------------------------------------
# Pit building
# --------------------------------------------------------------------------

TEAM = [hx(c) for c in ["e8352b", "f1efea", "f2c230", "5ec8e5", "3ecf6a", "a855f7", "e07a2f", "3d68b0"]]


def make_pit_building(seed=77):
    """Roof from above (8 garages of 32 px), pit lane side at the bottom with
    the garage doors open and warm light spilling onto the apron."""
    W, H = 256, 64
    g = rng(seed)
    img = canvas(W, H)
    roof = [hx("3e4148"), hx("4c5058"), hx("5a5e67"), hx("686c75"), hx("7d8189"), hx("a3a6ab")]
    RH = 46
    rect(img, 0, 0, W, RH, roof[2])
    # standing-seam metal roof: a faint rib every 4 px
    for x in range(2, W, 4):
        rect(img, x, 0, x + 1, RH, hx("60646d"))
    for x in range(0, W, 32):
        rect(img, x, 0, x + 1, RH, roof[1])
        rect(img, x + 1, 0, x + 2, RH, roof[3])
    rect(img, 0, 22, W, 23, roof[1])
    rect(img, 0, 23, W, 24, roof[3])
    for i in range(8):
        x0 = i * 32
        if i in (1, 6):
            # rooftop hospitality terrace: deck, rail, umbrellas
            rect(img, x0 + 3, 3, x0 + 30, 21, hx("5a4c3d"))
            for y in range(3, 21, 2):
                rect(img, x0 + 3, y, x0 + 30, y + 1, hx("6a5a48"))
            rect(img, x0 + 3, 3, x0 + 30, 4, hx("b9bec6"))
            rect(img, x0 + 3, 3, x0 + 4, 21, hx("b9bec6"))
            rect(img, x0 + 29, 4, x0 + 30, 21, hx("5d626d"))
            rect(img, x0 + 3, 20, x0 + 30, 21, hx("5d626d"))
            for (ux, uy, col) in [(x0 + 9, 9, RED_RAMP), (x0 + 20, 8, WHITE_RAMP), (x0 + 14, 15, RED_RAMP)]:
                um = disc_mask(7, 7, 3.5, 3.5, 3.4)
                # contact shadow first, then the canopy
                for yy, xx in zip(*np.nonzero(um)):
                    img[uy - 2 + yy, ux - 2 + xx] = hx("3e352c")
                for yy, xx in zip(*np.nonzero(um)):
                    t = (xx - 3) + (yy - 3)
                    c = col[4] if t <= -3 else col[3] if t <= 0 else col[2] if t <= 3 else col[1]
                    img[uy - 3 + yy, ux - 3 + xx] = c
                px(img, ux, uy, hx("f8f5ec"))
        else:
            # skylight
            sx = x0 + 5 + int(g.random() * 6)
            rect(img, sx, 6, sx + 12, 11, hx("1c2b3a"))
            rect(img, sx + 1, 7, sx + 11, 10, hx("2b4458"))
            for k in range(3):
                px(img, sx + 2 + k, 7 + k, hx("5d8aa6"))
                px(img, sx + 3 + k, 7 + k, hx("41687f"))
            rect(img, sx, 11, sx + 12, 12, roof[0])
        # AC unit with fan
        ax = x0 + 8 + int(g.random() * 12)
        ay = 27 + int(g.random() * 4)
        rect(img, ax, ay, ax + 9, ay + 7, hx("8d8f94"))
        rect(img, ax, ay, ax + 9, ay + 1, hx("b9bec6"))
        rect(img, ax, ay + 6, ax + 9, ay + 7, hx("5d626d"))
        rect(img, ax + 8, ay, ax + 9, ay + 7, hx("5d626d"))
        fan = disc_mask(9, 7, 4.5, 3.5, 2.6)
        for yy, xx in zip(*np.nonzero(fan)):
            img[ay + yy, ax + xx] = hx("2c2e34")
        px(img, ax + 4, ay + 3, hx("8d8f94"))
        px(img, ax + 3, ay + 2, hx("5d626d"))
        px(img, ax + 5, ay + 4, hx("5d626d"))
        rect(img, ax + 1, ay + 7, ax + 10, ay + 8, roof[0])
        rect(img, ax + 9, ay + 1, ax + 10, ay + 7, roof[0])
        # vents
        for k in range(0 if i in (1, 6) else 2):
            vx = x0 + 4 + int(g.random() * 24)
            vy = 15 + int(g.random() * 5)
            px(img, vx, vy, hx("2c2e34"))
            px(img, vx + 1, vy, hx("8d8f94"))
            px(img, vx + 1, vy + 1, roof[0])
        # team colour stripe near the front edge
        tc = TEAM[i]
        rect(img, x0 + 2, 39, x0 + 30, 42, tc)
        rect(img, x0 + 2, 39, x0 + 30, 40, _light(tc, 1.1))
        rect(img, x0 + 2, 42, x0 + 30, 43, _dark(tc, 0.55))
    # race control box in the middle (raised, glazed)
    rx0, rx1 = 104, 152
    rect(img, rx0, 2, rx1, 20, hx("1d1f23"))
    rect(img, rx0 + 1, 3, rx1 - 1, 16, hx("8a909b"))
    rect(img, rx0 + 1, 3, rx1 - 1, 4, hx("c4c7cc"))
    rect(img, rx0 + 1, 3, rx0 + 2, 16, hx("b9bec6"))
    rect(img, rx1 - 2, 4, rx1 - 1, 16, hx("5d626d"))
    draw_text(img, rx0 + 10, 7, "CONTROL", hx("34363c"))
    # glazed front, lit from inside
    rect(img, rx0 + 1, 16, rx1 - 1, 19, hx("2b3542"))
    for x in range(rx0 + 2, rx1 - 2):
        if x % 4 != 1:
            px(img, x, 17, hx("f2d28a"))
            px(img, x, 18, hx("c9a860") if x % 4 == 3 else hx("e8c47a"))
    rect(img, rx0, 20, rx1 + 1, 21, roof[0])
    rect(img, rx1, 3, rx1 + 1, 21, roof[0])
    # parapet
    rect(img, 0, 0, W, 1, roof[5])
    rect(img, 0, 1, W, 2, roof[4])
    rect(img, 0, 0, 1, RH, roof[5])
    rect(img, 1, 1, 2, RH, roof[4])
    rect(img, W - 1, 0, W, RH, roof[0])
    rect(img, W - 2, 1, W - 1, RH, roof[1])
    # front fascia with team number boards
    rect(img, 0, RH - 2, W, RH - 1, roof[4])
    rect(img, 0, RH - 1, W, RH + 3, hx("1d1f23"))
    for i in range(8):
        x0 = i * 32 + 13
        rect(img, x0, RH, x0 + 6, RH + 2, hx("34363c"))
        px(img, x0 + 2, RH, TEAM[i])
        px(img, x0 + 3, RH, TEAM[i])
    # apron: garage doors open, warm light fans out onto the pit lane
    AY = RH + 3
    apron = [hx("2a2c31"), hx("38383a"), hx("4a4640"), hx("62594b"), hx("80715a")]
    rect(img, 0, AY, W, H, apron[0])
    for i in range(8):
        x0 = i * 32
        for y in range(AY, H):
            t = y - AY
            for x in range(x0 + 3, x0 + 29):
                # trapezoid widening away from the door, three stepped levels
                cxd = abs(x + 0.5 - (x0 + 16))
                lvl = 0
                for k, (half, depth) in enumerate([(14 + t * 0.6, 14), (11 + t * 0.4, 10), (8 + t * 0.2, 6)]):
                    if cxd <= half and t < depth:
                        lvl = k + 1
                        edge = cxd > half - 1 or t == depth - 1
                        if edge and (x + y) % 2 == 0:
                            lvl = k
                img[y, x] = apron[lvl]
        rect(img, x0, AY, x0 + 3, H, hx("4a4c54"))
        rect(img, x0, AY, x0 + 1, H, hx("6f727a"))
        rect(img, x0 + 3, AY, x0 + 29, AY + 1, hx("f2d28a"))
        rect(img, x0 + 29, AY, x0 + 32, H, hx("4a4c54"))
        rect(img, x0 + 31, AY, x0 + 32, H, hx("34363c"))
    rect(img, 0, H - 1, W, H, hx("dcdad4"))
    return img


# --------------------------------------------------------------------------
# Tents
# --------------------------------------------------------------------------


def _roof_faces(w, h, x0, y0, x1, y1):
    """Face id per pixel for a hip roof on [x0,x1)x[y0,y1): 0 N, 1 W, 2 S, 3 E, -1 outside."""
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    cx, cy = xx + 0.5, yy + 0.5
    inside = (cx >= x0) & (cx < x1) & (cy >= y0) & (cy < y1)
    stack = np.stack([cy - y0, cx - x0, y1 - cy, x1 - cx])
    face = np.argmin(stack, axis=0)
    return np.where(inside, face, -1)


def make_tent(w, h, x0, y0, x1, y1, stripes, offset=(3, 3), radial=True):
    img = canvas(w, h)
    face = _roof_faces(w, h, x0, y0, x1, y1)
    lvl = {1: 4, 0: 3, 3: 2, 2: 1}  # W lit most, then N, E, S
    cx0, cy0 = (x0 + x1) / 2, (y0 + y1) / 2
    half = (y1 - y0) / 2
    for y in range(h):
        for x in range(w):
            f = face[y, x]
            if f < 0:
                continue
            if radial:
                ang = math.atan2(y + 0.5 - cy0, x + 0.5 - cx0)
                s = int(math.floor((ang + math.pi) / (2 * math.pi) * stripes)) % 2
            elif f in (0, 2):
                s = int((x - x0) // 4) % 2
            else:
                # hip ends: stripes run down the slope too (parallel to the long faces' stripes)
                s = int((y - y0) // 4) % 2
            k = lvl[f]
            img[y, x] = RED_RAMP[k] if s == 0 else WHITE_RAMP[max(1, k)]
    # hip and ridge lines catch the light
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            f = face[y, x]
            if f < 0:
                continue
            if (face[y, x + 1] != f and face[y, x + 1] >= 0) or (face[y + 1, x] != f and face[y + 1, x] >= 0):
                img[y, x] = mix(img[y, x], hx("f8f5ec"), 0.35)
    # scalloped valance along the eaves
    m = face >= 0
    edge = m & ~erode(m)
    for y, x in zip(*np.nonzero(edge)):
        img[y, x] = RED_RAMP[1] if (x + y) % 3 else WHITE_RAMP[1]
    if radial:
        px(img, int(cx0), int(cy0), hx("f8f5ec"))
        px(img, int(cx0) - 1, int(cy0) - 1, hx("ffffff"))
    return drop_shadow_baked(outline(img, hx("3a1c1d")), *offset)


# --------------------------------------------------------------------------
# Small props
# --------------------------------------------------------------------------


def make_marshal_post():
    """Booth roof (white, orange band), track side at the bottom: light panel,
    a marshal in orange with a yellow flag."""
    img = canvas(16, 16)
    rect(img, 2, 1, 12, 9, WHITE_RAMP[3])
    rect(img, 2, 1, 12, 2, WHITE_RAMP[4])
    rect(img, 2, 1, 3, 9, WHITE_RAMP[4])
    rect(img, 11, 2, 12, 9, WHITE_RAMP[1])
    rect(img, 3, 8, 12, 9, WHITE_RAMP[1])
    rect(img, 3, 4, 11, 6, hx("e07a2f"))
    rect(img, 3, 4, 11, 5, hx("f0904a"))
    rect(img, 11, 4, 12, 6, hx("a8521f"))
    # light panel on the front edge
    rect(img, 3, 9, 11, 11, hx("17181b"))
    px(img, 4, 9, hx("f2c230"))
    px(img, 6, 9, hx("3ecf6a"))
    px(img, 8, 9, hx("5ec8e5"))
    # marshal (orange overalls) standing at the front with a flag
    px(img, 6, 12, hx("e0b48f"))
    px(img, 5, 13, hx("f0904a"))
    px(img, 6, 13, hx("e07a2f"))
    px(img, 7, 13, hx("a8521f"))
    px(img, 6, 14, hx("a8521f"))
    for y in (10, 11, 12, 13):
        px(img, 9, y, hx("8a909b"))
    rect(img, 10, 10, 13, 12, hx("f2c230"))
    px(img, 12, 11, hx("c49a1e"))
    return drop_shadow_baked(outline(img, hx("1d1f23")), 2, 2)


def make_tv_tower():
    img = canvas(16, 16)
    for y in range(2, 11):
        for x in range(2, 11):
            img[y, x] = hx("6a5a48") if y % 2 == 0 else hx("5a4c3d")
    rect(img, 2, 2, 11, 3, STEEL_RAMP[3])
    rect(img, 2, 2, 3, 11, STEEL_RAMP[3])
    rect(img, 10, 3, 11, 11, STEEL_RAMP[1])
    rect(img, 3, 10, 11, 11, STEEL_RAMP[1])
    for (x, y) in [(2, 2), (10, 2), (2, 10), (10, 10)]:
        px(img, x, y, STEEL_RAMP[4])
    # operator
    px(img, 5, 5, hx("2a2420"))
    px(img, 4, 6, hx("3d68b0"))
    px(img, 5, 6, hx("3d68b0"))
    px(img, 6, 6, hx("27427a"))
    # crane arm out towards the track, camera head
    for k in range(5):
        px(img, 7 + k, 7 + k, hx("1d1f23"))
        px(img, 8 + k, 7 + k, hx("6e6f78"))
    rect(img, 12, 12, 15, 15, hx("17181b"))
    px(img, 12, 12, hx("4a4c54"))
    px(img, 13, 12, hx("34363c"))
    px(img, 14, 14, hx("5ec8e5"))
    return drop_shadow_baked(outline(img, hx("141518")), 2, 2)


def make_light_tower():
    """16 x 32: lit lamp head at the top, lattice mast, base plinth."""
    img = canvas(16, 32)
    for y in range(8, 28):
        img[y, 7] = STEEL_RAMP[3]
        img[y, 8] = STEEL_RAMP[1]
    for y in range(10, 27, 4):
        px(img, 6, y, STEEL_RAMP[2])
        px(img, 9, y + 2, STEEL_RAMP[0])
    rect(img, 5, 27, 11, 30, hx("6f727a"))
    rect(img, 5, 27, 11, 28, hx("a9a8a5"))
    rect(img, 10, 28, 11, 30, hx("4a4c54"))
    rect(img, 1, 1, 15, 8, hx("26272c"))
    rect(img, 1, 1, 15, 2, STEEL_RAMP[2])
    for row in range(2):
        for col in range(5):
            x, y = 2 + col * 3 - (1 if col == 4 else 0), 2 + row * 3
            if col == 4:
                x = 13 - 1
            rect(img, x, y, x + 2, y + 2, hx("f2c230"))
            px(img, x, y, hx("fffbe8"))
            px(img, x + 1, y, hx("fff3cf"))
            px(img, x, y + 1, hx("ffe9a8"))
    out = outline(img, hx("141518"))
    m = alpha_mask(out, 127)
    for (x, y) in [(11, 30), (12, 30), (12, 31), (13, 31), (7, 31), (8, 31), (9, 31), (10, 31), (11, 31)]:
        if not m[y, x]:
            out[y, x] = SHADOW
    return out


def make_light_glow(size=48):
    """Warm halo with stepped alpha rings (dithered by one pixel at each step)."""
    img = canvas(size, size)
    c = size / 2
    levels = [(0.35, 110), (0.6, 74), (0.82, 44), (1.0, 20)]
    bay = np.array([[0, 2], [3, 1]])
    for y in range(size):
        for x in range(size):
            d = math.hypot(x + 0.5 - c, y + 0.5 - c) / c
            a = 0
            for i, (r, al) in enumerate(levels):
                if d <= r:
                    a = al
                    if d > r - 0.045 and bay[y % 2, x % 2] < 2:
                        a = levels[i + 1][1] if i + 1 < len(levels) else 0
                    break
            if a:
                img[y, x] = (255, 214, 140, a)
    return img


# --------------------------------------------------------------------------
# Billboards, brake boards, gantry, crowd strip
# --------------------------------------------------------------------------


def make_billboard(key):
    """96 x 10: board top edge (2 px), 7 px face with the sponsor, feet."""
    W, H = 96, 10
    sp = SPONSORS[key]
    img = canvas(W, H)
    rect(img, 0, 0, W, 1, STEEL_RAMP[3])
    rect(img, 0, 1, W, 2, STEEL_RAMP[1])
    face = canvas(W, 7, sp["bg"][1])
    blend(face, sponsor_panel(W - 4, key), 2, 1)
    rect(face, 0, 0, W, 1, sp["bg"][2])
    rect(face, 0, 6, W, 7, sp["bg"][0])
    blend(img, face, 0, 2)
    rect(img, 0, 2, 1, 9, STEEL_RAMP[3])
    rect(img, W - 1, 2, W, 9, STEEL_RAMP[0])
    for x in (6, 30, 64, 88):
        rect(img, x, 9, x + 2, 10, STEEL_RAMP[0])
    return img


BRAKE_DIGITS = {
    "1": [".#", "##", ".#", ".#", ".#", ".#"],
    "5": ["###", "#..", "##.", "..#", "..#", "##."],
    "0": [".#.", "#.#", "#.#", "#.#", "#.#", ".#."],
}


def make_brake_board(num):
    img = canvas(12, 16)
    for y in range(10, 15):
        img[y, 5] = STEEL_RAMP[3]
        img[y, 6] = STEEL_RAMP[1]
    rect(img, 0, 0, 12, 10, WHITE_RAMP[3])
    rect(img, 0, 0, 12, 1, WHITE_RAMP[4])
    rect(img, 0, 0, 1, 10, WHITE_RAMP[4])
    rect(img, 11, 1, 12, 10, WHITE_RAMP[1])
    rect(img, 0, 9, 12, 10, WHITE_RAMP[0])
    s = str(num)
    tw = sum(len(BRAKE_DIGITS[c][0]) for c in s) + len(s) - 1
    x = (12 - tw + 1) // 2
    for c in s:
        for yy, row in enumerate(BRAKE_DIGITS[c]):
            for xx, ch in enumerate(row):
                if ch == "#":
                    img[2 + yy, x + xx] = hx("141518")
        x += len(BRAKE_DIGITS[c][0]) + 1
    for (x, y) in [(7, 12), (8, 12), (7, 13), (8, 13), (9, 13), (8, 14), (9, 14), (10, 14), (5, 15), (6, 15),
                   (7, 15)]:
        if img[y, x][3] == 0:
            img[y, x] = SHADOW
    return img


GANTRY_PODS = [44, 54, 64, 74, 84]


def make_gantry():
    """128 x 16 start-light gantry from above; pods hang on the track side."""
    W, H = 128, 16
    img = canvas(W, H)
    rect(img, 8, 3, W - 8, 4, STEEL_RAMP[4])
    rect(img, 8, 4, W - 8, 5, STEEL_RAMP[2])
    rect(img, 8, 9, W - 8, 10, STEEL_RAMP[3])
    rect(img, 8, 10, W - 8, 11, STEEL_RAMP[1])
    for x in range(8, W - 8):
        k = (x - 8) % 8
        y = 5 + (k if k < 4 else 7 - k)
        if 5 <= y <= 8:
            img[y, x] = STEEL_RAMP[2]
    for x0 in (0, W - 10):
        rect(img, x0, 0, x0 + 10, 14, hx("4a4c54"))
        rect(img, x0, 0, x0 + 10, 1, STEEL_RAMP[4])
        rect(img, x0, 0, x0 + 1, 14, STEEL_RAMP[3])
        rect(img, x0 + 9, 1, x0 + 10, 14, hx("26272c"))
        rect(img, x0, 13, x0 + 10, 14, hx("26272c"))
        rect(img, x0 + 3, 4, x0 + 7, 10, hx("2c2e34"))
        rect(img, x0 + 3, 4, x0 + 7, 5, hx("1d1f23"))
    for cxp in GANTRY_PODS:
        x0 = cxp - 4
        rect(img, x0, 5, x0 + 8, 15, hx("17181b"))
        rect(img, x0, 5, x0 + 8, 6, hx("3a3c42"))
        rect(img, x0, 5, x0 + 1, 15, hx("2c2e34"))
        for ly in (7, 11):
            rect(img, x0 + 2, ly, x0 + 6, ly + 2, hx("3a1c1d"))
            px(img, x0 + 2, ly, hx("5a2428"))
    for x0 in (12, W - 38):
        rect(img, x0, 4, x0 + 26, 10, hx("17181b"))
        rect(img, x0 + 1, 5, x0 + 25, 9, hx("d23129"))
        plate = canvas(24, 5, hx("d23129"))
        draw_text(plate, 1, 0, "START", hx("f8f5ec"))
        blend(img, plate[:4], x0 + 1, 5)
    return img


def make_gantry_light():
    """4 x 2 lit lamp. Draw at (pod_x - 2, 7) and (pod_x - 2, 11) for each pod."""
    img = canvas(4, 2)
    rect(img, 0, 0, 4, 2, hx("e8352b"))
    px(img, 0, 0, hx("ffb09a"))
    px(img, 1, 0, hx("ff6a4a"))
    px(img, 3, 1, hx("b02020"))
    return img


def make_crowd_strip(seed=88):
    """64 x 12 spectator bank, tiles along u. v=0 back (top), v=11 fence side."""
    W, H = 64, 12
    g = rng(seed)
    img = canvas(W, H)
    bank = [hx("1e3326"), hx("243c2c"), hx("2a4532")]
    for y in range(H):
        for x in range(W):
            img[y, x] = bank[1] if y < 3 else bank[2]
    for x in range(0, W, 2):
        img[2, x] = bank[0]
    pts = []
    for row in range(3):
        y = 2 + row * 3
        x = int(g.random() * 3)
        while x < W - 1:
            pts.append((x, y + (1 if g.random() < 0.3 else 0)))
            x += 3 + (1 if g.random() < 0.35 else 0)
    for (x, y) in sorted(pts, key=lambda p: p[1]):
        if g.random() < 0.9:
            person(img, x, y, g, wrap=True)
    for (fx, col) in [(9, hx("e8352b")), (41, hx("f2c230"))]:
        for y in range(1, 6):
            px(img, fx, y, STEEL_RAMP[2], True)
        rect(img, fx + 1, 0, fx + 5, 3, col, wrap=True)
        px(img, fx + 4, 2, _dark(col), True)
        px(img, fx + 1, 0, _light(col), True)
    um = disc_mask(7, 5, 3.5, 2.5, 2.8)
    for yy, xx in zip(*np.nonzero(um)):
        c = hx("3d68b0") if (xx + yy) % 3 else hx("f1efea")
        if yy == 0 or xx == 0:
            c = _light(c)
        px(img, 25 + xx, 3 + yy, c, True)
    for x in range(W):
        img[H - 1, x] = hx("17281f")
        img[H - 2, x] = mix(img[H - 2, x], hx("17281f"), 0.5)
    return img


# --------------------------------------------------------------------------


def build():
    out = make_trees()
    out["grandstand_long.png"] = make_grandstand(192, 1, ["pitwall", "kura", "geofuel"])
    out["grandstand_short.png"] = make_grandstand(96, 2, ["mtkvari"])
    out["pit_building.png"] = make_pit_building()
    out["tent_1.png"] = make_tent(32, 32, 1, 1, 28, 28, 8, offset=(3, 3))
    out["tent_2.png"] = make_tent(48, 32, 1, 1, 44, 28, 0, offset=(3, 3), radial=False)
    out["marshal_post.png"] = make_marshal_post()
    out["tv_tower.png"] = make_tv_tower()
    out["light_tower.png"] = make_light_tower()
    out["light_glow.png"] = make_light_glow()
    for i, key in enumerate(["pitwall", "kura", "mtkvari", "geofuel"], 1):
        out[f"billboard_{i}.png"] = make_billboard(key)
    for n in (150, 100, 50):
        out[f"brake_board_{n}.png"] = make_brake_board(n)
    out["gantry.png"] = make_gantry()
    out["gantry_light.png"] = make_gantry_light()
    out["crowd_strip.png"] = make_crowd_strip()
    for name in ["grandstand_long.png", "grandstand_short.png", "pit_building.png", "gantry.png"] + \
            [f"billboard_{i}.png" for i in range(1, 5)]:
        out[name.replace(".png", "_shadow.png")] = shadow_only(out[name])
    for name, img in out.items():
        save(img, OUT / name)
    return out


if __name__ == "__main__":
    for name in build():
        print("wrote", OUT / name)
