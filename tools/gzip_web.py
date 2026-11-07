"""Writes .gz copies of the web build's big files (wasm, pck, js) for the server."""
import gzip
from pathlib import Path

web = Path(__file__).resolve().parent.parent / "build" / "web"
for f in web.iterdir():
    if f.suffix in (".wasm", ".pck", ".js", ".html") and not f.name.endswith(".gz"):
        data = f.read_bytes()
        out = gzip.compress(data, compresslevel=9, mtime=0)
        (web / (f.name + ".gz")).write_bytes(out)
        print(f"{f.name}: {len(data) / 1e6:.1f} MB -> {len(out) / 1e6:.1f} MB")
