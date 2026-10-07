#!/usr/bin/env python3
"""Aligns the MODEL's planned trajectory with the LIVE trace, frame by frame.

The live tick rate is 240 Hz and the plan is 60 Hz, so 4 engine ticks == 1 plan
frame. Damage ticks observed on sans_bonegap1 with the plan loaded:

    tick 289 -> plan frame 84   heart abs y = 366.6   hit by bone (by=366, h=20)
    tick 297 -> plan frame 86   heart abs y = 370.0
    tick 305 -> plan frame 88   heart abs y = 373.9
    tick 393 -> plan frame 110  heart abs y = 351.9   hit by bone (by=257, h=95)

This prints what the MODEL thinks the heart's position is at those frames, so
the two can be compared directly instead of inferred.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"
C2_FLOOR = 378.0

# (plan_frame, live_abs_y, what hit it)
LIVE = [
    (84, 366.6, "by=366 h=20"),
    (86, 370.0, "by=366 h=20"),
    (88, 373.9, "by=366 h=20"),
    (110, 351.9, "by=257 h=95"),
]


def main() -> int:
    bake = bake_cspace(GAME / "sans_bonegap1.csv", auto_size=True,
                       soul_w=4, soul_h=4, physics_mode="c2")
    T = bake.B_hazard.shape[0]
    sol = solve_lattice_dp(bake)
    if sol.is_deadlock:
        print("deadlock:", sol.deadlock_frame)
        return 1
    traj = sol.trajectory
    acts = sol.action_sequence
    x0, y0 = bake.initial_state
    print(f"model arena {bake.B_hazard.shape[2]}x{bake.B_hazard.shape[1]}  init=({x0},{y0})  plan T={T}")
    print()

    print("plan around the damage frames (local coords, y up, floor=0):")
    print(f"{'frame':>6}{'x':>6}{'y':>6}{'vy':>8}{'kappa':>7}{'action':>9}")
    for f in range(50, 62):
        if f < len(traj):
            print(f"{f:>6}{traj[f][0]:>6}{traj[f][1]:>6}{traj[f][2]:>8}{traj[f][3]:>7}"
                  f"{str(tuple(acts[f])) if f < len(acts) else '-':>9}")
    print("  ...")
    for f in (80, 82, 84, 86, 88, 90, 108, 110, 112):
        if f < len(traj):
            a = tuple(acts[f]) if f < len(acts) else "-"
            print(f"{f:>6}{traj[f][0]:>6}{traj[f][1]:>6}{traj[f][2]:>8}{traj[f][3]:>7}{str(a):>9}")

    print()
    print("=" * 72)
    print("model vs live at the damage frames")
    print("=" * 72)
    print(f"{'frame':>6}{'model y':>9}{'live abs y':>12}{'live local y':>14}{'delta':>9}  hit by")
    for f, live_abs, hit in LIVE:
        if f >= len(traj):
            continue
        my = traj[f][1]
        live_local = C2_FLOOR - live_abs
        print(f"{f:>6}{my:>9}{live_abs:>12.1f}{live_local:>14.1f}{my - live_local:>9.1f}  {hit}")

    print()
    ys = [t[1] for t in traj]
    print(f"model y range over the whole plan: {min(ys)} .. {max(ys)}")
    segs = []
    cur = None
    for i, a in enumerate(acts):
        if a[1] == 1 and cur is None:
            cur = i
        elif a[1] == 0 and cur is not None:
            segs.append((cur, i - 1)); cur = None
    if cur is not None:
        segs.append((cur, len(acts) - 1))
    print(f"jump segments: {len(segs)} -> {segs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
