"""Social images: link preview (Open Graph), X and Discord banners, YouTube thumbnail.

    python tools/brand/social.py

Writes brand/social/. Each image is drawn on a small native canvas (the 3D car
rendered at that exact pixel density, the ground ray-cast through the same
camera) and scaled 3x or 4x with nearest filtering.
"""
from __future__ import annotations

import numpy as np

import backdrop as bd
import brandkit as bk
from brandkit import (BG, BLACK, GREEN, INK, INK_2, INK_3, LINE, PANEL, RED, RED_DEEP, canvas, fit_up, load, over,
                      save_rgb, style_letters, display_mask, text_img, up, wordmark)

OUT = bk.BRAND / "social"
UI = bk.SPRITES / "ui"
TAGLINE = "DRIVE IT. RUN IT. PROVE IT."


def icon(name: str, color) -> np.ndarray:
    a = load(UI / f"icon_{name}.png")
    out = a.copy()
    m = a[..., 3] > 0
    # the game icons are white/grey; tint by brightness
    k = a[..., :3].max(axis=-1, keepdims=True).astype(np.float32) / 255.0
    out[..., :3] = np.clip(np.array(color[:3], np.float32) * (0.35 + 0.65 * k), 0, 255).astype(np.uint8)
    out[~m] = 0
    return out


def nine(name: str, w: int, h: int, margin: int = 8) -> np.ndarray:
    """9-slice one of the game's panel sprites to w x h (edges tiled, no scaling)."""
    src = load(UI / f"{name}.png")
    S = src.shape[0]
    m = margin
    out = canvas(w, h)
    mid = src[m:S - m, m:S - m]
    for y in range(m, h - m, S - 2 * m):
        for x in range(m, w - m, S - 2 * m):
            over(out, mid[:min(S - 2 * m, h - m - y), :min(S - 2 * m, w - m - x)], x, y)
    for x in range(m, w - m, S - 2 * m):
        ww = min(S - 2 * m, w - m - x)
        out[0:m, x:x + ww] = src[0:m, m:m + ww]
        out[h - m:h, x:x + ww] = src[S - m:S, m:m + ww]
    for y in range(m, h - m, S - 2 * m):
        hh = min(S - 2 * m, h - m - y)
        out[y:y + hh, 0:m] = src[m:m + hh, 0:m]
        out[y:y + hh, w - m:w] = src[m:m + hh, S - m:S]
    out[0:m, 0:m] = src[0:m, 0:m]
    out[0:m, w - m:w] = src[0:m, S - m:S]
    out[h - m:h, 0:m] = src[S - m:S, 0:m]
    out[h - m:h, w - m:w] = src[S - m:S, S - m:S]
    return out


def chip(icon_name: str, text: str, icon_color, text_color=INK, panel="panel") -> np.ndarray:
    ic = icon(icon_name, icon_color)
    t = text_img(text, text_color)
    w = 6 + ic.shape[1] + 4 + t.shape[1] + 8
    h = 24
    c = nine(panel, w, h)
    over(c, ic, 5, (h - ic.shape[0]) // 2)
    over(c, t, 6 + ic.shape[1] + 4, (h - t.shape[0]) // 2 + 1)
    return c


def lines(texts, colors, gap=5) -> np.ndarray:
    imgs = [text_img(t, c, shadow=BLACK) for t, c in zip(texts, colors)]
    W = max(i.shape[1] for i in imgs)
    H = sum(i.shape[0] for i in imgs) + gap * (len(imgs) - 1)
    out = canvas(W, H)
    y = 0
    for i in imgs:
        over(out, i, 0, y)
        y += i.shape[0] + gap
    return out


# ---------------------------------------------------------------- Open Graph 1200 x 630
def og() -> np.ndarray:
    W, H = 400, 210
    img, cam = bd.scene(W, H, "asset_og", 284, 116, R=30.0, turn=-1, kerb_side=-1, half=7.0, gain=3.0,
                        seed=11, finish=-4.6)
    bd.darken_left(img, 10, 230, amount=0.62)
    bd.vignette(img, strength=0.5, start=0.85)
    over(img, wordmark("color"), 20, 26)
    tl = lines(["The F1 team game where you drive.", "Every lap verified on Solana."], [INK, INK_2], gap=6)
    over(img, tl, 26, 84)
    ch = chip("chain", "LAPS ON-CHAIN", GREEN, INK)
    over(img, ch, 24, 150)
    return fit_up(img, 3, 1200, 630)


# ---------------------------------------------------------------- X banner 1500 x 500
def x_banner() -> np.ndarray:
    W, H = 500, 167
    img, cam = bd.scene(W, H, "asset_xbanner", 392, 84, R=30.0, turn=-1, kerb_side=-1, half=7.0, gain=3.0,
                        seed=12, finish=-4.6)
    bd.darken_left(img, 60, 330, amount=0.6)
    bd.vignette(img, strength=0.45, start=0.85, aspect=0.5)
    wm = wordmark("color")
    x0 = 150
    over(img, wm, x0, 30)
    t = text_img(TAGLINE, INK_2, shadow=BLACK)
    over(img, t, x0 + (wm.shape[1] - t.shape[1]) // 2, 30 + wm.shape[0] + 7)
    return fit_up(img, 3, 1500, 500)


# ---------------------------------------------------------------- Discord 960 x 540
def discord() -> np.ndarray:
    W, H = 320, 180
    img, cam = bd.scene(W, H, "asset_discord", 222, 104, R=30.0, turn=-1, kerb_side=-1, half=7.0, gain=3.0,
                        seed=13, finish=-4.6)
    bd.darken_left(img, 10, 200, amount=0.6)
    bd.vignette(img, strength=0.5, start=0.8)
    wm = wordmark("color")
    over(img, wm, 14, 18)
    t = text_img(TAGLINE, INK_2, shadow=BLACK)
    over(img, t, 22, 18 + wm.shape[0] + 6)
    return up(img, 3)


# ---------------------------------------------------------------- YouTube 1280 x 720
def yt_thumb() -> np.ndarray:
    W, H = 320, 180
    img, cam = bd.scene(W, H, "asset_ytthumb", 212, 122, R=26.0, turn=-1, kerb_side=-1, half=7.0, gain=3.1,
                        seed=14, finish=-5.0, speed_lines=True, sky=lambda im, hit: bd.horizon(
                            im, hit, seed=5, towers=((0.76, 30), (0.96, 26)), stand=(0.36, 1.0)))
    bd.darken_left(img, 0, 150, amount=0.5)
    bd.vignette(img, strength=0.5, start=0.8)
    wm = wordmark("color")
    over(img, wm, 8, 10)
    hook = style_letters(display_mask("F1 + SOLANA", 22, 5, 7, 3, space=7), ext=2, ext_c=RED_DEEP)
    over(img, hook, 12, 10 + wm.shape[0] + 6)
    return up(img, 4)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    out = {
        "og_image_1200x630.png": og(),
        "x_banner_1500x500.png": x_banner(),
        "discord_banner_960x540.png": discord(),
        "youtube_thumb_1280x720.png": yt_thumb(),
    }
    for name, img in out.items():
        save_rgb(img, OUT / name)
    return out


if __name__ == "__main__":
    for n, im in build().items():
        print("wrote", OUT / n, im.shape[1], "x", im.shape[0])
