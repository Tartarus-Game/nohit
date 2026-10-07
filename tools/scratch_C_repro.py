#!/usr/bin/env python3
"""VERIFY_C scratch: reproduce the sans_bonegap1 solve and compare
sol.trajectory against the independent replayer's simulated trajectory.

Read-only audit tool: imports the package, changes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402
from nohit.verifier.replayer import replay_and_verify  # noqa: E402

GAME = ROOT / "c2-sans-fight"


def rle(seq):
    out = []
    for a in seq:
        a = (int(a[0]), int(a[1]))
        if out and out[-1][0] == a:
            out[-1][1] += 1
        else:
            out.append([a, 1])
    return out


def main() -> int:
    T = 150
    bake = bake_cspace(GAME / "sans_bonegap1.csv", T=T, auto_size=True,
                       soul_w=4, soul_h=4, physics_mode="c2")
    md = bake.metadata
    print("== bake ==")
    print("B_hazard.shape :", bake.B_hazard.shape)
    print("initial_state  :", bake.initial_state)
    print("physics_mode   :", md.get("physics_mode"))
    print("v_walk / v_jump:", md.get("v_walk"), md.get("v_jump"))
    print("soul_size      :", md.get("soul_size"))
    print("slam_frames    :", md.get("slam_frames"))
    print("has B_blue     :", md.get("B_blue") is not None)
    print("has B_orange   :", md.get("B_orange") is not None)
    print("hazard any     :", bool(np.any(bake.B_hazard)), "density",
          round(float(bake.B_hazard.mean()), 5))
    print("platform frames with entries:",
          sum(1 for p in bake.platform_table if len(p)))

    sol = solve_lattice_dp(bake)
    print("\n== solve ==")
    print("is_deadlock    :", sol.is_deadlock, sol.deadlock_frame)
    print("T (actions)    :", len(sol.action_sequence), "T (traj)", len(sol.trajectory))
    print("peak_alive     :", sol.stats.peak_alive_states)
    print("dp_ms          :", round(sol.stats.dp_solve_time_ms, 1))

    acts = sol.action_sequence
    print("distinct actions used:", sorted({(int(a[0]), int(a[1])) for a in acts}))
    print("counts per action    :", {str(k): int(v) for k, v in
                                    zip(*np.unique(np.array(acts), axis=0, return_counts=True))})
    print("RLE (action,runlen)  :", json.dumps([[list(a), n] for a, n in rle(acts)]))

    traj = sol.trajectory
    xs = [int(s[0]) for s in traj]
    print("\nsolver traj x[0..T-1]  :", xs)
    print("solver traj x RLE      :", end=" ")
    r = []
    for x in xs:
        if r and r[-1][0] == x:
            r[-1][1] += 1
        else:
            r.append([x, 1])
    print(json.dumps([[x, n] for x, n in r]))
    print("traj state at f=0      :", tuple(int(v) for v in traj[0]))
    print("traj state at f=T-1    :", tuple(int(v) for v in traj[-1]))

    ver = replay_and_verify(bake, acts)
    print("\n== replay ==")
    print("passed         :", ver.passed)
    print("collision_frames:", ver.collision_frames)
    print("kinematic_errors:", ver.kinematic_errors)
    rt = ver.simulated_trajectory
    rxs = [int(s[0]) for s in rt]
    print("replay  x[0..T-1]      :", rxs)
    r2 = []
    for x in rxs:
        if r2 and r2[-1][0] == x:
            r2[-1][1] += 1
        else:
            r2.append([x, 1])
    print("replay  x RLE          :", json.dumps([[x, n] for x, n in r2]))

    # --- trajectory vs replay comparison -----------------------------------
    n = min(len(traj), len(rt))
    A = np.array([[int(v) for v in s] for s in traj[:n]], dtype=np.int64)
    B = np.array([[int(v) for v in s] for s in rt[:n]], dtype=np.int64)
    d = np.abs(A - B)
    per_frame_max = d.max(axis=1)
    print("\n== sol.trajectory vs replay ==")
    print("frames compared        :", n)
    print("max abs diff (all 5 comps):", int(d.max()))
    print("  -> max |dx|          :", int(d[:, 0].max()), "at frame",
          int(np.argmax(d[:, 0])))
    print("  -> max |dy|          :", int(d[:, 1].max()), "at frame",
          int(np.argmax(d[:, 1])))
    print("  -> max |dvy|         :", int(d[:, 2].max()))
    print("  -> max |dkappa|      :", int(d[:, 3].max()))
    print("  -> max |dtau|        :", int(d[:, 4].max()))
    first = int(np.argmax(per_frame_max > 0)) if np.any(per_frame_max > 0) else -1
    print("first differing frame  :", first)
    print("sol[first]  :", tuple(int(v) for v in traj[first]) if first >= 0 else None)
    print("repl[first] :", tuple(int(v) for v in rt[first]) if first >= 0 else None)
    print("dx per frame (sol - replay) decimated:",
          [int(v) for v in (A[:, 0] - B[:, 0])[::10]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
