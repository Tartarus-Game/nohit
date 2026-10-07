#!/usr/bin/env python3
"""Fits the jump model to the two LIVE calibration points.

Live, measured through real DOM key events on the compiled export:

    hold 24 engine ticks (= 6 plan frames @60 Hz)  -> apex  4.49 px
    hold 40 engine ticks (= 10 plan frames)        -> apex 23.40 px

The engine's own trace for the 24-tick case:

    tick 2: dy = -179.26   VPad.Up = 1     <- impulse lands
    tick 4: dy =  -28.07   VPad.Up = 0     <- cutoff already applied
    apex  : 4.49 px

i.e. the -180 impulse survives roughly ONE engine tick before
HEART_JUMPHOLD_CUTOFF clamps it to -30 px/s, and the rest of the rise is the
0.5 px/frame coast decaying under gravity.

This script brute-forces the two free parameters that describe that behaviour in
the 60 Hz model -- how many frames the full impulse survives (`impulse_frames`)
and the velocity it is then clamped to (`clamped_px_per_frame`) -- and reports
which pair reproduces BOTH live apexes.

The winner is then written into dynamics.py as a named constant so the choice is
documented rather than guessed.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine.dynamics import MODEL_FPS  # noqa: E402

G_FRAME = 180.0 / (MODEL_FPS * MODEL_FPS)     # 0.05 px/frame^2
V_JUMP = 180.0 / MODEL_FPS                    # 3.0 px/frame
LIVE = [(6, 4.49), (10, 23.40)]


def apex(hold_frames: int, impulse_frames: int, clamp_v: float) -> float:
    """apex of the calibrated jump in px above the floor."""
    vy = V_JUMP
    y = 0.0
    peak = 0.0
    for f in range(hold_frames + 60):
        if f == impulse_frames and clamp_v < vy:
            vy = clamp_v
        y += vy
        vy -= G_FRAME
        peak = max(peak, y)
    return peak


def main() -> int:
    print(f"MODEL_FPS={MODEL_FPS}  v_jump={V_JUMP:.3f} px/frame  g={G_FRAME:.4f} px/frame^2")
    print(f"live targets: {LIVE}\n")

    best = None
    for impulse_frames in itertools.count(0):
        if impulse_frames > 6:
            break
        for clamp_v in [round(0.5 + 0.05 * k, 3) for k in range(0, 40)]:
            err = 0.0
            errs = []
            for hold, target in LIVE:
                a = apex(hold, impulse_frames, clamp_v)
                errs.append(a - target)
                err += (a - target) ** 2
            if best is None or err < best[0]:
                best = (err, impulse_frames, clamp_v, errs)

    err, imp, cl, errs = best
    print("best fit:")
    print(f"  impulse survives {imp} frames, then clamped to {cl} px/frame")
    for (hold, target), e in zip(LIVE, errs):
        got = apex(hold, imp, cl)
        print(f"   hold {hold:>2} frames: model {got:6.2f} px  live {target:6.2f} px  delta {e:+.2f}")
    print(f"  RMS error = {(err / len(LIVE)) ** 0.5:.3f} px")

    print()
    print("current model (no clamp, impulse once):")
    for hold, target in LIVE:
        a = apex(hold, 0, 1e9)
        print(f"   hold {hold:>2} frames: model {a:6.2f} px  live {target:6.2f} px  delta {a - target:+.2f}")

    print()
    print("suggested constant for dynamics.py:")
    print(f"  JUMP_IMPULSE_FRAMES: int = {imp}")
    print(f"  JUMP_CLAMP_PX_PER_FRAME: float = {cl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
