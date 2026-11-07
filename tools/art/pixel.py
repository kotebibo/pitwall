"""Shared helpers for the Pit Wall pixel-art generators.

Everything works on numpy RGBA arrays (H, W, 4) of uint8. Images are small, so
clarity beats speed. Every random choice is seeded so the art is reproducible:

    python tools/art/build_all.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SPRITES = ROOT / "game" / "assets" / "sprites"

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------


def hx(h: str, a: int = 255) -> tuple[int, int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


UI = {
    "bg": hx("141518"),
    "panel": hx("1d1f23"),
    "line": hx("34363c"),
    "line2": hx("4a4c54"),
    "ink": hx("f1efea"),
    "ink2": hx("a3a3ad"),
    "ink3": hx("6e6f78"),
    "red": hx("e8352b"),
    "yellow": hx("f2c230"),
    "blue": hx("5ec8e5"),
    "green": hx("3ecf6a"),
    "purple": hx("a855f7"),
}

CLEAR = (0, 0, 0, 0)
SHADOW = (0, 0, 0, 102)  # the one shadow tone: black at 40 %

# Kerb / paint ramps (hue shifted: warm lights, cool darks)
RED_RAMP = [hx("7a1a26"), hx("a8242a"), hx("d23129"), hx("e8352b"), hx("f2603f")]
WHITE_RAMP = [hx("8e909a"), hx("b7b8bf"), hx("dcdad4"), hx("ebe8e1"), hx("f8f5ec")]
STEEL_RAMP = [hx("3d414b"), hx("5d626d"), hx("8a909b"), hx("b9bec6"), hx("e2e0da")]
CONCRETE = [hx("2c2e34"), hx("3e4148"), hx("555960"), hx("6f727a"), hx("8d8f94"), hx("a9a8a5")]


def mix(a, b, t: float):
    a = [int(v) for v in a]
    b = [int(v) for v in b]
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(4))


def with_alpha(c, a: int):
    return (c[0], c[1], c[2], a)


# --------------------------------------------------------------------------
# Canvas helpers
# --------------------------------------------------------------------------


def canvas(w: int, h: int, color=CLEAR) -> np.ndarray:
    a = np.zeros((h, w, 4), np.uint8)
    a[:, :] = color
    return a


def save(arr: np.ndarray, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path)
    return path


def load(path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGBA"))


def px(a: np.ndarray, x: int, y: int, c, wrap: bool = False):
    h, w = a.shape[:2]
    if wrap:
        x %= w
        y %= h
    elif not (0 <= x < w and 0 <= y < h):
        return
    a[y, x] = c


def rect(a, x0, y0, x1, y1, c, wrap=False):
    """Filled rectangle, x1/y1 exclusive."""
    if wrap:
        for y in range(y0, y1):
            for x in range(x0, x1):
                px(a, x, y, c, True)
        return
    h, w = a.shape[:2]
    x0c, x1c = max(0, x0), min(w, x1)
    y0c, y1c = max(0, y0), min(h, y1)
    if x0c < x1c and y0c < y1c:
        a[y0c:y1c, x0c:x1c] = c


def hline(a, x0, x1, y, c, wrap=False):
    rect(a, x0, y, x1, y + 1, c, wrap)


def vline(a, x, y0, y1, c, wrap=False):
    rect(a, x, y0, x + 1, y1, c, wrap)


def blend(dst: np.ndarray, src: np.ndarray, x: int = 0, y: int = 0, wrap: bool = False):
    """Alpha-composite src over dst at (x, y)."""
    sh, sw = src.shape[:2]
    dh, dw = dst.shape[:2]
    if wrap:
        ys = (np.arange(sh) + y) % dh
        xs = (np.arange(sw) + x) % dw
        region = dst[np.ix_(ys, xs)]
        out = _over(region, src)
        dst[np.ix_(ys, xs)] = out
        return dst
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dw, x + sw), min(dh, y + sh)
    if x0 >= x1 or y0 >= y1:
        return dst
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    dst[y0:y1, x0:x1] = _over(dst[y0:y1, x0:x1], s)
    return dst


def _over(d: np.ndarray, s: np.ndarray) -> np.ndarray:
    sa = s[..., 3:4].astype(np.float32) / 255.0
    da = d[..., 3:4].astype(np.float32) / 255.0
    oa = sa + da * (1 - sa)
    rgb = (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    out = np.concatenate([rgb, oa * 255.0], axis=-1)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def paint_mask(a: np.ndarray, mask: np.ndarray, c):
    a[mask] = c


def scale(a: np.ndarray, k: int) -> np.ndarray:
    return np.repeat(np.repeat(a, k, axis=0), k, axis=1)


def tile(a: np.ndarray, nx: int, ny: int) -> np.ndarray:
    return np.tile(a, (ny, nx, 1))


def flip_h(a):
    return a[:, ::-1].copy()


# --------------------------------------------------------------------------
# Masks, outlines, shadows
# --------------------------------------------------------------------------


def alpha_mask(a: np.ndarray, thresh: int = 0) -> np.ndarray:
    return a[..., 3] > thresh


def shift(mask: np.ndarray, dx: int, dy: int, wrap=False) -> np.ndarray:
    if wrap:
        return np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    out = np.zeros_like(mask)
    h, w = mask.shape[:2]
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = mask[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def dilate(mask, wrap=False, diag=False):
    m = mask.copy()
    offs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if diag:
        offs += [(1, 1), (-1, -1), (1, -1), (-1, 1)]
    for dx, dy in offs:
        m |= shift(mask, dx, dy, wrap)
    return m


def erode(mask, wrap=False):
    m = mask.copy()
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        m &= shift(mask, dx, dy, wrap)
    return m


def outline(a: np.ndarray, dark, light=None, wrap=False) -> np.ndarray:
    """Selective 1px outline: transparent pixels touching the sprite get `dark`;
    if `light` is given, outline pixels on the lit (top/left) side use it."""
    m = alpha_mask(a, 127)
    ring = dilate(m, wrap) & ~m
    out = a.copy()
    out[ring] = dark
    if light is not None:
        # pixel is on the lit side if the sprite is to its right or below it
        lit = ring & (shift(m, -1, 0, wrap) | shift(m, 0, -1, wrap)) & ~(shift(m, 1, 0, wrap) | shift(m, 0, 1, wrap))
        out[lit] = light
    return out


def inner_outline(a: np.ndarray, dark, light=None):
    """Recolour the sprite's own edge pixels (keeps the silhouette size)."""
    m = alpha_mask(a, 127)
    edge = m & ~erode(m)
    out = a.copy()
    out[edge] = dark
    if light is not None:
        lit = edge & (~shift(m, 1, 0) | ~shift(m, 0, 1)) & shift(m, -1, 0) & shift(m, 0, -1)
        out[lit] = light
    return out


def drop_shadow(a: np.ndarray, dx: int, dy: int, color=SHADOW, wrap=False) -> np.ndarray:
    """Return a copy with a single-tone shadow of the silhouette behind it."""
    m = alpha_mask(a, 127)
    sm = shift(m, dx, dy, wrap) & ~m
    out = a.copy()
    out[sm] = color
    return out


def shadow_only(a: np.ndarray, dx: int = 0, dy: int = 0, color=SHADOW) -> np.ndarray:
    m = shift(alpha_mask(a, 127), dx, dy)
    out = canvas(a.shape[1], a.shape[0])
    out[m] = color
    return out


# --------------------------------------------------------------------------
# Noise (tileable) and dithering
# --------------------------------------------------------------------------

BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16.0 + 1 / 32
BAYER2 = np.array([[0, 2], [3, 1]], np.float32) / 4.0 + 1 / 8


def bayer(w: int, h: int, n: int = 4) -> np.ndarray:
    m = BAYER4 if n == 4 else BAYER2
    return np.tile(m, (h // m.shape[0] + 1, w // m.shape[1] + 1))[:h, :w]


def value_noise(w: int, h: int, cell: int, seed: int) -> np.ndarray:
    """Tileable smooth value noise in [0, 1]. w and h must be multiples of cell."""
    rng = np.random.default_rng(seed)
    gx, gy = max(1, w // cell), max(1, h // cell)
    lat = rng.random((gy, gx))
    ys = np.arange(h) / cell
    xs = np.arange(w) / cell
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = ys - y0
    fx = xs - x0
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    y0m, y1m = y0 % gy, (y0 + 1) % gy
    x0m, x1m = x0 % gx, (x0 + 1) % gx
    a = lat[np.ix_(y0m, x0m)]
    b = lat[np.ix_(y0m, x1m)]
    c = lat[np.ix_(y1m, x0m)]
    d = lat[np.ix_(y1m, x1m)]
    top = a + (b - a) * fx[None, :]
    bot = c + (d - c) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def fbm(w, h, cells, weights, seed):
    acc = np.zeros((h, w))
    tot = 0.0
    for i, (c, wt) in enumerate(zip(cells, weights)):
        acc += value_noise(w, h, c, seed + i * 101) * wt
        tot += wt
    acc /= tot
    lo, hi = acc.min(), acc.max()
    return (acc - lo) / max(hi - lo, 1e-9)


def quantize(field: np.ndarray, levels: int, dither: float = 1.0, n: int = 4) -> np.ndarray:
    """Field in [0,1] -> int levels 0..levels-1 with ordered dithering at the steps."""
    h, w = field.shape
    t = (bayer(w, h, n) - 0.5) * dither
    q = np.floor(field * levels + t)
    return np.clip(q, 0, levels - 1).astype(int)


def clean_orphans(idx: np.ndarray, wrap=True, passes: int = 1) -> np.ndarray:
    """Pixels whose 4 neighbours all share one other value take that value."""
    out = idx.copy()
    for _ in range(passes):
        n = [np.roll(out, 1, 0), np.roll(out, -1, 0), np.roll(out, 1, 1), np.roll(out, -1, 1)]
        same = (n[0] == n[1]) & (n[1] == n[2]) & (n[2] == n[3]) & (n[0] != out)
        if not wrap:
            same[0, :] = same[-1, :] = False
            same[:, 0] = same[:, -1] = False
        out = np.where(same, n[0], out)
    return out


def palette_map(idx: np.ndarray, pal) -> np.ndarray:
    pal = np.array(pal, np.uint8)
    return pal[np.clip(idx, 0, len(pal) - 1)]


# --------------------------------------------------------------------------
# Height-field shading (light from the top-left, slightly above)
# --------------------------------------------------------------------------

LIGHT = np.array([-0.62, -0.62, 0.48])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def shade_height(hf: np.ndarray, strength: float = 1.0, light=LIGHT) -> np.ndarray:
    gy, gx = np.gradient(hf * strength)
    nx, ny, nz = -gx, -gy, np.ones_like(hf)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx * light[0] + ny * light[1] + nz * light[2]) / ln


def disc_mask(w, h, cx, cy, r) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    return (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r


def ellipse_mask(w, h, cx, cy, rx, ry) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    return ((xx + 0.5 - cx) / rx) ** 2 + ((yy + 0.5 - cy) / ry) ** 2 <= 1.0


def polygon_mask(w, h, pts, ss: int = 1, thresh: float = 0.5) -> np.ndarray:
    """Rasterise a polygon (pixel centres inside). ss>1 supersamples, majority vote."""
    from PIL import ImageDraw

    im = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(im).polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    m = np.array(im) > 0
    if ss > 1:
        m = m.reshape(h, ss, w, ss).mean(axis=(1, 3)) >= thresh
    return m


# --------------------------------------------------------------------------
# Tiny pixel font (5 px tall, variable width)
# --------------------------------------------------------------------------

_GLYPHS = {
    "A": [".##.", "#..#", "####", "#..#", "#..#"],
    "B": ["###.", "#..#", "###.", "#..#", "###."],
    "C": [".###", "#...", "#...", "#...", ".###"],
    "D": ["###.", "#..#", "#..#", "#..#", "###."],
    "E": ["####", "#...", "###.", "#...", "####"],
    "F": ["####", "#...", "###.", "#...", "#..."],
    "G": [".###", "#...", "#.##", "#..#", ".###"],
    "H": ["#..#", "#..#", "####", "#..#", "#..#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"],
    "J": ["...#", "...#", "...#", "#..#", ".##."],
    "K": ["#..#", "#.#.", "##..", "#.#.", "#..#"],
    "L": ["#...", "#...", "#...", "#...", "####"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
    "N": ["#..#", "##.#", "#.##", "#..#", "#..#"],
    "O": [".##.", "#..#", "#..#", "#..#", ".##."],
    "P": ["###.", "#..#", "###.", "#...", "#..."],
    "Q": [".##.", "#..#", "#..#", "#.#.", ".#.#"],
    "R": ["###.", "#..#", "###.", "#.#.", "#..#"],
    "S": [".###", "#...", ".##.", "...#", "###."],
    "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#..#", "#..#", "#..#", "#..#", ".##."],
    "V": ["#...#", "#...#", ".#.#.", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"],
    "X": ["#..#", "#..#", ".##.", "#..#", "#..#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."],
    "Z": ["####", "...#", ".##.", "#...", "####"],
    "0": [".##.", "#..#", "#..#", "#..#", ".##."],
    "1": [".#", "##", ".#", ".#", ".#"],
    "2": ["###.", "...#", ".##.", "#...", "####"],
    "3": ["###.", "...#", ".##.", "...#", "###."],
    "4": ["#..#", "#..#", "####", "...#", "...#"],
    "5": ["####", "#...", "###.", "...#", "###."],
    "6": [".##.", "#...", "###.", "#..#", ".##."],
    "7": ["####", "...#", "..#.", ".#..", ".#.."],
    "8": [".##.", "#..#", ".##.", "#..#", ".##."],
    "9": [".##.", "#..#", ".###", "...#", ".##."],
    " ": ["..", "..", "..", "..", ".."],
    "-": ["...", "...", "###", "...", "..."],
    ".": [".", ".", ".", ".", "#"],
    ",": ["..", "..", "..", ".#", "#."],
    ":": [".", "#", ".", "#", "."],
    "/": ["...#", "..#.", ".#..", "#...", "...."],
    "_": ["....", "....", "....", "....", "####"],
    "x": ["...", "...", "#.#", ".#.", "#.#"],
    "(": [".#", "#.", "#.", "#.", ".#"],
    ")": ["#.", ".#", ".#", ".#", "#."],
    "+": ["...", ".#.", "###", ".#.", "..."],
    "%": ["#..#", "..#.", ".#..", "#..#", "...."],
    "!": ["#", "#", "#", ".", "#"],
    "'": ["#", "#", ".", ".", "."],
    "&": [".#..", "#.#.", ".#.#", "#.#.", ".#.#"],
}


def text_width(s: str, spacing: int = 1) -> int:
    w = 0
    for ch in s:
        g = _GLYPHS.get(ch.upper() if ch.upper() in _GLYPHS else ch, _GLYPHS[" "])
        w += len(g[0]) + spacing
    return max(0, w - spacing)


def draw_text(a: np.ndarray, x: int, y: int, s: str, c, spacing: int = 1, shadow=None):
    cx = x
    for ch in s:
        key = ch if ch in _GLYPHS else ch.upper()
        g = _GLYPHS.get(key, _GLYPHS[" "])
        for gy, row in enumerate(g):
            for gx, v in enumerate(row):
                if v == "#":
                    if shadow is not None:
                        px(a, cx + gx + 1, y + gy + 1, shadow)
                    px(a, cx + gx, y + gy, c)
        cx += len(g[0]) + spacing
    return cx


def text_image(s: str, c, spacing: int = 1, pad: int = 0) -> np.ndarray:
    w = text_width(s, spacing) + pad * 2
    img = canvas(w, 5 + pad * 2)
    draw_text(img, pad, pad, s, c, spacing)
    return img


def from_ascii(rows: list[str], colors: dict) -> np.ndarray:
    h, w = len(rows), max(len(r) for r in rows)
    a = canvas(w, h)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in colors:
                a[y, x] = colors[ch]
    return a


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def poisson_torus(w, h, r, seed, k=30, max_pts=100000):
    """Bridson poisson disk on a torus (for tileable scatter)."""
    g = rng(seed)
    cell = r / math.sqrt(2)
    gw, gh = int(math.ceil(w / cell)), int(math.ceil(h / cell))
    grid = -np.ones((gh, gw), int)
    pts = []
    active = []

    def fits(p):
        gx, gy = int(p[0] / cell), int(p[1] / cell)
        for yy in range(gy - 2, gy + 3):
            for xx in range(gx - 2, gx + 3):
                i = grid[yy % gh, xx % gw]
                if i >= 0:
                    q = pts[i]
                    dx = abs(q[0] - p[0])
                    dy = abs(q[1] - p[1])
                    dx = min(dx, w - dx)
                    dy = min(dy, h - dy)
                    if dx * dx + dy * dy < r * r:
                        return False
        return True

    p0 = (g.random() * w, g.random() * h)
    pts.append(p0)
    grid[int(p0[1] / cell) % gh, int(p0[0] / cell) % gw] = 0
    active.append(0)
    while active and len(pts) < max_pts:
        i = active[int(g.random() * len(active))]
        base = pts[i]
        found = False
        for _ in range(k):
            ang = g.random() * 2 * math.pi
            rad = r * (1 + g.random())
            p = ((base[0] + rad * math.cos(ang)) % w, (base[1] + rad * math.sin(ang)) % h)
            if fits(p):
                pts.append(p)
                grid[int(p[1] / cell) % gh, int(p[0] / cell) % gw] = len(pts) - 1
                active.append(len(pts) - 1)
                found = True
                break
        if not found:
            active.remove(i)
    return pts
