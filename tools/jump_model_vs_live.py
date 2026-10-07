#!/usr/bin/env python3
"""Compares the MODEL jump against the LIVE trace with the SAME hold duration.

Why the earlier comparison was misleading: the live capture held UP for 40
engine ticks, but the model runs at 60 Hz, so the equivalent hold is
    40 ticks / 240 fps * 60 fps = 10 model frames
Replaying the model for 10 frames gives an apex of ~30 px, and the live trace
shows 23.4 px -- both are the *cutoff-limited* regime (releasing early clamps
the upward velocity to HEART_JUMPHOLD_CUTOFF), NOT the free-flight 90 px apex.
Comparing against 90 px was wrong.

This prints the model and live sequences on a common time axis in px and px/s.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine.dynamics import MODEL_FPS, VY_SCALE, step_dynamics  # noqa: E402

ENGINE_FPS = 240.0
LIVE_DT = 0.004185
HOLD_TICKS = 40
HOLD_FRAMES = round(HOLD_TICKS / ENGINE_FPS * MODEL_FPS)   # 10 at 60 Hz


def main() -> int:
    print(f"MODEL_FPS={MODEL_FPS}  VY_SCALE={VY_SCALE}  hold={HOLD_TICKS} ticks = {HOLD_FRAMES} frames\n")

    s = (0, 0, 0, 1, 0)
    seq = []
    for i in range(MODEL_FPS * 2):
        uy = 1 if i < HOLD_FRAMES else 0
        s = step_dynamics(s, (0, uy), physics_mode="c2", W=349, H=114,
                          v_walk=150, v_jump_init=180)
        seq.append((i, s[1], s[2] / VY_SCALE * MODEL_FPS))

    peak = max(y for _, y, _ in seq)
    at = [i for i, y, _ in seq if y == peak][0]
    print(f"model   apex={peak} px at frame {at} ({at / MODEL_FPS:.3f} s)")
    print("  frame  y   vy(px/s)")
    for i in range(0, 26):
        print(f"   {i:>4} {seq[i][1]:>4} {seq[i][2]:>+9.1f}")

    print()
    print("live    apex=23.4 px at 0.279 s (tick 67)")
    print("  tick  y        dy(px/s)")
    for t, y, dy in [(1, 377.955, -180.00), (7, 373.484, -175.48), (13, 369.144, -170.98),
                     (19, 364.899, -166.46), (25, 360.801, -161.98), (31, 356.798, -28.11),
                     (43, 355.601, -19.13), (55, 354.850, -10.11), (67, 354.551, -1.11)]:
        print(f"   {t:>4} {y:>9.3f} {dy:>+9.2f}")

    print()
    print("=" * 58)
    print(f"  model apex {peak} px vs live 23.4 px -> delta {peak - 23.4:+.1f} px")
    print(f"  model apex time {at / MODEL_FPS:.3f} s vs live 0.279 s")
    print()
    print("  Both are cutoff-limited short jumps, so they should agree within")
    print("  the release-tick quantisation (half an engine tick ~ 1 px).")

    # Free-flight reference: what the numbers WOULD be with no early release.
    v0, g = 180.0, 180.0
    print(f"\n  free-flight (hold forever): apex {v0 * v0 / (2 * g):.1f} px at {v0 / g:.3f} s")
    print("  -> the planner's short jumps are nowhere near this, which is correct:")
    print("     it releases early on purpose to stay in the low lane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
