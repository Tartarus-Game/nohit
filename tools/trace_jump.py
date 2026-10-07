#!/usr/bin/env python3
"""Frame-by-frame trace of the c2 jump, to compare against the live measurement.

Live ground truth (compiled export, 240 Hz):
    tick 1 : dy 0 -> -180      (single impulse, HEART_JUMP_STRENGTH)
    then   : dy += 180*dt each tick (gravity 180 px/s^2)
    release: dy -151 -> -27    (HEART_JUMPHOLD_CUTOFF = 30 px/s)
    peak   : ~23.4 px above the floor at ~0.279 s
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine.dynamics import VY_SCALE, step_dynamics  # noqa: E402

W, H = 349, 114
KW = dict(physics_mode="c2", W=W, H=H, v_walk=150, v_jump_init=180)


def main() -> int:
    print("=== 60 Hz, hold UP for 10 frames (== 40 ticks at 240 Hz) ===")
    s = (0, 0, 0, 1, 0)
    peak = 0
    peak_at = 0
    rows = []
    for i in range(80):
        uy = 1 if i < 10 else 0
        s = step_dynamics(s, (0, uy), **KW)
        y = s[1]
        rows.append((i, uy, y, s[2] / VY_SCALE, s[3]))
        if y > peak:
            peak, peak_at = y, i

    print(f"{'i':>3} {'uy':>3} {'y':>4} {'vy px/f':>9} {'kappa':>6}")
    for i, uy, y, vy, k in rows[:26]:
        print(f"{i:>3} {uy:>3} {y:>4} {vy:>+9.3f} {k:>6}")
    print(f"\npeak = {peak} px at frame {peak_at} ({peak_at / 60:.3f} s)")
    print("live  = 23.4 px at 0.279 s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
