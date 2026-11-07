"""Regenerate every environment + UI sprite, then the contact sheet.

    python tools/art/build_all.py

Order matters: the menu background and the contact sheet read sprites that the
earlier steps write.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deco  # noqa: E402
import menu_bg  # noqa: E402
import preview  # noqa: E402
import track  # noqa: E402
import ui  # noqa: E402

if __name__ == "__main__":
    n = len(track.build())
    n += len(deco.build())
    n += len(ui.build())
    menu_bg.build()
    preview.build()
    print(f"wrote {n + 1} sprites and {preview.OUT}")
