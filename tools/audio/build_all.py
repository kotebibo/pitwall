"""Rebuild every sound, check them and rewrite AUDIO_NOTES.md.

    python tools/audio/build_all.py [--png DIR]

Needs numpy and scipy (Pillow only for --png pictures).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # keep tools/audio free of __pycache__

import time

import check_audio
import gen_engine
import gen_music
import gen_race
import gen_sfx
import write_notes


def main(argv: list[str]) -> int:
    t0 = time.time()
    gen_engine.main()
    gen_sfx.main()
    gen_race.main()
    gen_music.main()
    print(f"rendered in {time.time() - t0:.1f} s")
    status = check_audio.main(argv)
    write_notes.main()
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
