"""Rebuilds the whole Pit Wall brand kit into brand/.

    python tools/brand/build_all.py            # 2D only (uses the existing 3D renders)
    python tools/brand/build_all.py --render   # also re-render the 3D car with Godot (needs a GPU)
"""
from __future__ import annotations

import sys

import icons
import keyart
import logo
import readme
import render_jobs
import renders
import contact_sheet
import social

if __name__ == "__main__":
    if "--render" in sys.argv:
        render_jobs.run()
    for mod in (logo, icons, keyart, social, renders):
        n = len(mod.build())
        print(f"{mod.__name__}: {n} files")
    contact_sheet.build()
    readme.build()
    print("brand_sheet.png, README.md")
