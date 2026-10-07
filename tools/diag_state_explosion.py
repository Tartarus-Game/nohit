#!/usr/bin/env python3
"""Explains the state-count explosion in solve_lattice_dp.

Question being answered: state merging already exists, so why does sans_bonegap1
still carry ~37k alive states per frame?

Hypothesis: dedup happens AFTER the 6x expansion (it merges *children*), so the
expensive `step_dynamics_batch` is still called on 6N candidates every frame.
Merging the *parents* before expanding would cut that.

This prints, per frame:
  * N      = alive states going in
  * 6N     = candidates fed to step_dynamics_batch
  * unique children / unique (x,y) / unique packed keys
  * the collapse ratio, which bounds the achievable speedup
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine import solver as SV  # noqa: E402
from nohit.engine.dynamics import step_dynamics_batch  # noqa: E402
from nohit.engine.state import pack_states_array  # noqa: E402

WAVE = "sans_bonegap1"
PROBE = (30, 60, 100, 150, 200, 250)


def main() -> int:
    bake = bake_cspace(
        Path(__file__).resolve().parent.parent / "c2-sans-fight" / f"{WAVE}.csv",
        auto_size=True, soul_w=4, soul_h=4, physics_mode="c2",
    )
    B = bake.B_hazard
    T, H, W = B.shape
    meta = bake.metadata
    act = np.array(SV.ACTIONS, dtype=np.int32)
    act_idx = np.arange(6, dtype=np.int64)

    x0, y0 = bake.initial_state
    states = np.array([[x0, y0, 0, 1, 0]], dtype=np.int32)
    packed = pack_states_array(states)

    print(f"{WAVE}  T={T} arena={W}x{H}  init={bake.initial_state}")
    print(f"safe cells at f=100: {int((~B[100]).sum()):,}")
    print()
    print(f"{'f':>5}{'N':>9}{'6N':>10}{'uniq_child':>12}{'uniq_xy':>10}"
          f"{'uniq6N_keys':>13}{'collapse':>10}")

    for t in range(T - 1):
        N = len(states)
        rep = np.repeat(states, 6, axis=0)
        rep_packed = np.repeat(packed, 6)
        ai = np.tile(act_idx, N)
        ux = act[ai, 0]
        uy = act[ai, 1]

        nxt = step_dynamics_batch(
            rep, ux, uy, platforms=(), is_slam=False,
            W=W, H=H, w=4, h=4,
            v_walk=meta.get("v_walk", 150), v_jump_init=meta.get("v_jump", 180),
            physics_mode="c2",
        )
        nx, ny = nxt[:, 0], nxt[:, 1]
        safe = ~B[t + 1][ny, nx]
        kept = nxt[safe]

        if t in PROBE and len(kept):
            keys = pack_states_array(kept)
            u_child = len(np.unique(keys))
            u_xy = len(np.unique(kept[:, 0].astype(np.int64) * 1000 + kept[:, 1]))
            # how many (parent, action) pairs map onto the same child key?
            n_safe = int(safe.sum())
            print(f"{t:>5}{N:>9,}{6 * N:>10,}{u_child:>12,}{u_xy:>10,}"
                  f"{n_safe:>13,}{6 * N / max(u_child, 1):>9.2f}x")

        if len(kept):
            pk = pack_states_array(kept)
            uniq, first = np.unique(pk, return_index=True)
            states = kept[first]
            packed = uniq
        else:
            print(f"{t:>5}  DEAD")
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
