#!/usr/bin/env python3
"""Final bit-layout: x9 + y8 + vy10 + kappa1 + tau4 = 32 bits.

vy must cover BOTH models' reachable ranges:
  * docs : [-12, 8] px/frame (integers)
  * c2   : [-12.5 * VY_SCALE, +3.0 * VY_SCALE]
A 10-bit field holds 1024 values, so the c2 span (12.5 + 3.0 = 15.5 px/frame)
allows at most VY_SCALE ~ 60. We use VY_SCALE = 40 with a bias of 450:
     -12.5 * 40 = -500  ->  450 + (-500) = -50 ... negative!
So the bias must be >= the negative magnitude. Using bias 500 and VY_SCALE 40:
     -500 -> 0 (exact floor), +120 -> 620, well inside [0, 1023].
The gravity step then quantises 0.05 -> 2 cells = 0.0625 (-0 -> +25%) ...

Actually 0.05 * 40 = 2.0 exactly, so the gravity step survives EXACTLY at
VY_SCALE = 40. That is the key insight: pick a scale that makes the gravity
increment an integer number of cells.

    0.05 px/frame^2 is 1/20 px/frame^2. Any scale that is a multiple of 20
    represents it exactly: 20, 40, 60, ...
    60 * 12.5 = 750 > field, 40 * 12.5 = 500 <= field.  ->  VY_SCALE = 40.

This patch applies that.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# --- state.py --------------------------------------------------------------
state_path = ROOT / "nohit" / "engine" / "state.py"
text = state_path.read_text(encoding="utf-8")

text = text.replace("VY_KEY_BITS: int = 11", "VY_KEY_BITS: int = 10")
text = text.replace("VY_KEY_BIAS: int = 1600", "VY_KEY_BIAS: int = 500")
text = text.replace("_TAU_BITS = 3", "_TAU_BITS = 4")
text = text.replace(
    """#   bits 17..27 : vy + 1600  (11 bits, covers [-1600, 447] exactly)
#   bit  28     : kappa      (1 bit)
#   bits 29..31 : tau        (3 bits, [0, 7])""",
    """#   bits 17..26 : vy + 500   (10 bits, covers [-500, 523] exactly)
#   bit  27     : kappa      (1 bit)
#   bits 28..31 : tau        (4 bits, [0, 15], the docs jump-hold counter)""",
)
text = text.replace(
    """# `vy` is stored in the model's native integer unit (px/frame for "docs",
# px/frame*VY_SCALE for "c2"). The 11-bit field with a bias of 1600 covers:
#   * c2  -- [-12.5 * 128, +3.0 * 128] = [-1600, +384]
#   * docs -- [-12, 8] -> [1588, 1608]
#
# The field was 10 bits with VY_SCALE = 16, but that quantised the 0.05
# px/frame^2 gravity step up to 0.0625 (+25%), which made the planner's jump
# peak only 21 px against the engine's measured 72 px. Widening to 11 bits
# allows VY_SCALE = 128, cutting the error to ~6%.
#
# `tau` must stay in the key: it is the jump-hold counter and it selects the
# ascent gravity branch. It only needs to reach TAU_MAX (8..15), and 7 covers
# the values the docs model actually produces; the c2 model does not use it.""",
    """# `vy` is stored in the model's native integer unit (px/frame for "docs",
# px/frame * VY_SCALE for "c2"). The 10-bit field with a bias of 500 covers:
#   * c2   -- VY_SCALE = 40 gives [-500, +120], i.e. [-12.5, +3.0] px/frame
#   * docs -- [-12, 8] -> [488, 508]
#
# VY_SCALE = 40 is not arbitrary: the authoritative gravity step is
# 0.05 px/frame^2 = 1/20, and 40 is the largest multiple of 20 whose product
# with the 12.5 px/frame terminal velocity still fits the field. That makes the
# gravity increment exactly 2 cells, so gravity integrates WITHOUT quantisation
# error -- the previous scales (16, 32) rounded 0.05 up to 0.0625 (+25%), which
# capped the planner's jump at 21 px against the engine's 72 px.
#
# `tau` keeps its 4 bits: it is the docs jump-hold counter (0..15) and selects
# the ascent gravity branch, so truncating it would merge real states.""",
)

state_path.write_text(text, encoding="utf-8")
print("patched", state_path)

# --- dynamics.py -----------------------------------------------------------
dyn_path = ROOT / "nohit" / "engine" / "dynamics.py"
dtext = dyn_path.read_text(encoding="utf-8")
dtext = dtext.replace("VY_SCALE: int = 128", "VY_SCALE: int = 40")
dyn_path.write_text(dtext, encoding="utf-8")
print("patched", dyn_path)
