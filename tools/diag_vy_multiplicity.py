#!/usr/bin/env python3
"""Shows the exact (vy, kappa, tau) multiplicity behind the state-count growth.

VERIFY_C-phase diagnostics showed N ~= 9x the number of distinct (x, y) cells.
The suspicion is that most of those 9 are NOT genuinely different physical
situations -- they are the same jump sampled at different phases, or sub-pixel
residuals (`tau`) that cannot affect anything.

This replays the solver's expansion and, for one busy frame, prints how many
states share each (x, y), with the full (vy, kappa, tau) breakdown, plus how many
of the 640 possible vy values actually occur.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine import solver as SV  # noqa: E402
from nohit.engine.dynamics import step_dynamics_batch  # noqa: E402
from nohit.engine.state import pack_states_array, unpack_states_vec  # noqa: E402

WAVE = "sans_bonegap1"
REPORT_FRAMES = (100, 200)


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

    for t in range(T - 1):
        N = len(states)
        rep = np.repeat(states, 6, axis=0)
        ai = np.tile(act_idx, N)
        nxt = step_dynamics_batch(
            rep, act[ai, 0], act[ai, 1], platforms=(), is_slam=False,
            W=W, H=H, w=4, h=4,
            v_walk=meta.get("v_walk", 150), v_jump_init=meta.get("v_jump", 180),
            physics_mode="c2",
        )
        safe = ~B[t + 1][nxt[:, 1], nxt[:, 0]]
        kept = nxt[safe]
        if len(kept):
            pk = pack_states_array(kept)
            uniq, first = np.unique(pk, return_index=True)
            states = kept[first]
            packed = uniq
        else:
            print(f"dead at {t}")
            return 0

        if t in REPORT_FRAMES:
            vy = states[:, 2]
            kappa = states[:, 3]
            tau = states[:, 4]
            xy = states[:, 0].astype(np.int64) * 1000 + states[:, 1]
            counts = collections.Counter(xy.tolist())
            multi = {k: v for k, v in counts.items() if v > 1}
            print(f"===== frame {t}: N={len(states):,}  distinct (x,y)={len(counts):,}"
                  f"  ratio={len(states)/len(counts):.2f}")
            print(f"  distinct vy = {len(np.unique(vy))}"
                  f"   distinct kappa = {len(np.unique(kappa))}"
                  f"   distinct tau = {len(np.unique(tau))}")
            print(f"  kappa histogram: "
                  f"{dict(collections.Counter(kappa.tolist()))}")
            print(f"  vy min/max = {vy.min()} .. {vy.max()}  (scaled by VY_SCALE)")
            print(f"  states on >1 per cell: {sum(multi.values()):,}"
                  f"   max multiplicity = {max(counts.values())}")
            # Detail for the busiest cell and a floor cell
            for target in sorted(multi, key=lambda k: -multi[k])[:3]:
                cx, cy = divmod(target, 1000)
                sel = xy == target
                trio = sorted(zip(vy[sel].tolist(), kappa[sel].tolist(), tau[sel].tolist()))
                print(f"    cell (x={cx}, y={cy})  n={sel.sum()}  "
                      f"(vy,kappa,tau) = {trio}")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
