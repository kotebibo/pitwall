"""Exports the 3D car render library from brand/renders/_src to brand/renders.

    python tools/brand/renders.py

For each angle and livery: <name>.png (native pixels, transparent, 1 px
outline), <name>_3x.png (3x nearest) and <name>_shadow.png (the soft contact
shadow on its own layer, to put under the car on a backdrop).
"""
from __future__ import annotations

import shutil

import brandkit as bk
from brandkit import load, save, up

OUT = bk.BRAND / "renders"
ANGLES = ("hero", "hero_left", "rear34", "side", "top", "low_front")
LIVERIES = ("red", "white", "purple")


def _crop_both(a, b, pad=2):
    import numpy as np
    m = (a[..., 3] > 0) | (b[..., 3] > 0)
    ys, xs = np.nonzero(m)
    y0, y1 = max(0, ys.min() - pad), min(a.shape[0], ys.max() + 1 + pad)
    x0, x1 = max(0, xs.min() - pad), min(a.shape[1], xs.max() + 1 + pad)
    return a[y0:y1, x0:x1].copy(), b[y0:y1, x0:x1].copy()


def build():
    out = []
    for a in ANGLES:
        for c in LIVERIES:
            name = f"car_{a}_{c}"
            src = bk.RENDERS / f"{name}.png"
            if not src.exists():
                continue
            car = load(src)
            sh = load(bk.RENDERS / f"{name}_shadow.png")
            # car and shadow share one crop box, so the two layers stack aligned
            img, shadow = _crop_both(car, sh, pad=2)
            save(img, OUT / f"{name}.png")
            save(up(img, 3), OUT / f"{name}_3x.png")
            save(shadow, OUT / f"{name}_shadow.png")
            out += [f"{name}.png", f"{name}_3x.png", f"{name}_shadow.png"]
    return out


if __name__ == "__main__":
    for n in build():
        print("wrote", OUT / n)
