"""UI chrome: logo, 9-slice panels/buttons/tabs, icons, steering wheel, rotary,
wing profiles, garage backdrop, vignette. The menu background lives in menu_bg.py.

    python tools/art/ui.py
"""

from __future__ import annotations

import json
import math

import numpy as np
from PIL import Image, ImageDraw

from pixel import (
    CLEAR, SHADOW, SPRITES, UI, alpha_mask, blend, canvas, clean_orphans, dilate, disc_mask, draw_text, erode, fbm,
    from_ascii, hx, mix, outline, palette_map, poisson_torus, polygon_mask, px, quantize, rect, rng, save, shift,
    text_width,
    with_alpha,
)

OUT = SPRITES / "ui"

INK = UI["ink"]
RED = UI["red"]
BLACK = hx("0b0c0e")


# --------------------------------------------------------------------------
# Logo
# --------------------------------------------------------------------------


def _glyph_polys(ch, h, s):
    """Angular, condensed letter shapes as (outer polygons, hole polygons, width)."""
    c = max(2, round(s * 0.75))  # chamfer
    if ch == "P":
        w = round(h * 0.62)
        m = round(h * 0.56)
        outer = [[(0, 0), (w - c, 0), (w, c), (w, m - c), (w - c, m), (s, m), (s, h), (0, h)]]
        holes = [[(s, s), (w - s, s), (w - s, m - s), (s, m - s)]]
        return outer, holes, w
    if ch == "I":
        w = s + 1
        return [[(0, 0), (w, 0), (w, h), (0, h)]], [], w
    if ch == "T":
        w = round(h * 0.62)
        a = (w - s - 1) // 2
        return [[(0, 0), (w, 0), (w, s), (a + s + 1, s), (a + s + 1, h), (a, h), (a, s), (0, s)]], [], w
    if ch == "W":
        w = round(h * 0.96)
        mid = w // 2
        hs = (s + 1) // 2
        top_mid = round(h * 0.34)
        outer = [[(0, 0), (s, 0), (s, h - s), (mid - hs, h - s), (mid - hs, top_mid), (mid + hs + (s % 2 == 0), top_mid),
                  (mid + hs + (s % 2 == 0), h - s), (w - s, h - s), (w - s, 0), (w, 0), (w, h - c), (w - c, h),
                  (c, h), (0, h - c)]]
        return outer, [], w
    if ch == "A":
        w = round(h * 0.62)
        cb = round(h * 0.5)
        k = c + 2
        outer = [[(0, k), (k, 0), (w - k, 0), (w, k), (w, h), (0, h)]]
        holes = [[(s, s + 1), (w - s, s + 1), (w - s, cb - 1), (s, cb - 1)],
                 [(s, cb + s - 1), (w - s, cb + s - 1), (w - s, h), (s, h)]]
        return outer, holes, w
    if ch == "L":
        w = round(h * 0.52)
        return [[(0, 0), (s, 0), (s, h - s), (w, h - s), (w, h), (0, h)]], [], w
    raise KeyError(ch)


def _wordmark_mask(text, h, s, gap, word_gap, shear):
    """Rasterise the word upright, then shear it to italic by whole pixels."""
    widths = []
    for ch in text:
        widths.append(word_gap if ch == " " else _glyph_polys(ch, h, s)[2])
    total = sum(widths) + gap * (len(text) - 1)
    pad = h // shear + 2
    W = total + pad
    im = Image.new("L", (W, h), 0)
    d = ImageDraw.Draw(im)
    x = 0
    for ch, w in zip(text, widths):
        if ch != " ":
            outer, holes, _ = _glyph_polys(ch, h, s)
            for poly in outer:
                d.polygon([(x + px_, py_) for px_, py_ in poly], fill=255)
            for poly in holes:
                d.polygon([(x + px_, py_) for px_, py_ in poly], fill=0)
        x += w + gap
    up = np.array(im) > 0
    # PIL polygons include the far edge; trim to the intended box per row
    out = np.zeros((h, W), bool)
    for y in range(h):
        off = (h - 1 - y) // shear
        out[y, off:off + total] = up[y, :total]
    return out


def make_logo(h, s, gap, word_gap, shear, W, H, small=False):
    img = canvas(W, H)
    m = _wordmark_mask("PIT WALL", h, s, gap, word_gap, shear)
    mh, mw = m.shape
    stripe_h = 3 if small else 5
    cell = 2 if small else 3
    ccols, crows = (3, 2) if small else (4, 2)
    flag_w = ccols * cell
    dash_room = 10 if small else 17
    pad = h // shear + 2
    core = mw - pad  # width of the letters' bottom row
    total_w = dash_room + mw
    ox = (W - total_w) // 2 + dash_room
    oy = 1 if small else 2
    sy0 = oy + mh + (2 if small else 3)
    stripe = np.zeros((H, W), bool)
    x_start = ox + (2 if small else 4)
    x_end = ox + core - flag_w - (3 if small else 4)

    def sheared_row(y0, y1, a, b, mask):
        for y in range(y0, y1):
            off = (y1 - 1 - y) // shear
            mask[y, max(0, a + off):max(0, b + off)] = True

    sheared_row(sy0, sy0 + stripe_h, x_start, x_end, stripe)
    if small:
        dashes = [(x_start - 8, x_start - 3), (x_start - 12, x_start - 10)]
    else:
        dashes = [(x_start - 12, x_start - 4), (x_start - 19, x_start - 15)]
    for (a, b) in dashes:
        sheared_row(sy0, sy0 + stripe_h, a, b, stripe)
    word = np.zeros((H, W), bool)
    word[oy:oy + mh, ox:ox + mw] = m
    ext = np.zeros_like(word)
    for k in range(1, (1 if small else 2) + 1):
        ext |= shift(word, k, k)
    ext &= ~word
    img[ext] = hx("7a1a26")
    img[word] = INK
    lower = np.zeros_like(word)
    lower[oy + int(mh * 0.62):oy + mh, :] = True
    img[word & lower] = hx("d9d5cc")
    img[word & ~shift(word, 0, 1)] = hx("ffffff")
    img[stripe] = RED
    img[stripe & ~shift(stripe, 0, 1)] = hx("f2603f")
    img[stripe & ~shift(stripe, 0, -1)] = hx("a8242a")
    # chequered flag block at the end of the stripe, sheared with it
    fy0 = sy0 + stripe_h - crows * cell
    fx0 = x_end + (2 if small else 3)
    for r in range(crows):
        for c in range(ccols):
            col = INK if (r + c) % 2 == 0 else hx("26272c")
            for dy in range(cell):
                y = fy0 + r * cell + dy
                off = (sy0 + stripe_h - 1 - y) // shear
                for dx in range(cell):
                    px(img, fx0 + c * cell + dx + off, y, col)
    return outline(img, BLACK)


# --------------------------------------------------------------------------
# 9-slice chrome
# --------------------------------------------------------------------------


def _notch(img, n, color=CLEAR):
    """Cut n-px diagonal notches into the four corners."""
    H, W = img.shape[:2]
    for i in range(n):
        for j in range(n - i):
            img[i, j] = color
            img[i, W - 1 - j] = color
            img[H - 1 - i, j] = color
            img[H - 1 - i, W - 1 - j] = color


def _notch_border(img, n, color):
    """Draw the diagonal border lines along the notches."""
    H, W = img.shape[:2]
    for i in range(n + 1):
        j = n - i
        for (y, x) in [(i, j), (i, W - 1 - j), (H - 1 - i, j), (H - 1 - i, W - 1 - j)]:
            img[y, x] = color


def make_panel(border, accent=None, inner=None, chamfer_col=None):
    """24 x 24, 9-slice margins 8. Chamfered top-left and bottom-right corners."""
    S = 24
    n = 4
    img = canvas(S, S, UI["panel"])
    rect(img, 0, 0, S, 1, border)
    rect(img, 0, S - 1, S, S, border)
    rect(img, 0, 0, 1, S, border)
    rect(img, S - 1, 0, S, S, border)
    rect(img, 1, 1, S - 1, 2, inner or hx("23252a"))
    for i in range(n):
        for j in range(n - i):
            img[i, j] = CLEAR
            img[S - 1 - i, S - 1 - j] = CLEAR
    dc = chamfer_col or border
    for i in range(n + 1):
        img[i, n - i] = dc
        img[S - 1 - i, S - 1 - (n - i)] = dc
    # square-ish corners elsewhere get a 1 px round-off
    img[0, S - 1] = CLEAR
    img[S - 1, 0] = CLEAR
    if accent is not None:
        rect(img, n + 1, 0, S - 1, 2, accent)
        rect(img, n + 1, 0, S - 1, 1, mix(accent, hx("ffffff"), 0.18))
        img[0, S - 1] = CLEAR
        img[1, n - 1] = accent
        img[0, n] = mix(accent, hx("ffffff"), 0.18)
    return img


def make_button(face, hi, edge, border, pressed=False):
    W, H = 24, 16
    img = canvas(W, H)
    rect(img, 0, 0, W, H, border)
    if not pressed:
        rect(img, 1, 1, W - 1, H - 3, face)
        rect(img, 1, 1, W - 1, 2, hi)
        rect(img, 1, H - 3, W - 1, H - 1, edge)
    else:
        rect(img, 1, 1, W - 1, 2, edge)            # shadow at the top: face sits lower
        rect(img, 1, 2, W - 1, H - 2, face)
        rect(img, 1, H - 2, W - 1, H - 1, edge)
    # rounded (1 px) corners
    for (x, y) in [(0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)]:
        img[y, x] = CLEAR
    return img


def make_tab(active):
    W, H = 24, 14
    img = canvas(W, H)
    face = UI["panel"] if active else hx("17181b")
    border = UI["line2"] if active else UI["line"]
    rect(img, 0, 0, W, H, face)
    rect(img, 0, 0, W, 1, border)
    rect(img, 0, 0, 1, H, border)
    rect(img, W - 1, 0, W, H, border)
    if not active:
        rect(img, 0, H - 1, W, H, UI["line"])
    # notched top corners
    for i in range(2):
        for j in range(2 - i):
            img[i, j] = CLEAR
            img[i, W - 1 - j] = CLEAR
    for (y, x) in [(0, 2), (1, 1), (2, 0), (0, W - 3), (1, W - 2), (2, W - 1)]:
        img[y, x] = border
    if active:
        rect(img, 3, 0, W - 3, 2, RED)
        rect(img, 3, 0, W - 3, 1, hx("f2603f"))
    else:
        rect(img, 1, 1, W - 1, 2, hx("1d1f23"))
    return img


# --------------------------------------------------------------------------
# Icons (16 x 16, ink, 1 px strokes)
# --------------------------------------------------------------------------

ICONS = {
    "flag": [
        "................",
        "..############..",
        "..###..##..###..",
        "..###..##..###..",
        "..#..##..##..#..",
        "..#..##..##..#..",
        "..###..##..###..",
        "..###..##..###..",
        "..############..",
        "..#.............",
        "..#.............",
        "..#.............",
        "..#.............",
        "..#.............",
        ".###............",
        "................",
    ],
    "stopwatch": [
        "......###.......",
        ".......#........",
        ".......#....#...",
        ".....#####.#....",
        "...##.....##....",
        "..#.........#...",
        "..#....#....#...",
        ".#.....#.....#..",
        ".#.....#.....#..",
        ".#.....###...#..",
        ".#...........#..",
        ".#...........#..",
        "..#.........#...",
        "..#.........#...",
        "...##.....##....",
        ".....#####......",
    ],
    "wrench": [
        "................",
        "...........#..#.",
        "..........##..##",
        "..........##..##",
        "..........######",
        ".........######.",
        "........###.....",
        ".......###......",
        "......###.......",
        ".....###........",
        "....###.........",
        "...###..........",
        "..###...........",
        ".###............",
        ".##.............",
        "................",
    ],
    "car": [
        "................",
        "....########....",
        ".......##.......",
        "..##...##...##..",
        "..############..",
        "..##..####..##..",
        "......####......",
        ".....######.....",
        "....###..###....",
        "....###..###....",
        "....########....",
        "..##.######.##..",
        "..############..",
        "..##.######.##..",
        "....########....",
        "................",
    ],
    "pack": [
        "................",
        "...#.#.#.#.#.#..",
        "...###########..",
        "...#.........#..",
        "...#.........#..",
        "...#....#....#..",
        "...#...###...#..",
        "...#.#######.#..",
        "...#..#####..#..",
        "...#..##.##..#..",
        "...#..#...#..#..",
        "...#.........#..",
        "...#.........#..",
        "...###########..",
        "...#.#.#.#.#.#..",
        "................",
    ],
    "trophy": [
        "................",
        "...##########...",
        "...#........#...",
        ".###........###.",
        ".#.#........#.#.",
        ".#.#........#.#.",
        "..##........##..",
        "....#......#....",
        ".....#....#.....",
        "......#..#......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".....######.....",
        "....########....",
        "................",
    ],
    "lock": [
        "................",
        ".....######.....",
        "....#......#....",
        "....#......#....",
        "....#......#....",
        "....#......#....",
        "..############..",
        "..############..",
        "..#####..#####..",
        "..#####..#####..",
        "..######.#####..",
        "..######.#####..",
        "..############..",
        "..############..",
        "................",
        "................",
    ],
    "play": [
        "................",
        "................",
        "....##..........",
        "....###.........",
        "....####........",
        "....#####.......",
        "....######......",
        "....#######.....",
        "....#######.....",
        "....######......",
        "....#####.......",
        "....####........",
        "....###.........",
        "....##..........",
        "................",
        "................",
    ],
    "back": [
        "................",
        "................",
        "................",
        "......#.........",
        ".....##.........",
        "....##..........",
        "...##...........",
        "..############..",
        "..############..",
        "...##...........",
        "....##..........",
        ".....##.........",
        "......#.........",
        "................",
        "................",
        "................",
    ],
    "gamepad": [
        "................",
        "................",
        "................",
        "...##########...",
        "..#..........#..",
        ".#...#....#...#.",
        ".#..###..#.#..#.",
        "#....#....#....#",
        "#..............#",
        "#..............#",
        "#...########...#",
        "#..#........#..#",
        ".##..........##.",
        "................",
        "................",
        "................",
    ],
    "keyboard": [
        "................",
        "................",
        "................",
        ".##############.",
        ".#............#.",
        ".#.#.#.#.#.#..#.",
        ".#............#.",
        ".#..#.#.#.#.#.#.",
        ".#............#.",
        ".#...######...#.",
        ".#............#.",
        ".##############.",
        "................",
        "................",
        "................",
        "................",
    ],
    "sound": [
        "................",
        "................",
        "......#.....#...",
        ".....##......#..",
        "....###..#....#.",
        "#######...#...#.",
        "#######...#...#.",
        "#######...#...#.",
        "#######...#...#.",
        "....###..#....#.",
        ".....##......#..",
        "......#.....#...",
        "................",
        "................",
        "................",
        "................",
    ],
    "mute": [
        "................",
        "................",
        "......#.........",
        ".....##.........",
        "....###.........",
        "#######..#...#..",
        "#######...#.#...",
        "#######....#....",
        "#######...#.#...",
        "....###..#...#..",
        ".....##.........",
        "......#.........",
        "................",
        "................",
        "................",
        "................",
    ],
    "coin": [
        "................",
        ".....#####......",
        "...##.....##....",
        "..#.........#...",
        ".#.....#.....#..",
        ".#.....#.....#..",
        "#....#####....#.",
        "#.....###.....#.",
        "#.....#.#.....#.",
        ".#...#...#...#..",
        ".#...........#..",
        "..#.........#...",
        "...##.....##....",
        ".....#####......",
        "................",
        "................",
    ],
    "user": [
        "................",
        "......####......",
        ".....#....#.....",
        "....#......#....",
        "....#......#....",
        "....#......#....",
        ".....#....#.....",
        "......####......",
        "................",
        "....########....",
        "...#........#...",
        "..#..........#..",
        "..#..........#..",
        "..############..",
        "................",
        "................",
    ],
}


def _bolt():
    m = polygon_mask(16, 16, [(10, 0.5), (3.5, 9), (7.5, 9), (5.5, 15.5), (12.5, 6.5), (8.5, 6.5), (11.5, 0.5)], ss=4)
    return m


def _gear():
    yy, xx = np.mgrid[0:64, 0:64] / 4.0
    dx, dy = xx + 0.125 - 8, yy + 0.125 - 8
    d = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)
    teeth = (np.cos(8 * th) > 0.3) & (d <= 7.6)
    m = ((d <= 5.6) | teeth) & (d > 2.3)
    m = m.reshape(16, 4, 16, 4).mean(axis=(1, 3)) >= 0.5
    return m


def _chain_old():
    def capsule(ax, ay, bx, by, r, sub):
        yy, xx = np.mgrid[0:64, 0:64] / 4.0 + 0.125
        vx, vy = bx - ax, by - ay
        t = np.clip(((xx - ax) * vx + (yy - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        d = np.hypot(xx - (ax + t * vx), yy - (ay + t * vy))
        return (d <= r) & (d > r - sub)
    a = capsule(3.6, 12.4, 7.2, 8.8, 3.0, 1.5)
    b = capsule(8.8, 7.2, 12.4, 3.6, 3.0, 1.5)
    m = (a | b).reshape(16, 4, 16, 4).mean(axis=(1, 3)) >= 0.45
    return m


def _chain():
    rows = [
        "................",
        "................",
        "................",
        ".########.......",
        "#........#......",
        "#...............",
        "#......########.",
        "#.....#........#",
        "#........#.....#",
        ".########......#",
        "...............#",
        "......#........#",
        ".......########.",
        "................",
        "................",
        "................",
    ]
    return np.array([[c == "#" for c in r] for r in rows])


def make_icons():
    out = {}
    for name, rows in ICONS.items():
        rows = [r.ljust(16, ".")[:16] for r in rows]
        out[name] = from_ascii(rows, {"#": INK})
    for name, m in (("bolt", _bolt()), ("settings", _gear()), ("chain", _chain())):
        img = canvas(16, 16)
        img[m] = INK
        out[name] = img
    return out


# --------------------------------------------------------------------------
# Steering wheel (front view, as seen from the driver)
# --------------------------------------------------------------------------


def _rrect(W, H, x0, y0, x1, y1, r):
    yy, xx = np.mgrid[0:H, 0:W].astype(float) + 0.5
    inside = (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
    cx = np.clip(xx, x0 + r, x1 - r)
    cy = np.clip(yy, y0 + r, y1 - r)
    return inside & ((xx - cx) ** 2 + (yy - cy) ** 2 <= r * r)


def _round_button(img, cx, cy, ramp, r=3.5):
    """ramp = [dark, mid, light, glint]."""
    H, W = img.shape[:2]
    img[disc_mask(W, H, cx, cy, r + 1)] = BLACK
    for y, x in zip(*np.nonzero(disc_mask(W, H, cx, cy, r))):
        t = (x + 0.5 - cx) + (y + 0.5 - cy)
        img[y, x] = ramp[2] if t < -2 else ramp[1] if t < 2.5 else ramp[0]
    px(img, int(cx - 1.5), int(cy - 1.5), ramp[3])


WHEEL = {
    "size": [192, 112],
    "screen": {"x": 66, "y": 20, "w": 60, "h": 34},
    "rotaries": [
        {"id": "upper_left", "center": [48, 32]},
        {"id": "upper_right", "center": [144, 32]},
        {"id": "lower_left", "center": [48, 68]},
        {"id": "lower_right", "center": [144, 68]},
    ],
}

BUTTON_RAMPS = {
    "green": [hx("1e7a3e"), hx("2fae58"), hx("3ecf6a"), hx("9af0b4")],
    "blue": [hx("2a7690"), hx("44a6c6"), hx("5ec8e5"), hx("b8ecf8")],
    "yellow": [hx("9a7a18"), hx("d2a628"), hx("f2c230"), hx("fff0a8")],
    "red": [hx("8f2027"), hx("c22d28"), hx("e8352b"), hx("ffa090")],
    "purple": [hx("6a2fa8"), hx("8c45d6"), hx("a855f7"), hx("dcb8ff")],
    "white": [hx("8e909a"), hx("c9c8c4"), hx("f1efea"), hx("ffffff")],
    "orange": [hx("9a4a1a"), hx("cc6a28"), hx("f08a3a"), hx("ffd0a0")],
}


def make_steering_wheel():
    W, H = 192, 112
    img = canvas(W, H)
    body = _rrect(W, H, 22, 2, 170, 96, 12)
    grip_l = _rrect(W, H, 1, 10, 37, 111, 15)
    grip_r = _rrect(W, H, 155, 10, 191, 111, 15)
    yy, xx = np.mgrid[0:H, 0:W]
    # carbon twill on the body with a stepped gloss band
    weave = ((xx // 2 + yy // 2) % 2 == 0)
    carbon = [hx("17181b"), hx("1c1d21"), hx("212328"), hx("272a30")]
    band = xx * 0.55 - yy
    gloss = ((band > 18) & (band < 30)) | ((band > 70) & (band < 76))
    base = np.where(weave, 1, 0) + np.where(gloss, 2, 0)
    for k in range(4):
        img[body & (base == k)] = carbon[k]
    # grips: matte rubber, vertical ribs, finger notches on the inner side
    rub = [hx("121315"), hx("17181b"), hx("1e2024"), hx("2c2e34")]
    for g_mask, inner_x, sign, gx0, gx1 in ((grip_l, 37, 1, 1, 37), (grip_r, 155, -1, 155, 191)):
        t = (xx + 0.5 - gx0) / (gx1 - gx0)
        img[g_mask] = rub[1]
        img[g_mask & (t < 0.3)] = rub[2]
        img[g_mask & (t >= 0.72)] = rub[0]
        ribs = g_mask & ((xx % 3) == 0) & (t >= 0.3) & (t < 0.72)
        img[ribs] = rub[0]
        img[g_mask & ((xx % 3) == 0) & (t < 0.3)] = rub[1]
        for fy in (40, 52, 64, 76):
            img[disc_mask(W, H, inner_x - sign * 1.5, fy, 3.2) & g_mask] = rub[0]
        # carbon cap on top of the grip, separated from the rubber by a red line
        cap = g_mask & (yy < 27)
        img[cap & (base == 0)] = carbon[0]
        img[cap & (base != 0)] = carbon[1]
        img[g_mask & (yy == 27)] = hx("a8242a")
        img[g_mask & (yy == 28)] = rub[0]
        edge = g_mask & ~erode(g_mask)
        img[edge] = rub[0]
        img[edge & (~shift(g_mask, 1, 0) | ~shift(g_mask, 0, 1))] = rub[3]
        img[edge & cap & (~shift(g_mask, 1, 0) | ~shift(g_mask, 0, 1))] = hx("4a4c54")
    # body rim: top/left lit, bottom/right dark
    edge = body & ~erode(body)
    img[edge & ~grip_l & ~grip_r] = hx("0e0f11")
    img[edge & (~shift(body, 1, 0) | ~shift(body, 0, 1)) & ~grip_l & ~grip_r] = hx("4a4c54")
    eb = erode(body)
    inner2 = eb & ~erode(eb)
    img[inner2 & (~shift(eb, 1, 0) | ~shift(eb, 0, 1)) & ~grip_l & ~grip_r] = hx("2f3238")
    # faceplate around the screen
    plate = _rrect(W, H, 60, 6, 132, 86, 6)
    img[plate] = hx("141518")
    pe = plate & ~erode(plate)
    img[pe] = hx("2a2c31")
    img[pe & (~shift(plate, 1, 0) | ~shift(plate, 0, 1))] = hx("3a3d44")
    # shift lights: 15 LEDs, drawn dim (lit in game)
    leds = []
    rect(img, 64, 9, 128, 15, BLACK)
    dim = {"green": (hx("1d4a2c"), hx("3ecf6a")), "red": (hx("4a1a1a"), hx("e8352b")),
           "blue": (hx("1a3a4a"), hx("5ec8e5"))}
    for i in range(15):
        col = "green" if i < 5 else "red" if i < 10 else "blue"
        x = 66 + i * 4
        rect(img, x, 11, x + 3, 13, dim[col][0])
        px(img, x, 11, mix(dim[col][0], dim[col][1], 0.45))
        leds.append({"x": x, "y": 11, "w": 3, "h": 2, "color": col})
    # screen and bezel
    sc = WHEEL["screen"]
    sx, sy, sw, sh = sc["x"], sc["y"], sc["w"], sc["h"]
    rect(img, sx - 2, sy - 2, sx + sw + 2, sy + sh + 2, hx("2a2c31"))
    rect(img, sx - 2, sy - 2, sx + sw + 2, sy - 1, hx("3a3d44"))
    rect(img, sx - 1, sy - 1, sx + sw + 1, sy + sh + 1, BLACK)
    rect(img, sx, sy, sx + sw, sy + sh, hx("0b0c0e"))
    # rotary sockets: recessed wells (lip lit top-left, inner wall lit bottom-right)
    for r in WHEEL["rotaries"]:
        cx, cy = r["center"]
        lip = disc_mask(W, H, cx, cy, 13.5)
        well = disc_mask(W, H, cx, cy, 11.5)
        for y, x in zip(*np.nonzero(lip & ~well)):
            t = (x + 0.5 - cx) + (y + 0.5 - cy)
            img[y, x] = hx("3a3d44") if t < -6 else hx("26282d") if t < 6 else hx("101113")
        for y, x in zip(*np.nonzero(well)):
            t = (x + 0.5 - cx) + (y + 0.5 - cy)
            img[y, x] = hx("08090b") if t < -4 else hx("0d0e10") if t < 8 else hx("1a1b1f")
    buttons = []
    for (cx, cy, col) in [(74, 66, "green"), (87, 66, "blue"), (105, 66, "yellow"), (118, 66, "red"),
                          (82, 79, "purple"), (96, 80, "white"), (110, 79, "orange"),
                          (36, 8, "yellow"), (156, 8, "red")]:
        _round_button(img, cx, cy, BUTTON_RAMPS[col])
        buttons.append({"center": [cx, cy], "color": col})
    draw_text(img, 80, 89, "PIT WALL", hx("4a4c54"))
    rect(img, 80, 95, 112, 96, hx("a8242a"))
    img = outline(img, BLACK)
    info = dict(WHEEL)
    info["shift_lights"] = leds
    info["buttons"] = buttons
    info["rotary_ring_size"] = 28
    info["rotary_knob_size"] = 20
    info["notes"] = ("Pixel coordinates in steering_wheel.png. Centre rotary_ring.png and rotary.png on each "
                     "rotary centre; draw screen text inside 'screen' (filled #0b0c0e). Shift lights are drawn "
                     "dim; light them by drawing a rect of the LED colour over each.")
    return img, info


def make_rotary():
    S = 20
    img = canvas(S, S)
    c = 10.0
    for y in range(S):
        for x in range(S):
            dx, dy = x + 0.5 - c, y + 0.5 - c
            d = math.hypot(dx, dy)
            if d > 9.6:
                continue
            ang = math.atan2(dy, dx)
            lit = -(dx + dy) / max(d, 0.01)
            if d > 8.6:
                col = BLACK
            elif d > 6.6:
                knurl = int((ang + math.pi) / (2 * math.pi) * 24) % 2
                col = [hx("2c2e34"), hx("4a4c54")][knurl]
                if lit > 0.5 and knurl:
                    col = hx("6e6f78")
                if lit < -0.5:
                    col = [hx("1d1f23"), hx("34363c")][knurl]
            elif d > 5.8:
                col = hx("17181b")
            else:
                col = hx("3a3c43") if lit > 0.35 else hx("2f3137") if lit > -0.35 else hx("26282d")
                if d < 2.0:
                    col = hx("1d1f23")
            img[y, x] = col
    # pointer notch at the top, 2 px wide so it stays centred when rotated
    for y in range(1, 8):
        img[y, 9] = INK
        img[y, 10] = INK
    img[1, 9] = RED
    img[1, 10] = RED
    return img


def make_rotary_ring():
    """11 ticks over a 300 degree arc: tick i at (-150 + 30 i) degrees from the top, clockwise."""
    S = 28
    img = canvas(S, S)
    c = 14.0
    for i in range(11):
        a = math.radians(-150 + 30 * i)
        major = i in (0, 5, 10)
        r0 = 10.6 if major else 11.6
        col = INK if major else UI["ink2"]
        for k in range(12):
            r = r0 + (13.6 - r0) * k / 11
            px(img, int(math.floor(c + r * math.sin(a))), int(math.floor(c - r * math.cos(a))), col)
    return img


# --------------------------------------------------------------------------
# Wing profiles (side view, car travelling to the left)
# --------------------------------------------------------------------------


def _airfoil(le, chord, angle_deg, t, camber, n=40):
    """Inverted cambered aerofoil (downforce) as a screen-space polygon."""
    up, lo = [], []
    p = 0.4
    for i in range(n + 1):
        xr = (1 - math.cos(math.pi * i / n)) / 2
        yt = 5 * t * (0.2969 * math.sqrt(xr) - 0.126 * xr - 0.3516 * xr ** 2 + 0.2843 * xr ** 3 - 0.1036 * xr ** 4)
        yt += 0.012 * xr  # finite trailing edge so the tail survives at pixel size
        if xr < p:
            yc = camber / p ** 2 * (2 * p * xr - xr * xr)
        else:
            yc = camber / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * xr - xr * xr)
        yc = -yc
        up.append((xr * chord, -(yc + yt) * chord))
        lo.append((xr * chord, -(yc - yt) * chord))
    a = math.radians(angle_deg)
    out = []
    for (x, y) in up + lo[::-1]:
        out.append((le[0] + x * math.cos(a) + y * math.sin(a), le[1] - x * math.sin(a) + y * math.cos(a)))
    return out


def _paint_aerofoil(img, poly, accent=None):
    """Carbon aerofoil: lit upper surface, dark underside, bright leading edge,
    optional coloured trailing-edge tip (last 4 px)."""
    H, W = img.shape[:2]
    m = polygon_mask(W, H, poly, ss=4, thresh=0.4)
    yy, xx = np.mgrid[0:H, 0:W]
    img[m] = hx("3a3c43")
    lower = m & ~shift(m, 0, -1)
    upper = m & ~shift(m, 0, 1)
    img[m & shift(upper, 0, 1)] = hx("4a4c54")
    img[lower] = hx("1d1f23")
    img[upper] = UI["ink2"]
    xs = np.nonzero(m.any(axis=0))[0]
    x0, x1 = xs.min(), xs.max()
    le = m & (xx <= x0 + 1)
    img[le] = INK
    if accent is not None:
        tip = m & (xx >= x1 - 3)
        img[tip] = accent
        img[tip & upper] = hx("f2603f")
    return m


def _endplate(W, H, pts, stripe_y):
    img = canvas(W, H)
    ep = polygon_mask(W, H, pts, ss=4)
    img[ep] = with_alpha(hx("1d1f23"), 210)
    e = ep & ~erode(ep)
    img[e] = UI["ink3"]
    img[e & ~shift(ep, 0, 1)] = UI["ink2"]
    band = ep & (np.mgrid[0:H, 0:W][0] >= stripe_y) & ~e
    img[band] = RED
    img[band & (np.mgrid[0:H, 0:W][0] == stripe_y)] = hx("f2603f")
    return img


def make_wings():
    out, meta = {}, {}
    img = _endplate(96, 24, [(3, 8), (22, 1), (93, 1), (93, 23), (12, 23), (3, 16)], 20)
    for x in range(80, 90, 3):
        rect(img, x, 14, x + 1, 19, hx("34363c"))
    _paint_aerofoil(img, _airfoil((8, 18.5), 54, 7, 0.15, 0.05))
    out["wing_side_main.png"] = img
    fl = canvas(64, 16)
    _paint_aerofoil(fl, _airfoil((15, 9), 36, 0, 0.16, 0.06), accent=RED)
    out["wing_side_flap.png"] = fl
    meta["rear"] = {
        "main": "wing_side_main.png", "flap": "wing_side_flap.png",
        "flap_pivot": [16, 9], "flap_pivot_in_main": [59, 10],
        "flap_angle_deg": {"high_downforce": -24, "default": -18, "low_drag": -10, "drs_open": -2},
        "note": ("Pivot is near the flap leading edge. Place the flap so flap_pivot lands on flap_pivot_in_main, "
                 "then rotate by the angle (Godot degrees, clockwise positive). Car travels to the left; "
                 "negative raises the trailing edge. The flap may overhang the main image at steep angles."),
    }
    img = _endplate(96, 20, [(2, 9), (10, 2), (94, 2), (94, 19), (2, 19)], 17)
    _paint_aerofoil(img, _airfoil((5, 14.5), 58, 3, 0.12, 0.045))
    out["front_wing_side.png"] = img
    fl = canvas(48, 12)
    _paint_aerofoil(fl, _airfoil((7, 6.5), 34, 0, 0.16, 0.06), accent=RED)
    out["front_wing_side_flap.png"] = fl
    meta["front"] = {
        "main": "front_wing_side.png", "flap": "front_wing_side_flap.png",
        "flap_pivot": [8, 6], "flap_pivot_in_main": [61, 10],
        "flap_angle_deg": {"high_downforce": -22, "default": -15, "low_drag": -8},
    }
    return out, meta


# --------------------------------------------------------------------------
# Garage backdrop
# --------------------------------------------------------------------------


def make_garage_floor(seed=21):
    W = H = 128
    pal = [hx("53565e"), hx("61646c"), hx("6b6e76"), hx("70737b"), hx("7a7d85"), hx("8e9198"), hx("646d79"),
           hx("85784f")]
    g = rng(seed)
    q = quantize(fbm(W, H, [64, 32], [1, 0.5], seed), 3, dither=0.8)
    idx = clean_orphans(np.where(q == 0, 2, 3), passes=2)
    for (fx, fy) in poisson_torus(W, H, 2.6, seed + 1):
        x, y = int(fx) % W, int(fy) % H
        r = g.random()
        idx[y, x] = 1 if r < 0.4 else 4 if r < 0.8 else 6 if r < 0.9 else 5
    for k in range(0, W, 64):
        idx[:, k] = 0
        idx[:, (k + 1) % W] = 5
        idx[k, :] = 0
        idx[(k + 1) % H, :] = 5
    for (cx, cy) in [(4, 4), (68, 68)]:
        for t in range(6):
            idx[cy, cx + t] = 7
            idx[cy + t, cx] = 7
    return palette_map(idx, pal)


def make_garage_wall():
    W, H = 256, 64
    img = canvas(W, H, hx("202226"))
    for x in range(0, W, 32):
        rect(img, x, 0, x + 1, H, hx("17181b"))
        rect(img, x + 1, 0, x + 2, H, hx("2a2c31"))
    rect(img, 0, 0, W, 2, hx("2c2e34"))
    rect(img, 0, 2, W, 3, hx("fff3cf"))
    rect(img, 0, 3, W, 4, hx("8a7e62"))
    # team branding stripe
    rect(img, 0, 8, W, 15, RED)
    rect(img, 0, 8, W, 9, hx("f2603f"))
    rect(img, 0, 14, W, 15, hx("a8242a"))
    rect(img, 0, 15, W, 16, hx("141518"))
    for x0 in (8, 136):
        draw_text(img, x0, 9, "PIT WALL", INK)
        for r in range(2):
            for c in range(4):
                col = INK if (r + c) % 2 == 0 else hx("26272c")
                rect(img, x0 + 40 + c * 2, 10 + r * 2, x0 + 42 + c * 2, 12 + r * 2, col)
    draw_text(img, 72, 9, "RACING TEAM", hx("f8d0c8"))
    draw_text(img, 200, 9, "GARAGE 1", hx("f8d0c8"))
    # tyre stacks with compound bands
    comp = [hx("e8352b"), hx("f2c230"), hx("f1efea")]
    for s_i, x0 in enumerate((6, 22)):
        for k in range(4):
            y0 = 58 - (k + 1) * 9
            rect(img, x0, y0, x0 + 14, y0 + 8, hx("141518"))
            rect(img, x0 + 1, y0 + 1, x0 + 13, y0 + 7, hx("1d1f23"))
            rect(img, x0 + 1, y0 + 1, x0 + 13, y0 + 2, hx("34363c"))
            rect(img, x0 + 1, y0 + 4, x0 + 13, y0 + 5, comp[(s_i + k) % 3])
            px(img, x0, y0, hx("202226"))
            px(img, x0 + 13, y0, hx("202226"))
    # pegboards with tools
    for x0 in (44, 160):
        rect(img, x0, 20, x0 + 52, 50, hx("2f3238"))
        rect(img, x0, 20, x0 + 52, 21, hx("4a4c54"))
        rect(img, x0, 49, x0 + 52, 50, hx("17181b"))
        for y in range(23, 48, 3):
            for x in range(x0 + 2, x0 + 51, 3):
                px(img, x, y, hx("26282d"))
        for i in range(6):
            tx = x0 + 4 + i * 5
            ln = 10 + i * 2
            rect(img, tx, 24, tx + 1, 24 + ln, hx("b9bec6"))
            rect(img, tx - 1, 24, tx + 2, 26, hx("8a909b"))
            px(img, tx, 24, hx("2f3238"))
            px(img, tx + 1, 24 + ln - 1, hx("5d626d"))
        rect(img, x0 + 36, 24, x0 + 46, 27, hx("8a909b"))
        rect(img, x0 + 40, 27, x0 + 42, 40, hx("c2412c"))
        for i in range(3):
            sx_ = x0 + 37 + i * 4
            rect(img, sx_, 42, sx_ + 2, 46, [hx("e8352b"), hx("f2c230"), hx("5ec8e5")][i])
            rect(img, sx_, 39, sx_ + 1, 42, hx("b9bec6"))
    # telemetry monitor
    mx0 = 104
    rect(img, mx0, 20, mx0 + 50, 46, BLACK)
    rect(img, mx0 + 2, 22, mx0 + 48, 44, hx("10141a"))
    pts_g = [36, 34, 30, 31, 27, 26, 29, 33, 35, 32, 28, 25, 24, 27, 30, 34]
    for i in range(len(pts_g) - 1):
        for t in range(3):
            px(img, mx0 + 4 + i * 3 + t, pts_g[i] + (pts_g[i + 1] - pts_g[i]) * t // 3, UI["green"])
    for i in range(14):
        px(img, mx0 + 5 + i * 3, 40 - (i % 4), UI["blue"])
    rect(img, mx0 + 3, 23, mx0 + 15, 24, UI["ink3"])
    rect(img, mx0 + 22, 46, mx0 + 28, 52, hx("17181b"))
    # tool chest
    cx0 = 216
    rect(img, cx0, 30, cx0 + 36, 58, hx("8f2027"))
    rect(img, cx0, 30, cx0 + 36, 32, hx("e04030"))
    for k in range(5):
        y = 34 + k * 5
        rect(img, cx0 + 2, y, cx0 + 34, y + 4, hx("c22d28"))
        rect(img, cx0 + 2, y + 3, cx0 + 34, y + 4, hx("8f2027"))
        rect(img, cx0 + 12, y + 1, cx0 + 24, y + 2, hx("b9bec6"))
    rect(img, cx0 + 35, 32, cx0 + 36, 58, hx("5a1820"))
    # skirting
    rect(img, 0, 58, W, 60, hx("2c2e34"))
    rect(img, 0, 58, W, 59, hx("3a3d44"))
    rect(img, 0, 60, W, H, hx("141518"))
    return img


def make_vignette():
    """Dark corners, 12 alpha steps; stretch it over the screen (linear filter recommended)."""
    S = 64
    img = canvas(S, S)
    for y in range(S):
        for x in range(S):
            dx = (x + 0.5 - S / 2) / (S / 2)
            dy = (y + 0.5 - S / 2) / (S / 2)
            t = max(0.0, (math.sqrt(dx * dx + dy * dy) / math.sqrt(2) - 0.45) / 0.55)
            a = round(min(1.0, t) ** 1.6 * 12) / 12 * 200
            if a > 0:
                img[y, x] = (7, 8, 10, int(a))
    return img


# --------------------------------------------------------------------------


def build():
    out = {}
    out["logo.png"] = make_logo(32, 6, 3, 10, 3, 192, 48)
    out["logo_small.png"] = make_logo(14, 3, 2, 5, 3, 96, 24, small=True)
    out["panel.png"] = make_panel(UI["line"])
    out["panel_accent.png"] = make_panel(UI["line"], accent=RED)
    out["panel_hover.png"] = make_panel(UI["line2"], inner=hx("26282d"), chamfer_col=UI["ink3"])
    out["button.png"] = make_button(hx("26282d"), hx("3a3c43"), hx("141518"), UI["line2"])
    out["button_hover.png"] = make_button(hx("2f3238"), hx("4a4c54"), hx("17181b"), UI["ink3"])
    out["button_pressed.png"] = make_button(hx("222429"), hx("3a3c43"), hx("101113"), UI["line2"], pressed=True)
    out["button_primary.png"] = make_button(RED, hx("f2603f"), hx("8f2027"), hx("5a1820"))
    out["button_primary_hover.png"] = make_button(hx("f0473a"), hx("ff8066"), hx("a8242a"), hx("7a1a26"))
    out["tab.png"] = make_tab(False)
    out["tab_active.png"] = make_tab(True)
    for name, img in make_icons().items():
        out[f"icon_{name}.png"] = img
    wheel, info = make_steering_wheel()
    out["steering_wheel.png"] = wheel
    out["rotary.png"] = make_rotary()
    out["rotary_ring.png"] = make_rotary_ring()
    wings, wmeta = make_wings()
    out.update(wings)
    out["garage_floor.png"] = make_garage_floor()
    out["garage_wall.png"] = make_garage_wall()
    out["vignette.png"] = make_vignette()
    for name, img in out.items():
        save(img, OUT / name)
    (OUT / "steering_wheel.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    (OUT / "wings.json").write_text(json.dumps(wmeta, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    for name in build():
        print("wrote", OUT / name)
