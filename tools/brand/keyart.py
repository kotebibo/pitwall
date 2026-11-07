"""Title key art and boot splash.

    python tools/brand/keyart.py

Writes brand/keyart/. The key art is drawn at the game's own resolution
(640 x 360, the viewport size) and scaled 3x to 1920 x 1080, so it can also be
dropped into the game pixel for pixel (title_keyart_640x360*.png).
"""
from __future__ import annotations

import numpy as np

import backdrop as bd
import brandkit as bk
from brandkit import BG, INK_2, canvas, over, save_rgb, text_img, up, wordmark

OUT = bk.BRAND / "keyart"


def keyart_scene() -> np.ndarray:
    W, H = 640, 360
    img, cam = bd.scene(W, H, "asset_keyart", 412, 198, R=36.0, turn=-1, kerb_side=-1, half=7.0,
                        pools=[((0.4, 0.0), 7.5, 1.05), ((-15, -3), 9.0, 0.6), ((15, 5), 8.0, 0.45),
                               ((-6, -14), 7.0, 0.35)], gain=3.0, seed=7, finish=-4.6)
    # floodlight spill from the top right, then quiet the left third for menu text
    bd.lighten(img, 660, -30, 330, (255, 226, 170), amount=0.16)
    bd.darken_left(img, 30, 300, amount=0.6)
    bd.vignette(img, strength=0.5, start=0.8)
    return img


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    out = {}
    clean = keyart_scene()
    logo = clean.copy()
    over(logo, wordmark("color"), 24, 22)
    out["title_keyart_1920x1080.png"] = up(logo, 3)
    out["title_keyart_nologo_1920x1080.png"] = up(clean, 3)
    out["title_keyart_640x360.png"] = logo
    out["title_keyart_nologo_640x360.png"] = clean
    # boot splash: wordmark centred on the background, at the game's 2x window scale
    sp = canvas(640, 360, BG)
    wm = wordmark("color")
    over(sp, wm, (640 - wm.shape[1]) // 2, (360 - wm.shape[0]) // 2 - 4)
    out["boot_splash_1280x720.png"] = up(sp, 2)
    for name, img in out.items():
        save_rgb(img, OUT / name)
    return out


if __name__ == "__main__":
    for n in build():
        print("wrote", OUT / n)
