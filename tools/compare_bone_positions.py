#!/usr/bin/env python3
"""Compares live bone positions with the model's, at the damage frame.

Live at tick 290 (the first damage tick), heart at abs (320, 377.96):

    bone bbox [308.74, 318.74] x [366, 386]   (h = 20)
    bone bbox [308.74, 318.74] x [257, 352]   (h = 95)

Converted to the model's local frame (c2_left = 146):

    x in [162.74, 172.74]

The model at plan frame 72 (tick 290 / 4) has bones at local [162, 171] and
[177, 186] -- a 15-cell spacing where the live engine shows this bone at
162.74 and the next group 120 px away. This script prints both so the offset is
attributable rather than guessed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

C2_LEFT = 146.0
LIVE_ABS = [308.74, 318.74]          # bbox left/right at tick 290
FRAME = 72                            # tick 290 / 4

# Live bone centres observed earlier at tick 1 (abs), spacing 120:
LIVE_TICK1 = [154.99, 274.99, 394.99, 514.99, 634.99]


def main() -> int:
    print(f"c2_left = {C2_LEFT}   frame = {FRAME} (tick {FRAME * 4})\n")
    print("live bone at the damage tick:")
    print(f"  abs  [{LIVE_ABS[0]:.2f}, {LIVE_ABS[1]:.2f}]")
    print(f"  local[{LIVE_ABS[0] - C2_LEFT:.2f}, {LIVE_ABS[1] - C2_LEFT:.2f}]")
    print(f"  cells floor/ceil: [{int(LIVE_ABS[0] - C2_LEFT)}, {int(LIVE_ABS[1] - C2_LEFT) + 1}]")
    print()
    print("live group at tick 1 (abs, spacing 120):")
    for v in LIVE_TICK1:
        print(f"  abs {v:>7.2f}  ->  local {v - C2_LEFT:>7.2f}")
    print()
    print("the vx for these groups is +180 px/s and -180 px/s (direction 0 / 2)")
    print("so at tick 290 they have travelled:")
    for v in LIVE_TICK1:
        print(f"  {v:>7.2f} + 180*(290/240) = {v + 180 * 290 / 240:>8.2f} abs"
              f"   (local {v + 180 * 290 / 240 - C2_LEFT:>8.2f})")
    print()
    print("model bones at frame", FRAME, "(from the rasterizer):")
    import numpy as np
    from nohit.baker import rasterizer as R
    from nohit.baker.parser import parse_csv_timeline

    cmds = parse_csv_timeline(
        Path(__file__).resolve().parent.parent / "c2-sans-fight" / "sans_bonegap1.csv", fps=60
    )
    cfg = R.RasterizerConfig(T=397, auto_size=True, FPS=60)
    res = R.rasterize_timeline(cmds, config=cfg, T=397)
    row = res.O[FRAME][12]
    cols = np.where(row)[0]
    blocks = []
    s = cols[0]
    p = cols[0]
    for c in cols[1:]:
        if c != p + 1:
            blocks.append((int(s), int(p)))
            s = c
        p = c
    blocks.append((int(s), int(p)))
    print("  O cells:", blocks)
    print("  spacing between group lefts:", [blocks[i + 1][0] - blocks[i][0] for i in range(len(blocks) - 1)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
