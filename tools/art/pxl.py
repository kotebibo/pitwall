"""Tiny pixel-art toolkit shared by the Pit Wall art generators.

Everything works on numpy RGBA uint8 arrays shaped (h, w, 4).
No antialiasing anywhere unless a function says so explicitly.
"""
from __future__ import annotations

import json
import os
from typing import Iterable, Sequence

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPRITES = os.path.join(ROOT, "game", "assets", "sprites")

# --------------------------------------------------------------------------
# colour helpers
# --------------------------------------------------------------------------

def hx(s: str, a: int = 255) -> tuple:
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), a)


def ramp(*cols: str) -> list:
    return [hx(c) for c in cols]


def mix(c1, c2, t: float) -> tuple:
    return tuple(int(round(c1[i] * (1 - t) + c2[i] * t)) for i in range(4))


def with_alpha(c, a: int) -> tuple:
    return (c[0], c[1], c[2], a)


# UI palette (shared with the rest of the game)
UI = {
    "bg": hx("#141518"),
    "panel": hx("#1d1f23"),
    "line": hx("#34363c"),
    "ink": hx("#f1efea"),
    "ink2": hx("#a3a3ad"),
    "red": hx("#e8352b"),
    "yellow": hx("#f2c230"),
    "purple": hx("#a855f7"),
    "blue": hx("#5ec8e5"),
    "green": hx("#3ecf6a"),
}

# material ramps, index 0 = darkest (outline) ... last = highlight
# paint is "almost grey" with a tiny warm highlight / cool shadow so that a
# multiply tint picks up a hint of hue shifting.
PAINT = ramp("#3b3c44", "#6b6c74", "#95969c", "#c4c4c6", "#ebeae6", "#fdfcf8")
# lifts level-5 paint above the team colour (multiply alone cannot brighten)
HI = hx("#fff2dc", 60)
CARBON = ramp("#0e0f11", "#16181c", "#1f2228", "#2b2f36", "#3b414b", "#56606e")
TYRE = ramp("#0a0a0c", "#121214", "#18181b", "#1f1f23", "#2a2a2e", "#3a3a40")
METAL = ramp("#3c414b", "#646b78", "#949cab", "#c8ced8", "#eef1f5")
VISOR = ramp("#101a26", "#22405f", "#3f78a8", "#9fd4f2")
DARK = hx("#08090b")
SPEC = hx("#fff8e8", 150)  # specular overlay on top of tinted paint

# --------------------------------------------------------------------------
# canvas
# --------------------------------------------------------------------------

def canvas(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w, 4), np.uint8)


def put(img: np.ndarray, x: int, y: int, c) -> None:
    h, w = img.shape[:2]
    if 0 <= x < w and 0 <= y < h:
        img[y, x] = c


def get(img: np.ndarray, x: int, y: int):
    h, w = img.shape[:2]
    if 0 <= x < w and 0 <= y < h:
        return tuple(int(v) for v in img[y, x])
    return (0, 0, 0, 0)


def rect(img, x0, y0, x1, y1, c) -> None:
    """Filled rect, inclusive coordinates."""
    h, w = img.shape[:2]
    xa, xb = max(0, min(x0, x1)), min(w - 1, max(x0, x1))
    ya, yb = max(0, min(y0, y1)), min(h - 1, max(y0, y1))
    if xa <= xb and ya <= yb:
        img[ya:yb + 1, xa:xb + 1] = c


def hline(img, x0, x1, y, c):
    rect(img, x0, y, x1, y, c)


def vline(img, x, y0, y1, c):
    rect(img, x, y0, x, y1, c)


def line(img, x0, y0, x1, y1, c) -> None:
    """Bresenham line, 1px, no AA."""
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        put(img, x0, y0, c)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def line_pts(x0, y0, x1, y1) -> list:
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def poly_mask(w: int, h: int, pts: Sequence, ) -> np.ndarray:
    """Even-odd scanline fill sampled at pixel centres. Returns bool mask."""
    m = np.zeros((h, w), bool)
    n = len(pts)
    for y in range(h):
        yc = y + 0.5
        xs = []
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            if (y0 <= yc < y1) or (y1 <= yc < y0):
                xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            xa = int(np.ceil(xs[i] - 0.5))
            xb = int(np.floor(xs[i + 1] - 0.5))
            xa, xb = max(0, xa), min(w - 1, xb)
            if xa <= xb:
                m[y, xa:xb + 1] = True
    return m


def ellipse_mask(w, h, cx, cy, rx, ry) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    return ((xx + 0.5 - cx) / rx) ** 2 + ((yy + 0.5 - cy) / ry) ** 2 <= 1.0


def fill_mask(img, mask, c):
    img[mask] = c


def edge_of(mask: np.ndarray) -> np.ndarray:
    """Pixels of mask that touch a non-mask pixel (4-neighbourhood)."""
    m = mask
    p = np.pad(m, 1)
    inner = p[1:-1, 2:] & p[1:-1, :-2] & p[2:, 1:-1] & p[:-2, 1:-1]
    return m & ~inner


def dilate(mask: np.ndarray, r: int = 1, diag: bool = True) -> np.ndarray:
    out = mask.copy()
    for _ in range(r):
        p = np.pad(out, 1)
        n = p[1:-1, 2:] | p[1:-1, :-2] | p[2:, 1:-1] | p[:-2, 1:-1] | p[1:-1, 1:-1]
        if diag:
            n = n | p[2:, 2:] | p[:-2, :-2] | p[2:, :-2] | p[:-2, 2:]
        out = n
    return out


def outline(img: np.ndarray, c, diag: bool = False) -> np.ndarray:
    """Add a 1px outline outside the opaque pixels of img (returns new)."""
    a = img[..., 3] > 0
    ring = dilate(a, 1, diag) & ~a
    out = img.copy()
    out[ring] = c
    return out


def alpha_over(dst: np.ndarray, src: np.ndarray, ox: int = 0, oy: int = 0) -> None:
    """Composite src over dst in place at offset (proper 'over')."""
    dh, dw = dst.shape[:2]
    sh, sw = src.shape[:2]
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(dw, ox + sw), min(dh, oy + sh)
    if x0 >= x1 or y0 >= y1:
        return
    s = src[y0 - oy:y1 - oy, x0 - ox:x1 - ox].astype(np.float32) / 255.0
    d = dst[y0:y1, x0:x1].astype(np.float32) / 255.0
    sa = s[..., 3:4]
    da = d[..., 3:4]
    oa = sa + da * (1 - sa)
    oc = np.where(oa > 0, (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6), 0)
    dst[y0:y1, x0:x1, :3] = np.clip(oc * 255 + 0.5, 0, 255).astype(np.uint8)
    dst[y0:y1, x0:x1, 3:4] = np.clip(oa * 255 + 0.5, 0, 255).astype(np.uint8)


def multiply(img: np.ndarray, col) -> np.ndarray:
    out = img.copy().astype(np.float32)
    for i in range(3):
        out[..., i] = out[..., i] * col[i] / 255.0
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def flip_h(img):
    return img[:, ::-1].copy()


def flip_v(img):
    return img[::-1].copy()


def scale(img: np.ndarray, k: int) -> np.ndarray:
    return np.repeat(np.repeat(img, k, axis=0), k, axis=1)


def rotate_nearest(img: np.ndarray, deg: float) -> np.ndarray:
    im = Image.fromarray(img, "RGBA")
    return np.array(im.rotate(deg, resample=Image.NEAREST, expand=False))


def save(img: np.ndarray, *parts: str) -> str:
    path = os.path.join(SPRITES, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(img, "RGBA").save(path)
    return path


def load(*parts: str) -> np.ndarray:
    return np.array(Image.open(os.path.join(SPRITES, *parts)).convert("RGBA"))


def save_json(obj, *parts: str) -> str:
    path = os.path.join(SPRITES, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
    return path


# --------------------------------------------------------------------------
# tiny bitmap font (3x5 and 5x7 caps) for stencil text / labels
# --------------------------------------------------------------------------

FONT5 = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "01010", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "0": ["01110", "10011", "10101", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "#": ["01010", "11111", "01010", "01010", "01010", "11111", "01010"],
    " ": ["000", "000", "000", "000", "000", "000", "000"],
}

FONT3 = {
    "A": ["010", "101", "111", "101", "101"],
    "B": ["110", "101", "110", "101", "110"],
    "C": ["011", "100", "100", "100", "011"],
    "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"],
    "F": ["111", "100", "110", "100", "100"],
    "G": ["011", "100", "101", "101", "011"],
    "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"],
    "K": ["101", "101", "110", "101", "101"],
    "L": ["100", "100", "100", "100", "111"],
    "M": ["101", "111", "111", "101", "101"],
    "N": ["110", "101", "101", "101", "101"],
    "O": ["010", "101", "101", "101", "010"],
    "P": ["110", "101", "110", "100", "100"],
    "R": ["110", "101", "110", "101", "101"],
    "S": ["011", "100", "010", "001", "110"],
    "T": ["111", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "010"],
    "W": ["101", "101", "111", "111", "101"],
    "Y": ["101", "101", "010", "010", "010"],
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["110", "001", "010", "100", "111"],
    "3": ["110", "001", "010", "001", "110"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "110", "001", "110"],
    "6": ["011", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "110"],
    "-": ["000", "000", "111", "000", "000"],
    "/": ["001", "001", "010", "100", "100"],
    "Z": ["111", "001", "010", "100", "111"],
    "Q": ["010", "101", "101", "110", "011"],
    "X": ["101", "101", "010", "101", "101"],
    "J": ["001", "001", "001", "101", "010"],
    "+": ["000", "010", "111", "010", "000"],
    "_": ["000", "000", "000", "000", "111"],
    ".": ["000", "000", "000", "000", "010"],
    " ": ["00", "00", "00", "00", "00"],
}


def text_width(s: str, font=FONT3, gap: int = 1) -> int:
    return sum(len(font[ch][0]) + gap for ch in s) - gap


def draw_text(img, x, y, s, c, font=FONT3, gap: int = 1, stencil: bool = False) -> int:
    """Draw text; stencil=True knocks out a vertical bridge in each glyph."""
    cx = x
    for ch in s:
        g = font[ch]
        gw = len(g[0])
        for j, rowbits in enumerate(g):
            for i, b in enumerate(rowbits):
                if b == "1":
                    if stencil and j == len(g) // 2 and ch not in "-" and 0 < i < gw - 1 and ch in "ABDOPR0689":
                        continue
                    put(img, cx + i, y + j, c)
        cx += gw + gap
    return cx
