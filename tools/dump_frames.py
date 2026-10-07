#!/usr/bin/env python3
"""Dumps every animation frame's size and hotspot from the compiled export.

Needed because the live measurement contradicts the plain-bbox reading:

    tick 290, HP 92->91
        t65 hitbox bbox [318, 375.95 .. 322, 379.95]   (4x4)
        bone  h=20 bbox [308, 366    .. 318, 386   ]
        -> x overlap is exactly 0.00 px, y overlap is 6 px

A hit at zero x-overlap means the C2 collision test is not using those plain
axis-aligned boxes: NinePatch/`t31` uses a collision POLYGON, and the heart may
test against `t55` (16x20) rather than `t65`. This dumps the authoritative frame
rects so the geometry can be read rather than inferred.
"""

from __future__ import annotations

import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "c2-sans-fight" / "data.js"

FRAME_RE = re.compile(
    r'\[\s*"images/([^"]+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)'
    r'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*,\s*([\d.eE+-]+)\s*,\s*([\d.eE+-]+)'
)


def main() -> int:
    d = DATA.read_text(encoding="utf-8", errors="ignore")
    print(f"{'image':<34}{'frame':>10}{'size':>10}{'hotspot':>16}")
    seen = set()
    for m in FRAME_RE.finditer(d):
        img, fx, fy, ax, ay, w, h, hsx, hsy = m.groups()
        key = (img, fx, fy)
        if key in seen:
            continue
        seen.add(key)
        if any(k in img.lower() for k in ("bone", "heart", "hitbox")):
            print(f"{img:<34}{fx+','+fy:>10}{w+'x'+h:>10}{hsx+','+hsy:>16}")
    print()
    print("BoneV object-type declaration:")
    i = d.find('"t31"')
    print("  " + " ".join(d[i:i + 330].split()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
