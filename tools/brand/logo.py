"""Logo system: wordmark, stacked lockup, tagline lockup, icon marks, loading logos.

    python tools/brand/logo.py

Writes brand/logo/. Every file is drawn at 1x on the pixel grid and scaled by
whole numbers with nearest filtering only.
"""
from __future__ import annotations

import numpy as np

import brandkit as bk
from brandkit import (BG, BLACK, CHECK_DARK, INK, INK_2, INK_SHADE, RED, RED_DEEP, RED_HI, RED_LO, WHITE, canvas,
                      outline_mask, over, save, shift, text_mask, trim, up)
import marks

OUT = bk.BRAND / "logo"
TAGLINE = "DRIVE IT. RUN IT. PROVE IT."
SCALES = (1, 2, 4, 8)


# ---------------------------------------------------------------- layer rendering
def draw(L: dict, mode: str = "color") -> np.ndarray:
    """Render a lockup's masks. mode: color | white | black | red | flat."""
    h, w = L["word"].shape
    img = canvas(w, h)
    if mode in ("white", "black", "red"):
        c = {"white": INK, "black": BG, "red": RED}[mode]
        for k in ("word", "stripe", "flag_light", "text"):
            if k in L:
                img[L[k]] = c
        return trim(img)
    img[L["ext"]] = RED_DEEP
    img[L["word"]] = INK
    lower = L.get("word_lower")
    if lower is not None:
        img[lower] = INK_SHADE
    img[L["word"] & ~shift(L["word"], 0, 1)] = WHITE
    st = L["stripe"]
    img[st] = RED
    img[st & ~shift(st, 0, 1)] = RED_HI
    img[st & ~shift(st, 0, -1)] = RED_LO
    img[L["flag_light"]] = INK
    img[L["flag_dark"]] = CHECK_DARK
    if "text" in L:
        img[L["text"]] = L.get("text_color", INK_2)
    if mode == "color":
        sil = img[..., 3] > 0
        if "text" in L:
            sil &= ~dilate_text(L)
        img[outline_mask(sil) & ~L.get("text", np.zeros_like(sil))] = BLACK
    return trim(img)


def dilate_text(L):
    from pixel import dilate
    return dilate(L["text"]) & ~(L["word"] | L["stripe"] | L["ext"] | L["flag_light"] | L["flag_dark"])


def _sheared_rows(mask, y0, y1, a, b, shear=3):
    for y in range(y0, y1):
        off = (y1 - 1 - y) // shear
        mask[y, max(0, a + off):max(0, b + off)] = True


def _tight(m):
    xs = np.nonzero(m.any(axis=0))[0]
    return m[:, xs.min():xs.max() + 1]


# ---------------------------------------------------------------- stacked
def stacked_layers(h=32, s=6, gap=3, line_gap=6):
    ui = bk._ui_module()
    pit = _tight(ui._wordmark_mask("PIT", h, s, gap, 10, 3))
    wall = _tight(ui._wordmark_mask("WALL", h, s, gap, 10, 3))
    W = wall.shape[1] + 40
    H = 2 * h + line_gap + 24
    x0, y0 = 22, 3
    word = np.zeros((H, W), bool)
    # PIT centred over WALL along the italic axis
    shx = (h + line_gap) // 3
    core_w = wall.shape[1] - (h - 1) // 3
    core_p = pit.shape[1] - (h - 1) // 3
    px = x0 + shx + (core_w - core_p) // 2
    word[y0:y0 + h, px:px + pit.shape[1]] = pit
    word[y0 + h + line_gap:y0 + 2 * h + line_gap, x0:x0 + wall.shape[1]] = wall
    ext = np.zeros_like(word)
    for k in (1, 2):
        ext |= shift(word, k, k)
    ext &= ~word
    lower = np.zeros_like(word)
    for yy in (y0, y0 + h + line_gap):
        lower[yy + int(h * 0.62):yy + h] = True
    # stripe under WALL, with the wordmark's two dashes and chequer block
    sy0 = y0 + 2 * h + line_gap + 3
    sh = 5
    stripe = np.zeros_like(word)
    x_start = x0 + 4
    x_end = x0 + core_w - 12 - 4
    _sheared_rows(stripe, sy0, sy0 + sh, x_start, x_end)
    _sheared_rows(stripe, sy0, sy0 + sh, x_start - 12, x_start - 4)
    _sheared_rows(stripe, sy0, sy0 + sh, x_start - 19, x_start - 15)
    fl, fd = np.zeros_like(word), np.zeros_like(word)
    fx0 = x_end + 3
    for r in range(2):
        for c in range(4):
            tgt = fl if (r + c) % 2 == 0 else fd
            for dy in range(3):
                y = sy0 + sh - 6 + r * 3 + dy
                off = (sy0 + sh - 1 - y) // 3
                for dx in range(3):
                    tgt[y, fx0 + c * 3 + dx + off] = True
    L = {"word": word, "ext": ext, "stripe": stripe, "flag_light": fl, "flag_dark": fd,
         "word_lower": word & lower}
    allm = word | ext | stripe | fl | fd
    ys, xs = np.nonzero(allm)
    y_0, y_1, x_0, x_1 = ys.min() - 1, ys.max() + 2, xs.min() - 1, xs.max() + 2
    return {k: v[y_0:y_1, x_0:x_1] for k, v in L.items()}


# ---------------------------------------------------------------- tagline lockup
def tagline_layers(text=TAGLINE, gap=6):
    """The wordmark with the tagline set under it in Pixelify Sans (the game's
    UI font, 7 px caps), centred on the lockup's full width."""
    W = bk.wordmark_layers()
    t = text_mask(text, 11, 1)
    t = t[:, np.nonzero(t.any(axis=0))[0].min():]
    wh, ww = W["word"].shape
    th, tw = t.shape
    tx = max(0, (ww - tw) // 2)
    H = wh + gap + th + 1
    Wd = max(ww, tx + tw + 1)
    L = {}
    for k, v in W.items():
        m = np.zeros((H, Wd), bool)
        m[:wh, :ww] = v
        L[k] = m
    tm = np.zeros((H, Wd), bool)
    tm[wh + gap - 1:wh + gap - 1 + th, tx:tx + tw] = t
    L["text"] = tm
    return L


# ---------------------------------------------------------------- build
def build():
    OUT.mkdir(parents=True, exist_ok=True)
    out = {}
    # wordmark
    wm = bk.wordmark_layers()
    for mode, suffix in (("color", ""), ("white", "_white"), ("black", "_black")):
        img = draw(wm, mode)
        for k in SCALES:
            out[f"logo_wordmark{suffix}_{k}x.png"] = up(img, k)
    out["logo_wordmark_small_1x.png"] = draw(bk.wordmark_layers(h=14, s=3, gap=2, word_gap=5, small=True))
    out["logo_wordmark_small_2x.png"] = up(out["logo_wordmark_small_1x.png"], 2)
    # stacked
    st = stacked_layers()
    for mode, suffix in (("color", ""), ("white", "_white"), ("black", "_black")):
        img = draw(st, mode)
        for k in SCALES:
            out[f"logo_stacked{suffix}_{k}x.png"] = up(img, k)
    # tagline lockup
    tl = tagline_layers()
    tl_c = dict(tl)
    tl_c["text_color"] = INK_2
    for mode, suffix in (("color", ""), ("white", "_white"), ("black", "_black")):
        img = draw(tl_c, mode)
        for k in (1, 2, 4):
            out[f"logo_tagline{suffix}_{k}x.png"] = up(img, k)
    # marks: primary (PW) and the two alternates
    for n in (16, 24, 32, 48, 64, 128):
        out[f"logo_mark_{n}.png"] = marks.mark_pw(n)
    out["logo_mark_256.png"] = up(marks.mark_pw(64), 4)
    out["logo_mark_512.png"] = up(marks.mark_pw(64), 8)
    out["logo_mark_1024.png"] = up(marks.mark_pw(128), 8)
    for n in (16, 32, 64):
        out[f"logo_mark_alt1_car_{n}.png"] = marks.mark_car(n)
        out[f"logo_mark_alt2_p_{n}.png"] = marks.mark_p(n)
    out["logo_mark_alt1_car_512.png"] = up(marks.mark_car(64), 8)
    out["logo_mark_alt2_p_512.png"] = up(marks.mark_p(64), 8)
    # loading screen
    out["loading_logo.png"] = _pad_to(up(draw(wm, "color"), 2), 384, 96, align=2)
    out["loading_logo_128.png"] = up(marks.mark_pw(64), 2)
    for name, img in out.items():
        save(img, OUT / name)
    return out


def _pad_to(img, W, H, align=1):
    """Centre on a transparent W x H canvas; offsets snapped to `align` so a
    2x image stays on the 2x pixel grid."""
    c = canvas(W, H)
    h, w = img.shape[:2]
    if w > W or h > H:
        raise ValueError(f"{w}x{h} does not fit {W}x{H}")
    x, y = (W - w) // 2 // align * align, (H - h) // 2 // align * align
    over(c, img, x, y)
    return c


if __name__ == "__main__":
    for n in build():
        print("wrote", OUT / n)
