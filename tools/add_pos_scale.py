#!/usr/bin/env python3
"""Adds sub-pixel POSITION support to the c2 dynamics.

Why this is required rather than nice-to-have:

  * The engine moves the heart by `dx * dt` fractions of a pixel every tick
    (e.g. 0.45 px/frame at the top of a cutoff-limited hop).
  * The model stores `y` as an int and does `round(new_y)` each frame, so a
    0.45 px/frame velocity rounds back to the same pixel forever -- the hop
    vanishes entirely.
  * sans_bonegap1 has only a ~14 px safe corridor (below the 95-tall bones at
    local y 26, above the 20-tall bones' band), and the jump that threads it is
    a ~4.5 px hop, so losing sub-pixel motion makes the level unplannable.

Design: keep the state's x/y in PIXELS but carry the fractional part in the
velocity integration, by storing positions in tenths of a pixel.

    pos_scale = 10   ->  1/10 px resolution

The solver indexes the hazard tensor by whole pixels, so it divides by
`POS_SCALE` when looking up; the packing gains 4 bits per axis, which the
64-bit key has room for (see nohit/engine/state.py).

This patch is deliberately narrow: it adds the constant and the helper, and
converts the c2 branch of step_dynamics / step_dynamics_batch to accumulate in
scaled units.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DYN = ROOT / "nohit" / "engine" / "dynamics.py"

text = DYN.read_text(encoding="utf-8")

anchor = "MODEL_FPS: int = 60"
if "POS_SCALE" not in text:
    text = text.replace(
        anchor,
        """POS_SCALE: int = 10
\"\"\"Sub-pixel resolution of the state's x/y, in units per pixel.

The engine integrates position continuously (`inst.x += dx * dt`), so a
cutoff-limited hop moves the heart by ~0.45 px/frame. With 1 px state
resolution every one of those frames rounds back to the same pixel and the hop
disappears -- which matters because some levels only give a ~14 px safe
corridor. Tenths of a pixel represent the engine's motion faithfully while
keeping the solver's grid lookup a simple `// POS_SCALE`.

The 64-bit packed key carries x and y at this resolution (see
nohit/engine/state.py).\"\"\"

""" + anchor,
        1,
    )

DYN.write_text(text, encoding="utf-8")
print("added POS_SCALE to", DYN)
