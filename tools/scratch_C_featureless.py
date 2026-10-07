#!/usr/bin/env python3
"""VERIFY_C scratch: featureless-arena left/right drift probe.

Builds B_hazard = zeros((T, H, W), bool) (no hazard anywhere), initial_state =
(x0, 0), metadata = {"slam_frames": [T-2]} so the solver's empty-arena fast
path (solver.py:222) cannot short-circuit and the real DP + backtrack runs.

Usage: python tools/scratch_C_featureless.py <x0> [T] [W] [H]
Read-only audit tool: imports the package, changes nothing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from nohit.common.types import BakeResult  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402
from nohit.engine.state import unpack_state  # noqa: E402


def rle(vals):
    out = []
    for v in vals:
        v = tuple(int(t) for t in v) if isinstance(v, (tuple, list, np.ndarray)) else int(v)
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def main() -> int:
    x0 = int(sys.argv[1]) if len(sys.argv) > 1 else 174
    T = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    W = int(sys.argv[3]) if len(sys.argv) > 3 else 349
    H = int(sys.argv[4]) if len(sys.argv) > 4 else 114
    y0 = 0
    phys = sys.argv[5] if len(sys.argv) > 5 else "docs"
    if phys == "c2":
        md = {"slam_frames": [T - 2], "physics_mode": "c2", "v_walk": 150,
              "v_jump": 180, "soul_size": (4, 4)}
    else:
        md = {"slam_frames": [T - 2]}
    B = np.zeros((T, H, W), dtype=bool)
    bake = BakeResult(B_hazard=B, platform_table=[[] for _ in range(T)],
                      initial_state=(x0, y0), metadata=md)
    print(f"arena T={T} H={H} W={W} x0={x0} y0={y0} metadata={md}")
    print("hazard any:", bool(np.any(B)))

    t0 = time.perf_counter()
    sol = solve_lattice_dp(bake)
    dt = time.perf_counter() - t0
    print(f"solve wall time: {dt:.1f}s  dp_ms={sol.stats.dp_solve_time_ms:.1f}")
    print("is_deadlock:", sol.is_deadlock, sol.deadlock_frame)
    if sol.is_deadlock:
        return 0
    print("peak_alive :", sol.stats.peak_alive_states)
    print("total_expl :", sol.stats.total_states_explored)
    print("alive[:12] :", sol.stats.alive_states_history[:12])
    print("alive[-5:] :", sol.stats.alive_states_history[-5:])
    print("len(actions):", len(sol.action_sequence), "len(traj):", len(sol.trajectory))

    acts = [tuple(int(v) for v in a) for a in sol.action_sequence]
    print("action string (raw, as one line 'ux,uy;...'):")
    print(";".join(f"{a[0]},{a[1]}" for a in acts))
    print("RLE:", json.dumps([[list(a), n] for a, n in rle(acts)]))
    print("action histogram:", {str(k): int(v) for k, v in
                                zip(*np.unique(np.array(acts), axis=0, return_counts=True))})

    traj = sol.trajectory
    xs = [int(s[0]) for s in traj]
    print("traj x[0..T-1]:", xs)
    print("traj x RLE    :", json.dumps(rle(xs)))
    print("traj x[0], x[-1]:", xs[0], xs[-1], " net drift:", xs[-1] - xs[0])
    print("traj f0 :", tuple(int(v) for v in traj[0]))
    print("traj f-1:", tuple(int(v) for v in traj[-1]))
    print("verify traj[0] == initial_state:",
          tuple(int(v) for v in traj[0]) == (x0, y0, 0, 1, 0))
    # does the backtracked chain actually start at the init state?
    packed0 = int(np.uint32(0))  # placeholder
    from nohit.engine.state import pack_state
    print("pack(init) =", pack_state(x0, y0, 0, 1, 0),
          " pack(traj[0]) =", pack_state(*[int(v) for v in traj[0]]))
    # replay the extracted actions through the independent scalar stepper
    from nohit.verifier.replayer import replay_and_verify
    ver = replay_and_verify(bake, acts)
    rt = ver.simulated_trajectory
    rxs = [int(s[0]) for s in rt]
    print("replay passed:", ver.passed, "collisions:", ver.collision_frames,
          "kin_errors:", ver.kinematic_errors)
    print("replay x[0..T-1]:", rxs)
    print("replay x RLE   :", json.dumps(rle(rxs)))
    print("replay net drift:", rxs[-1] - rxs[0])
    n = min(len(traj), len(rt))
    A = np.array([[int(v) for v in s] for s in traj[:n]], dtype=np.int64)
    Bm = np.array([[int(v) for v in s] for s in rt[:n]], dtype=np.int64)
    d = np.abs(A - Bm)
    print("max|sol.traj - replay| over 5 comps:", int(d.max()),
          " max|dx|:", int(d[:, 0].max()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
