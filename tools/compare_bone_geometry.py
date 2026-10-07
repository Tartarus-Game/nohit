#!/usr/bin/env python3
"""Compares the MODEL's bone geometry with the LIVE bounding boxes.

Live absolute coordinates (arena floor y = 378, left x = 146) captured from the
running export at frame ~53:

    BoneV height 95 : x = 185.7, y = 257   -> bbox [185.7, 195.7] x [257, 352]
    BoneV height 20 : x = 185.7, y = 366   -> bbox [185.7, 195.7] x [366, 386]

The solver works in LOCAL arena space (origin bottom-left, y up):
    local_x = abs_x - c2_left
    local_y = c2_floor - (abs_y + height)   .. c2_floor - abs_y

So for the two bones above:

    h=95: local_y = 378-352 .. 378-257 = 26 .. 121
    h=20: local_y = 378-386 .. 378-366 = -8 ..  12

The heart spawns at local (174, 0). The h=20 bone therefore OVERLAPS the heart's
resting position -- which is exactly where the first damage lands. This script
prints the model's view of the same frames so the two can be compared directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"
C2_LEFT = 146.0
C2_FLOOR = 378.0


def main() -> int:
    bake = bake_cspace(GAME / "sans_bonegap1.csv", T=397, auto_size=True,
                       soul_w=4, soul_h=4, physics_mode="c2")
    B = bake.B_hazard
    T, H, W = B.shape
    print(f"model arena: W={W} H={H}   init={bake.initial_state}")
    print(f"local_y range: 0..{H - 1}   (heart spawns at local y={bake.initial_state[1]})")
    print()

    print("live bone boxes converted to LOCAL space:")
    for name, abs_y, h in (("h=95", 257.0, 95), ("h=20", 366.0, 20)):
        lo = C2_FLOOR - (abs_y + h)
        hi = C2_FLOOR - abs_y
        print(f"  {name:>5}: abs y {abs_y:.0f}..{abs_y + h:.0f}  ->  local y {lo:.0f}..{hi:.0f}"
              f"   {'(outside arena)' if lo < 0 or hi > H - 1 else ''}")
    print()

    print("model hazard rows at the frames around the first damage (tick 283 ~ plan frame 92):")
    for t in (53, 55, 60, 88, 90, 92, 94, 96):
        if t >= T:
            continue
        row = B[t]
        cols = np.where(row.any(axis=0))[0]
        if not len(cols):
            print(f"  t={t:>4}: NO hazard")
            continue
        # which rows are dangerous near the heart column
        hx = bake.initial_state[0]
        col = row[:, hx]
        rows_hot = np.where(col)[0]
        # connected blocks of dangerous x
        blocks = []
        s = cols[0]; p = cols[0]
        for c in cols[1:]:
            if c != p + 1:
                blocks.append((s, p)); s = c
            p = c
        blocks.append((s, p))
        print(f"  t={t:>4}: {len(cols):>4} hot cols, blocks={blocks[:5]}")
        print(f"          at heart col x={hx}: dangerous rows={rows_hot.tolist()[:20]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
