"""Development pack (sealed foil pouch), shake frames, open frame, burst and
sparkle.

Run:  python tools/art/packs.py
Writes game/assets/sprites/packs/*.png
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from pxl import (FONT3, FONT5, alpha_over, canvas, draw_text, hx, put, rect,  # noqa: E402
                 save, text_width)

PW, PH = 96, 112
OUT = hx("#0b0c0e")
INK = hx("#f1efea")
FOIL = [hx("#121316"), hx("#191b1f"), hx("#212328"), hx("#2b2e35"), hx("#3a3e47"), hx("#555b67")]
RED = [hx("#3a0c10"), hx("#7a1a1d"), hx("#b82a26"), hx("#e8352b"), hx("#ff6a4a"), hx("#ffb39a")]
YEL = [hx("#6e4f0e"), hx("#d9a21f"), hx("#f2c230"), hx("#ffe27a")]

X0, X1 = 12, 83          # pouch body columns
Y0, Y1 = 8, 103          # pouch rows (incl. seals)
SEAL = 8                 # crimped seal height


def foil_col(x):
    """Vertical sheen bands across the pouch (light from the left)."""
    t = (x - X0) / (X1 - X0)
    if t < 0.04:
        return FOIL[4]
    if t < 0.10:
        return FOIL[3]
    if 0.22 < t < 0.27:
        return FOIL[4]
    if 0.27 <= t < 0.31:
        return FOIL[3]
    if t > 0.95:
        return FOIL[0]
    if t > 0.86:
        return FOIL[1]
    if 0.62 < t < 0.65:
        return FOIL[3]
    return FOIL[2]


def stencil_big(img, x, y, s, col, shade, k=2):
    """Chunky 2x stencil letters: solid strokes, 1px stencil bridges where the
    stem meets a bowl, 1px drop shadow."""
    cuts = {"D": [(1, 0), (1, 6)], "P": [(1, 0)], "B": [(1, 0), (1, 6)], "R": [(1, 0)],
            "A": [(2, 0)], "O": [(2, 0), (2, 6)], "C": [(2, 0), (2, 6)], "E": [(1, 0), (1, 6)],
            "K": [], "V": [(2, 6)]}
    cx = x
    for ch in s:
        g = FONT5[ch]
        gw = len(g[0])
        cell = set()
        for j, row in enumerate(g):
            for i, b in enumerate(row):
                if b == "1":
                    cell.add((i, j))
        px = set()
        for (i, j) in cell:
            for yy in range(k):
                for xx in range(k):
                    px.add((cx + i * k + xx, y + j * k + yy))
        for (i, j) in cuts.get(ch, []):
            for yy in range(k):
                px.discard((cx + i * k, y + j * k + yy))
        for (u, v) in px:
            if (u + 1, v + 1) not in px:
                put(img, u + 1, v + 1, shade)
        for (u, v) in px:
            put(img, u, v, col)
        cx += (gw + 1) * k
    return cx


def text_w_big(s, k=2):
    return sum((len(FONT5[c][0]) + 1) * k for c in s) - k


def make_pouch(open_top=False):
    img = canvas(PW, PH)
    # body
    for x in range(X0, X1 + 1):
        c = foil_col(x)
        rect(img, x, Y0, x, Y1, c)
    # pillowed edges: darker rim inside the seals
    for y in range(Y0 + SEAL, Y1 - SEAL + 1):
        put(img, X0, y, FOIL[4])
        put(img, X1, y, FOIL[0])
    # crimped seals: vertical ridges, zigzag outer edge
    for (ys, ye, outer) in ((Y0, Y0 + SEAL - 1, Y0), (Y1 - SEAL + 1, Y1, Y1)):
        for y in range(ys, ye + 1):
            for x in range(X0, X1 + 1):
                ridge = (x - X0) % 3
                c = [FOIL[4], FOIL[3], FOIL[1]][ridge]
                put(img, x, y, c)
        # seal boundary line
        yb = ye + 1 if outer == Y0 else ys - 1
        rect(img, X0, yb, X1, yb, FOIL[0])
        # zigzag teeth on the outer edge
        for x in range(X0, X1 + 1):
            if (x - X0) % 4 in (0, 3):
                put(img, x, outer, (0, 0, 0, 0))
    # tear notch (right side, just under the top seal)
    for i in range(3):
        for j in range(3 - i):
            put(img, X1 - j, Y0 + SEAL + 1 + i, (0, 0, 0, 0))
            put(img, X1 - j, Y0 + SEAL + 5 - i, (0, 0, 0, 0))

    # red brand header band
    rect(img, X0 + 1, 18, X1 - 1, 36, RED[3])
    rect(img, X0 + 1, 18, X1 - 1, 18, RED[4])
    rect(img, X0 + 1, 19, X0 + 1, 35, RED[4])
    rect(img, X0 + 1, 35, X1 - 1, 35, RED[1])
    rect(img, X0 + 1, 36, X1 - 1, 36, OUT)
    rect(img, X1 - 1, 19, X1 - 1, 35, RED[2])
    # white pinstripe under the band
    rect(img, X0 + 1, 37, X1 - 1, 37, hx("#d9d6cf"))
    rect(img, X0 + 1, 38, X1 - 1, 38, OUT)
    # PW roundel (dark disc, white monogram)
    cx, cy = 25, 27
    for y in range(cy - 7, cy + 8):
        for x in range(cx - 7, cx + 8):
            d = math.hypot(x - cx + 0.5, y - cy + 0.5)
            if d <= 7.2:
                put(img, x, y, OUT)
            if d <= 6.2:
                put(img, x, y, hx("#1b1c20") if (x - cx) + (y - cy) < 3 else hx("#121316"))
    draw_text(img, cx - 6, cy - 3, "PW", INK, FONT3)
    rect(img, cx - 5, cy + 3, cx + 4, cy + 3, RED[3])
    # brand text with a dark drop shadow
    draw_text(img, 37, 22, "PIT WALL", RED[0], FONT5)
    draw_text(img, 36, 21, "PIT WALL", INK, FONT5)
    draw_text(img, 37, 30, "SERIES 01", RED[0], FONT3)
    # thin red pinstripes down the body sides
    for x in (X0 + 3, X1 - 3):
        rect(img, x, 40, x, Y1 - SEAL - 8, RED[2])

    # DEV / PACK stencil block on a dark plate
    rect(img, 18, 39, 77, 73, OUT)
    rect(img, 19, 40, 76, 72, hx("#15161a"))
    rect(img, 19, 40, 76, 40, FOIL[3])
    w1 = text_w_big("DEV")
    stencil_big(img, 48 - w1 // 2, 43, "DEV", INK, hx("#b9b5ac"))
    w2 = text_w_big("PACK")
    stencil_big(img, 48 - w2 // 2, 58, "PACK", YEL[2], YEL[0])
    # corner bolts on the plate
    for (bx, by) in ((21, 42), (74, 42), (21, 70), (74, 70)):
        put(img, bx, by, FOIL[4])

    # hazard strip above the bottom seal
    hy = Y1 - SEAL - 6
    for y in range(hy, hy + 4):
        for x in range(X0 + 1, X1):
            put(img, x, y, YEL[2] if ((x + y) // 3) % 2 == 0 else OUT)
    rect(img, X0 + 1, hy - 1, X1 - 1, hy - 1, OUT)
    rect(img, X0 + 1, hy + 4, X1 - 1, hy + 4, OUT)

    # barcode + serial label (bottom right)
    lx, ly = 52, 77
    rect(img, lx - 1, ly - 1, lx + 24, ly + 13, OUT)
    rect(img, lx, ly, lx + 23, ly + 12, hx("#e9e6df"))
    bars = [1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1]
    for i, b in enumerate(bars):
        if b:
            rect(img, lx + 1 + i, ly + 1, lx + 1 + i, ly + 6, hx("#141518"))
    draw_text(img, lx + 2, ly + 8, "0417", hx("#141518"), FONT3)
    rect(img, lx + 18, ly + 8, lx + 21, ly + 11, RED[3])
    # small spec text on the left
    rect(img, 17, 77, 43, 90, OUT)
    rect(img, 18, 78, 42, 89, hx("#15161a"))
    draw_text(img, 20, 79, "SEASON", hx("#8c8f98"), FONT3)
    draw_text(img, 20, 85, "2026", INK, FONT3)
    rect(img, 36, 85, 40, 89, RED[3])

    # specular glints on the foil
    for (x, y) in ((15, 18), (16, 17), (15, 52), (40, 94), (41, 93)):
        if img[y, x, 3]:
            put(img, x, y, FOIL[5])

    # outer outline
    a = img[..., 3] > 0
    p = np.pad(a, 1)
    ring = (p[1:-1, 2:] | p[1:-1, :-2] | p[2:, 1:-1] | p[:-2, 1:-1]) & ~a
    img[ring] = OUT

    if open_top:
        img = tear_open(img)
    return img


def tear_open(img):
    """Rip the top seal off along a jagged line; light pours out."""
    from pxl import poly_mask
    out = img.copy()
    tear_y = Y0 + SEAL + 1
    jag = [0, 2, 1, 2, 0, 1, 2, 1, 0, 2, 1, 0, 2, 2, 0, 1, 2, 1]
    edge = {}
    for x in range(X0 - 1, X1 + 2):
        t = tear_y + jag[(x - X0 + 1) // 3 % len(jag)]
        edge[x] = t
        out[:t, x] = 0
    # opening: dark lip with hot light just inside
    for x in range(X0, X1 + 1):
        t = edge[x]
        put(out, x, t, OUT)
        put(out, x, t + 1, hx("#fff2c4"))
    # torn strip of the top seal, flipped up and curling away to the right
    flap = canvas(PW, PH)
    for i in range(26):
        x = X1 - 18 + i
        y0 = 3 + (i * i) // 60
        for y in range(y0, y0 + 5):
            ridge = [FOIL[5], FOIL[4], FOIL[3]][(x - X0) % 3]
            c = ridge if y < y0 + 4 else FOIL[1]
            put(flap, x, y, c)
        put(flap, x, y0 + 4 + (1 if i % 3 == 0 else 0), FOIL[1])
    a = flap[..., 3] > 0
    p = np.pad(a, 1)
    ring = (p[1:-1, 2:] | p[1:-1, :-2] | p[2:, 1:-1] | p[:-2, 1:-1]) & ~a
    flap[ring] = OUT
    # light beams: chunky opaque wedges (pale core, yellow body, gold tip)
    rays = canvas(PW, PH)
    mx, my = 47.5, tear_y + 1.5
    angles = [-58, -36, -16, 0, 16, 36, 58]
    for k, ang in enumerate(angles):
        a0 = math.radians(ang - 90)
        long_ = k % 2 == 1 or ang == 0
        spread = math.radians(6 if long_ else 4)
        length = 36 if long_ else 24
        base_x = mx + ang * 0.45
        for (ln, col) in ((length, hx("#f2c230")), (length * 0.75, hx("#ffe27a")),
                          (length * 0.4, hx("#fff6d8"))):
            pts = [(base_x - 2, my), (base_x + 2, my),
                   (base_x + math.cos(a0 + spread) * ln, my + math.sin(a0 + spread) * ln),
                   (base_x + math.cos(a0 - spread) * ln, my + math.sin(a0 - spread) * ln)]
            msk = poly_mask(PW, PH, pts)
            rays[msk] = col
    # glow pool over the mouth
    for x in range(X0 + 1, X1):
        for dy in (1, 2):
            y = edge[x] - dy
            if y >= 0:
                rays[y, x] = hx("#fff6d8") if dy == 1 else hx("#ffe27a")
    res = canvas(PW, PH)
    alpha_over(res, rays)
    alpha_over(res, out)
    alpha_over(res, flap)
    return res


def skew(img, k, squash=0, anchor_bottom=True):
    """Pixel-clean tilt (row shifts) and vertical squash (drop rows)."""
    h, w = img.shape[:2]
    out = canvas(w, h)
    rows = list(range(h))
    if squash:
        drop = set(int(h * (i + 1) / (squash + 1)) for i in range(squash))
        rows = [r for r in rows if r not in drop]
        rows = [None] * (h - len(rows)) + rows if anchor_bottom else rows + [None] * (h - len(rows))
    pivot = h - 8
    for y, src in enumerate(rows):
        if src is None:
            continue
        sh = int(round((pivot - y) * k))
        row = img[src]
        if sh > 0:
            out[y, sh:] = row[:w - sh]
        elif sh < 0:
            out[y, :w + sh] = row[-sh:]
        else:
            out[y] = row
    return out


def make_burst():
    s = 64
    img = canvas(s, s)
    c = 31.5
    n = 16
    for y in range(s):
        for x in range(s):
            dx, dy = x + 0.5 - 32, y + 0.5 - 32
            d = math.hypot(dx, dy)
            ang = math.atan2(dy, dx)
            k = (ang / (2 * math.pi) * n) % 1.0
            long_ray = int((ang / (2 * math.pi) * n) % 2) == 0
            ray_w = 0.22 * (1 - d / 34)
            in_ray = abs(k - 0.5) < max(ray_w, 0.0) and d < (31 if long_ray else 22)
            if d < 5:
                img[y, x] = (255, 255, 255, 255)
            elif d < 8:
                img[y, x] = (255, 242, 196, 240)
            elif d < 11:
                img[y, x] = (255, 226, 122, 170)
            elif in_ray:
                if d < 18:
                    img[y, x] = (255, 236, 170, 210)
                elif d < 25:
                    img[y, x] = (242, 194, 48, 150)
                else:
                    img[y, x] = (242, 194, 48, 80)
            elif d < 14 and (x + y) % 2 == 0:
                img[y, x] = (255, 226, 122, 90)
    return img


def make_sparkles():
    strip = canvas(32, 8)
    W_ = (255, 255, 255, 255)
    Y_ = YEL[3]
    G_ = YEL[2]
    frames = [
        {(3, 3): W_, (4, 4): W_, (3, 4): Y_, (4, 3): Y_},
        {(3, 3): W_, (4, 4): W_, (3, 4): W_, (4, 3): W_, (3, 1): Y_, (3, 2): Y_, (4, 5): Y_, (4, 6): Y_,
         (1, 4): Y_, (2, 4): Y_, (5, 3): Y_, (6, 3): Y_},
        {(3, 3): W_, (4, 4): W_, (3, 4): W_, (4, 3): W_, (3, 0): G_, (3, 1): Y_, (3, 2): W_,
         (4, 5): W_, (4, 6): Y_, (4, 7): G_, (0, 4): G_, (1, 4): Y_, (2, 4): W_, (5, 3): W_, (6, 3): Y_,
         (7, 3): G_, (2, 2): G_, (5, 5): G_, (5, 2): G_, (2, 5): G_},
        {(3, 3): Y_, (4, 4): Y_, (3, 4): W_, (4, 3): W_, (3, 2): G_, (4, 5): G_, (2, 4): G_, (5, 3): G_},
    ]
    for i, f in enumerate(frames):
        for (x, y), c in f.items():
            put(strip, i * 8 + x, y, c)
    return strip


def main():
    closed = make_pouch()
    save(closed, "packs", "pack_closed.png")
    save(skew(closed, 0.035, squash=3), "packs", "pack_shake_1.png")
    save(skew(closed, -0.035, squash=1), "packs", "pack_shake_2.png")
    save(make_pouch(open_top=True), "packs", "pack_open.png")
    save(make_burst(), "packs", "burst.png")
    save(make_sparkles(), "packs", "sparkle.png")


if __name__ == "__main__":
    main()
