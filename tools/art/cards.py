"""Trading-card frames, card back, reveal glows and layout.json.

Run:  python tools/art/cards.py
Writes game/assets/sprites/cards/*.png and cards/layout.json
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from pxl import (FONT3, FONT5, alpha_over, canvas, draw_text, hx, put, rect,  # noqa: E402
                 save, save_json, text_width)

CW, CH = 112, 152
INK = hx("#f1efea")
INK2 = hx("#a3a3ad")
OUT = hx("#0b0c0e")
PANEL = hx("#1d1f23")
PANEL_D = hx("#17191c")
PANEL_DD = hx("#121316")
LINE = hx("#34363c")
BG = hx("#141518")

# rarity ramps: 0 darkest .. 4 lightest; [2] is the named rarity colour
RARITY = {
    "common": [hx("#2b2e34"), hx("#565b64"), hx("#9aa0aa"), hx("#c8ccd3"), hx("#eef0f3")],
    "rare": [hx("#0f3240"), hx("#1d6a85"), hx("#5ec8e5"), hx("#a6ecfb"), hx("#e6fbff")],
    "epic": [hx("#2a1048"), hx("#5a24a0"), hx("#a855f7"), hx("#cf9bff"), hx("#f3e6ff")],
    "legendary": [hx("#4a2c06"), hx("#9a6a12"), hx("#f2c230"), hx("#ffe27a"), hx("#fff8dc")],
}
BRAND = [hx("#3a0c10"), hx("#7a1a1d"), hx("#e8352b"), hx("#ff6a4a"), hx("#ffc2a8")]

# layout (x, y, w, h)
ART = (24, 18, 64, 64)
LABEL = (34, 5, 44, 9)
NAME = (8, 87, 96, 13)
STATS = (8, 104, 96, 38)
PIPS_Y = 145


def chamfer_mask(w, h, c):
    m = np.ones((h, w), bool)
    for i in range(c):
        for j in range(c - i):
            m[i, j] = m[i, w - 1 - j] = m[h - 1 - i, j] = m[h - 1 - i, w - 1 - j] = False
    return m


def inset(mask):
    p = np.pad(mask, 1)
    return mask & p[1:-1, 2:] & p[1:-1, :-2] & p[2:, 1:-1] & p[:-2, 1:-1]


def bevel_ring(img, mask, ramp_lit, ramp_dark, ramp_mid=None):
    """Colour the outer ring of mask: top/left lit, bottom/right dark."""
    ring = mask & ~inset(mask)
    h, w = mask.shape
    ys, xs = np.nonzero(ring)
    for y, x in zip(ys, xs):
        # which side: compare to centre with the diagonal split
        lit = (x + y) < (w + h) / 2 - (abs(x - w / 2) - abs(y - h / 2)) * 0 and (y < h * 0.5 or x < w * 0.08)
        top = y <= 3 or x <= 3
        bottom = y >= h - 4 or x >= w - 4
        if top and not bottom:
            img[y, x] = ramp_lit
        elif bottom and not top:
            img[y, x] = ramp_dark
        else:
            # corners: split along the anti-diagonal
            img[y, x] = ramp_lit if (x / w + y / h) < 1.0 else ramp_dark
    return inset(mask)


def frame_base(r):
    """Shared frame: outline, 3px bevelled rarity border, inner line, panel."""
    img = canvas(CW, CH)
    m = chamfer_mask(CW, CH, 4)
    img[m] = OUT
    m1 = inset(m)
    m1 = bevel_ring(img, m1, r[3], r[1])
    m2 = bevel_ring(img, m1, r[2], r[1])
    m3 = bevel_ring(img, m2, r[2], r[0])
    m4 = bevel_ring(img, m3, OUT, OUT)
    img[m4] = PANEL
    # top highlight row on the panel (light from the top-left)
    ys, xs = np.nonzero(m4)
    top = ys.min()
    for x in range(xs.min(), xs.max() + 1):
        if m4[top, x]:
            img[top, x] = hx("#26292e")
    return img


def window(img, r, x, y, w, h):
    """Art window: transparent hole with a dark lip and a rarity bevel."""
    # outer bevel
    rect(img, x - 3, y - 3, x + w + 2, y + h + 2, r[1])
    rect(img, x - 3, y - 3, x + w + 2, y - 3, r[2])
    rect(img, x - 3, y - 3, x - 3, y + h + 2, r[2])
    rect(img, x - 2, y - 2, x + w + 1, y + h + 1, OUT)
    rect(img, x - 1, y - 1, x + w, y + h, PANEL_DD)
    # hole
    img[y:y + h, x:x + w] = 0
    # cut corners of the window frame
    for (cx, cy) in ((x - 3, y - 3), (x + w + 2, y - 3), (x - 3, y + h + 2), (x + w + 2, y + h + 2)):
        put(img, cx, cy, PANEL)


def plate(img, r, x, y, w, h, accent=True):
    rect(img, x, y, x + w - 1, y + h - 1, PANEL_DD)
    rect(img, x, y, x + w - 1, y, OUT)
    rect(img, x, y + h - 1, x + w - 1, y + h - 1, hx("#26292e"))
    rect(img, x, y, x, y + h - 1, OUT)
    rect(img, x + w - 1, y, x + w - 1, y + h - 1, hx("#26292e"))
    if accent:
        rect(img, x + 1, y + 1, x + 2, y + h - 2, r[2])
        rect(img, x + 1, y + 1, x + 1, y + h - 2, r[3])


def label_tab(img, r, x, y, w, h):
    rect(img, x - 1, y - 1, x + w, y + h, OUT)
    rect(img, x, y, x + w - 1, y + h - 1, r[1])
    rect(img, x, y, x + w - 1, y, r[2])
    rect(img, x, y + h - 1, x + w - 1, y + h - 1, r[0])
    for (cx, cy) in ((x - 1, y - 1), (x + w, y - 1), (x - 1, y + h), (x + w, y + h)):
        put(img, cx, cy, PANEL)


def gem(img, cx, cy, r, size=2):
    """Small faceted diamond gem centred at (cx, cy)."""
    pts = []
    for dy in range(-size - 1, size + 2):
        for dx in range(-size - 1, size + 2):
            d = abs(dx) + abs(dy)
            if d == size + 1:
                put(img, cx + dx, cy + dy, OUT)
            elif d <= size:
                if dx + dy < 0:
                    c = r[3]
                elif dx + dy == 0:
                    c = r[2]
                else:
                    c = r[1]
                put(img, cx + dx, cy + dy, c)
    put(img, cx - 1, cy - 1, r[4])


def pips(img, r, n):
    total = n * 5 - 1
    x0 = CW // 2 - total // 2
    for i in range(n):
        x = x0 + i * 5
        rect(img, x - 1, PIPS_Y - 1, x + 3, PIPS_Y + 3, OUT)
        rect(img, x, PIPS_Y, x + 2, PIPS_Y + 2, r[2])
        put(img, x, PIPS_Y, r[4])
        put(img, x + 2, PIPS_Y + 2, r[1])


def side_stripes(img, r):
    """Racing chevrons along the lower sides of the stats panel."""
    for k in range(3):
        y = 120 + k * 5
        for side in (0, 1):
            x = 4 if side == 0 else CW - 5
            put(img, x, y, r[2])
            put(img, x, y + 1, r[1])


def header_band(img, r):
    """Speed-stripe header across the top of the panel, behind the label."""
    for y in range(5, 15):
        for x in range(5, CW - 5):
            if img[y, x, 3] and tuple(img[y, x]) == PANEL:
                if ((x + y) // 2) % 5 == 0:
                    img[y, x] = r[0]
    for x in range(5, CW - 5):
        if tuple(img[15, x]) == PANEL:
            img[15, x] = r[0]


def chevrons(img, r, y):
    for side in (-1, 1):
        for k in range(3):
            cx = CW // 2 + side * (16 + k * 4)
            for i in range(3):
                put(img, cx - side * i, y + i, r[1] if k else r[2])
                put(img, cx - side * i, y + 4 - i, r[1] if k else r[2])


def make_frame(name):
    r = RARITY[name]
    img = frame_base(r)
    header_band(img, r)
    window(img, r, *ART)
    label_tab(img, r, *LABEL)
    plate(img, r, *NAME)
    plate(img, r, *STATS, accent=False)
    # separators inside the stats area guide 3 stat rows
    sx, sy, sw, sh = STATS
    for i in (1, 2):
        y = sy + i * sh // 3
        for x in range(sx + 3, sx + sw - 3, 2):
            put(img, x, y, LINE)
    n = {"common": 1, "rare": 2, "epic": 3, "legendary": 4}[name]
    pips(img, r, n)
    chevrons(img, r, PIPS_Y - 1)
    # rarity hairline above the name plate
    for x in range(NAME[0] + 4, NAME[0] + NAME[2] - 4):
        put(img, x, NAME[1] - 2, r[0])
    ax, ay, aw, ah = ART
    if name in ("rare", "epic", "legendary"):
        # gems on the window corners
        for (gx, gy) in ((ax - 3, ay - 3), (ax + aw + 2, ay - 3)):
            gem(img, gx, gy, r, 2 if name != "rare" else 1)
    if name in ("epic", "legendary"):
        for (gx, gy) in ((ax - 3, ay + ah + 2), (ax + aw + 2, ay + ah + 2)):
            gem(img, gx, gy, r, 1)
        # circuit traces down both sides of the window
        for side in (0, 1):
            x = ax - 9 if side == 0 else ax + aw + 8
            for y in range(ay + 6, ay + ah - 6):
                put(img, x, y, r[1])
            for y in (ay + 6, ay + ah - 7):
                put(img, x, y, r[3])
            xx = x + (3 if side == 0 else -3)
            for i in range(4):
                put(img, x + (i if side == 0 else -i), ay + 20, r[1])
                put(img, x + (i if side == 0 else -i), ay + ah - 20, r[1])
            put(img, xx, ay + 20, r[3])
            put(img, xx, ay + ah - 20, r[3])
    if name == "legendary":
        # gold filigree brackets at the four frame corners + shine glints
        for (cx, cy, sx_, sy_) in ((6, 6, 1, 1), (CW - 7, 6, -1, 1), (6, CH - 7, 1, -1),
                                   (CW - 7, CH - 7, -1, -1)):
            for i in range(7):
                put(img, cx + sx_ * i, cy, r[3] if i < 5 else r[2])
                put(img, cx, cy + sy_ * i, r[3] if i < 5 else r[2])
            put(img, cx + sx_ * 2, cy + sy_ * 2, r[2])
            put(img, cx + sx_, cy + sy_, r[4])
        # diagonal shine across the top-left border
        for (x, y) in ((14, 1), (15, 1), (13, 2), (14, 2), (12, 3), (19, 1), (18, 2)):
            if img[y, x, 3]:
                put(img, x, y, r[4])
        for (x, y) in ((1, 40), (2, 39), (1, 41), (3, 38)):
            put(img, x, y, r[4])
        side_stripes(img, r)
    if name == "epic":
        side_stripes(img, r)
    return img


# --------------------------------------------------------------------------
# card back
# --------------------------------------------------------------------------

def big_letter(img, ch, x, y, face, shade, out, k=2):
    g = FONT5[ch]
    # drop shadow first
    for j, row in enumerate(g):
        for i, b in enumerate(row):
            if b == "1":
                rect(img, x + i * k + 1, y + j * k + 1, x + i * k + k, y + j * k + k, out)
    for j, row in enumerate(g):
        for i, b in enumerate(row):
            if b == "1":
                rect(img, x + i * k, y + j * k, x + i * k + k - 1, y + j * k + k - 1, face)
                # lower-right pixel of each cell shaded for a bevel
                put(img, x + i * k + k - 1, y + j * k + k - 1, shade)


def make_back():
    r = [hx("#3a0c10"), hx("#7a1a1d"), hx("#b82a26"), hx("#e8352b"), hx("#ff8a6a")]
    img = frame_base([r[0], r[1], r[2], r[3], r[4]])
    m = chamfer_mask(CW, CH, 4)
    body = inset(inset(inset(inset(inset(m)))))
    img[body] = hx("#16171a")
    # racing stripes: two red bands + thin white pinstripes, top to bottom
    for x0, x1 in ((44, 51), (60, 67)):
        rect(img, x0, 6, x1, CH - 7, r[2])
        rect(img, x0, 6, x0, CH - 7, r[3])
        rect(img, x1, 6, x1, CH - 7, r[1])
    for x in (41, 70):
        rect(img, x, 6, x, CH - 7, hx("#d9d6cf"))
    # chequered bands top and bottom
    for yb in (10, CH - 18):
        for yy in range(yb, yb + 8):
            for xx in range(8, CW - 8):
                c = hx("#d9d6cf") if ((xx - 8) // 4 + (yy - yb) // 4) % 2 == 0 else hx("#0e0f11")
                if body[yy, xx]:
                    img[yy, xx] = c
        rect(img, 8, yb - 1, CW - 9, yb - 1, OUT)
        rect(img, 8, yb + 8, CW - 9, yb + 8, OUT)
    # emblem: chamfered shield in the centre
    ex, ey, ew, eh = 26, 46, 60, 60
    sh = chamfer_mask(ew, eh, 10)
    sub = canvas(ew, eh)
    sub[sh] = OUT
    s1 = inset(sh)
    s1 = bevel_ring(sub, s1, r[3], r[1])
    s2 = bevel_ring(sub, s1, r[2], r[0])
    s3 = bevel_ring(sub, s2, OUT, OUT)
    sub[s3] = hx("#1b1c20")
    # inner diagonal speed lines
    for i in range(0, 60, 6):
        for t in range(0, 8):
            x, y = 6 + i - t, 46 + t
            if 0 <= x < ew and 0 <= y < eh and s3[y, x]:
                sub[y, x] = hx("#232529")
    alpha_over(img, sub, ex, ey)
    # PW monogram (2x scaled 5x7 glyphs)
    big_letter(img, "P", 38, 55, INK, hx("#c9c5bc"), r[1], k=3)
    big_letter(img, "W", 57, 55, INK, hx("#c9c5bc"), r[1], k=3)
    # red underline + PIT WALL
    rect(img, 36, 79, 75, 80, r[3])
    rect(img, 36, 80, 75, 80, r[1])
    tw = text_width("PIT WALL", FONT5)
    draw_text(img, CW // 2 - tw // 2, 84, "PIT WALL", hx("#d9d6cf"), FONT5)
    return img


# --------------------------------------------------------------------------
# glows (136 x 176) behind a revealed card
# --------------------------------------------------------------------------

def make_glow(name):
    r = RARITY[name]
    gw, gh = CW + 24, CH + 24
    img = canvas(gw, gh)
    x0, y0, x1, y1 = 12, 12, 12 + CW - 1, 12 + CH - 1
    col = r[3]
    bands = [(3, 170), (6, 115), (9, 65), (12, 30)]
    for y in range(gh):
        for x in range(gw):
            dx = max(x0 - x, 0, x - x1)
            dy = max(y0 - y, 0, y - y1)
            d = (dx * dx + dy * dy) ** 0.5
            a = 0
            if d == 0:
                a = 190
            else:
                for lim, al in bands:
                    if d <= lim:
                        a = al
                        break
            if a and d > 9 and (x + y) % 2:
                a = 0  # dithered outer band for a soft pixel edge
            if a:
                img[y, x] = (col[0], col[1], col[2], a)
    # four bright corner flares for epic / legendary
    if name in ("epic", "legendary"):
        for (cx, cy) in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            for i in range(1, 11):
                a = max(0, 220 - i * 20)
                for (px, py) in ((cx - i, cy), (cx + i, cy), (cx, cy - i), (cx, cy + i)):
                    if 0 <= px < gw and 0 <= py < gh:
                        img[py, px] = (r[4][0], r[4][1], r[4][2], max(a, int(img[py, px, 3])))
    return img


def make_window_bg(name):
    """Optional 64x64 backdrop for the art window (stepped spotlight)."""
    r = RARITY[name]
    img = canvas(64, 64)
    base = np.array(hx("#16181c")[:3], float)
    tint = np.array(r[1][:3], float)
    for y in range(64):
        for x in range(64):
            d = ((x - 31.5) ** 2 + ((y - 36) * 1.2) ** 2) ** 0.5
            step = 3 if d < 12 else 2 if d < 20 else 1 if d < 28 else 0
            c = base + (tint - base) * (0.10 * step)
            img[y, x] = (int(c[0]), int(c[1]), int(c[2]), 255)
    return img


def main():
    for name in RARITY:
        save(make_frame(name), "cards", f"frame_{name}.png")
        save(make_window_bg(name), "cards", f"window_bg_{name}.png")
    for name in ("rare", "epic", "legendary"):
        save(make_glow(name), "cards", f"glow_{name}.png")
    save(make_back(), "cards", "back.png")
    layout = {
        "card": [CW, CH],
        "art_window": list(ART),
        "rarity_label": list(LABEL),
        "name_plate": list(NAME),
        "stats_area": list(STATS),
        "stat_rows": [[STATS[0] + 3, STATS[1] + 1 + i * (STATS[3] // 3), STATS[2] - 6, STATS[3] // 3 - 1]
                      for i in range(3)],
        "rarity_pips_y": PIPS_Y,
        "glow": {"size": [CW + 24, CH + 24], "card_offset": [12, 12]},
        "note": "rects are [x, y, w, h] in card pixels; art window is transparent "
                "(optional window_bg_<rarity>.png fits it exactly).",
    }
    save_json(layout, "cards", "layout.json")


if __name__ == "__main__":
    main()
