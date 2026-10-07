#!/usr/bin/env python3
"""Calibrates the FLOOR reference from the live engine vs the model.

Measured live values (arena floor reported as abs y = 378 by /api/tas):

    heart at REST           : abs y = 377.89   (stable, no input)
    heart sprite            : 16 wide x 20 tall, hotspot centred
    damage hitbox           : 4 x 4, re-centred on the heart each tick
    BoneV height=20         : abs y = 366, bbox y in [366, 386]
    BoneV height=95         : abs y = 257, bbox y in [257, 352]

A bone with bbox [366, 386] has its BOTTOM at 386, i.e. 8 px BELOW the reported
floor of 378. If the floor were the bone's resting line, a 20-tall bone sitting
on it would span [358, 378] -- not [366, 386].

This script prints the model's local-space view of the same bones so the offset
between the two frames is explicit and can be corrected in one place.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

C2_FLOOR = 378.0            # what the API reports
HEART_REST_ABS_Y = 377.89   # measured, stable
BONES = [
    ("h=95 vx=+", 257.0, 95),
    ("h=20 vx=+", 366.0, 20),
]


def main() -> int:
    print(f"reported c2_floor     = {C2_FLOOR}")
    print(f"heart rest abs y      = {HEART_REST_ABS_Y}")
    print(f"difference            = {C2_FLOOR - HEART_REST_ABS_Y:+.2f} px")
    print()
    print("bone -> local y under TWO candidate floor references:")
    print(f"  {'bone':<11}{'abs bbox':<18}{'local (floor=378)':<22}{'local (floor=386)'}")
    for name, abs_y, h in BONES:
        lo1 = C2_FLOOR - (abs_y + h)
        hi1 = C2_FLOOR - abs_y
        lo2 = 386.0 - (abs_y + h)
        hi2 = 386.0 - abs_y
        print(f"  {name:<11}[{abs_y:.0f},{abs_y + h:.0f}]{'':<8}"
              f"[{lo1:.0f},{hi1:.0f}]{'':<14}[{lo2:.0f},{hi2:.0f}]")
    print()
    print("The model currently builds the h=20 bone at local y=-8 (span [-8,12]).")
    print("For it to sit ON the floor its local y must be 0, so the correct")
    print("reference is abs 386 -- i.e. the model's local frame is shifted 8 px")
    print("relative to the engine's.")
    print()
    print("Consequence: the model treats local y in [0,12] as the short-bone band,")
    print("and the heart's rest position (local y=2) falls INSIDE it, so the")
    print("planner believes it must keep jumping -- while in the live engine the")
    print("resting heart is below those bones and safe until it is lifted to")
    print("abs y=366.6, where the first damage actually lands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
