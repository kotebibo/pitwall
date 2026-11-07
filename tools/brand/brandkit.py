"""Pit Wall brand kit: shared pieces for the brand generators.

Palette, the PIT WALL wordmark as separate layers (so it can be drawn in full
colour or one colour), an angular italic display face that matches the
wordmark, Pixelify Sans body text without antialiasing, and small image
helpers. Everything is pixel art on numpy RGBA arrays (h, w, 4); images are
only ever scaled by whole numbers with nearest filtering.

The game's shared helpers (tools/art/pxl.py, pixel.py, ui.py) are imported,
never modified.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.append(str(ROOT / "tools" / "art"))  # after tools/brand, so names never shadow

import pixel  # noqa: E402  (game art helpers)
from pixel import bayer, dilate, shift  # noqa: E402

BRAND = ROOT / "brand"
RENDERS = BRAND / "renders" / "_src"  # raw Godot output (+ _shadow.png, .json camera)
SPRITES = ROOT / "game" / "assets" / "sprites"
FONT_PATH = ROOT / "game" / "assets" / "fonts" / "PixelifySans.ttf"


def hx(s: str, a: int = 255) -> tuple:
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), a)


# ---------------------------------------------------------------- palette
BG = hx("141518")
PANEL = hx("1d1f23")
LINE = hx("34363c")
LINE_STRONG = hx("4a4c54")
INK = hx("f1efea")
INK_2 = hx("a3a3ad")
INK_3 = hx("6e6f78")
RED = hx("e8352b")
RED_HI = hx("f2603f")
RED_LO = hx("a8242a")
RED_DEEP = hx("7a1a26")
RED_DARK = hx("3a1c1d")
YELLOW = hx("f2c230")
PURPLE = hx("a855f7")
BLUE = hx("5ec8e5")
GREEN = hx("3ecf6a")
WHITE = hx("ffffff")
INK_SHADE = hx("d9d5cc")
BLACK = hx("0b0c0e")
CHECK_DARK = hx("26272c")
CLEAR = (0, 0, 0, 0)


# ---------------------------------------------------------------- image helpers
def canvas(w: int, h: int, c=CLEAR) -> np.ndarray:
    a = np.zeros((h, w, 4), np.uint8)
    a[...] = c
    return a


def up(a: np.ndarray, k: int) -> np.ndarray:
    """Whole-number nearest upscale."""
    return np.repeat(np.repeat(a, k, axis=0), k, axis=1) if k > 1 else a.copy()


def over(dst: np.ndarray, src: np.ndarray, x: int = 0, y: int = 0) -> np.ndarray:
    """Alpha-composite src onto dst at (x, y), clipped. In place; returns dst."""
    H, W = dst.shape[:2]
    h, w = src.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return dst
    s = src[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    d = dst[y0:y1, x0:x1].astype(np.float32)
    sa = s[..., 3:4] / 255.0
    da = d[..., 3:4] / 255.0
    oa = sa + da * (1 - sa)
    rgb = np.where(oa > 0, (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6), 0)
    out = np.concatenate([rgb, oa * 255.0], axis=-1)
    dst[y0:y1, x0:x1] = np.clip(np.round(out), 0, 255).astype(np.uint8)
    return dst


def paint(a: np.ndarray, mask: np.ndarray, c) -> np.ndarray:
    a[mask] = c
    return a


def trim(a: np.ndarray, pad: int = 0) -> np.ndarray:
    ys, xs = np.nonzero(a[..., 3])
    if len(xs) == 0:
        return a
    t = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    if pad:
        out = canvas(t.shape[1] + 2 * pad, t.shape[0] + 2 * pad)
        out[pad:pad + t.shape[0], pad:pad + t.shape[1]] = t
        return out
    return t


def mask_of(a: np.ndarray) -> np.ndarray:
    return a[..., 3] > 0


def recolor(a: np.ndarray, c) -> np.ndarray:
    out = canvas(a.shape[1], a.shape[0])
    out[mask_of(a)] = c
    return out


def outline_mask(m: np.ndarray, diag: bool = False) -> np.ndarray:
    return dilate(m, diag=diag) & ~m


def flip_h(a: np.ndarray) -> np.ndarray:
    return a[:, ::-1].copy()


def save(a: np.ndarray, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a, "RGBA").save(path, optimize=True)
    return path


def save_rgb(a: np.ndarray, path: Path | str) -> Path:
    """Opaque PNG (social images: no alpha channel)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a[..., :3].copy(), "RGB").save(path, optimize=True)
    return path


def load(path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGBA"))


def fit_up(native: np.ndarray, k: int, W: int, H: int) -> np.ndarray:
    """Upscale by k and centre-crop to exactly W x H (for sizes not divisible by k)."""
    big = up(native, k)
    y0 = (big.shape[0] - H) // 2
    x0 = (big.shape[1] - W) // 2
    return big[y0:y0 + H, x0:x0 + W].copy()


def shade(a: np.ndarray, k: float) -> np.ndarray:
    out = a.copy()
    out[..., :3] = np.clip(out[..., :3].astype(np.float32) * k, 0, 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------- shear (italic)
def shear_mask(m: np.ndarray, shear: int = 3, extra: int | None = None) -> np.ndarray:
    """Shear an upright mask to italic by whole pixels: the bottom row stays,
    each `shear` rows up move one pixel right."""
    h, w = m.shape
    pad = (h - 1) // shear + 1 if extra is None else extra
    out = np.zeros((h, w + pad), bool)
    for y in range(h):
        off = (h - 1 - y) // shear
        out[y, off:off + w] = m[y]
    return out


def poly_fill(w: int, h: int, polys, holes=()) -> np.ndarray:
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    for p in polys:
        d.polygon(p, fill=255)
    for p in holes:
        d.polygon(p, fill=0)
    return np.array(im) > 0


# ---------------------------------------------------------------- display face
# Glyphs on a module grid: columns alternate stem (s) / counter (w_in), rows are
# bar / counter / bar / counter / bar. '#' full, '.' empty, '1'..'4' a full cell
# with its TL / TR / BR / BL corner chamfered, 'v' and 'n' diagonal helpers.
GLYPHS = {
    "A": ["1#2", "#.#", "###", "#.#", "#.#"],
    "B": ["##2", "#.#", "##.", "#.#", "##3"],
    "C": ["1##", "#..", "#..", "#..", "4##"],
    "D": ["##2", "#.#", "#.#", "#.#", "##3"],
    "E": ["###", "#..", "##.", "#..", "###"],
    "F": ["###", "#..", "##.", "#..", "#.."],
    "G": ["1##", "#..", "#.#", "#.#", "4##"],
    "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["#", "#", "#", "#", "#"],
    "J": ["..#", "..#", "..#", "#.#", "4#3"],
    "K": ["#.#", "#.#", "##3", "#.#", "#.#"],
    "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["1###2", "#.#.#", "#.#.#", "#.#.#", "#.#.#"],
    "N": ["1#2", "#.#", "#.#", "#.#", "#.#"],
    "O": ["1#2", "#.#", "#.#", "#.#", "4#3"],
    "P": ["##2", "#.#", "##3", "#..", "#.."],
    "R": ["##2", "#.#", "##.", "#.#", "#.#"],
    "S": ["1##", "#..", "4#2", "..#", "##3"],
    "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "4#3"],
    "V": ["#.#", "#.#", "#.#", "#.#", "4#3"],
    "W": ["#...#", "#...#", "#.#.#", "#.#.#", "4###3"],
    "X": ["#.#", "#.#", "4#3", "#.#", "#.#"],
    "Y": ["#.#", "#.#", "4#3", ".#.", ".#."],
    "Z": ["###", "..#", "1#3", "#..", "###"],
    "0": ["1#2", "#.#", "#.#", "#.#", "4#3"],
    "1": ["##", ".#", ".#", ".#", ".#"],
    "2": ["##2", "..#", "1#3", "#..", "###"],
    "3": ["##2", "..#", ".##", "..#", "##3"],
    "4": ["#.#", "#.#", "4##", "..#", "..#"],
    "5": ["###", "#..", "##2", "..#", "##3"],
    "6": ["1##", "#..", "##2", "#.#", "4#3"],
    "7": ["###", "..#", "..#", "..#", "..#"],
    "8": ["1#2", "#.#", "###", "#.#", "4#3"],
    "9": ["1#2", "#.#", "4##", "..#", "##3"],
    "+": ["...", ".#.", "###", ".#.", "..."],
    "-": ["...", "...", "###", "...", "..."],
    ".": ["#", ".", ".", ".", "#"],  # placeholder, special-cased
    " ": [".", ".", ".", ".", "."],
}


def _cell_poly(x0, y0, x1, y1, kind, c):
    """Polygon for one grid cell; kind '#' or a chamfered corner '1'..'4'."""
    if kind == "#":
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if kind == "1":  # TL
        return [(x0 + c, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0 + c)]
    if kind == "2":  # TR
        return [(x0, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1), (x0, y1)]
    if kind == "3":  # BR
        return [(x0, y0), (x1, y0), (x1, y1 - c), (x1 - c, y1), (x0, y1)]
    if kind == "4":  # BL
        return [(x0, y0), (x1, y0), (x1, y1), (x0 + c, y1), (x0, y1 - c)]
    return None


def _poly_glyph(ch: str, h: int, s: int, w_in: int, c: int):
    """Glyphs with diagonals, as polygons on a (W, h) box; None if not special."""
    W = 2 * s + w_in
    cx = W / 2
    t = s * 1.15  # horizontal thickness of a diagonal stroke
    P = None
    if ch == "N":
        P = [[(0, c), (c, 0), (s, 0), (s, h), (0, h)], [(W - s, 0), (W, 0), (W, h), (W - s, h)],
             [(0, 0), (t, 0), (W, h), (W - t, h)]]
    elif ch == "V":
        y1 = round(h * 0.45)
        P = [[(0, 0), (s, 0), (s, y1), (cx + s / 2, h), (cx - s / 2 - 1, h), (0, y1 + s / 2)],
             [(W - s, 0), (W, 0), (W, y1 + s / 2), (cx + s / 2 + 1, h), (cx - s / 2, h), (W - s, y1)]]
    elif ch == "Y":
        y1 = round(h * 0.5)
        P = [[(0, 0), (s, 0), (s, y1 - s), (cx, y1), (cx, y1 + s), (0, y1 - s / 2)],
             [(W - s, 0), (W, 0), (W, y1 - s / 2), (cx, y1 + s), (cx, y1), (W - s, y1 - s)],
             [(cx - s / 2, y1), (cx + s / 2, y1), (cx + s / 2, h), (cx - s / 2, h)]]
    elif ch == "X":
        P = [[(0, 0), (t, 0), (W, h), (W - t, h)], [(W - t, 0), (W, 0), (t, h), (0, h)]]
    elif ch == "K":
        m = h / 2
        P = [[(0, 0), (s, 0), (s, h), (0, h)], [(W - t, 0), (W, 0), (s + t * 0.4, m + s / 2), (s, m + s / 2), (s, m - s / 2)],
             [(s, m - s / 2), (s + t * 0.6, m - s / 2), (W, h), (W - t, h)]]
    elif ch == "Z":
        P = [[(0, 0), (W, 0), (W, s), (0, s)], [(0, h - s), (W, h - s), (W, h), (0, h)],
             [(W - t, s), (W, s), (t, h - s), (0, h - s)]]
    elif ch == "1":
        Wd = s + max(2, w_in // 2 + 1)
        P = [[(Wd - s, 0), (Wd, 0), (Wd, h), (Wd - s, h)], [(0, s), (Wd - s - (s - 1), 0), (Wd - s, 0), (Wd - s, s), (s, 2 * s - 1), (0, 2 * s - 1)]]
        return Wd, P
    elif ch == "+":
        a = (h - 3 * s) // 2
        y0 = s + a
        Wp = 3 * s
        P = [[(0, y0), (Wp, y0), (Wp, y0 + s), (0, y0 + s)], [(s, y0 - s), (2 * s, y0 - s), (2 * s, y0 + 2 * s), (s, y0 + 2 * s)]]
        return Wp, P
    if P is None:
        return None
    return W, P


def glyph_mask(ch: str, h: int, s: int, w_in: int, c: int | None = None) -> np.ndarray:
    """Upright glyph mask (h rows)."""
    c = max(1, round(s * 0.75)) if c is None else c
    pg = _poly_glyph(ch, h, s, w_in, c)
    if pg is not None:
        W, polys = pg
        # supersample 4x and threshold, so diagonals are even staircases
        k = 4
        im = Image.new("L", (W * k, h * k), 0)
        d = ImageDraw.Draw(im)
        for p in polys:
            d.polygon([(x * k, y * k) for x, y in p], fill=255)
        a = np.array(im, np.float32).reshape(h, k, W, k).mean(axis=(1, 3))
        return a >= 128
    if ch == " ":
        return np.zeros((h, max(2, w_in)), bool)
    if ch == ".":
        m = np.zeros((h, s), bool)
        m[h - s:, :] = True
        return m
    rows = GLYPHS[ch]
    ncols = len(rows[0])
    colw = [s if i % 2 == 0 else w_in for i in range(ncols)]
    if ncols == 1:
        colw = [s]
    if ncols == 2:
        colw = [w_in // 2 + 1, s]  # the "1": short flag + stem
    a = (h - 3 * s) // 2
    b = h - 3 * s - a
    rowh = [s, a, s, b, s]
    W = sum(colw)
    # PIL fills polygons inclusive of the far edge: draw in a 1 px larger grid
    # with cells shrunk by one and take the exact box afterwards.
    im = Image.new("L", (W + 1, h + 1), 0)
    d = ImageDraw.Draw(im)
    y = 0
    for r, row in enumerate(rows):
        x = 0
        for k, kind in enumerate(row):
            if kind != ".":
                p = _cell_poly(x, y, x + colw[k] - 1, y + rowh[r] - 1, kind, c - 1)
                if p:
                    d.polygon(p, fill=255)
            x += colw[k]
        y += rowh[r]
    return (np.array(im) > 0)[:h, :W]


def display_mask(text: str, h: int, s: int, w_in: int, gap: int, space: int | None = None,
                 shear: int = 3) -> np.ndarray:
    parts = []
    for i, ch in enumerate(text):
        if ch == " ":
            parts.append(np.zeros((h, space if space is not None else w_in), bool))
        else:
            parts.append(glyph_mask(ch, h, s, w_in))
        if i < len(text) - 1:
            parts.append(np.zeros((h, gap), bool))
    m = np.concatenate(parts, axis=1)
    return shear_mask(m, shear) if shear else m


def style_letters(m: np.ndarray, ext: int = 2, outline: bool = True, fill=INK, shade_c=INK_SHADE,
                  top=WHITE, ext_c=RED_DEEP, line=BLACK, shade_from: float = 0.62, pad: int = 3) -> np.ndarray:
    """The wordmark treatment: ink letters, shaded lower part, white top edge,
    a down-right extrusion and a 1 px dark outline."""
    h, w = m.shape
    P = pad
    word = np.zeros((h + 2 * P, w + 2 * P), bool)
    word[P:P + h, P:P + w] = m
    img = canvas(word.shape[1], word.shape[0])
    if ext:
        e = np.zeros_like(word)
        for k in range(1, ext + 1):
            e |= shift(word, k, k)
        e &= ~word
        img[e] = ext_c
    img[word] = fill
    if shade_c is not None:
        lower = np.zeros_like(word)
        lower[P + int(h * shade_from):P + h, :] = True
        img[word & lower] = shade_c
    if top is not None:
        img[word & ~shift(word, 0, 1)] = top
    if outline:
        sil = img[..., 3] > 0
        img[outline_mask(sil)] = line
    return trim(img)


# ---------------------------------------------------------------- body text (Pixelify Sans)
_FONT_CACHE: dict = {}


def _font(size: int, weight: int = 400):
    key = (size, weight)
    if key not in _FONT_CACHE:
        f = ImageFont.truetype(str(FONT_PATH), size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        _FONT_CACHE[key] = f
    return _FONT_CACHE[key]


def text_mask(s: str, size: int = 11, tracking: int = 1, weight: int = 400, space: int | None = None) -> np.ndarray:
    """Pixelify Sans at its native pixel size (11 px = 7 px caps), no antialiasing,
    drawn glyph by glyph with extra tracking."""
    f = _font(size, weight)
    asc, desc = f.getmetrics()
    H = asc + desc + 2
    widths = []
    for ch in s:
        if ch == " ":
            widths.append(space if space is not None else max(3, size // 3))
        else:
            l, t, r, b = f.getbbox(ch)
            widths.append(r)
    W = sum(widths) + tracking * len(s) + 4
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    x = 0
    for ch, cw in zip(s, widths):
        if ch == "_":
            # Pixelify's underscore sits on the baseline as a short dash: draw a
            # full-width one a row lower so file names read correctly
            d.rectangle([x, asc + 1, x + cw - 1, asc + 1], fill=255)
        elif ch != " ":
            d.text((x, 0), ch, font=f, fill=255)
        x += cw + tracking
    m = np.array(im) > 127
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return m
    # keep a fixed baseline box: crop columns only, rows from cap top to baseline+desc
    cap_top = _cap_top(size, weight)
    return m[cap_top:asc + desc, xs.min():xs.max() + 1]


def _cap_top(size, weight):
    f = _font(size, weight)
    l, t, r, b = f.getbbox("H")
    return t


def text_img(s: str, c=INK, size: int = 11, tracking: int = 1, shadow=None, weight: int = 400,
             space: int | None = None) -> np.ndarray:
    m = text_mask(s, size, tracking, weight, space)
    pad = 1 if shadow is not None else 0
    img = canvas(m.shape[1] + pad, m.shape[0] + pad)
    if shadow is not None:
        sm = np.zeros(img.shape[:2], bool)
        sm[1:, 1:] = m
        img[sm] = shadow
    mm = np.zeros(img.shape[:2], bool)
    mm[:m.shape[0], :m.shape[1]] = m
    img[mm] = c
    return img


def cap_height(size: int = 11) -> int:
    f = _font(size)
    l, t, r, b = f.getbbox("H")
    return b - t


# ---------------------------------------------------------------- wordmark
def _ui_module():
    import ui  # tools/art/ui.py (game logo generator); imported, not modified
    return ui


def wordmark_layers(h=32, s=6, gap=3, word_gap=10, shear=3, small=False, text="PIT WALL"):
    """The game's PIT WALL wordmark (tools/art/ui.py make_logo) split into
    masks, cropped tight: word, extrusion, stripe, stripe_hi, stripe_lo,
    flag_light, flag_dark. Same geometry as the in-game logo.png."""
    ui = _ui_module()
    m = ui._wordmark_mask(text, h, s, gap, word_gap, shear)
    mh, mw = m.shape
    stripe_h = 3 if small else 5
    cell = 2 if small else 3
    ccols, crows = (3, 2) if small else (4, 2)
    flag_w = ccols * cell
    dash_room = 10 if small else 17
    pad = h // shear + 2
    core = mw - pad
    W = dash_room + mw + 8
    H = mh + 16
    ox = dash_room + 2
    oy = 3
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
    flag_l = np.zeros_like(word)
    flag_d = np.zeros_like(word)
    fy0 = sy0 + stripe_h - crows * cell
    fx0 = x_end + (2 if small else 3)
    for r in range(crows):
        for c in range(ccols):
            tgt = flag_l if (r + c) % 2 == 0 else flag_d
            for dy in range(cell):
                y = fy0 + r * cell + dy
                off = (sy0 + stripe_h - 1 - y) // shear
                for dx in range(cell):
                    tgt[y, fx0 + c * cell + dx + off] = True
    lower = np.zeros_like(word)
    lower[oy + int(mh * 0.62):oy + mh, :] = True
    L = {
        "word": word, "ext": ext, "stripe": stripe, "flag_light": flag_l, "flag_dark": flag_d,
        "word_lower": word & lower, "word_top": word & ~shift(word, 0, 1),
        "stripe_hi": stripe & ~shift(stripe, 0, 1), "stripe_lo": stripe & ~shift(stripe, 0, -1),
    }
    # crop to content + 1 px for the outline
    allm = word | ext | stripe | flag_l | flag_d
    ys, xs = np.nonzero(allm)
    y0, y1, x0, x1 = ys.min() - 1, ys.max() + 2, xs.min() - 1, xs.max() + 2
    return {k: v[y0:y1, x0:x1] for k, v in L.items()}


def wordmark(mode: str = "color", small: bool = False, **kw) -> np.ndarray:
    """mode: 'color' (game logo), 'white' / 'black' (one colour, no outline:
    letters, stripe and the light flag squares), or 'flat' (colour, no outline)."""
    L = wordmark_layers(small=small, **kw)
    h, w = L["word"].shape
    img = canvas(w, h)
    if mode in ("white", "black", "red"):
        c = {"white": INK, "black": BG, "red": RED}[mode]
        for k in ("word", "stripe", "flag_light"):
            img[L[k]] = c
        return trim(img)
    img[L["ext"]] = RED_DEEP
    img[L["word"]] = INK
    img[L["word_lower"]] = INK_SHADE
    img[L["word_top"]] = WHITE
    img[L["stripe"]] = RED
    img[L["stripe_hi"]] = RED_HI
    img[L["stripe_lo"]] = RED_LO
    img[L["flag_light"]] = INK
    img[L["flag_dark"]] = CHECK_DARK
    if mode == "color":
        sil = img[..., 3] > 0
        img[outline_mask(sil)] = BLACK
    return img


# ---------------------------------------------------------------- renders
def render(name: str) -> np.ndarray:
    return load(RENDERS / f"{name}.png")


def render_with_shadow(name: str, shadow_alpha: float = 1.0) -> np.ndarray:
    car = load(RENDERS / f"{name}.png")
    sp = RENDERS / f"{name}_shadow.png"
    if not sp.exists():
        return car
    sh = load(sp)
    if shadow_alpha != 1.0:
        sh[..., 3] = np.clip(sh[..., 3].astype(np.float32) * shadow_alpha, 0, 255).astype(np.uint8)
    out = sh.copy()
    over(out, car)
    return out


def dither_level(t: np.ndarray, steps: int, n: int = 4) -> np.ndarray:
    """Quantise a 0..1 field to `steps` levels with ordered dithering."""
    h, w = t.shape
    b = bayer(w, h, n)
    return np.clip(np.floor(t * steps + (b - 0.5)), 0, steps) / steps
