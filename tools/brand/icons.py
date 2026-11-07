"""Favicons, app icons and profile pictures, all from the PW mark.

    python tools/brand/icons.py

Writes brand/icons/ (favicons, app icons) and brand/social/avatar_*.png. Every size is drawn on its own pixel grid (hand-placed
at 16/24/32, built from the wordmark glyphs above that) and scaled by whole
numbers only.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

import backdrop as bd
import brandkit as bk
from brandkit import BG, RED, canvas, over, save, save_rgb, up
import marks

OUT = bk.BRAND / "icons"
SOCIAL = bk.BRAND / "social"


def circle_mask(n):
    yy, xx = np.mgrid[0:n, 0:n]
    return ((xx + 0.5 - n / 2) ** 2 + (yy + 0.5 - n / 2) ** 2) <= (n / 2) ** 2


def avatar_car(native: int, render: str) -> np.ndarray:
    """The 3D car, nose toward the viewer, on a dark night-track square; the
    car is kept inside the inscribed circle."""
    img, cam = bd.scene(native, native, render, native * 0.5, native * 0.5, R=24.0, turn=-1,
                        kerb_side=-1, half=7.0, speed_lines=False, trails=True, finish=-4.2,
                        pools=[((0.3, 0.0), 6.0, 1.15)], gain=3.0, seed=4)
    bd.vignette(img, strength=0.6, start=0.6, aspect=1.0)
    return img


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    out = {}
    out["favicon_16.png"] = marks.mark_pw(16)
    out["favicon_32.png"] = marks.mark_pw(32)
    out["favicon_48.png"] = marks.mark_pw(48)
    # app icons: full bleed (the OS rounds the corners); content inside the maskable safe zone
    a64 = marks.mark_pw_fullbleed(64, 46)
    out["app_icon_512.png"] = up(a64, 8)
    out["app_icon_192.png"] = up(a64, 3)
    out["apple_touch_icon_180.png"] = up(marks.mark_pw_fullbleed(60, 44), 3)
    # profile pictures: full-bleed red, PW inside the circle crop
    out["avatar_1024.png"] = up(marks.mark_pw_fullbleed(128, 88), 8)
    out["avatar_400.png"] = up(marks.mark_pw_fullbleed(100, 68), 4)
    # alternate profile picture: the 3D car
    out["avatar_car_1024.png"] = up(avatar_car(256, "asset_avatar_big"), 4)
    out["avatar_car_400.png"] = up(avatar_car(200, "asset_avatar"), 2)
    for name, img in out.items():
        if name.startswith("avatar"):
            save_rgb(img, SOCIAL / name)  # profile pictures live with the social images
        elif name.startswith(("app_icon", "apple")):
            save_rgb(img, OUT / name)
        else:
            save(img, OUT / name)
    # multi-size .ico with the exact hand-drawn frames (no resampling)
    frames = [Image.fromarray(out[f"favicon_{n}.png"], "RGBA") for n in (16, 32, 48)]
    frames[-1].save(OUT / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)],
                    append_images=frames[:-1])
    return out


if __name__ == "__main__":
    for n in build():
        print("wrote", (SOCIAL if n.startswith("avatar") else OUT) / n)
    print("wrote", OUT / "favicon.ico")
