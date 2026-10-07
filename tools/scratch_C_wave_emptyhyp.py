#!/usr/bin/env python3
"""VERIFY_C scratch: hypothesis test -- could a sans_bonegap1 run show the
left-wall plan because its hazard tensor came out EMPTY?

Builds a BakeResult with the c2 geometry/kinematics of the real wave
(W=349, H=114, initial (174,2), v_walk=150 px/s = 2.5 px/frame, soul 4x4) but an
all-False hazard tensor and a slam frame (which is what forces the solver past
its empty-arena fast path into the DP's no-hazard `else:` branch).

Usage: python tools/scratch_C_wave_emptyhyp.py <variant> [T]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
from scratch_C_bias_sweep import load_solver, report  # noqa: E402

from nohit.common.types import BakeResult  # noqa: E402


def main() -> int:
    variant = sys.argv[1] if len(sys.argv) > 1 else "handed"
    T = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    md = {"slam_frames": [T - 2], "physics_mode": "c2", "v_walk": 150, "v_jump": 180,
          "soul_size": (4, 4)}
    B = np.zeros((T, 114, 349), dtype=bool)
    bake = BakeResult(B_hazard=B, platform_table=[[] for _ in range(T)],
                      initial_state=(174, 2), metadata=md)
    print(f"empty-hazard tensor {B.shape} initial_state=(174,2) metadata={md}")
    solve = load_solver(variant)
    sol = solve(bake)
    if sol.is_deadlock:
        print("DEADLOCK", sol.deadlock_frame)
        return 0
    report(sol, bake, variant, f"empty-hazard c2-kinematics T={T}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
