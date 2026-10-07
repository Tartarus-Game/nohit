#!/usr/bin/env python3
"""Traces a SHORT (6-frame) jump exactly as the plan performs it.

The plan for sans_bonegap1 lifts the heart only 18 px (local), holding UP for 6
frames at 60 Hz. By hand:

    impulse  v0 = 180 px/s / 60 = 3.0 px/frame
    gravity  g  = 180 px/s^2 / 3600 = 0.05 px/frame^2

    held 6 frames:  v goes 3.0 -> 2.75, rise = sum(v) ~= 17.3
    after release:  the cutoff clamps v to 30/60 = 0.5 px/frame in ONE step,
                    which throws away 2.25 px/frame of upward speed
    coast:          v decays 0.5 -> 0 in 10 frames and adds ~2.5 px
    => expected apex ~= 17.3 + 2.5 ~= 20 px

The live engine instead reached local y ~= 26 at the same plan frame, i.e. it
did NOT lose that 2.25 px/frame at release. That is the discrepancy under test:
whether HEART_JUMPHOLD_CUTOFF is applied as an instantaneous clamp in the model
but as a gradual decay in the engine.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine.dynamics import MODEL_FPS, VY_SCALE, step_dynamics  # noqa: E402

HOLD = 6


def main() -> int:
    print(f"MODEL_FPS={MODEL_FPS}  VY_SCALE={VY_SCALE}  hold={HOLD} frames")
    print()
    s = (0, 0, 0, 1, 0)
    prev_v = None
    peak = 0
    peak_at = 0
    print(f"{'frame':>6}{'uy':>4}{'y':>6}{'vy(px/f)':>11}{'dv':>9}{'kappa':>7}")
    for i in range(40):
        uy = 1 if i < HOLD else 0
        s = step_dynamics(s, (0, uy), physics_mode="c2", W=349, H=114,
                          v_walk=150, v_jump_init=180)
        v = s[2] / VY_SCALE
        dv = "" if prev_v is None else f"{v - prev_v:+.4f}"
        if s[1] > peak:
            peak, peak_at = s[1], i
        if i < 26:
            print(f"{i:>6}{uy:>4}{s[1]:>6}{v:>11.4f}{dv:>9}{s[3]:>7}")
        prev_v = v

    print()
    print(f"model apex = {peak} px at frame {peak_at}")
    print()
    print("hand calculation:")
    v0, g = 3.0, 0.05
    held = sum(v0 - g * k for k in range(HOLD))
    print(f"  held {HOLD} frames rise      = {held:.2f} px")
    print(f"  v at release             = {v0 - g * HOLD:.3f} px/frame")
    print(f"  cutoff target            = {30.0 / MODEL_FPS:.3f} px/frame")
    print(f"  speed discarded at release = {(v0 - g * HOLD) - 30.0 / MODEL_FPS:.3f} px/frame")
    coast = (30.0 / MODEL_FPS) ** 2 / (2 * g)
    print(f"  coast after cutoff       = {coast:.2f} px")
    print(f"  => apex if cutoff clamps = {held + coast:.1f} px")
    print(f"  => apex if v is KEPT     = {held + (v0 - g * HOLD) ** 2 / (2 * g):.1f} px")
    print()
    print(f"  live engine reached ~26 px (heart at abs 351.9 -> local 26.1)")
    print(f"  => the engine behaves like 'v is KEPT', the model like 'cutoff clamps'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
