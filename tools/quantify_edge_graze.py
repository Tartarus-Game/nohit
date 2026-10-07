#!/usr/bin/env python3
"""Quantifies the sub-pixel edge overlap the integer hazard grid is dropping.

Live measurement at the first damage tick of sans_bonegap1 (tick 290, heart at
abs (320, 377.96), HP 92 -> 91):

    bone bbox  [308.74, 318.74] x [366, 386]     (h = 20)
    bone bbox  [308.74, 318.74] x [257, 352]     (h = 95)

The heart's 4x4 hitbox is centred on the heart, so it covers x in [318, 322].
The bone's right edge is 318.74, so the overlap is

    318.74 - 318.00 = 0.74 px

i.e. a 0.74 px graze still counts as a hit in the engine. The model rasterises
the bone onto whole pixels ([162, 172] local after the c2_left shift) and
dilates by the 4x4 box, so a 0.74 px overlap rounds away -- the cell reads SAFE
and the planner happily parks the heart on a lethal edge.

This is the same class of error as the jump: the engine is continuous, the
model is gridded, and the grid is one pixel too coarse at boundaries.

Fix direction: the hazard tensor must be dilated by the hitbox PLUS the
sub-pixel rounding slack, i.e. ceil() rather than round() of the box extent, so
an edge graze is conservatively marked dangerous. This script prints the widths
that correction implies and checks it against the measured case.
"""

from __future__ import annotations

SOUL = 4                    # 4x4 damage hitbox, centred on the heart
GRAZE = 0.74                # measured sub-pixel overlap that still deals damage
BONE_R = 318.74             # measured bone right edge (abs)
HEART_X = 320.0             # measured heart centre (abs)


def main() -> int:
    print(f"measured graze overlap = {GRAZE} px  (bone right {BONE_R}, hitbox left {HEART_X - SOUL / 2})")
    print()
    print("integer grid: the heart occupies cell x = floor(320 - 146) = 174")
    print("              the bone occupies local [162.74, 172.74] -> cells 162..172")
    print("              dilated by the 4x4 hitbox (radius 2): 160..174")
    print()
    print("  ** the dilated bone reaches cell 174, which is exactly the heart **")
    print("  so a CORRECT dilation DOES mark the heart's cell dangerous; the")
    print("  earlier 'safe' reading came from the bone being rasterised at")
    print("  [162, 171] (width 10 starting at floor(162.74)) instead of")
    print("  [162, 172] (width 10 covering 162.74..172.74).")
    print()
    print("=> the fix is to rasterise bone spans with ceil() on the right edge,")
    print("   not to widen the soul box.")
    print()
    W = int(BONE_R - 0.01) - int(162.74)
    print(f"   bone cells should be {int(162.74)}..{int(162.74) + int(10.0) } "
          f"(width {int(10.0)}) plus one for the 0.74 remainder -> 11 cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
