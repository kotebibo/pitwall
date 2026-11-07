"""Renders every 3D car image the brand kit uses, with Godot.

    python tools/brand/render_jobs.py            # all jobs
    python tools/brand/render_jobs.py keyart     # only jobs whose name contains "keyart"

Writes brand/renders/_src/<name>.png (+ _shadow.png, + .json camera) through
game/scenes/car3d/render_brand.gd. Needs a GPU: a Godot window opens briefly.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys

from brandkit import BRAND, RENDERS, ROOT

GODOT = r"D:\dev\tools\godot\Godot_v4.7.2-stable_win64_console.exe"
RED, INK, PURPLE = "e8352b", "f1efea", "a855f7"
PI = math.pi

C_RED = {"primary": RED, "secondary": INK, "compound": "medium"}
C_WHITE = {"primary": INK, "secondary": RED, "compound": "soft"}
C_PURPLE = {"primary": PURPLE, "secondary": INK, "compound": "hard"}

ANGLES = {
    "hero": {"yaw": -0.62, "pitch": 22.0, "steer": 0.14},
    "hero_left": {"yaw": PI + 0.62, "pitch": 22.0, "steer": -0.14},
    "rear34": {"yaw": 0.75, "pitch": 26.0},
    "side": {"yaw": 0.0, "pitch": 4.0},
    "top": {"yaw": PI / 2, "pitch": 90.0},
    "low_front": {"yaw": -1.12, "pitch": 6.0, "persp": True, "dist": 8.0, "steer": 0.2},
}


def j(name, angle=None, colors=C_RED, **kw):
    d = dict(ANGLES[angle]) if angle else {}
    d.update(colors)
    d.update(kw)
    d["name"] = name
    d.setdefault("shadow", True)
    return d


def jobs():
    out = []
    # the library set (brand/renders): five angles in red, two colourways
    for a in ANGLES:
        out.append(j(f"car_{a}_red", a, ppm=60.0))
    for cname, c in (("white", C_WHITE), ("purple", C_PURPLE)):
        for a in ("hero", "hero_left", "rear34", "side"):
            out.append(j(f"car_{a}_{cname}", a, c, ppm=60.0))
    # per-asset renders (exact pixel density for each layout)
    out.append(j("asset_keyart", None, yaw=PI + 0.78, pitch=24.0, steer=-0.16, ppm=74.0))
    out.append(j("asset_og", None, yaw=PI + 0.74, pitch=24.0, steer=-0.16, ppm=40.0))
    out.append(j("asset_xbanner", None, yaw=PI + 0.74, pitch=24.0, steer=-0.16, ppm=34.0))
    out.append(j("asset_discord", None, yaw=PI + 0.74, pitch=24.0, steer=-0.16, ppm=34.0))
    out.append(j("asset_ytthumb", None, yaw=-1.12, pitch=7.0, persp=True, dist=8.0, steer=0.2, ppm=44.0))
    out.append(j("asset_avatar", None, yaw=-1.25, pitch=16.0, steer=0.12, ppm=40.0))
    out.append(j("asset_avatar_big", None, yaw=-1.25, pitch=16.0, steer=0.12, ppm=52.0))
    out.append(j("asset_splash", None, yaw=PI + 0.74, pitch=24.0, steer=-0.16, ppm=30.0))
    # icon sources: the car head-on, small
    out.append(j("icon_front_64_white", None, C_WHITE, yaw=-PI / 2, pitch=10.0, ppm=22.0, margin=1, shadow=False))
    out.append(j("icon_front_32_white", None, C_WHITE, yaw=-PI / 2, pitch=8.0, ppm=12.0, margin=1, shadow=False,
                 outline=False))
    return out


def run(only: str = "") -> None:
    js = [x for x in jobs() if only in x["name"]]
    RENDERS.mkdir(parents=True, exist_ok=True)
    path = RENDERS / "_jobs.json"
    path.write_text(json.dumps(js, indent=1), encoding="utf-8")
    cmd = [GODOT, "--path", str(ROOT / "game"), "-s", "res://scenes/car3d/render_brand.gd", "--",
           f"jobs={path.as_posix()}", f"out={RENDERS.as_posix()}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    for line in r.stdout.splitlines():
        if "render_brand" in line and ("error" in line.lower() or "done" in line or "jobs" in line):
            print(line)
    if r.returncode != 0:
        print(r.stderr[-2000:])
    path.unlink(missing_ok=True)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
