#!/usr/bin/env python3
"""Dumps the model's ACTIVE bone bboxes at a given frame, in live absolute
coordinates, so it can be diffed directly against a live snapshot.

Live snapshot at tick 290 (heart abs (320, 377.96), first damage):

    h=20 bones near the heart:  [308.738, 318.738]  and  [322.262, 332.262]
    both spanning y [366, 386]

Usage: python tools/dump_model_bones.py [frame]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from nohit.baker import rasterizer as R  # noqa: E402
from nohit.baker.parser import parse_csv_timeline  # noqa: E402

FRAME = int(sys.argv[1]) if len(sys.argv) > 1 else 72
C2_LEFT = 146.0
C2_FLOOR = 378.0


def main() -> int:
    cmds = parse_csv_timeline(
        Path(__file__).resolve().parent.parent / "c2-sans-fight" / "sans_bonegap1.csv", fps=60
    )
    res = R.rasterize_timeline(
        cmds, config=R.RasterizerConfig(T=397, auto_size=True, FPS=60), T=397
    )
    O = res.O
    print(f"frame {FRAME} (tick {FRAME * 4})   arena {O.shape[2]}x{O.shape[1]}")
    print()
    print("model bones, converted back to ABSOLUTE canvas space:")
    print(f"  {'cells x':<16}{'abs x bbox':<26}{'abs y bbox':<22}{'h'}")
    for y in (12, 26, 40):
        if y >= O.shape[1]:
            continue
        cols = np.where(O[FRAME][y])[0]
        if not len(cols):
            continue
        blocks = []
        s = cols[0]
        p = cols[0]
        for c in cols[1:]:
            if c != p + 1:
                blocks.append((int(s), int(p)))
                s = c
            p = c
        blocks.append((int(s), int(p)))
        print(f"  --- local y = {y} ---")
        for lo, hi in blocks:
            abs_lo = lo + C2_LEFT
            abs_hi = hi + C2_LEFT
            print(f"  [{lo:>4},{hi:>4}]    abs [{abs_lo:.0f}, {abs_hi:.0f}]{'':<8}"
                  f"local y {C2_FLOOR - (y + 1):.0f}..{C2_FLOOR - y:.0f}")
    print()
    print("live at tick 290 (abs):")
    print("  h=20  [308.738, 318.738]  y [366, 386]")
    print("  h=20  [322.262, 332.262]  y [366, 386]")
    print("  h=95  [308.738, 318.738]  y [257, 352]")
    print("  h=20  [322.262, 332.262]  y [257, 352]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
