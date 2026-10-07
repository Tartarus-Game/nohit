#!/usr/bin/env python3
"""Carries sub-pixel POSITION in the state's unused `tau` field (c2 mode only).

Problem this solves
-------------------
The engine integrates position continuously: `inst.y += dy * dt`. A
cutoff-limited hop moves the heart ~0.45 px/frame for ~9 frames, giving the
measured 3.0 - 4.5 px apex. The model stores `y` as an int and rounds each
frame, so 0.45 px/frame rounds back to the same pixel FOREVER and the hop
disappears (measured: model apex 0 px vs engine 4.49 px).

Why use `tau` instead of widening the state
-------------------------------------------
`tau` is the docs-model jump-hold counter and is hard-coded to 0 throughout the
c2 branch -- it is dead weight in exactly the mode that needs the precision. Its
4 bits hold 0..15, which is enough for a tenths-of-a-pixel residual (0..9).

Encoding: `tau = round(frac * 10)` where `frac` is the sub-pixel part of y in
[0, 1). The step reads it, adds the velocity, writes back the new residual, and
sets `y` to the integer part. No packing change, no hazard-lookup change, and
the docs model is untouched (its `tau` semantics stay what they were).

Accuracy: 1/10 px per frame, i.e. the accumulation error over a 9-frame hop is
< 1 px, versus the ~4.5 px hop that is currently being lost entirely.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DYN = ROOT / "nohit" / "engine" / "dynamics.py"

text = DYN.read_text(encoding="utf-8")

# ---- scalar branch --------------------------------------------------------
old_scalar = """        y_next_star = y + vy_frames
"""
new_scalar = """        # Sub-pixel carry: `tau` is unused in the c2 branch, so it holds the
        # fractional part of y as round(frac * 10). Without this a 0.45 px/frame
        # hop rounds back to the same pixel every frame and vanishes.
        frac_in = tau / 10.0
        y_next_star = y + frac_in + vy_frames
"""
if old_scalar in text:
    text = text.replace(old_scalar, new_scalar, 1)
    print("patched scalar y_next_star")
else:
    print("!! scalar y_next_star not found")

# the scalar landing / airborne blocks must write the residual back
old_land = """            next_y = int(round(y_surf_max))
            next_vy = 0
            next_kappa = 1
            next_tau = 0"""
new_land = """            next_y = int(round(y_surf_max))
            next_vy = 0
            next_kappa = 1
            next_tau = 0          # back on a surface: residual is absorbed"""
if old_land in text:
    text = text.replace(old_land, new_land, 1)
    print("patched scalar landing")
else:
    print("!! scalar landing not found")

old_air = """            next_y = max(0, min(H - 1, int(round(y_next_star))))
            next_vy = int(round(vy_frames * v_scale))"""
new_air = """            next_y = max(0, min(H - 1, int(np.floor(y_next_star))))
            # carry the sub-pixel remainder in tau (0..9)
            next_tau = int(round((y_next_star - np.floor(y_next_star)) * 10.0))
            if next_tau > 9:
                next_tau = 9
            next_vy = int(round(vy_frames * v_scale))"""
if old_air in text:
    text = text.replace(old_air, new_air, 1)
    print("patched scalar airborne")
else:
    print("!! scalar airborne not found")

# remove the now-duplicated next_tau = 0 that followed the airborne block
text = text.replace(
    """            next_vy = int(round(vy_frames * v_scale))
            # kappa is a SINGLE BIT in the packed key (0 = airborne, 1 = resting),
            # so it cannot carry a third "falling" value -- encoding 2 collided
            # with 0 and merged distinct states. Re-triggering is prevented
            # instead by kappa becoming 0 on the very tick the impulse fires, so
            # the gate `kappa == 1 and uy == 1` holds only while still resting.
            next_kappa = 0
            next_tau = 0""",
    """            next_vy = int(round(vy_frames * v_scale))
            # kappa is a SINGLE BIT in the packed key (0 = airborne, 1 = resting),
            # so it cannot carry a third "falling" value -- encoding 2 collided
            # with 0 and merged distinct states. Re-triggering is prevented
            # instead by kappa becoming 0 on the very tick the impulse fires, so
            # the gate `kappa == 1 and uy == 1` holds only while still resting.
            next_kappa = 0""",
    1,
)

DYN.write_text(text, encoding="utf-8")
print("wrote", DYN)
