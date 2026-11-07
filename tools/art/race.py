"""Pit Wall race art: pit crew (car scale), pit lane (world scale), start lights,
podium cutscene, race HUD icons.

    python tools/art/race.py        # writes game/assets/sprites/race/*

Scales
  * crew, loose tyres, wheel-gun spark: 10 px per metre, like car/ (they stand
    around the 80x32 car sprite).
  * pit lane, pit box, garage front, pit wall, entry line, speed board:
    1 px = 0.25 m (4 px per metre), like track/ and deco/.
  * start lights, podium, trophy, confetti, champagne, flag, icons: UI pixels
    (640x360 logical screen).
Light comes from the top-left everywhere. Every random choice is seeded.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import pixel as X  # noqa: E402  (canvas/rect/blend/outline/noise/5 px font)
import pxl as P  # noqa: E402   (car material ramps: PAINT, CARBON, TYRE, METAL, VISOR)

hx = X.hx
OUT = X.SPRITES / "race"
CAR_DIR = X.SPRITES / "car"
CLEAR = (0, 0, 0, 0)
INK = X.UI["ink"]
OUTLINE = hx("1d1f23")          # same outline colour as deco/ props
CAR_SHADOW = (0, 0, 0, 115)     # car/shadow.png tone, so crew shadows match the car
COMPOUND = {"soft": hx("e8352b"), "medium": hx("f2c230"), "hard": hx("f1efea")}


def save(img, name):
    X.save(img, OUT / name)
    return img


# ===========================================================================
# PIT CREW (10 px per metre)
#
# Each sprite is drawn as an ASCII grid of *parts* facing +y (down the canvas,
# towards a car below). Parts are shaded automatically from their own shape:
# edges facing the top-left light are lifted one step, edges facing the
# bottom-right drop one step, and a part lying under a higher part (an arm
# over the torso) gets a one-step contact shadow on its top/left side. The grid
# can be rotated before shading, so a sprite facing -x is still lit from the
# top-left. Overalls and the jack body go to the tintable _paint layer, the rest
# (gloves, boots, visor, tools, outline) to _detail.
# ===========================================================================

# part char -> (material, z). z decides which part casts a contact shadow on
# which; it is only used for shading, the grid itself has one part per pixel.
PARTS = {
    "L": ("suit", 0),     # legs / knee
    "B": ("boot", 0),
    "S": ("suit", 1),     # back + shoulders
    "a": ("sleeve", 2),   # arms (one step darker than the back so the shoulders read)
    "K": ("helmet", 4),   # crew helmet (fixed white, like the real crews' lids)
    "G": ("glove", 5),
    "W": ("gun", 3),      # wheel-gun body
    "Y": ("collar", 3),   # yellow collar on the gun
    "N": ("socket", 3),   # gun socket (chrome)
    "J": ("jack", 1),     # jack body (team colour)
    "M": ("metal", 2),    # jack handle bar + lifting cradle
    "R": ("rubber", 2),   # jack wheels
    "P": ("pole", 3),     # lollipop pole
    "D": ("sign", 6),     # lollipop disc face
    "d": ("signrim", 6),  # lollipop disc rim
    "T": ("hole", -1),    # where the carried tyre goes (left empty, drawn by the game)
}

GUN = [hx("16181c"), hx("23262d"), hx("343841"), hx("4a505c"), hx("6a7280")]
COLLAR = [hx("8a5a10"), hx("c88a1c"), hx("f2c230"), hx("ffe07a")]
SIGN = {
    "stop": [hx("5a1418"), hx("a8242a"), hx("e8352b"), hx("f2603f"), hx("ff9a80")],
    "go": [hx("12401f"), hx("1f7a3a"), hx("3ecf6a"), hx("6fe08f"), hx("b4f5c6")],
}
SIGNRIM = [hx("8e909a"), hx("b7b8bf"), hx("dcdad4"), hx("f8f5ec"), hx("ffffff")]

# material -> (ramp, base index, layer)
MATERIALS = {
    "suit": (P.PAINT, 3, "paint"),
    "sleeve": (P.PAINT, 2, "paint"),
    "jack": (P.PAINT, 3, "paint"),
    "helmet": (X.WHITE_RAMP, 2, "detail"),
    "glove": (P.CARBON, 2, "detail"),
    "boot": (P.CARBON, 2, "detail"),
    "gun": (GUN, 2, "detail"),
    "collar": (COLLAR, 2, "detail"),
    "socket": (P.METAL, 3, "detail"),
    "metal": (P.METAL, 2, "detail"),
    "rubber": (P.TYRE, 3, "detail"),
    "pole": (P.METAL, 3, "detail"),
    "signrim": (SIGNRIM, 2, "detail"),
}


def parse(rows):
    h, w = len(rows), max(len(r) for r in rows)
    g = np.full((h, w), ".", dtype="<U1")
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            g[y, x] = ch
    return g


FACING_K = {"down": 0, "right": 1, "up": 2, "left": 3}  # np.rot90 steps (counter-clockwise)


def rot_grid(g, facing):
    """Grids are drawn facing +y (down). Rotate to face down / right / up / left."""
    return np.rot90(g, FACING_K[facing]).copy()


def rot_point(pt, shape, facing):
    """Rotate a pixel-corner point (x, y) on a grid of `shape` (h, w) like rot_grid."""
    x, y = pt
    h, w = shape
    for _ in range(FACING_K[facing]):
        x, y = y, w - x       # one np.rot90 step
        h, w = w, h
    return (x, y)


def shade_grid(g, sign="stop"):
    """Grid of part chars -> (paint, detail) RGBA layers, unoutlined."""
    h, w = g.shape
    paint = X.canvas(w, h)
    detail = X.canvas(w, h)
    zs = np.full((h, w), -1.0)
    for y in range(h):
        for x in range(w):
            if g[y, x] in PARTS:
                zs[y, x] = PARTS[g[y, x]][1]
    for y in range(h):
        for x in range(w):
            ch = g[y, x]
            if ch not in PARTS or PARTS[ch][0] == "hole":
                continue
            mat, z = PARTS[ch]
            score = 0
            for dx, dy, lit in ((0, -1, 1), (-1, 0, 1), (0, 1, -1), (1, 0, -1)):
                nx, ny = x + dx, y + dy
                inside = 0 <= nx < w and 0 <= ny < h
                if inside and g[ny, nx] == ch:
                    continue
                nz = zs[ny, nx] if inside else -1
                if nz > z:
                    if lit > 0:
                        score -= 1      # a higher part shades our lit side
                elif nz < z:
                    score += lit        # exposed edge: lit top/left, dark bottom/right
            score = max(-2, min(2, score))
            if mat == "sign":
                ramp, base, layer = SIGN[sign], 2, "detail"
            else:
                ramp, base, layer = MATERIALS[mat]
            lvl = max(0, min(len(ramp) - 1, base + score))
            c = ramp[lvl]
            if layer == "paint":
                paint[y, x] = c
                if lvl == 5:
                    detail[y, x] = P.HI  # lifts the brightest paint above the tint
            else:
                detail[y, x] = c
    return paint, detail


def finish(paint, detail, hole=None, shadow_off=(2, 2)):
    """1 px outline (detail layer) + drop shadow. The shadow goes in the PAINT
    layer: black survives the multiply tint, and it then sits under everything,
    including a carried tyre drawn between the two layers. `hole` marks the
    carried tyre: no outline over it, but it does cast a shadow."""
    sil = (paint[..., 3] > 0) | (detail[..., 3] > 0)
    ring = X.dilate(sil) & ~sil
    solid = sil.copy()
    if hole is not None:
        ring &= ~hole
        solid |= hole
    detail = detail.copy()
    detail[ring] = OUTLINE
    sh = X.shift(solid | ring, *shadow_off) & ~(solid | ring)
    paint = paint.copy()
    paint[sh] = CAR_SHADOW
    return paint, detail


def merged(paint, detail, tint=None, under=None, ux=0, uy=0):
    """Paint (tinted) -> optional `under` layer at (ux, uy) (a carried tyre) -> detail."""
    out = X.canvas(paint.shape[1], paint.shape[0])
    P.alpha_over(out, paint if tint is None else P.multiply(paint, tint))
    if under is not None:
        P.alpha_over(out, under, ux, uy)
    P.alpha_over(out, detail)
    return out


# ---------------------------------------------------------------------------
# Wheels at car scale: a loose tyre lying flat, and the tilted wheel a carrier
# holds. Both show the compound as a ring on the sidewall.
# ---------------------------------------------------------------------------

RUBBER = [hx("0d0e10"), hx("17181b"), hx("212226"), hx("2e3035"), hx("43454c"), hx("5c5e66")]  # track.py
RIM = [hx("16181c"), hx("23262d"), hx("343841"), hx("4a505c"), hx("6a7280")]
NUT = [hx("8a5a10"), hx("c88a1c"), hx("f2c230"), hx("ffe07a")]
LIGHT2 = (-0.7071, -0.7071)


def tyre_flat(compound, d=9):
    """Loose tyre lying flat, d x d plus a +1 px shadow (canvas d+1)."""
    st = COMPOUND[compound]
    st_d = P.mix(st, RUBBER[1], 0.5)
    img = X.canvas(d + 1, d + 1)
    c0 = d / 2
    for y in range(d):
        for x in range(d):
            dx, dy = x + 0.5 - c0, y + 0.5 - c0
            r = math.hypot(dx, dy)
            if r > d / 2 + 0.1:
                continue
            lit = (dx * LIGHT2[0] + dy * LIGHT2[1]) / max(r, 1e-6)
            if r > d / 2 - 1.05:      # tread shoulder: highlight arc top-left
                c = RUBBER[5] if lit > 0.7 else RUBBER[4] if lit > 0.2 else RUBBER[3] if lit > -0.4 else RUBBER[1]
            elif r > d / 2 - 2.05:    # sidewall, compound ring
                c = st if lit > -0.3 else st_d
            elif r > 1.2:             # rim
                c = RIM[1] if lit > 0.3 else RIM[3] if lit < -0.3 else RIM[2]
            else:                     # centre-lock nut
                c = NUT[2] if lit > 0 or r < 0.3 else NUT[1]
            img[y, x] = c
    m = img[..., 3] > 0
    img[X.shift(m, 1, 1) & ~m] = CAR_SHADOW
    return img


HELD_ROWS = [  # 9 x 7 wheel tilted towards the viewer: tread on top, sidewall face below
    "..54443..",
    ".4SSSSs3.",
    "4SrRRRrs2",
    "3SRrnrRs1",
    "3srrrrrs1",
    ".2sssss1.",
    "..21110..",
]


def tyre_held(compound):
    st = COMPOUND[compound]
    sd = P.mix(st, RUBBER[1], 0.5)
    img = X.canvas(9, 7)
    for y, r in enumerate(HELD_ROWS):
        for x, ch in enumerate(r):
            if ch == ".":
                continue
            img[y, x] = (RUBBER[int(ch)] if ch.isdigit() else st if ch == "S" else sd if ch == "s"
                         else RIM[2] if ch == "r" else RIM[3] if ch == "R" else NUT[2])
    return img


# ---------------------------------------------------------------------------
# Crew grids, all drawn facing +y ('.' = empty). Helmet K, sleeves a, gloves G.
# ---------------------------------------------------------------------------

GUNNER = {
    # a: kneeling, socket on the wheel nut; one boot behind, right knee forward
    "a": [
        "................",
        "................",
        ".....BB.........",
        ".....LL.........",
        ".....LSSSSS.....",
        "....SSSSSSSS....",
        "...SSSSSSSSSS...",
        "..aSSSSKKSSSSa..",
        "..aa.SKKKKS.aaL.",
        "..aa..KKKK..aLL.",
        "...a...KK...a...",
        "...aG......Ga...",
        "....GGWYYWGG....",
        "......WWWW......",
        ".......NN.......",
        "................",
    ],
    # b: leaning in on the gun, elbows out (the gun stays on the nut)
    "b": [
        "................",
        "................",
        ".....BB.........",
        ".....LL.........",
        ".....LSSSSS.....",
        "....SSSSSSSS....",
        "...SSSSSSSSSS...",
        "..SSSSSSSSSSSS..",
        ".aaSSSSKKSSSSaa.",
        ".aa..SKKKKS..aL.",
        "..a...KKKK...aLL",
        "..aG...KK...Ga..",
        "...GGGWYYWGGG...",
        "......WWWW......",
        ".......NN.......",
        "................",
    ],
}

CARRIER = {
    # a: standing, wheel held in front; W marks the wheel's top-left corner
    "a": ([
        "................",
        "................",
        ".....SSSSSS.....",
        "...SSSSSSSSSS...",
        "..SSSSSKKSSSSS..",
        "..aSSSKKKKSSSa..",
        "..a.S.KKKK.S.a..",
        "..a....KK....a..",
        "..a..........a..",
        "...a........a...",
        "...a........a...",
        "...a........a...",
        "....G.......G...",
        "....G.......G...",
        "................",
        "................",
        "................",
        "................",
    ], (4, 10)),
    # b: arms pushed out, wheel one pixel further forward
    "b": ([
        "................",
        "................",
        ".....SSSSSS.....",
        "...SSSSSSSSSS...",
        "..SSSSSKKSSSSS..",
        "..aSSSKKKKSSSa..",
        "..a.S.KKKK.S.a..",
        "..a....KK....a..",
        "..a..........a..",
        "...a........a...",
        "...a........a...",
        "...a........a...",
        "...a........a...",
        "....G.......G...",
        "....G.......G...",
        "................",
        "................",
        "................",
    ], (4, 11)),
}

JACK = [  # facing +y: T-handle in the hands, shaft, wheels, lifting cradle
    "................",
    "................",
    ".....SSSSSS.....",
    "...SSSSSSSSSS...",
    "..SSSSSKKSSSSS..",
    "..aSSSKKKKSSSa..",
    "..a.S.KKKK.S.a..",
    "...a...KK...a...",
    "....aG....Ga....",
    ".....GMMMMG.....",
    ".......JJ.......",
    ".......JJ.......",
    ".......JJ.......",
    ".......JJ.......",
    ".......JJ.......",
    ".....RRJJRR.....",
    ".....RRJJRR.....",
    ".......JJ.......",
    "......JJJJ......",
    ".....JJJJJJ.....",
    "....MMMMMMMM....",
    "................",
]
JACK_LIFT = (8, 21)  # pixel corner at the front face of the cradle (facing +y)

LOLLIPOP = [  # facing +y; pole + disc are added in code (pole from the right hand)
    "......................",
    "......................",
    ".....SSSSSS...........",
    "...SSSSSSSSSS.........",
    "..SSSSSKKSSSSS........",
    "..aSSSKKKKSSSa........",
    "..a.S.KKKK.S.aa.......",
    "..a....KK.....aa......",
    "...G...........G......",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
]
DISC = [
    "..ddd..",
    ".dDDDd.",
    "dDDDDDd",
    "dDDDDDd",
    "dDDDDDd",
    ".dDDDd.",
    "..ddd..",
]
# disc centre (pixel corner) per state, facing +y. 'go' lifts the board up and
# swings it back towards the holder, out of the car's path.
LOLLIPOP_SIGN = {"stop": (18.5, 17.5), "go": (15.5, 14.5)}
LOLLIPOP_HAND = (15, 8)


def lollipop_grid(state):
    g = parse(LOLLIPOP)
    cx, cy = LOLLIPOP_SIGN[state]
    x0, y0 = int(cx - 3.5), int(cy - 3.5)
    hx_, hy_ = LOLLIPOP_HAND
    for (px_, py_) in P.line_pts(hx_, hy_ + 1, int(cx) - 1, int(cy) - 1):
        if g[py_, px_] == ".":
            g[py_, px_] = "P"
    for yy, row in enumerate(DISC):
        for xx, ch in enumerate(row):
            if ch != ".":
                g[y0 + yy, x0 + xx] = ch
    return g


def carrier_grid(frame):
    rows, (wx, wy) = CARRIER[frame]
    g = parse(rows)
    held = tyre_held("medium")
    for yy, xx in zip(*np.nonzero(held[..., 3] > 0)):
        if g[wy + yy, wx + xx] == ".":
            g[wy + yy, wx + xx] = "T"
    return g, (wx, wy)


def build_crew_sprite(g, facing="down", sign="stop"):
    """-> paint, detail, wheel_mask (all already rotated to `facing`)."""
    g = rot_grid(g, facing)
    hole = g == "T"
    p, d = shade_grid(g, sign)
    p, d = finish(p, d, hole if hole.any() else None)
    return p, d, hole


def crew_sprites():
    """name -> dict(paint, detail, facing, anchors {name: (x, y) pixel corner})."""
    out = {}
    for fr, rows in GUNNER.items():
        p, d, _ = build_crew_sprite(parse(rows))
        out[f"crew_tyre_gunner_{fr}"] = dict(paint=p, detail=d, facing="down",
                                             anchors={"socket_tip": (8, 15)})
    for fr in CARRIER:
        g, (wx, wy) = carrier_grid(fr)
        p, d, _ = build_crew_sprite(g)
        out[f"crew_tyre_carrier_{fr}"] = dict(paint=p, detail=d, facing="down",
                                              anchors={"wheel_topleft": (wx, wy),
                                                       "wheel_center": (wx + 4.5, wy + 3.5)})
    g = parse(JACK)
    for name, facing in (("crew_jack_front", "left"), ("crew_jack_rear", "right")):
        p, d, _ = build_crew_sprite(g, facing)
        out[name] = dict(paint=p, detail=d, facing=facing,
                         anchors={"lift_point": rot_point(JACK_LIFT, g.shape, facing)})
    for state in ("stop", "go"):
        g = lollipop_grid(state)
        p, d, _ = build_crew_sprite(g, "left", state)
        out[f"crew_lollipop_{state}"] = dict(
            paint=p, detail=d, facing="left",
            anchors={"sign_center": rot_point(LOLLIPOP_SIGN[state], g.shape, "left")})
    return out


# ---------------------------------------------------------------------------
# Car composite (for previews and the pit-stop mock): reads the car/ layers.
# ---------------------------------------------------------------------------

def car_layer(name):
    return X.load(CAR_DIR / f"{name}.png")


def compose_car(tint, helmet=hx("f2c230"), combo=("low_rake", "downwash", "outwash", "highdf"),
                compound="medium", front_tyres=True):
    fl, sp, fw, rw = combo
    out = X.canvas(80, 32)
    for name in ("shadow", f"floor_{fl}"):
        P.alpha_over(out, car_layer(name))
    P.alpha_over(out, car_layer(f"tyre_rear_{compound}"))
    if front_tyres:
        ft = car_layer(f"tyre_front_{compound}")
        P.alpha_over(out, ft, 58 - 5, 6 - 1)
        P.alpha_over(out, ft[::-1].copy(), 58 - 5, 22 - 1)
    for part in (f"sidepods_{sp}", "body", f"front_wing_{fw}", f"rear_wing_{rw}"):
        P.alpha_over(out, P.multiply(car_layer(f"{part}_paint"), tint))
        P.alpha_over(out, car_layer(f"{part}_detail"))
    P.alpha_over(out, P.multiply(car_layer("helmet_paint"), helmet))
    P.alpha_over(out, car_layer("halo_detail"))
    return out


# Canonical pit-stop layout, car scale. Points are car-relative pixel corners
# (car centre = pixel corner (40, 16) of the 80x32 car canvas, nose +x, y down).
# Each entry: sprite, the sprite anchor that goes on the point, the point,
# flip_v (crew on the +y side of the car are the -y sprite flipped), and
# where it draws relative to the car layers.
PIT_STOP_LAYOUT = [
    ("crew_jack_front", "lift_point", (30, 0), False, "under_car"),
    ("crew_jack_rear", "lift_point", (-29, 0), False, "under_car"),
    ("crew_tyre_gunner", "socket_tip", (18, -10), False, "over_car"),
    ("crew_tyre_gunner", "socket_tip", (-18, -10), False, "over_car"),
    ("crew_tyre_gunner", "socket_tip", (18, 10), True, "over_car"),
    ("crew_tyre_gunner", "socket_tip", (-18, 10), True, "over_car"),
    ("crew_tyre_carrier", "wheel_center", (32, -14), False, "over_car"),     # tyre on, front
    ("crew_tyre_carrier", "wheel_center", (-32, -14), False, "over_car"),    # tyre on, rear
    ("crew_tyre_carrier", "wheel_center", (32, 14), True, "over_car"),
    ("crew_tyre_carrier", "wheel_center", (-32, 14), True, "over_car"),
    ("crew_tyre_carrier", "wheel_center", (6, -15), False, "over_car"),      # tyre off, front
    ("crew_tyre_carrier", "wheel_center", (-6, -15), False, "over_car"),     # tyre off, rear
    ("crew_tyre_carrier", "wheel_center", (6, 15), True, "over_car"),
    ("crew_tyre_carrier", "wheel_center", (-6, 15), True, "over_car"),
    ("crew_lollipop", "sign_center", (36, -5), False, "over_car"),
]


def place_origin(spr, anchor, point, flip):
    """Top-left (car-relative) of a crew sprite so its anchor lands on point."""
    h = spr["paint"].shape[0]
    ax, ay = spr["anchors"][anchor]
    if flip:
        ay = h - ay
    return int(round(point[0] - ax)), int(round(point[1] - ay))


def draw_crew(dst, spr, ox, oy, tint, flip=False, compound="medium"):
    """Paint (team tint) -> held wheel (carriers) -> detail, at (ox, oy)."""
    p, d = spr["paint"], spr["detail"]
    if flip:
        p, d = p[::-1].copy(), d[::-1].copy()
    X.blend(dst, P.multiply(p, tint), ox, oy)
    if "wheel_topleft" in spr["anchors"]:
        w = tyre_held(compound)
        wx, wy = spr["anchors"]["wheel_topleft"]
        if flip:
            w = w[::-1].copy()
            wy = p.shape[0] - wy - w.shape[0]
        X.blend(dst, w, ox + wx, oy + wy)
    X.blend(dst, d, ox, oy)


def make_wheel_gun_spark():
    """2 frames of 7x7 (strip 14x7): flash at the nut, then sparks flying out.
    Centre the frame on the gunner's socket_tip."""
    W_ = hx("fff8e8")
    Yb = hx("ffe07a")
    Y = hx("f2c230")
    O = hx("ff6a1f", 230)
    y = hx("f2c230", 150)
    o = hx("e8352b", 140)
    f0 = [
        "...y...",
        ".o.Y.o.",
        "..YWY..",
        "yYWWWYy",
        "..YWY..",
        ".o.Y.o.",
        "...y...",
    ]
    f1 = [
        "O.....o",
        ".y...Y.",
        "...b...",
        "..bWy..",
        "...y...",
        ".Y...y.",
        "o.....O",
    ]
    cmap = {"W": W_, "b": Yb, "Y": Y, "O": O, "y": y, "o": o}
    strip = X.canvas(14, 7)
    for i, f in enumerate((f0, f1)):
        blk = X.from_ascii(f, cmap)
        X.blend(strip, blk, i * 7, 0)
    return strip


# ===========================================================================
# PIT LANE (1 px = 0.25 m, like track/ and deco/)
# ===========================================================================

PIT_ASPHALT = [
    hx("1d1f23"),  # 0 deep aggregate shadow
    hx("25272b"),  # 1 darker patch / rubber
    hx("2a2c31"),  # 2 base (the pit building apron colour)
    hx("2d2f34"),  # 3 lighter patch
    hx("36383e"),  # 4 aggregate lit
    hx("41434a"),  # 5 bright aggregate
    hx("222429"),  # 6 aggregate mid-shadow
]
LINE_WHITE = [hx("b7b8bf"), hx("d2cfc8"), hx("ebe8e1")]


def pit_asphalt(W, H, seed):
    """Darker pit-lane asphalt, tiles along u (x). Same recipe as track/asphalt."""
    g = X.rng(seed)
    f = X.fbm(W, 32, [32, 16, 8], [1, 0.55, 0.25], seed)[:H]
    q = X.quantize(f, 5, dither=0.9)
    idx = np.full((H, W), 2, int)
    idx = np.where(q == 0, 1, idx)
    idx = np.where(q == 4, 3, idx)
    idx = X.clean_orphans(idx, passes=3)
    shapes = [
        [(0, 0, 4), (1, 1, 0)],
        [(0, 0, 4), (1, 0, 3), (1, 1, 0), (2, 1, 0)],
        [(0, 0, 4), (0, 1, 3), (1, 1, 0)],
        [(0, 0, 5), (1, 0, 4), (1, 1, 0)],
        [(0, 0, 0)],
        [(0, 0, 6), (1, 0, 6)],
    ]
    for (fx, fy) in X.poisson_torus(W, H, 3.2, seed + 9):
        if g.random() > 0.75:
            continue
        sh = shapes[int(g.random() * len(shapes))]
        for dx, dy, code in sh:
            idx[(int(fy) + dy) % H, (int(fx) + dx) % W] = code
    return idx


def make_pit_lane():
    """64 x 24, tiles along u. Laid out for garages above / track below (the
    way deco/pit_building.png faces, so the baked light stays right):
    v=1 dashed line (2 m dash, 2 m gap) to the working lane with the boxes,
    v=22 solid white edge line on the pit-wall side."""
    W, H = 64, 24
    idx = pit_asphalt(W, H, 41)
    # rubbered-in band where cars run (v 8..15), dithered edges
    bay = X.bayer(W, H)
    for v in range(7, 17):
        t = 1.0 if 9 <= v <= 14 else 0.45
        for u in range(W):
            if bay[v, u] < t * 0.55 and idx[v, u] in (2, 3):
                idx[v, u] = 1
    img = X.palette_map(idx, PIT_ASPHALT)
    g = X.rng(5)
    for u in range(W):
        if (u % 16) < 8:
            img[1, u] = LINE_WHITE[2] if (u % 16) not in (0, 7) else LINE_WHITE[1]
    for u in range(W):
        img[22, u] = LINE_WHITE[2] if g.random() > 0.08 else LINE_WHITE[0]
        img[21, u] = P.mix(PIT_ASPHALT[2], LINE_WHITE[0], 0.18)  # faint paint bleed
    return img


def make_pit_box():
    """28 x 14 team box (7 x 3.5 m), car drives towards +u (nose at the right).
    Returns (paint, detail): paint = worn grey fill to tint with the team
    colour, detail = white outline + wheel/jack marks, drawn on top."""
    W, H = 28, 14
    paint = X.canvas(W, H)
    detail = X.canvas(W, H)
    fill = [hx("7c7c80"), hx("9a9a9d"), hx("b0b0b2"), hx("c4c4c6")]  # matte ground paint (tint me)
    g = X.rng(12)
    for y in range(2, H - 2):
        for x in range(2, W - 2):
            c = fill[2]
            if y == 2 or x == 2:
                c = fill[3]                               # lit inner edge (top-left)
            elif y == H - 3 or x == W - 3:
                c = fill[1]
            paint[y, x] = c
    # rubber scuffs where the wheels stop and the car pulls away, a few chips
    for (sx, sy) in ((19, 3), (19, 10), (5, 3), (5, 10)):
        for (dx, dy) in ((0, 0), (1, 0), (2, 0), (-1, 0), (-3, 0)):
            if g.random() < 0.8:
                paint[sy, sx + dx] = fill[0] if dx > -2 else fill[1]
    for _ in range(5):
        x, y = 3 + int(g.random() * (W - 6)), 3 + int(g.random() * (H - 6))
        paint[y, x] = fill[1]
    # white outline (1 px = 25 cm line), a few worn pixels
    for x in range(W):
        for y in (0, H - 1):
            detail[y, x] = LINE_WHITE[2] if (x * 7 + y) % 11 else LINE_WHITE[0]
    for y in range(H):
        for x in (0, W - 1):
            detail[y, x] = LINE_WHITE[2] if (y * 5 + x) % 9 else LINE_WHITE[0]
    # front wheel stop marks (front axle 1.8 m ahead of the box centre, track 1.6 m)
    for y in (3, 10):
        X.rect(detail, 20, y, 23, y + 1, LINE_WHITE[2])
        X.px(detail, 21, y + (1 if y == 3 else -1), LINE_WHITE[1])
    # rear wheel marks: short ticks
    for y in (3, 10):
        X.rect(detail, 5, y, 7, y + 1, LINE_WHITE[1])
    # front / rear jack crosses on the centre line, just inside the box ends
    for cx_ in (25, 2):
        X.px(detail, cx_, 6, LINE_WHITE[2])
        X.px(detail, cx_, 7, LINE_WHITE[2])
    return paint, detail


def make_pit_entry_line():
    """32 x 8, tiles along u. v 0-1: the solid white pit-entry line. v 2-7:
    hatched gore (45 degree stripes, 2 px every 8 px). Use v 0-1 alone for a
    bare line."""
    W, H = 32, 8
    img = X.canvas(W, H)
    g = X.rng(9)
    for u in range(W):
        img[0, u] = LINE_WHITE[2]
        img[1, u] = LINE_WHITE[1] if g.random() > 0.15 else LINE_WHITE[0]
    for v in range(2, H):
        for u in range(W):
            k = (u - v) % 8
            if k < 2:
                c = LINE_WHITE[2] if k == 0 else LINE_WHITE[1]
                img[v, u] = X.with_alpha(c, 220 if g.random() > 0.12 else 140)
    return img


SPEED_DIGITS = {
    "8": [".#.", "#.#", ".#.", "#.#", "#.#", ".#."],
    "0": [".#.", "#.#", "#.#", "#.#", "#.#", ".#."],
}


def make_pit_speed_board():
    """12 x 16 pit-lane speed limit sign: round, '80' in a red ring, on a post
    with a small baked shadow (same post + shadow as deco/brake_board_*.png)."""
    img = X.canvas(12, 16)
    for y in range(12, 15):
        img[y, 5] = X.STEEL_RAMP[3]
        img[y, 6] = X.STEEL_RAMP[1]
    # round sign, 12 px: 2 px red ring, white face, lit from the top-left
    for y in range(12):
        for x in range(12):
            dx, dy = x + 0.5 - 6, y + 0.5 - 6
            r = math.hypot(dx, dy)
            if r > 6.05:
                continue
            lit = -(dx + dy) / max(r, 1e-6)
            if r > 4.4:
                img[y, x] = X.RED_RAMP[4] if lit > 0.6 else X.RED_RAMP[3] if lit > -0.5 else X.RED_RAMP[1]
            else:
                img[y, x] = X.WHITE_RAMP[4] if lit > 0.75 and r > 3.4 else X.WHITE_RAMP[3]
    for (x_, y_) in ((2, 1), (1, 2)):
        img[y_, x_] = X.RED_RAMP[4]
    x = 2
    for ch in "80":
        for yy, row in enumerate(SPEED_DIGITS[ch]):
            for xx, c in enumerate(row):
                if c == "#":
                    img[3 + yy, x + xx] = hx("141518")
        x += 4
    for (x_, y_) in [(7, 12), (8, 12), (7, 13), (8, 13), (9, 13), (8, 14), (9, 14), (10, 14), (5, 15), (6, 15),
                     (7, 15)]:
        if img[y_, x_][3] == 0:
            img[y_, x_] = X.SHADOW
    return img


ROOF = [hx("3e4148"), hx("4c5058"), hx("5a5e67"), hx("686c75"), hx("7d8189"), hx("a3a6ab")]  # deco pit_building
APRON = [hx("2a2c31"), hx("38383a"), hx("4a4640"), hx("62594b"), hx("80715a")]


def make_garage_front():
    """32 x 20 garage bay front from above; the apron ends at v=19 and the pit
    lane continues below. Same bay pitch, roof and apron light as
    deco/pit_building.png. Returns (full, paint): `full` is complete with the
    team areas in neutral grey; `paint` holds only those team-colour pixels
    (grey ramp) to draw ON TOP of `full` with the team colour as modulate."""
    W, H = 32, 20
    img = X.canvas(W, H)
    paint = X.canvas(W, H)
    # roof edge: standing seams every 4 px, parapet + bay dividers
    X.rect(img, 0, 0, W, 9, ROOF[2])
    for x in range(2, W, 4):
        X.rect(img, x, 0, x + 1, 9, hx("60646d"))
    X.rect(img, 0, 0, 1, 9, ROOF[1])
    X.rect(img, 1, 0, 2, 9, ROOF[3])
    # team colour band on the roof edge (v 3..5): paint ramp, lit top row
    team = [P.PAINT[4], P.PAINT[3], P.PAINT[2]]
    for x in range(2, W - 2):
        for k, y in enumerate((3, 4, 5)):
            img[y, x] = team[k]
            paint[y, x] = team[k]
    X.rect(img, 2, 6, W - 2, 7, hx("2c2e34"))          # band shadow on the roof
    X.rect(img, 0, 8, W, 9, ROOF[4])                    # roof front lip, lit
    # fascia (dark) with the team number board + garage lights
    X.rect(img, 0, 9, W, 12, hx("1d1f23"))
    X.rect(img, 12, 9, 20, 11, hx("34363c"))
    for x in range(13, 19):
        img[10, x] = P.PAINT[4]
        paint[10, x] = P.PAINT[4]
    img[9, 12] = hx("4a4c54")
    for x in (3, 7, 24, 28):
        img[11, x] = hx("f2d28a")
    # apron: open door spills warm light onto the pit lane (3 stepped levels)
    AY = 12
    X.rect(img, 0, AY, W, H, APRON[0])
    for y in range(AY, H):
        t = y - AY
        for x in range(3, 29):
            cxd = abs(x + 0.5 - 16)
            lvl = 0
            for k, (half, depth) in enumerate([(14 + t * 0.6, 8), (11 + t * 0.4, 6), (8 + t * 0.2, 4)]):
                if cxd <= half and t < depth:
                    lvl = k + 1
                    edge = cxd > half - 1 or t == depth - 1
                    if edge and (x + y) % 2 == 0:
                        lvl = k
            img[y, x] = APRON[lvl]
    X.rect(img, 3, AY, 29, AY + 1, hx("f2d28a"))       # door threshold glow
    # door posts
    X.rect(img, 0, AY, 3, H, hx("4a4c54"))
    X.rect(img, 0, AY, 1, H, hx("6f727a"))
    X.rect(img, 29, AY, 32, H, hx("4a4c54"))
    X.rect(img, 31, AY, 32, H, hx("34363c"))
    # two tyres in team-colour blankets waiting by the door (left), from above
    disc = [".##.", "#ab#", "#bc#", ".##."]
    for sx in (4, 9):
        for yy, row in enumerate(disc):
            for xx, ch in enumerate(row):
                if ch == ".":
                    continue
                lvl = {"#": 3, "a": 4, "b": 2, "c": 1}[ch]
                if ch == "#" and (xx + yy) <= 1:
                    lvl = 4
                elif ch == "#" and (xx + yy) >= 5:
                    lvl = 2
                img[14 + yy, sx + xx] = P.PAINT[lvl]
                paint[14 + yy, sx + xx] = P.PAINT[lvl]
        img[18, sx + 1] = img[18, sx + 2] = img[17, sx + 4] = X.SHADOW
    return img, paint


def make_pit_wall_strip():
    """32 x 8, tiles along u. Pit-lane side at the top (garages above, track
    below, like make_pit_lane): v 0-3 the team stand (engineers in headsets at
    their monitors), v 4-6 the concrete wall top (lit edge at v=4), v=7 the
    wall's shadow falling on the track."""
    W, H = 32, 8
    img = X.canvas(W, H)
    C = X.CONCRETE
    # stand deck (v 0..3): dark, lit back rail
    X.rect(img, 0, 0, W, 4, hx("26282d"))
    X.rect(img, 0, 0, W, 1, hx("34363c"))
    # engineers on stools (heads + headset) on the lane side of the desk
    for u, hair in ((4, hx("8a6a3a")), (12, hx("2a2420")), (20, hx("4a3424")), (28, hx("1c1d21"))):
        img[1, u] = hair
        img[1, u + 1] = hx("e8352b")             # headset band (brand red)
        img[2, u] = P.mix(hair, hx("000000"), 0.3)
        img[2, u + 1] = hair
    # monitors on the desk edge facing the engineers (screens lit)
    for k, u in enumerate((2, 10, 18, 26)):
        scr = [hx("5ec8e5"), hx("3ecf6a"), hx("5ec8e5"), hx("f2c230")][k]
        X.rect(img, u, 3, u + 6, 4, hx("0b0c0e"))
        X.rect(img, u + 1, 3, u + 5, 4, P.mix(scr, hx("0b0c0e"), 0.45))
        img[3, u + 1] = scr
        img[3, u + 3] = P.mix(scr, hx("ffffff"), 0.3)
    # concrete wall top (v 4..6) with expansion joints every 2 m
    X.rect(img, 0, 4, W, 5, C[5])
    X.rect(img, 0, 5, W, 6, C[4])
    X.rect(img, 0, 6, W, 7, C[2])
    for u in range(0, W, 8):
        img[5, u] = C[3]
        img[6, u] = C[1]
    X.rect(img, 0, 7, W, 8, X.SHADOW)
    return img


# ===========================================================================
# START SEQUENCE (UI pixels)
# ===========================================================================

POD_X = [32, 56, 80, 104, 128]      # pod centres (pixel corners), start_lights.png
POD_Y = 24                          # pod centre (pixel corner)
LAMP_DY = (-7, 6)                   # lamp centres relative to the pod centre
LAMP_R = 5.0
HOUSING = [hx("0b0c0e"), hx("141518"), hx("1b1c20"), hx("2c2e34"), hx("3a3c42")]
LENS_OFF = [hx("1e0f11"), hx("2a1416"), hx("3a1c1d"), hx("5a2428"), hx("7a3a3a")]
LENS_ON = [hx("8f2027"), hx("e8352b"), hx("ff3b2e"), hx("ff6a4a"), hx("ffb09a"), hx("ffe2d4")]


def _lamp(img, cx, cy, ramp, lit=False):
    """Round lamp of radius LAMP_R centred on pixel corner (cx, cy), lit top-left."""
    for y in range(int(cy - LAMP_R) - 1, int(cy + LAMP_R) + 1):
        for x in range(int(cx - LAMP_R) - 1, int(cx + LAMP_R) + 1):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            r = math.hypot(dx, dy)
            if r > LAMP_R:
                continue
            k = -(dx + dy) / max(r, 1e-6)
            if not lit:
                c = ramp[0] if r > LAMP_R - 1 else ramp[2]
                if r <= LAMP_R - 1 and k > 0.3 and r > 1.5:
                    c = ramp[3]
                if r <= LAMP_R - 1 and k < -0.5:
                    c = ramp[1]
            else:
                c = ramp[0] if r > LAMP_R - 1 else ramp[2] if r > 3.2 else ramp[3] if r > 1.8 else ramp[4]
                if r <= LAMP_R - 1 and r > 1.8 and k > 0.55:
                    c = ramp[4]
            X.px(img, x, y, c)
    # glint (glass) on the upper-left
    X.px(img, int(cx - 3), int(cy - 3), ramp[4] if not lit else ramp[5])
    X.px(img, int(cx - 2), int(cy - 3), ramp[3] if not lit else ramp[4])


def make_start_lights():
    """160 x 40 start gantry from the front: truss + five pods, all lamps off."""
    W, H = 160, 40
    img = X.canvas(W, H)
    S = X.STEEL_RAMP
    # truss: two chords + zig-zag lattice
    X.rect(img, 2, 1, W - 2, 2, S[4])
    X.rect(img, 2, 2, W - 2, 3, S[2])
    X.rect(img, 2, 7, W - 2, 8, S[3])
    X.rect(img, 2, 8, W - 2, 9, S[1])
    for x in range(2, W - 2):
        k = (x - 2) % 8
        y = 3 + (k if k < 4 else 7 - k)
        if 3 <= y <= 6:
            img[y, x] = S[2] if k < 4 else S[1]
    for x0 in (0, W - 4):                       # end brackets
        X.rect(img, x0, 0, x0 + 4, 11, hx("4a4c54"))
        X.rect(img, x0, 0, x0 + 4, 1, S[4])
        X.rect(img, x0, 0, x0 + 1, 11, S[3])
        X.rect(img, x0 + 3, 1, x0 + 4, 11, hx("26272c"))
        X.rect(img, x0, 10, x0 + 4, 11, hx("26272c"))
        X.px(img, x0 + 2, 4, hx("26272c"))
        X.px(img, x0 + 2, 7, hx("26272c"))
    for cx in POD_X:
        x0, x1, y0, y1 = cx - 9, cx + 9, 9, 39
        # hanger
        X.rect(img, cx - 3, 8, cx + 3, 10, S[1])
        X.rect(img, cx - 3, 8, cx + 3, 9, S[3])
        # housing with rounded corners, lit rim top-left
        X.rect(img, x0, y0, x1, y1, HOUSING[2])
        X.rect(img, x0, y0, x1, y0 + 1, HOUSING[4])
        X.rect(img, x0, y0, x0 + 1, y1, HOUSING[3])
        X.rect(img, x1 - 1, y0 + 1, x1, y1, HOUSING[0])
        X.rect(img, x0 + 1, y1 - 1, x1, y1, HOUSING[0])
        for (x, y) in ((x0, y0), (x1 - 1, y0), (x0, y1 - 1), (x1 - 1, y1 - 1)):
            img[y, x] = CLEAR
        X.px(img, x0 + 1, y0 + 1, HOUSING[4])
        for dy in LAMP_DY:
            ly = POD_Y + dy
            # recess ring + hood (visor) over the top of each lamp
            for y in range(ly - 7, ly + 7):
                for x in range(cx - 7, cx + 7):
                    r = math.hypot(x + 0.5 - cx, y + 0.5 - ly)
                    if LAMP_R < r <= LAMP_R + 1.2:
                        img[y, x] = HOUSING[1] if (y + 0.5 - ly) > -2 else HOUSING[0]
            for x in range(cx - 6, cx + 6):
                if abs(x + 0.5 - cx) < 5.6:
                    img[ly - 6, x] = HOUSING[0]
            X.rect(img, cx - 4, ly - 7, cx + 4, ly - 6, HOUSING[3])
            _lamp(img, cx, ly, LENS_OFF)
    return img


ON_W, ON_H = 26, 38                 # start_light_on.png, centred on a pod centre


def make_start_light_on():
    """One pod's two lamps lit red plus a stepped glow; 26 x 38, centre (13, 19)
    goes on the pod centre (POD_X[i], POD_Y) of start_lights.png."""
    img = X.canvas(ON_W, ON_H)
    cx, cy = ON_W // 2, ON_H // 2
    glow = [(LAMP_R + 3.5, 28), (LAMP_R + 2.4, 60), (LAMP_R + 1.3, 110)]
    for rr, a in glow:
        for dy in LAMP_DY:
            ly = cy + dy
            for y in range(ON_H):
                for x in range(ON_W):
                    if math.hypot(x + 0.5 - cx, y + 0.5 - ly) <= rr:
                        cur = img[y, x]
                        if cur[3] < a:
                            img[y, x] = (255, 59, 46, a)
    for dy in LAMP_DY:
        _lamp(img, cx, cy + dy, LENS_ON, lit=True)
    return img


# ===========================================================================
# PODIUM CUTSCENE (UI pixels, 640 x 360 screen)
# ===========================================================================

GOLD = [hx("4a3008"), hx("7a5210"), hx("b07a18"), hx("e0a828"), hx("f2c230"), hx("ffe07a"), hx("fff6cf")]
SILVER = [hx("3d414b"), hx("5d626d"), hx("8a909b"), hx("b9bec6"), hx("dcdfe4"), hx("f4f5f7")]
BRONZE = [hx("4a2410"), hx("7a3c18"), hx("a8582a"), hx("d07a3c"), hx("e8a060"), hx("f6c79a")]
PANEL = [hx("101113"), hx("17181b"), hx("1d1f23"), hx("26282d"), hx("34363c"), hx("4a4c54"), hx("6e6f78")]

PODIUM_W, PODIUM_H = 200, 80
# (place, x0, x1 exclusive, top of the front face)
STEPS = [(2, 6, 68, 34), (1, 68, 132, 18), (3, 132, 194, 44)]
STEP_TOP_DEPTH = 6          # visible top surface (slight view from above)
PLINTH_Y = 70

BIG_DIGITS = {  # 9 x 15, 2-3 px strokes
    "1": [
        "...###...",
        "..####...",
        ".#####...",
        "###.##...",
        "....##...",
        "....##...",
        "....##...",
        "....##...",
        "....##...",
        "....##...",
        "....##...",
        "....##...",
        "....##...",
        ".#######.",
        ".#######.",
    ],
    "2": [
        ".######..",
        "########.",
        "##....###",
        "......###",
        "......###",
        ".....###.",
        "....###..",
        "...###...",
        "..###....",
        ".###.....",
        "###......",
        "##.......",
        "##.......",
        "#########",
        "#########",
    ],
    "3": [
        "########.",
        "#########",
        "......###",
        "......###",
        "......##.",
        "..#####..",
        "..######.",
        "......###",
        "......###",
        "......###",
        "......###",
        "##....###",
        "#########",
        ".#######.",
        "..#####..",
    ],
}


def _big_digit(img, x0, y0, ch, ramp):
    rows = BIG_DIGITS[ch]
    m = np.zeros((len(rows) + 2, len(rows[0]) + 2), bool)
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c == "#":
                m[y + 1, x + 1] = True
    edge_tl = m & ~X.shift(m, 1, 0) | m & ~X.shift(m, 0, 1)      # lit top/left edges
    edge_br = m & ~X.shift(m, -1, 0) | m & ~X.shift(m, 0, -1)
    ring = X.dilate(m, diag=True) & ~m
    drop = X.shift(m, 1, 1) & ~m
    for y in range(m.shape[0]):
        for x in range(m.shape[1]):
            px_, py_ = x0 + x - 1, y0 + y - 1
            if drop[y, x]:
                X.px(img, px_, py_, PANEL[0])
            elif ring[y, x]:
                X.px(img, px_, py_, PANEL[1])
            if m[y, x]:
                c = ramp[3]
                if edge_tl[y, x]:
                    c = ramp[5]
                elif edge_br[y, x]:
                    c = ramp[1]
                X.px(img, px_, py_, c)


def make_podium():
    """200 x 80 three-step podium seen slightly from above. Returns (img, meta)."""
    img = X.canvas(PODIUM_W, PODIUM_H)
    ramps = {1: GOLD, 2: SILVER, 3: BRONZE}
    spots = {}
    for place, x0, x1, ty in sorted(STEPS, key=lambda s: -s[3]):   # lowest step first
        # top surface, seen slightly from above: a trapezoid whose back edge
        # pulls in on the outer side(s) only (the inner side butts against the
        # taller middle step)
        inset_l = place in (1, 2)
        inset_r = place in (1, 3)
        for k in range(STEP_TOP_DEPTH):
            y = ty - STEP_TOP_DEPTH + k
            ins = int(round((STEP_TOP_DEPTH - 1 - k) * 0.5))
            a = x0 + (ins if inset_l else 0)
            b = x1 - (ins if inset_r else 0)
            X.rect(img, a, y, b, y + 1, PANEL[5] if k < 2 else PANEL[4])
            if inset_l:
                X.px(img, a, y, PANEL[6])
        a = x0 + (3 if inset_l else 0)
        b = x1 - (3 if inset_r else 0)
        X.rect(img, a, ty - STEP_TOP_DEPTH, b, ty - STEP_TOP_DEPTH + 1, PANEL[6])
        if place == 3:   # the middle step shades the left end of the third step's top
            for k in range(STEP_TOP_DEPTH):
                y = ty - STEP_TOP_DEPTH + k
                X.rect(img, x0, y, x0 + 4 - k // 2, y + 1, PANEL[3])
        # front lip (lit edge) + brand red stripe
        X.rect(img, x0, ty, x1, ty + 1, PANEL[6])
        X.rect(img, x0, ty + 1, x1, ty + 3, X.RED_RAMP[3])
        X.rect(img, x0, ty + 1, x1, ty + 2, X.RED_RAMP[4])
        X.rect(img, x0, ty + 3, x1, ty + 4, X.RED_RAMP[0])
        # front face
        X.rect(img, x0, ty + 4, x1, PLINTH_Y, PANEL[3])
        X.rect(img, x0, ty + 4, x0 + 1, PLINTH_Y, PANEL[4])
        X.rect(img, x1 - 1, ty + 4, x1, PLINTH_Y, PANEL[1])
        bay = X.bayer(x1 - x0, PODIUM_H)
        for y in range(PLINTH_Y - 8, PLINTH_Y):
            for x in range(x0 + 1, x1 - 1):
                if bay[y, x - x0] < (y - (PLINTH_Y - 8)) / 8.0:
                    img[y, x] = PANEL[2]
        # faint vertical panel seams
        for sx in range(x0 + 16, x1 - 8, 16):
            X.rect(img, sx, ty + 4, sx + 1, PLINTH_Y, PANEL[2])
        # place number (big digit), coloured gold / silver / bronze
        dw, dh = 9, 15
        dx = (x0 + x1) // 2 - dw // 2
        dy = ty + 4 + max(3, (PLINTH_Y - ty - 4 - dh) // 2 - 1)
        _big_digit(img, dx, dy, str(place), ramps[place])
        spots[str(place)] = [(x0 + x1) // 2, ty - STEP_TOP_DEPTH // 2]
    # plinth: PIT WALL brand band across the full width
    y0 = PLINTH_Y
    X.rect(img, 0, y0, PODIUM_W, PODIUM_H, X.RED_RAMP[2])
    X.rect(img, 0, y0, PODIUM_W, y0 + 1, X.RED_RAMP[4])
    X.rect(img, 0, PODIUM_H - 1, PODIUM_W, PODIUM_H, X.RED_RAMP[0])
    X.rect(img, 0, y0, 1, PODIUM_H, X.RED_RAMP[4])
    X.rect(img, PODIUM_W - 1, y0, PODIUM_W, PODIUM_H, X.RED_RAMP[0])
    for rep, cxm in enumerate((36, 100, 164)):
        txt = "PIT WALL"
        tw = X.text_width(txt)
        tx = cxm - tw // 2
        X.draw_text(img, tx + 1, y0 + 3, txt, X.RED_RAMP[0])
        X.draw_text(img, tx, y0 + 2, txt, hx("f8f5ec"))
        for cx0 in (tx - 10, tx + tw + 3):           # chequered tabs, as on the billboards
            for yy in range(2, 8):
                for xx in range(6):
                    X.px(img, cx0 + xx, y0 + yy, hx("f8f5ec") if (xx + yy) % 2 == 0 else hx("17181b"))
    return img, {"size": [PODIUM_W, PODIUM_H], "standing_spots": spots,
                 "note": "standing_spots: centre of each step's top surface (pixel coords); put a driver's "
                         "feet / the trophy base there"}


def make_trophy():
    """24 x 32 gold cup on a dark plinth, front view, 1 px outline."""
    W, H = 24, 32
    img = X.canvas(W, H)
    rows = {}   # y -> (x_left, x_right exclusive) of the gold body
    for y in range(3, 14):          # bowl: wide at the top, tapering
        t = (y - 3) / 10.0
        half = 8.0 - 5.0 * t ** 1.6
        rows[y] = (int(round(12 - half)), int(round(12 + half)))
    for y in range(14, 20):         # stem with a knob at y 16-17
        half = 2.5 if y in (16, 17) else 1.5 if y != 19 else 2.5
        rows[y] = (int(round(12 - half)), int(round(12 + half)))
    for y in (20, 21):              # foot collar
        rows[y] = (12 - 5, 12 + 5)
    for y, (a, b) in rows.items():
        w = b - a
        for x in range(a, b):
            t = (x + 0.5 - a) / w
            if t < 0.18:
                c = GOLD[4]
            elif t < 0.38:
                c = GOLD[5] if y < 14 else GOLD[4]
            elif t < 0.62:
                c = GOLD[4] if y < 14 else GOLD[3]
            elif t < 0.82:
                c = GOLD[3] if y < 14 else GOLD[2]
            else:
                c = GOLD[2] if y < 14 else GOLD[1]
            img[y, x] = c
    # rim + opening (dark inside of the cup)
    X.rect(img, 4, 2, 20, 3, GOLD[5])
    X.rect(img, 5, 3, 19, 4, GOLD[1])
    X.rect(img, 6, 3, 18, 4, GOLD[0])
    X.px(img, 4, 2, GOLD[6])
    X.px(img, 7, 6, GOLD[6])
    X.px(img, 7, 7, GOLD[6])
    X.px(img, 8, 5, GOLD[6])
    # band around the bowl
    for x in range(rows[10][0], rows[10][1]):
        img[10, x] = GOLD[2] if x > 12 else GOLD[3]
    # handles
    for (x, y) in ((3, 5), (2, 6), (2, 7), (2, 8), (3, 9), (4, 10)):
        img[y, x] = GOLD[4]
    for (x, y) in ((20, 5), (21, 6), (21, 7), (21, 8), (20, 9), (19, 10)):
        img[y, x] = GOLD[2]
    img[6, 3] = GOLD[1]
    img[7, 3] = GOLD[1]
    # plinth: dark carbon block with a gold plate
    X.rect(img, 5, 22, 19, 30, PANEL[3])
    X.rect(img, 5, 22, 19, 23, PANEL[5])
    X.rect(img, 5, 22, 6, 30, PANEL[4])
    X.rect(img, 18, 23, 19, 30, PANEL[1])
    X.rect(img, 5, 29, 19, 30, PANEL[1])
    X.rect(img, 8, 25, 16, 27, GOLD[3])
    X.rect(img, 8, 25, 16, 26, GOLD[4])
    X.px(img, 8, 25, GOLD[5])
    out = X.outline(img, OUTLINE)
    return out


CONFETTI = [  # 3 x 3 frames: shape rows (#: colour, +: highlight, -: shade), colour
    (["++.", "##.", "..."], X.UI["red"]),
    (["...", "+##", "..."], X.UI["yellow"]),
    (["+..", ".#.", "..-"], X.UI["blue"]),
    ([".+.", ".#.", ".-."], X.UI["green"]),
    (["+#.", ".#-", "..."], X.UI["purple"]),
    (["...", ".+#", ".#-"], X.UI["ink"]),
    (["..+", ".#.", "-.."], X.UI["red"]),
    (["#..", "+#.", ".-#"], X.UI["yellow"]),
]


def make_confetti():
    """8 frames of 3x3 in a 24x3 strip; each frame is one piece (brand colour,
    shape). Give each particle a random frame and spin it with rotation."""
    img = X.canvas(24, 3)
    for i, (rows, col) in enumerate(CONFETTI):
        hi = P.mix(col, hx("ffffff"), 0.45)
        lo = P.mix(col, hx("17181b"), 0.4)
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                if ch != ".":
                    img[y, i * 3 + x] = {"#": col, "+": hi, "-": lo}[ch]
    return img


def make_champagne_spray():
    """2 frames of 32 x 24 (strip 64 x 24). The bottle mouth sits at (1, 22) in
    each frame and the spray fans up and to the right: a solid foam jet that
    breaks into droplets. flip_h it for a spray to the left."""
    W, H = 32, 24
    strip = X.canvas(W * 2, H)
    g = X.rng(31)
    foam = [hx("ffffff"), hx("fff8e8"), hx("f8eecb"), hx("f2df9a"), hx("d9be6a")]
    parts = []
    for _ in range(60):
        t = g.random() ** 0.7
        ang = math.radians(-40 + (g.random() - 0.5) * 34 * (0.3 + t))
        parts.append((t, ang, g.random(), g.random()))
    for f in range(2):
        img = X.canvas(W, H)
        ox, oy = 1.5, 22.5
        for (t, ang, r1, r2) in parts:
            tt = (t + f * 0.09) % 1.0
            if tt < 0.18:
                continue                                    # the jet covers this part
            L = 4 + tt * 31
            x = ox + math.cos(ang) * L
            y = oy + math.sin(ang) * L + (tt ** 2) * 5      # droplets drop as they fly
            a = int(255 * (1.0 - 0.45 * tt))
            c = foam[min(4, 1 + int(r1 * 2.2 + tt * 1.6))]
            X.px(img, int(x), int(y), X.with_alpha(c, a))
            if tt < 0.5 and r2 < 0.55:                      # foam clumps (2 px)
                X.px(img, int(x) + 1, int(y), X.with_alpha(foam[2], a))
                X.px(img, int(x), int(y) + 1, X.with_alpha(foam[3], a))
            if r2 > 0.93:
                X.px(img, int(x), int(y), foam[0])          # sparkle
        # foam jet out of the bottle: 2 px wide, lit top edge
        for k in range(9):
            jx = 1 + k
            jy = 22 - int(k * 0.85)
            X.px(img, jx, jy, foam[1])
            X.px(img, jx, jy - 1, foam[0] if (k + f) % 3 else foam[1])
            X.px(img, jx, jy + 1, X.with_alpha(foam[3], 200))
        for k in range(3):                                  # jet breaking up
            X.px(img, 10 + k * 2, 13 - k * 2 - f, foam[1])
            X.px(img, 11 + k * 2, 14 - k * 2 + f, foam[2])
        X.blend(strip, img, f * W, 0)
    return strip


def make_chequered_flag():
    """4 frames of 48 x 32 (strip 192 x 32): pole on the left, flag waving
    to the right. Loop the frames at ~8 fps."""
    W, H = 48, 32
    strip = X.canvas(W * 4, H)
    FX0, FY0, FL, FH, CELL = 5, 4, 40, 20, 5
    whites = [hx("8e909a"), hx("dcdad4"), hx("f8f5ec")]
    blacks = [hx("0b0c0e"), hx("1c1d21"), hx("34363c")]
    for f in range(4):
        img = X.canvas(W, H)
        ph = f * math.pi / 2
        for x in range(FX0, FX0 + FL):
            u = x - FX0
            amp = 0.6 + 2.6 * (u / FL)
            off = amp * math.sin(2 * math.pi * u / 24.0 - ph)
            slope = (0.6 + 2.6 * ((u + 1) / FL)) * math.sin(2 * math.pi * (u + 1) / 24.0 - ph) - off
            droop = (u / FL) ** 2 * 2.0
            top = FY0 + off + droop * 0.3
            for y in range(H):
                v = y + 0.5 - top
                if not (0 <= v < FH - droop * 0.4):
                    continue
                cell = (int(u // CELL) + int(v // CELL)) % 2
                ramp = whites if cell == 0 else blacks
                lvl = 2 if slope < -0.18 else 0 if slope > 0.18 else 1
                img[y, x] = ramp[lvl]
        img = X.outline(img, OUTLINE)
        # pole + finial
        for y in range(2, H):
            img[y, 2] = X.STEEL_RAMP[4]
            img[y, 3] = X.STEEL_RAMP[2]
            img[y, 4] = X.STEEL_RAMP[0] if img[y, 4][3] == 0 else img[y, 4]
        X.rect(img, 1, 0, 5, 2, GOLD[4])
        X.px(img, 1, 0, GOLD[6])
        X.px(img, 4, 1, GOLD[2])
        X.blend(strip, img, f * W, 0)
    return strip


# ===========================================================================
# RACE HUD ICONS (UI pixels, ink style like ui/icon_*.png)
# ===========================================================================

TYRE_LETTER = {
    "soft": [".###", "#...", ".##.", "...#", "###."],
    "medium": ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
    "hard": ["#..#", "#..#", "####", "#..#", "#..#"],
}


def make_icon_tyre(compound):
    """12 x 12: tyre (dark rubber disc) with the compound band and its letter."""
    img = X.canvas(12, 12)
    col = COMPOUND[compound]
    for y in range(12):
        for x in range(12):
            r = math.hypot(x + 0.5 - 6, y + 0.5 - 6)
            if r > 6.0:
                continue
            if r > 5.0:
                img[y, x] = hx("2e3035")              # tread edge
            elif r > 3.6:
                img[y, x] = col                        # compound band
            else:
                img[y, x] = hx("17181b")              # sidewall / hub
    rows = TYRE_LETTER[compound]
    lw = len(rows[0])
    x0 = 6 - lw // 2 if lw % 2 == 0 else 4
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch == "#":
                img[4 + y - 1 + 1, x0 + x] = INK
    return img


def make_icon_pit():
    """16 x 16 'P' in a box with the panel chamfers (top-left, bottom-right)."""
    rows = [
        "................",
        ".....##########.",
        "....#.........#.",
        "...#..........#.",
        "..#...######..#.",
        ".#....#######.#.",
        ".#....##...##.#.",
        ".#....##...##.#.",
        ".#....#######.#.",
        ".#....######..#.",
        ".#....##......#.",
        ".#....##.....#..",
        ".#....##....#...",
        ".#.........#....",
        ".##########.....",
        "................",
    ]
    return X.from_ascii(rows, {"#": INK})


def make_icon_limiter():
    """16 x 16 pit limiter: gauge with the needle held against a limit stop."""
    rows = [
        "................",
        ".....######.....",
        "...##......##...",
        "..#..........#..",
        ".#.##.....#...#.",
        ".#..##.......##.",
        "#....##.........",
        "#.....##........",
        "#......##......#",
        "#.......#......#",
        "#..............#",
        ".#............#.",
        "................",
        "...##########...",
        "...##########...",
        "................",
    ]
    return X.from_ascii(rows, {"#": INK})


# ===========================================================================
# BUILD
# ===========================================================================

def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return int(f) if f.is_integer() else f
    if isinstance(o, np.integer):
        return int(o)
    return o


def write_json(obj, name):
    (OUT / name).write_text(json.dumps(_jsonable(obj), indent=2) + "\n", encoding="utf-8")


def build():
    """Write every race sprite + json. Returns {filename: image} for the sheet."""
    out = {}
    crew = crew_sprites()
    crew_meta = {}
    for name, s in crew.items():
        out[f"{name}_paint.png"] = s["paint"]
        out[f"{name}_detail.png"] = s["detail"]
        h, w = s["paint"].shape[:2]
        crew_meta[name] = {"size": [w, h], "facing": s["facing"], "anchors": s["anchors"]}
    for comp in COMPOUND:
        out[f"tyre_new_{comp}.png"] = tyre_flat(comp)
        out[f"tyre_held_{comp}.png"] = tyre_held(comp)
    out["wheel_gun_spark.png"] = make_wheel_gun_spark()

    out["pit_lane.png"] = make_pit_lane()
    bp, bd = make_pit_box()
    out["pit_box_paint.png"] = bp
    out["pit_box_detail.png"] = bd
    out["pit_box.png"] = merged(bp, bd)
    out["pit_entry_line.png"] = make_pit_entry_line()
    out["pit_speed_board.png"] = make_pit_speed_board()
    gf, gp = make_garage_front()
    out["garage_front.png"] = gf
    out["garage_front_paint.png"] = gp
    out["pit_wall_strip.png"] = make_pit_wall_strip()

    out["start_lights.png"] = make_start_lights()
    out["start_light_on.png"] = make_start_light_on()
    pod, pod_meta = make_podium()
    out["podium.png"] = pod
    out["trophy.png"] = make_trophy()
    out["confetti.png"] = make_confetti()
    out["champagne_spray.png"] = make_champagne_spray()
    out["chequered_flag.png"] = make_chequered_flag()

    for comp in COMPOUND:
        out[f"icon_tyre_{comp}.png"] = make_icon_tyre(comp)
    out["icon_pit.png"] = make_icon_pit()
    out["icon_limiter.png"] = make_icon_limiter()

    OUT.mkdir(parents=True, exist_ok=True)
    for name, img in out.items():
        save(img, name)

    write_json({
        "px_per_m": 10,
        "note": "Pixel-corner coordinates, y down. Sprites face +y ('down') unless 'facing' says otherwise. "
                "For crew on the +y side of the car use flip_v and mirror the anchor: y' = height - y. "
                "Draw order per sprite: _paint (modulate = team colour), [carriers only: "
                "tyre_held_<compound>.png centred on anchors.wheel_center, flip_v'd with the carrier], "
                "_detail (untinted). The drop shadow lives in _paint (black survives the tint).",
        "sprites": crew_meta,
        "frames": {"crew_tyre_gunner": ["a", "b"], "crew_tyre_carrier": ["a", "b"],
                   "crew_lollipop": ["stop", "go"]},
        "pit_stop_layout": {
            "note": "Points are relative to the car centre (pixel corner (40, 16) of the 80x32 car canvas), "
                    "nose +x. Put the named anchor of the sprite on the point. layer: under_car = draw "
                    "after car/shadow.png but before the car floor (the jack heads go under the car); "
                    "over_car = draw after the car. Use frame a/b alternately so the crew look busy.",
            "car_center_in_canvas": [40, 16],
            "crew": [{"sprite": n, "anchor": a, "at": pt, "flip_v": f, "layer": z}
                     for (n, a, pt, f, z) in PIT_STOP_LAYOUT],
        },
    }, "crew.json")

    write_json({
        "size": [160, 40],
        "pod_centers": [[x, POD_Y] for x in POD_X],
        "lamp_centers_per_pod": [[0, dy] for dy in LAMP_DY],
        "light_on": {"file": "start_light_on.png", "size": [ON_W, ON_H], "center": [ON_W // 2, ON_H // 2],
                     "topleft_per_pod": [[x - ON_W // 2, POD_Y - ON_H // 2] for x in POD_X]},
        "note": "Pixel-corner coordinates in start_lights.png. To light pod i, draw start_light_on.png "
                "centred on pod_centers[i] (Sprite2D centered = true at that point, or top-left at "
                "light_on.topleft_per_pod[i]). Pods light left to right, one per second; all go out "
                "together for the start.",
    }, "start_lights.json")
    write_json(pod_meta, "podium.json")
    return out


# ===========================================================================
# CONTACT SHEET  (race/preview_race.png, 3x on #141518)
# ===========================================================================

BG = X.UI["bg"]
TEAMS = [hx("e8352b"), hx("f1efea"), hx("f2c230"), hx("5ec8e5"), hx("3ecf6a"), hx("a855f7"), hx("e07a2f"),
         hx("3d68b0")]   # deco/pit_building.png team order
RED = hx("e8352b")


class Sheet:
    def __init__(self, width):
        self.W = width
        self.items = []
        self.x, self.y, self.row_h = 8, 8, 0

    def heading(self, text):
        self.newline(6)
        img = X.canvas(X.text_width(text) + 2, 7)
        X.draw_text(img, 0, 0, text, X.UI["ink"])
        self.items.append((8, self.y, img))
        self.items.append((8, self.y + 7, X.canvas(self.W - 16, 1, X.UI["line"])))
        self.y += 12

    def add(self, label, img, gap=10):
        lw = X.text_width(label)
        w = max(img.shape[1], lw)
        if self.x + w > self.W - 8:
            self.newline()
        lab = X.canvas(lw + 1, 6)
        X.draw_text(lab, 0, 0, label, X.UI["ink2"])
        self.items.append((self.x, self.y, lab))
        self.items.append((self.x, self.y + 8, img))
        self.x += w + gap
        self.row_h = max(self.row_h, img.shape[0] + 8)

    def newline(self, extra=4):
        if self.row_h:
            self.y += self.row_h + extra
        self.x, self.row_h = 8, 0

    def render(self):
        self.newline()
        c = X.canvas(self.W, self.y + 8, BG)
        for x, y, img in self.items:
            X.blend(c, img, x, y)
        return c


def on(img, color, pad=2):
    c = X.canvas(img.shape[1] + pad * 2, img.shape[0] + pad * 2, color)
    X.blend(c, img, pad, pad)
    return c


def tiled_bg(tile, w, h):
    th, tw = tile.shape[:2]
    return np.tile(tile, (h // th + 1, w // tw + 1, 1))[:h, :w].copy()


def pit_stop_scene(sprites, frame, lol, compound="medium", tint=RED):
    """Car-scale mock: team box, car on the jacks, full crew, a spare tyre stack."""
    W, H = 176, 100
    CX, CY = 84, 50
    sc = tiled_bg(X.palette_map(pit_asphalt(64, 32, 77), PIT_ASPHALT), W, H)
    # the team box at car scale (7 x 3.5 m = 70 x 35 px): worn team fill, white line
    box = X.canvas(70, 35)
    # matte ground paint: a darker grey than the car's paint so the car pops
    g = X.rng(4)
    fill = X.canvas(66, 31, hx("5e5e62"))
    for _ in range(90):
        X.px(fill, int(g.random() * 66), int(g.random() * 31), hx("535357") if g.random() < 0.7 else hx("6a6a6e"))
    X.blend(box, P.multiply(fill, tint), 2, 2)
    for x in range(70):
        box[0, x] = box[34, x] = LINE_WHITE[2]
    for y in range(35):
        box[y, 0] = box[y, 69] = LINE_WHITE[2]
    for y in (8, 25):
        X.rect(box, 52, y, 58, y + 2, LINE_WHITE[2])
    X.blend(sc, box, CX - 35, CY - 17)
    # dashed fast-lane line above the box, garage line below
    for x in range(W):
        if x % 20 < 10:
            sc[CY - 30, x] = LINE_WHITE[1]
    # spare tyres waiting (lying flat) by the box
    for i, (tx, ty) in enumerate(((8, 76), (18, 78), (8, 86))):
        X.blend(sc, tyre_flat(("soft", "soft", "hard")[i]), tx, ty)

    def put(layer):
        for i, (name, anc, pt, flip, z) in enumerate(PIT_STOP_LAYOUT):
            if z != layer:
                continue
            key = name
            if name in ("crew_tyre_gunner", "crew_tyre_carrier"):
                key = f"{name}_{frame if i % 2 == 0 else ('b' if frame == 'a' else 'a')}"
            if name == "crew_lollipop":
                key = f"{name}_{lol}"
            spr = sprites[key]
            ox, oy = place_origin(spr, anc, pt, flip)
            draw_crew(sc, spr, CX + ox, CY + oy, tint, flip, compound)
            if name == "crew_tyre_gunner" and key.endswith("_b"):
                sp = make_wheel_gun_spark()[:, (0 if frame == "a" else 7):(7 if frame == "a" else 14)]
                X.blend(sc, sp, CX + pt[0] - 3, CY + pt[1] - 3)

    put("under_car")
    X.blend(sc, compose_car(tint, hx("f2c230"), compound=compound), CX - 40, CY - 16)
    put("over_car")
    return sc


def pit_lane_mock(out):
    """World-scale mock (1 px = 0.25 m): garages, boxes, fast lane, pit wall,
    entry line, speed board, track. Garages on top, track below."""
    W = 256
    rows = []
    y = 0
    H = 20 + 16 + 24 + 8 + 20
    img = X.canvas(W, H, hx("2f3136"))
    gf, gp = out["garage_front.png"], out["garage_front_paint.png"]
    for i in range(8):
        X.blend(img, gf, i * 32, y)
        X.blend(img, P.multiply(gp, TEAMS[i]), i * 32, y)
    y += 20
    work = X.palette_map(pit_asphalt(64, 16, 77), PIT_ASPHALT)
    img[y:y + 16] = np.tile(work, (1, W // 64, 1))
    bp, bd = out["pit_box_paint.png"], out["pit_box_detail.png"]
    for i in range(8):
        X.blend(img, P.multiply(bp, TEAMS[i]), i * 32 + 2, y + 1)
        X.blend(img, bd, i * 32 + 2, y + 1)
    y += 16
    img[y:y + 24] = np.tile(out["pit_lane.png"], (1, W // 64, 1))
    y += 24
    wall_y = y
    img[y:y + 8] = tiled_bg(X.load(X.SPRITES / "track" / "asphalt.png"), W, 8)
    ws = np.tile(out["pit_wall_strip.png"], (1, W // 32, 1))
    X.blend(img, ws[:, 64:], 64, y)
    X.blend(img, np.tile(out["pit_entry_line.png"], (1, 2, 1)), 0, y)
    y += 8
    img[y:] = tiled_bg(X.load(X.SPRITES / "track" / "asphalt.png"), W, H - y)
    X.blend(img, out["pit_speed_board.png"], 66, wall_y - 14)
    return img


def podium_scene(out):
    """UI-scale mock (half of the 640x360 screen): podium, trophy, flag,
    champagne and confetti on a dark backdrop with a stepped spotlight."""
    W, H = 320, 180
    sc = X.canvas(W, H, BG)
    # stepped, dithered spotlight behind the podium
    bay = X.bayer(W, H)
    for y in range(H):
        for x in range(W):
            d = math.hypot((x - 160) / 1.6, (y - 120) / 1.0)
            t = max(0.0, 1.0 - d / 120.0)
            lvl = int(t * 3 + bay[y, x] * 0.9)
            if lvl > 0:
                sc[y, x] = [BG, hx("181a1e"), hx("1d1f23"), hx("23252a")][min(3, lvl)]
    pod = out["podium.png"]
    px0, py0 = 60, H - 80 - 6
    X.blend(sc, pod, px0, py0)
    spots = make_podium()[1]["standing_spots"]
    tro = out["trophy.png"]
    sx, sy = spots["1"]
    X.blend(sc, tro, px0 + sx - 12, py0 + sy - 30)
    sp = out["champagne_spray.png"]
    sx2, sy2 = spots["2"]
    X.blend(sc, sp[:, :32], px0 + sx2 - 1, py0 + sy2 - 36)
    sx3, sy3 = spots["3"]
    X.blend(sc, sp[:, 32:][:, ::-1], px0 + sx3 - 31, py0 + sy3 - 36)
    fl = out["chequered_flag.png"]
    X.blend(sc, fl[:, 0:48], 12, 30)
    X.blend(sc, fl[:, 96:144][:, ::-1], W - 60, 30)
    g = X.rng(3)
    cf = out["confetti.png"]
    for _ in range(70):
        x, y = int(g.random() * W), int(g.random() * (H - 70))
        k = int(g.random() * 8)
        X.blend(sc, cf[:, k * 3:k * 3 + 3], x, y)
    return sc


def preview(out):
    sprites = crew_sprites()
    sh = Sheet(744)
    sh.heading("PIT WALL - RACE ART (3X). CREW AT CAR SCALE 10 PX/M, PIT LANE AT 4 PX/M, UI AT 1X")
    sh.heading("PIT STOP MOCK: CAR LAYERS + CREW + HELD TYRES, TEAM TINT RED, SHOWN X2")
    a = pit_stop_scene(sprites, "a", "stop")
    b = pit_stop_scene(sprites, "b", "go")
    sh.add("frame a + lollipop_stop (jacks under the car)", X.scale(a, 2), gap=8)
    sh.add("frame b + lollipop_go + wheel_gun_spark", X.scale(b, 2), gap=0)
    sh.newline()
    sh.heading("PIT CREW X2 (PAINT TINTED RED + DETAIL; CARRIERS WITH TYRE_HELD_MEDIUM)")
    asph = X.palette_map(pit_asphalt(64, 32, 77), PIT_ASPHALT)
    for name, s in sprites.items():
        h, w = s["paint"].shape[:2]
        c = tiled_bg(asph, w + 4, h + 4)
        draw_crew(c, s, 2, 2, RED)
        sh.add(name.replace("crew_", ""), X.scale(c, 2))
    sh.newline()
    s = sprites["crew_tyre_gunner_a"]
    sh.add("gunner_a _paint", X.scale(on(s["paint"], hx("2a2c31")), 2))
    sh.add("_detail", X.scale(on(s["detail"], hx("2a2c31")), 2))
    for t, n in ((hx("f1efea"), "white"), (hx("3a6fd8"), "blue"), (hx("f2c230"), "yellow")):
        c = tiled_bg(asph, 20, 20)
        draw_crew(c, s, 2, 2, t)
        sh.add(n, X.scale(c, 2))
    s = sprites["crew_tyre_carrier_a"]
    for comp in COMPOUND:
        c = tiled_bg(asph, 20, 22)
        draw_crew(c, s, 2, 2, hx("3a6fd8"), compound=comp)
        sh.add(f"carrier {comp}", X.scale(c, 2))
    sh.newline()
    for comp in COMPOUND:
        sh.add(f"tyre_new_{comp}", X.scale(on(out[f"tyre_new_{comp}.png"], hx("2a2c31")), 3))
    for comp in COMPOUND:
        sh.add(f"tyre_held_{comp}", X.scale(on(out[f"tyre_held_{comp}.png"], hx("2a2c31")), 3))
    sh.add("wheel_gun_spark 2 frames", X.scale(on(out["wheel_gun_spark.png"], hx("2a2c31")), 3))
    sh.newline()
    sh.heading("PIT LANE (4 PX/M). STRIPS TILED ALONG U")
    sh.add("pit_lane.png x3", on(np.tile(out["pit_lane.png"], (1, 3, 1)), hx("2f3136")))
    sh.add("pit_wall_strip.png x4", on(np.tile(out["pit_wall_strip.png"], (1, 4, 1)), hx("2f3136")))
    sh.add("pit_entry_line.png x4", on(np.tile(out["pit_entry_line.png"], (1, 4, 1)), hx("2f3136")))
    sh.newline()
    sh.add("pit_box (untinted)", on(out["pit_box.png"], hx("2a2c31")))
    sh.add("_paint", on(out["pit_box_paint.png"], hx("2a2c31")))
    sh.add("_detail", on(out["pit_box_detail.png"], hx("2a2c31")))
    for t in TEAMS[:4]:
        c = on(P.multiply(out["pit_box_paint.png"], t), hx("2a2c31"))
        X.blend(c, out["pit_box_detail.png"], 2, 2)
        sh.add("tinted", c)
    sh.add("pit_speed_board", on(out["pit_speed_board.png"], hx("2f3136")))
    sh.add("garage_front", on(out["garage_front.png"], hx("2f3136")))
    sh.add("_paint", on(out["garage_front_paint.png"], hx("2f3136")))
    for t in TEAMS[:2]:
        c = on(out["garage_front.png"], hx("2f3136"))
        X.blend(c, P.multiply(out["garage_front_paint.png"], t), 2, 2)
        sh.add("tinted", c)
    sh.newline()
    sh.add("pit lane mock x2: garages, boxes, fast lane, pit wall, entry line, 80 board",
           X.scale(pit_lane_mock(out), 2))
    sh.newline()
    sh.heading("START SEQUENCE (UI 1X)")
    sl = out["start_lights.png"]
    on_ = out["start_light_on.png"]
    sh.add("start_lights.png (all off)", on(sl, BG))
    lit3 = sl.copy()
    for x in POD_X[:3]:
        X.blend(lit3, on_, x - ON_W // 2, POD_Y - ON_H // 2)
    sh.add("+ start_light_on x3", on(lit3, BG))
    lit5 = sl.copy()
    for x in POD_X:
        X.blend(lit5, on_, x - ON_W // 2, POD_Y - ON_H // 2)
    sh.add("x5", on(lit5, BG))
    sh.add("start_light_on", on(on_, hx("17181b")))
    sh.newline()
    sh.heading("PODIUM CUTSCENE (UI 1X)")
    sh.add("mock: podium + trophy + champagne + flag + confetti", podium_scene(out))
    sh.add("podium.png", on(out["podium.png"], BG))
    sh.newline()
    sh.add("trophy x2", X.scale(on(out["trophy.png"], BG), 2))
    sh.add("chequered_flag.png 4 frames x2", X.scale(on(out["chequered_flag.png"], BG), 2))
    sh.add("champagne_spray 2 frames x2", X.scale(on(out["champagne_spray.png"], BG), 2))
    sh.add("confetti 8 frames x4", X.scale(on(out["confetti.png"], BG), 4))
    sh.newline()
    sh.heading("RACE HUD ICONS (UI 1X, SHOWN X1 AND X3 ON THE PANEL COLOUR)")
    for n in ("icon_tyre_soft", "icon_tyre_medium", "icon_tyre_hard", "icon_pit", "icon_limiter"):
        sh.add(n, on(out[f"{n}.png"], X.UI["panel"], 3))
    for n in ("icon_tyre_soft", "icon_tyre_medium", "icon_tyre_hard", "icon_pit", "icon_limiter"):
        sh.add("x3", X.scale(on(out[f"{n}.png"], X.UI["panel"], 2), 3))
    yel = P.multiply(out["icon_limiter.png"], X.UI["yellow"])
    sh.add("limiter modulated", X.scale(on(yel, X.UI["panel"], 2), 3))
    sheet = sh.render()
    X.save(X.scale(sheet, 3), OUT / "preview_race.png")
    return sheet


if __name__ == "__main__":
    files = build()
    preview(files)
    for name in files:
        print("wrote", OUT / name)
    print("wrote", OUT / "crew.json", OUT / "start_lights.json", OUT / "podium.json", OUT / "preview_race.png")
