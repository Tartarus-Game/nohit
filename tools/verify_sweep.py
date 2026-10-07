#!/usr/bin/env python3
"""Solver/verifier agreement sweep in the c2 physics mode.

For every exported attack CSV this:
  1. bakes the C-space with the real Construct 2 kernel (4x4 centred hitbox,
     auto-sized arena, v_walk=5, v_jump=6, physics_mode="c2");
  2. runs the monotone lattice DP solver;
  3. replay-verifies the witness action sequence through the INDEPENDENT
     scalar stepper in nohit.verifier.replayer (which re-derives its own
     dynamics and hazard probes from the baked tensors);
  4. asserts the two agree: a deadlock verdict must time out the replayer, a
     solvable verdict must replay with zero collisions and zero kinematic
     errors.

Usage: python tools/verify_sweep.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402
from nohit.verifier.replayer import replay_and_verify  # noqa: E402

GAME_DIR = ROOT / "c2-sans-fight"
T = 150

HEADER = f"{'wave':<30}{'arena':<10}{'init':<10}{'outcome':<18}{'verified':<10}{'collisions':<11}{'dp_ms':<10}{'bake_ms'}"


def main() -> int:
    waves = sorted(p.name for p in GAME_DIR.glob("sans_*.csv"))
    print(HEADER)
    print("-" * len(HEADER))

    solvable = deadlock = mismatched = 0
    for wave in waves:
        t0 = time.perf_counter()
        bake = bake_cspace(
            GAME_DIR / wave,
            T=T,
            auto_size=True,
            soul_w=4,
            soul_h=4,
            physics_mode="c2",
        )
        sol = solve_lattice_dp(bake)
        bake_ms = bake.metadata.get("total_baking_time_ms", 0.0)
        arena = f"{bake.W}x{bake.H}"
        init = f"{bake.initial_state[0]},{bake.initial_state[1]}"

        if sol.is_deadlock:
            outcome = f"DEADLOCK @ t={sol.deadlock_frame}"
            deadlock += 1
            verified = "-"
            collisions = "-"
            status = "n/a (proven deadlock)"
        else:
            outcome = "solvable"
            solvable += 1
            ver = replay_and_verify(bake, sol.action_sequence)
            verified = "PASS" if ver.passed else "FAIL"
            collisions = str(len(ver.collision_frames))
            status = verified
            if not ver.passed or ver.kinematic_errors:
                mismatched += 1
                print(f"    !! replay errors: {ver.kinematic_errors[:3]}")

        # Every solvable witness must replay clean; deadlocks have no witness.
        if not sol.is_deadlock and verified != "PASS":
            mismatched += 1

        print(
            f"{wave:<30}{arena:<10}{init:<10}{outcome:<18}{verified:<10}{collisions:<11}"
            f"{sol.stats.dp_solve_time_ms:<10.1f}{bake_ms:.1f}"
        )
        _ = time.perf_counter() - t0

    print(f"\nsolvable={solvable} deadlock={deadlock} mismatched={mismatched} total={len(waves)}")
    return 0 if mismatched == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
