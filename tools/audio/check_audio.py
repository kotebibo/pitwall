"""Numeric checks and pictures for every WAV in game/assets/audio.

    python tools/audio/check_audio.py [--png DIR] [names...]

Checks: clipping, DC offset, start/end clicks for one-shots, loop seam
continuity (sample jump and spectral flux across the wrap compared with the
rest of the file), peak/RMS/LUFS. With --png it writes a waveform +
spectrogram image per file.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # keep tools/audio free of __pycache__

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from dsp import OUT_DIR, SR, lufs, read_wav, to_db


def stft_db(x: np.ndarray, nfft: int = 2048, hop: int = 256) -> np.ndarray:
    if len(x) < nfft:
        x = np.pad(x, (0, nfft - len(x)))
    win = np.hanning(nfft)
    frames = []
    for i in range(0, len(x) - nfft + 1, hop):
        frames.append(np.abs(np.fft.rfft(x[i:i + nfft] * win)))
    m = np.array(frames).T
    return 20 * np.log10(m + 1e-9)


def seam_report(x: np.ndarray) -> dict:
    # the wrap-around step compared with the steps right next to it (+-20 ms)
    w = int(0.02 * SR)
    local = np.abs(np.diff(np.concatenate([x[-w:], x[:w]])))
    local = np.delete(local, w - 1)  # leave the wrap step itself out
    typical = np.percentile(local, 99) + 1e-9
    jump = abs(x[0] - x[-1])
    # spectral flux across the seam vs. elsewhere
    nfft, hop = 1024, 512
    w = np.hanning(nfft)

    def spec(seg):
        return np.log(np.abs(np.fft.rfft(seg * w)) + 1e-6)

    n = len(x)
    seam = np.concatenate([x[-nfft:], x[:nfft]])
    flux_seam = np.mean([np.mean(np.abs(spec(seam[i:i + nfft]) - spec(seam[i + hop:i + hop + nfft])))
                         for i in range(0, nfft, hop)])
    fl = []
    for i in range(0, n - nfft - hop, hop * 4):
        fl.append(np.mean(np.abs(spec(x[i:i + nfft]) - spec(x[i + hop:i + hop + nfft]))))
    flux_ref = float(np.percentile(fl, 90)) if fl else 0.0
    return {"jump_ratio": jump / typical, "flux_ratio": flux_seam / (flux_ref + 1e-9)}


def colour(v: np.ndarray) -> np.ndarray:
    """0..1 -> magma-ish RGB."""
    stops = np.array([[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66],
                      [245, 125, 21], [250, 193, 39], [252, 255, 164]], dtype=float)
    p = np.clip(v, 0, 1) * (len(stops) - 1)
    i = np.minimum(p.astype(int), len(stops) - 2)
    f = (p - i)[..., None]
    return (stops[i] * (1 - f) + stops[i + 1] * f).astype(np.uint8)


def picture(name: str, x: np.ndarray, out: Path, max_hz: float = 12000, seconds: float | None = None, log: bool = True) -> Path:
    if seconds:
        x = x[:int(seconds * SR)]
    W, WH, SH = 1200, 140, 420
    img = Image.new("RGB", (W, WH + SH + 20), (12, 12, 14))
    dr = ImageDraw.Draw(img)
    # waveform (min/max per column)
    cols = np.array_split(x, W)
    for i, c in enumerate(cols):
        if len(c) == 0:
            continue
        lo, hi = float(c.min()), float(c.max())
        y0 = int(WH / 2 - hi * WH / 2)
        y1 = int(WH / 2 - lo * WH / 2)
        dr.line([(i, y0), (i, y1)], fill=(120, 200, 255))
    dr.line([(0, WH // 2), (W, WH // 2)], fill=(60, 60, 70))
    s = stft_db(x, 2048, max(64, len(x) // 1600))
    freqs = np.fft.rfftfreq(2048, 1 / SR)
    if log:
        fy = np.geomspace(30, max_hz, SH)
    else:
        fy = np.linspace(0, max_hz, SH)
    idx = np.clip(np.searchsorted(freqs, fy), 0, len(freqs) - 1)
    s = s[idx][::-1]
    top = s.max()
    v = (s - (top - 80)) / 80.0
    rgb = colour(v)
    spec_img = Image.fromarray(rgb).resize((W, SH), Image.BILINEAR)
    img.paste(spec_img, (0, WH + 20))
    dr.text((6, WH + 2), f"{name}  {len(x) / SR:.2f}s  ({'log' if log else 'lin'} 30..{max_hz:.0f} Hz)", fill=(230, 230, 230))
    if log:
        for f in (100, 300, 1000, 3000, 10000):
            if f < max_hz:
                yy = WH + 20 + int(SH - 1 - np.searchsorted(fy, f))
                dr.line([(0, yy), (12, yy)], fill=(255, 255, 255))
                dr.text((14, yy - 6), f"{f}", fill=(255, 255, 255))
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{name}.png"
    img.save(p)
    return p


def main(argv: list[str]) -> int:
    png_dir = None
    names = []
    i = 0
    while i < len(argv):
        if argv[i] == "--png":
            png_dir = Path(argv[i + 1])
            i += 2
        else:
            names.append(argv[i])
            i += 1
    files = sorted(OUT_DIR.glob("*.wav"))
    if names:
        files = [f for f in files if f.stem in names]
    bad = 0
    print(f"{'file':22s} {'sec':>6s} {'loop':>4s} {'peak':>7s} {'rms':>7s} {'lufs':>7s} {'dc':>8s}  notes")
    for f in files:
        x, sr, loop = read_wav(f)
        notes = []
        pk = to_db(np.max(np.abs(x)))
        rm = to_db(np.sqrt(np.mean(x * x)))
        lu = lufs(x)
        dc = float(np.mean(x))
        if pk > -0.5:
            notes.append("CLIP-RISK")
            bad += 1
        if abs(dc) > 2e-3:
            notes.append("DC")
            bad += 1
        if sr != SR:
            notes.append(f"sr={sr}")
        if loop:
            s = seam_report(x)
            notes.append(f"seam jump x{s['jump_ratio']:.2f} flux x{s['flux_ratio']:.2f}")
            if s["jump_ratio"] > 1.0 or s["flux_ratio"] > 1.3:
                notes.append("SEAM?")
                bad += 1
        else:
            if abs(x[0]) > 1e-3 or abs(x[-1]) > 1e-3:
                notes.append("EDGE-CLICK")
                bad += 1
            head = np.max(np.abs(x[:16]))
            if head > 0.2:
                notes.append(f"hard-start {head:.2f}")
        print(f"{f.stem:22s} {len(x) / sr:6.2f} {'yes' if loop else '':>4s} {pk:7.1f} {rm:7.1f} {lu:7.1f} {dc:8.5f}  {' '.join(notes)}")
        if png_dir:
            picture(f.stem, x, png_dir)
    print(f"{len(files)} files, {bad} issue(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
