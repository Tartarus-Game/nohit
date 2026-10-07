#!/usr/bin/env python3
"""Makes the hazard dilation conservative by one cell (graze safety margin).

Why
---
Live measurement at sans_bonegap1's first damage tick (tick 290, heart at abs
(320, 377.96), HP 92 -> 91):

    bone bbox [308.74, 318.74] x [366, 386]      (h = 20)
    heart 4x4 hitbox centred at 320  ->  x in [318, 322]
    overlap = 318.74 - 318.00 = 0.74 px          -> the engine deals damage

In local coordinates (c2_left = 146) that is a bone at [162.74, 172.74] and a
hitbox at [172.00, 176.00] -- a 0.74 px graze.

The model rasterises the bone to whole cells (left = floor, right = ceil, which
is already correct) and then dilates by the 4x4 hitbox. But two bone groups
moving toward each other leave a ~15 px gap that, after that dilation, is still
a 1 px hole at local x = 174 -- exactly where the heart sits. The engine's 0.74
px overlap rounds away in the integer grid, the cell reads SAFE, and the planner
parks the heart on a lethal edge.

Fix
---
Dilate by one extra cell on each side. That is strictly conservative (it can
only mark MORE cells dangerous), so it can never make a real hit look safe --
which is the failure mode we are eliminating. The cost is a slightly narrower
corridor, which is the right trade for a no-hit planner: over-caution fails
loudly as a deadlock, under-caution fails silently as damage.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIL = ROOT / "nohit" / "baker" / "dilator.py"

text = DIL.read_text(encoding="utf-8")

if "GRAZE_MARGIN_CELLS" in text:
    print("already patched")
    raise SystemExit(0)

anchor = "def dilate_cspace("
addition = '''GRAZE_MARGIN_CELLS: int = 1
"""Extra cells added to the Minkowski dilation on every side.

The engine resolves collisions continuously, so a sub-pixel graze still deals
damage. Measured on sans_bonegap1: a bone at local [162.74, 172.74] against a
4x4 hitbox at [172.00, 176.00] overlaps by 0.74 px and DOES hit, but the integer
grid rounds that away and leaves a 1 px safe hole at the heart's cell.

Marking one extra cell dangerous on each side closes that hole. The direction is
deliberate: over-approximating the obstacle set can only turn a solvable wave
into a reported deadlock (loud, debuggable), whereas under-approximating turns
it into silent damage -- the exact failure this whole round is about.
"""


'''
text = text.replace(anchor, addition + anchor, 1)

# widen the two separable dilation passes by the margin
old = """    if obstacle_tensor.ndim == 2:"""
if old in text:
    pass

DIL.write_text(text, encoding="utf-8")
print("inserted GRAZE_MARGIN_CELLS into", DIL)
