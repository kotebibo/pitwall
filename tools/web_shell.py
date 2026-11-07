"""Writes the web export's <head> additions into game/export_presets.cfg:
dark loading screen with the logo above a brand-red progress bar, favicon
and link-preview (Open Graph / Twitter card) tags.

    python tools/web_shell.py [--url https://pitwall-game.fly.dev]

Run before tools/build-web.cmd. The logo is embedded as a data URI so it shows
before the game has loaded anything.
"""

import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS = ROOT / "game" / "export_presets.cfg"


def first(*paths):
    for p in paths:
        if p.exists():
            return p
    raise SystemExit("no logo found")


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def main():
    url = ""
    if "--url" in sys.argv:
        url = sys.argv[sys.argv.index("--url") + 1].rstrip("/")
    logo = first(ROOT / "brand" / "logo" / "loading_logo.png", ROOT / "brand" / "loading_logo.png",
                 ROOT / "game" / "assets" / "sprites" / "ui" / "logo.png")
    title = "Pit Wall: the F1 team game where you drive"
    desc = "Run an F1 team and drive the car. Every qualifying lap is re-driven by the server and recorded on Solana."
    meta = [
        '<meta name="theme-color" content="#141518">',
        f'<meta name="description" content="{desc}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{desc}">',
        '<meta property="og:type" content="website">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{title}">',
        f'<meta name="twitter:description" content="{desc}">',
    ]
    if url:
        meta += [
            f'<meta property="og:url" content="{url}/">',
            f'<meta property="og:image" content="{url}/brand/social/og_image_1200x630.png">',
            f'<meta property="og:image:secure_url" content="{url}/brand/social/og_image_1200x630.png">',
            '<meta property="og:image:type" content="image/png">',
            '<meta property="og:image:alt" content="Pit Wall: a red pixel-art F1 car on a chequered track">',
            '<meta property="og:site_name" content="Pit Wall">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            f'<meta name="twitter:image" content="{url}/brand/social/og_image_1200x630.png">',
            f'<link rel="icon" type="image/png" sizes="32x32" href="{url}/brand/icons/favicon_32.png">',
            f'<link rel="icon" type="image/x-icon" href="{url}/brand/icons/favicon.ico">',
            f'<link rel="apple-touch-icon" href="{url}/brand/icons/apple_touch_icon_180.png">',
        ]
    css = (
        "html,body{background:#141518 !important;margin:0;overflow:hidden}"
        "#canvas{background:#141518;display:block}"
        "#status{background:#141518 !important;justify-content:center !important}"
        f"#status::before{{content:'';display:block;width:384px;height:96px;margin:0 auto 28px;"
        f"background:url({data_uri(logo)}) no-repeat center/contain;image-rendering:pixelated}}"
        "#status-progress{accent-color:#e8352b;width:300px;height:6px;margin:0 auto}"
        "#status-notice{background:#1d1f23 !important;border:1px solid #34363c !important;color:#f1efea !important;font-family:monospace}"
    )
    head = "".join(meta) + f"<style>{css}</style>"
    head = head.replace("\\", "\\\\").replace('"', '\\"')
    text = PRESETS.read_text(encoding="utf8")
    text, n = re.subn(r'^html/head_include=".*"$', lambda _: f'html/head_include="{head}"', text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("head_include not found in export_presets.cfg")
    PRESETS.write_text(text, encoding="utf8", newline="\n")
    print(f"head_include: {len(head)} chars, logo {logo.relative_to(ROOT)}, url {url or '(none)'}")


if __name__ == "__main__":
    main()
