#!/usr/bin/env python3
"""Instruments the DP forward loop to explain why sans_bonegap1 dies at t=73.

Round 5 established:
  * the collision geometry is aligned to ~1 px (bone abs [308.738, 318.738] vs
    model [308, 317]; heart 4x4 hitbox overlap 0.738 px -> real hit)
  * the bone structure is right: h=20 occupies local y [-8, 12] and h=95 occupies
    [26, 121], leaving a 14 px corridor at y [12, 25]
  * at the heart's column x=174 the model reports y=0..29 ALL safe
  * yet every starting y (0, 6, 12, ..., 24) still deadlocks at t=73
  * the alive-state count falls by EXACTLY 57 every frame from t=61 to t=72

A constant -57 per frame is a boundary/geometry signature, not a hazard wipe
(the global safe-cell count barely changes: 34430 -> 34842).

This script replays the same expansion the solver performs and prints, for each
frame, the (x, y) distribution of the survivors plus which states were lost and
why, so the bottleneck is identified instead of guessed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine.dynamics import step_dynamics_batch  # noqa: E402
from nohit.engine.state import pack_states_array  # noqa: E402
from nohit.engine import solver as SV  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"
ACTIONS = SV.ACTIONS


def main() -> int:
    bake = bake_cspace(GAME / "sans_bonegap1.csv", auto_size=True, soul_w=4, soul_h=4,
                       physics_mode="c2")
    B = bake.B_hazard
    T, H, W = B.shape
    meta = bake.metadata
    print(f"arena {W}x{H}  T={T}  init={bake.initial_state}")

    x0, y0 = bake.initial_state
    vy0, kappa0, tau0 = 0, 1, 0
    actions_arr = np.array(ACTIONS, dtype=np.int8)

    states = np.array([[x0, y0, vy0, kappa0, tau0]], dtype=np.int32)
    packed = pack_states_array(states)

    for t in range(T - 1):
        N = len(states)
        rep = np.repeat(states, 6, axis=0)
        rep_packed = np.repeat(packed, 6)
        act_idx = np.tile(np.arange(6, dtype=np.uint8), N)
        ux = actions_arr[act_idx, 0]
        uy = actions_arr[act_idx, 1]

        nxt = step_dynamics_batch(
            rep, ux, uy,
            platforms=bake.platform_table[t] if t < len(bake.platform_table) else (),
            is_slam=False, W=W, H=H, w=4, h=4,
            v_walk=meta.get("v_walk", 150), v_jump_init=meta.get("v_jump", 180),
            physics_mode="c2",
        )
        nx, ny = nxt[:, 0], nxt[:, 1]
        safe = ~B[t + 1][ny, nx]
        kept = nxt[safe]

        n_before, n_after = len(nxt), len(kept)
        if len(kept):
            pk = pack_states_array(kept)
            uniq, first = np.unique(pk, return_index=True)
            states = kept[first]
            packed = uniq
        else:
            states = kept
            packed = pack_states_array(kept) if len(kept) else np.empty(0, np.uint32)

        if 60 <= t <= 76 or t % 20 == 0:
            n = len(states)
            if n:
                xs, ys = states[:, 0], states[:, 1]
                print(f"t={t:>3}->{t+1:>3}  cand={n_before:>4} safe={n_after:>4} alive={n:>4}"
                      f"   x[{xs.min():>3},{xs.max():>3}] y[{ys.min():>3},{ys.max():>3}]"
                      f"  distinct x={len(np.unique(xs))} y={len(np.unique(ys))}")
            else:
                print(f"t={t:>3}->{t+1:>3}  cand={n_before:>4} safe={n_after:>4} alive=   0   DIED")
                print()
                print("blocked states before the safety probe (x, y counts):")
                allx, ally = nx, ny
                xy = np.stack([allx, ally], axis=1)
                uniq_xy, cnt = np.unique(xy, axis=0, return_counts=True)
                order = np.argsort(-cnt)[:12]
                for i in order:
                    print(f"    x={uniq_xy[i, 0]:>3} y={uniq_xy[i, 1]:>3}  cands={cnt[i]}")
                break
        if len(states) == 0:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
