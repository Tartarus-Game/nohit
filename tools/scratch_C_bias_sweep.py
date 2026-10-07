#!/usr/bin/env python3
"""VERIFY_C scratch: left/right bias sweep.

Two variants of solve_lattice_dp can be loaded:
  handed = the revision that was on disk when this audit started (frozen as
           tools/scratch_C_solver_handed.py, 19216 bytes / 486 lines)
  live   = whatever nohit/engine/solver.py contains right now

Modes:
  featureless <variant> <x0> [T] [W] [H]
      B_hazard = zeros((T,H,W), bool), initial_state=(x0,0),
      metadata={"slam_frames":[T-2]}  (forces the real DP past the fast path).
  wave <variant> <cfg>
      cfg = c2auto        : bake_cspace(sans_bonegap1.csv, T=150, auto_size=True,
                            soul 4x4, physics_mode="c2")  -> repo's canonical config
      cfg = c2auto_docsmeta: same baked tensors, but metadata={} so the DP runs
                            the docs stepper (v_walk=3 px/frame) on c2 geometry.

Read-only audit tool: nothing under nohit/ is written.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from nohit.common.types import BakeResult  # noqa: E402
from nohit.engine.state import pack_state, unpack_state  # noqa: E402
from nohit.verifier.replayer import replay_and_verify  # noqa: E402

GAME = ROOT / "c2-sans-fight"


def load_solver(variant: str):
    if variant == "handed":
        path = ROOT / "tools" / "scratch_C_solver_handed.py"
        spec = importlib.util.spec_from_file_location("solver_handed", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.solve_lattice_dp
    from nohit.engine.solver import solve_lattice_dp
    return solve_lattice_dp


def rle(vals):
    out = []
    for v in vals:
        v = tuple(int(t) for t in v) if isinstance(v, (tuple, list, np.ndarray)) else int(v)
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def report(sol, bake, variant, tag):
    acts = [tuple(int(v) for v in a) for a in sol.action_sequence]
    x0, y0 = int(bake.initial_state[0]), int(bake.initial_state[1])
    print(f"\n--- {tag} [{variant}] ---")
    print("is_deadlock        :", sol.is_deadlock, sol.deadlock_frame)
    print("peak_alive/total   :", sol.stats.peak_alive_states, sol.stats.total_states_explored)
    print("action string      :", ";".join(f"{a[0]},{a[1]}" for a in acts))
    print("action RLE         :", json.dumps([[list(a), n] for a, n in rle(acts)], separators=(",", ":")))
    print("action histogram   :", {str(k): int(v) for k, v in
                                  zip(*np.unique(np.array(acts), axis=0, return_counts=True))})
    print("left/right/idle    :",
          sum(1 for a in acts if a[0] == -1), "/",
          sum(1 for a in acts if a[0] == 1), "/",
          sum(1 for a in acts if a[0] == 0))
    xs = [int(s[0]) for s in sol.trajectory]
    print("traj x RLE         :", json.dumps(rle(xs), separators=(",", ":")))
    print("traj x[0], x[-1]   :", xs[0], xs[-1], " net drift:", xs[-1] - xs[0])
    print("traj[0] == init?   :", tuple(int(v) for v in sol.trajectory[0]) == (x0, y0, 0, 1, 0),
          tuple(int(v) for v in sol.trajectory[0]))
    print("traj[-1] terminal  :", tuple(int(v) for v in sol.trajectory[-1]))
    ver = replay_and_verify(bake, acts)
    rt = ver.simulated_trajectory
    rxs = [int(s[0]) for s in rt]
    print("replay passed      :", ver.passed, "collisions:", ver.collision_frames,
          "kin_errors:", ver.kinematic_errors[:2])
    print("replay x RLE       :", json.dumps(rle(rxs), separators=(",", ":")))
    print("replay x[0], x[-1] :", rxs[0], rxs[-1], " net drift:", rxs[-1] - rxs[0])
    n = min(len(sol.trajectory), len(rt))
    A = np.array([[int(v) for v in s] for s in sol.trajectory[:n]], dtype=np.int64)
    B = np.array([[int(v) for v in s] for s in rt[:n]], dtype=np.int64)
    d = np.abs(A - B)
    print(f"MAX |sol.trajectory[f] - replay[f]| = {int(d.max())}"
          f"   (max|dx| = {int(d[:, 0].max())} at f={int(np.argmax(d[:, 0]))},"
          f" max|dy| = {int(d[:, 1].max())}, max|dvy| = {int(d[:, 2].max())},"
          f" max|dkappa| = {int(d[:, 3].max())}, max|dtau| = {int(d[:, 4].max())})")
    nz = np.nonzero(d.max(axis=1) > 0)[0]
    print("first differing frame:", int(nz[0]) if len(nz) else None,
          " n differing frames:", int(len(nz)))


def main() -> int:
    mode = sys.argv[1]
    variant = sys.argv[2]
    solve = load_solver(variant)
    if mode == "featureless":
        x0 = int(sys.argv[3])
        T = int(sys.argv[4]) if len(sys.argv) > 4 else 150
        W = int(sys.argv[5]) if len(sys.argv) > 5 else 349
        H = int(sys.argv[6]) if len(sys.argv) > 6 else 114
        md = {"slam_frames": [T - 2]}
        B = np.zeros((T, H, W), dtype=bool)
        bake = BakeResult(B_hazard=B, platform_table=[[] for _ in range(T)],
                          initial_state=(x0, 0), metadata=md)
        print(f"featureless arena: B_hazard=zeros(({T},{H},{W}),bool) "
              f"initial_state=({x0},0) metadata={md}")
        t0 = time.perf_counter()
        sol = solve(bake)
        print(f"solve wall time    : {time.perf_counter() - t0:.1f}s "
              f"(dp_ms={sol.stats.dp_solve_time_ms:.1f})")
        if sol.is_deadlock:
            print("DEADLOCK", sol.deadlock_frame)
            return 0
        report(sol, bake, variant, f"featureless x0={x0} T={T} W={W} H={H}")
        return 0

    if mode == "wave":
        cfg = sys.argv[3] if len(sys.argv) > 3 else "c2auto"
        Th = int(sys.argv[4]) if len(sys.argv) > 4 else 150
        from nohit.baker.dilator import bake_cspace
        bake = bake_cspace(GAME / "sans_bonegap1.csv", T=Th, auto_size=True,
                           soul_w=4, soul_h=4, physics_mode="c2")
        print("baked: shape", bake.B_hazard.shape, "init", bake.initial_state,
              "phys", bake.metadata.get("physics_mode"), "v_walk", bake.metadata.get("v_walk"),
              "soul", bake.metadata.get("soul_size"),
              "blue", bake.metadata.get("B_blue") is not None,
              "orange", bake.metadata.get("B_orange") is not None,
              "slam", bake.metadata.get("slam_frames"))
        if cfg == "c2auto_docsmeta":
            bake = BakeResult(B_hazard=bake.B_hazard, platform_table=bake.platform_table,
                              initial_state=bake.initial_state, metadata={})
            print("-> rebuilt with metadata={} (docs stepper, v_walk=3, soul 8x8)")
        t0 = time.perf_counter()
        sol = solve(bake)
        print(f"solve wall time    : {time.perf_counter() - t0:.1f}s "
              f"(dp_ms={sol.stats.dp_solve_time_ms:.1f})")
        if sol.is_deadlock:
            print("DEADLOCK", sol.deadlock_frame)
            return 0
        report(sol, bake, variant, f"sans_bonegap1 cfg={cfg}")
        return 0

    raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    raise SystemExit(main())
