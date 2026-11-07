"""Pit Wall icon marks (no wordmark): three concepts, each drawn per size.

  pw   "PW" monogram in the wordmark's letters, on a red badge with the
       UI's chamfered corners, plus the speed stripe and chequer. (primary)
  car  the 3D car head-on (white livery) on the same red badge.
  p    the wordmark's italic P over the speed stripe, on a dark badge.

Sizes 16 and 24 are hand-placed pixel grids; 32 and up are built from the
same geometry as the wordmark (tools/art/ui.py glyphs).
"""
from __future__ import annotations

import numpy as np

from brandkit import (BG, BLACK, CHECK_DARK, INK, INK_SHADE, LINE, PANEL, RED, RED_DEEP, RED_HI, RED_LO, WHITE,
                      _ui_module, canvas, hx, shear_mask, shift)

TYRE = hx("2e3038")
TYRE_HI = hx("4a4c54")


def from_ascii(rows, colors) -> np.ndarray:
    h, w = len(rows), max(len(r) for r in rows)
    a = canvas(w, h)
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch in colors:
                a[y, x] = colors[ch]
    return a


def badge_mask(n: int, ch: int, r: int = 1) -> np.ndarray:
    """n x n with the UI panel's chamfered TL and BR corners, small round TR/BL."""
    yy, xx = np.mgrid[0:n, 0:n]
    m = (xx + yy >= ch) & ((n - 1 - xx) + (n - 1 - yy) >= ch)
    if r:
        m &= ~(((n - 1 - xx) + yy < r) | (xx + (n - 1 - yy) < r))
    return m


def _bevel(img, m, hi, lo):
    """1 px light top/left inner edge, dark bottom/right inner edge."""
    top = m & ~shift(m, 0, 1)
    left = m & ~shift(m, 1, 0)
    bot = m & ~shift(m, 0, -1)
    right = m & ~shift(m, -1, 0)
    img[(bot | right) & m] = lo
    img[(top | left) & m] = hi


def _sheared_rows(mask, y0, y1, a, b, shear):
    for y in range(y0, y1):
        off = (y1 - 1 - y) // shear
        mask[y, max(0, a + off):max(0, b + off)] = True


# ---------------------------------------------------------------- PW monogram
def mark_pw_fullbleed(n: int, inner: int, bg=RED) -> np.ndarray:
    """The PW mark's content (letters + stripe) of an `inner`-px badge, centred
    on a full-bleed n x n square: for app icons and avatars, where the OS or
    the site applies its own mask."""
    img = canvas(n, n)
    img[...] = bg
    content = mark_pw(inner, badge=False)
    from brandkit import over
    off = (n - inner) // 2
    over(img, content, off, off + max(0, round(inner / 64)))
    return img


def mark_pw(n: int, badge: bool = True) -> np.ndarray:
    """PW monogram badge. 16/24/32 are hand-placed; larger sizes use the
    wordmark's own P and W glyphs with the 32 px layout scaled up.
    badge=False: letters and stripe only, on transparent."""
    if n in SMALL:
        return _pw_small(n) if badge else _strip_badge(_pw_small(n), n)
    ui = _ui_module()
    k = n / 32.0
    h = round(14 * k)
    s = round(3 * k)
    gap = round(2 * k)
    m = ui._wordmark_mask("PW", h, s, gap, 0, 3)
    m = m[:, :np.nonzero(m.any(axis=0))[0].max() + 1]
    mh, mw = m.shape
    bm = badge_mask(n, round(7 * k), max(1, round(k)))
    img = canvas(n, n)
    if badge:
        img[bm] = RED
        _bevel(img, bm, RED_HI, RED_LO)
    else:
        bm = np.ones((n, n), bool)
    ext = round(2 * k * 0.75) if n >= 48 else 1
    oy = round(5 * k)
    ox = (n - mw) // 2
    word = np.zeros((n, n), bool)
    word[oy:oy + mh, ox:ox + mw] = m
    e = np.zeros_like(word)
    for i in range(1, ext + 1):
        e |= shift(word, i, i)
    e &= ~word & bm
    img[e] = RED_DEEP
    img[word] = INK
    lower = np.zeros_like(word)
    lower[oy + int(mh * 0.62):oy + mh] = True
    img[word & lower] = INK_SHADE
    img[word & ~shift(word, 0, 1)] = WHITE
    # speed stripe: one dash, the stripe, then a chequer block
    sy0, sh = round(23 * k), round(3 * k)
    stripe = np.zeros_like(word)
    _sheared_rows(stripe, sy0, sy0 + sh, round(7 * k), round(21 * k), 3)
    _sheared_rows(stripe, sy0, sy0 + sh, round(2 * k), round(6 * k) - 1, 3)
    stripe &= bm
    img[stripe] = INK
    img[stripe & ~shift(stripe, 0, 1)] = WHITE
    img[stripe & ~shift(stripe, 0, -1)] = INK_SHADE
    cell = max(1, round(k))
    fx0 = round(22 * k)
    for r in range(sh // cell):
        for c in range(4):
            col = INK if (r + c) % 2 == 0 else RED_DEEP
            for dy in range(cell):
                y = sy0 + r * cell + dy
                off = (sy0 + sh - 1 - y) // 3
                for dx in range(cell):
                    x = fx0 + c * cell + dx + off
                    if 0 <= x < n and bm[y, x]:
                        img[y, x] = col
    return img


def _strip_badge(img, n):
    """Keep only the letter / stripe colours of a small hand-placed mark."""
    out = img.copy()
    rgb = out[..., :3]
    for c in (RED, RED_HI, RED_LO):
        m = np.all(rgb == np.array(c[:3], np.uint8), axis=-1)
        out[m] = 0
    return out


def _edge(m):
    return m & ~(shift(m, 1, 0) & shift(m, -1, 0) & shift(m, 0, 1) & shift(m, 0, -1))


# Hand-placed letters for the small sizes (upright; sheared by whole pixels).
SMALL = {
    16: {
        "P": ["####.", "##.##", "##.##", "####.", "##...", "##...", "##...", "##..."],
        "W": ["##...##", "##...##", "##...##", "##.#.##", "##.#.##", "##.#.##", "##.#.##", ".#####."],
        "gap": 1, "split": 4, "top": 2, "ext": 1, "chamfer": 4,
        "stripe": {"y": 11, "h": 2, "x0": 4, "x1": 10, "dashes": [(1, 2)], "flag": (12, 3, 1)},
    },
    24: {
        "P": ["######.", "###..###", "###..###", "###..###", "#######.", "###.....", "###.....", "###.....", "###.....",
              "###....."],
        "W": ["###....###", "###....###", "###....###", "###.##.###", "###.##.###", "###.##.###", "###.##.###",
              "###.##.###", "###.##.###", ".########."],
        "gap": 1, "split": 0, "top": 4, "ext": 1, "chamfer": 5,
        "stripe": {"y": 17, "h": 2, "x0": 6, "x1": 15, "dashes": [(2, 4)], "flag": (17, 3, 1)},
    },
    32: {
        "P": ["#######..", "########.", "#########", "###...###", "###...###", "#########", "########.", "#######..",
              "###......", "###......", "###......", "###......", "###......", "###......"],
        "W": ["###........###", "###........###", "###........###", "###........###", "###........###",
              "###...##...###", "###...##...###", "###...##...###", "###...##...###", "###...##...###",
              "###...##...###", "##############", ".############.", "..##########.."],
        "gap": 2, "split": 0, "top": 5, "ext": 2, "chamfer": 7,
        "stripe": {"y": 23, "h": 3, "x0": 7, "x1": 20, "dashes": [(2, 5)], "flag": (22, 4, 1)},
    },
}


def _grid(rows):
    w = max(len(r) for r in rows)
    return np.array([[ch == "#" for ch in r.ljust(w, ".")] for r in rows], bool)


def _pw_small(n: int) -> np.ndarray:
    spec = SMALL[n]
    P, W = _grid(spec["P"]), _grid(spec["W"])
    h = max(P.shape[0], W.shape[0])
    up_ = np.zeros((h, P.shape[1] + spec["gap"] + W.shape[1]), bool)
    up_[:P.shape[0], :P.shape[1]] = P
    up_[:W.shape[0], P.shape[1] + spec["gap"]:] = W
    # italic: rows above `split` move one pixel right (16), or shear 1 per 3 rows (24)
    if spec["split"]:
        let = np.zeros((h, up_.shape[1] + 1), bool)
        let[:spec["split"], 1:] = up_[:spec["split"]]
        let[spec["split"]:, :-1] = up_[spec["split"]:]
    else:
        let = shear_mask(up_, 3)
    bm = badge_mask(n, spec["chamfer"], 1)
    img = canvas(n, n)
    img[bm] = RED
    _bevel(img, bm, RED_HI, RED_LO)
    word = np.zeros((n, n), bool)
    ox = (n - let.shape[1]) // 2
    oy = spec["top"]
    word[oy:oy + h, ox:ox + let.shape[1]] = let
    e = np.zeros_like(word)
    for i in range(1, spec["ext"] + 1):
        e |= shift(word, i, i)
    e &= ~word & bm
    img[e] = RED_DEEP
    img[word] = INK
    if n >= 32:
        lower = np.zeros_like(word)
        lower[oy + int(h * 0.62):oy + h] = True
        img[word & lower] = INK_SHADE
    if n >= 24:
        img[word & ~shift(word, 0, 1)] = WHITE
    st = spec["stripe"]
    stripe = np.zeros_like(word)
    _sheared_rows(stripe, st["y"], st["y"] + st["h"], st["x0"], st["x1"] + 1, 3)
    for a, b in st["dashes"]:
        _sheared_rows(stripe, st["y"], st["y"] + st["h"], a, b + 1, 3)
    img[stripe & bm] = INK
    fx, cols, cell = st["flag"]
    for r in range(st["h"] // cell):
        for c in range(cols):
            col = INK if (r + c) % 2 == 0 else RED_DEEP
            for dy in range(cell):
                for dx in range(cell):
                    y, x = st["y"] + r * cell + dy, fx + c * cell + dx
                    if bm[y, x]:
                        img[y, x] = col
    return img


# ---------------------------------------------------------------- head-on car
# 16 px is hand-drawn; 32 and 64 use the 3D car rendered head-on in the
# white-and-red livery (brand/renders/icon_front_*_white.png).
CAR16 = [
    "................",
    "..WWWWWWWWWWWW..",
    "..d..........d..",
    ".kkk...WW...kkk.",
    ".kkk..WddW..kkk.",
    ".kkk..WWWW..kkk.",
    "......wWWw......",
    "kkk..WWWWWW..kkk",
    "kkk.WWWWWWWW.kkk",
    "kkk..wwWWww..kkk",
    "kkk...WWWW...kkk",
    "kkk....WW....kkk",
    "WWWWWWWWWWWWWWWW",
    "wwwwww.WW.wwwwww",
    "................",
    "................",
]


def _red_badge(n):
    ch = {16: 4, 24: 5}.get(n, round(7 * n / 32))
    bm = badge_mask(n, ch, max(1, round(n / 32)))
    img = canvas(n, n)
    img[bm] = RED
    _bevel(img, bm, RED_HI, RED_LO)
    return img, bm


def mark_car(n: int) -> np.ndarray:
    import brandkit as bk
    if n == 16:
        img, bm = _red_badge(16)
        art = from_ascii(CAR16, {"W": INK, "w": INK_SHADE, "k": hx("1c1d21"), "d": hx("0b0c0e")})
        a = art[..., 3] > 0
        img[a & bm] = art[a & bm]
        return img
    src = 64 if n >= 64 else 32
    car = bk.render(f"icon_front_{src}_white")
    img, bm = _red_badge(src)
    h, w = car.shape[:2]
    bk.over(img, car, (src - w) // 2, (src - h) // 2 + (2 if src == 64 else 1))
    img[~bm] = 0
    if n > src:
        img = bk.up(img, n // src)
    return img


# ---------------------------------------------------------------- P + stripe
def mark_p(n: int) -> np.ndarray:
    ui = _ui_module()
    k = n / 32.0
    h = max(8, round(17 * k))
    s = max(2, round(4 * k))
    m = ui._wordmark_mask("P", h, s, 0, 0, 3)
    mh, mw = m.shape
    bm = badge_mask(n, max(3, round(6 * k)), 1)
    img = canvas(n, n)
    img[bm] = BG
    rim = bm & ~(shift(bm, 1, 0) & shift(bm, -1, 0) & shift(bm, 0, 1) & shift(bm, 0, -1))
    img[rim] = LINE
    stripe_h = max(2, round(3 * k))
    block = mh + 1 + max(1, round(2 * k)) + stripe_h
    oy = (n - block) // 2
    ox = (n - mw) // 2 + max(1, round(1 * k))
    word = np.zeros((n, n), bool)
    word[oy:oy + mh, ox:ox + mw] = m
    e = shift(word, 1, 1) & ~word
    img[e] = RED_DEEP
    img[word] = INK
    img[word & ~shift(word, 0, 1)] = WHITE
    sy0 = oy + mh + 1 + max(1, round(2 * k))
    stripe = np.zeros_like(word)
    _sheared_rows(stripe, sy0, sy0 + stripe_h, max(2, round(4 * k)) + 2, n - max(3, round(9 * k)), 3)
    _sheared_rows(stripe, sy0, sy0 + stripe_h, max(1, round(1 * k)) + 1, max(2, round(3 * k)) + 1, 3)
    stripe &= bm & ~rim
    img[stripe] = RED
    # chequer
    cell = max(1, round(1.5 * k))
    fx0 = n - max(3, round(9 * k)) + 1
    for r in range(max(2, stripe_h // cell)):
        for c in range(3):
            col = INK if (r + c) % 2 == 0 else CHECK_DARK
            for dy in range(cell):
                y = sy0 + stripe_h - (max(2, stripe_h // cell) - r) * cell + dy
                for dx in range(cell):
                    x = fx0 + c * cell + dx
                    if 0 <= y < n and 0 <= x < n and bm[y, x] and not rim[y, x]:
                        img[y, x] = col
    return img
