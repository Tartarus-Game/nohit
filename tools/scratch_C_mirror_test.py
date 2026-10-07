#!/usr/bin/env python3
"""VERIFY_C scratch: mirror-symmetry control for the sans_bonegap1 left run.

sans_bonegap1 baked in the canonical c2 config has W=349, so the map
x -> 348 - x is an exact involution of the reachable domain and it fixes the
start x0=174. Mirroring B_hazard about that axis therefore describes the
physically mirrored round with the SAME start state.

* If the extracted plan on the mirrored tensor is the exact mirror of the plan
  on the original tensor (left run <-> right run), the left run is driven by the
  hazard geometry.
* If the mirrored tensor still produces a LEFT run, the preference is
  structural (index / packed-key ordering), not hazard-driven.

Usage: python tools/scratch_C_mirror_test.py <variant> [T]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.common.types import BakeResult  # noqa: E402
from nohit.verifier.replayer import replay_and_verify  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
from scratch_C_bias_sweep import load_solver, rle  # noqa: E402

GAME = ROOT / "c2-sans-fight"


def summarize(tag, sol, bake):
    acts = [tuple(int(v) for v in a) for a in sol.action_sequence]
    xs = [int(s[0]) for s in sol.trajectory]
    print(f"\n--- {tag} ---")
    print("action RLE      :", json.dumps([[list(a), n] for a, n in rle(acts)], separators=(",", ":")))
    print("left/right/idle :", sum(1 for a in acts if a[0] == -1), "/",
          sum(1 for a in acts if a[0] == 1), "/", sum(1 for a in acts if a[0] == 0))
    print("x RLE           :", json.dumps(rle(xs), separators=(",", ":")))
    print("x[0], x[-1]     :", xs[0], xs[-1], " terminal:", tuple(int(v) for v in sol.trajectory[-1]))
    ver = replay_and_verify(bake, acts)
    rt = ver.simulated_trajectory
    n = min(len(sol.trajectory), len(rt))
    A = np.array([[int(v) for v in s] for s in sol.trajectory[:n]], dtype=np.int64)
    B = np.array([[int(v) for v in s] for s in rt[:n]], dtype=np.int64)
    print("replay passed   :", ver.passed, "max|sol.traj - replay| =", int(np.abs(A - B).max()))
    return acts, xs


def main() -> int:
    variant = sys.argv[1] if len(sys.argv) > 1 else "handed"
    T = int(sys.argv[2]) if len(sys.argv) > 2 else 385
    bake = bake_cspace(GAME / "sans_bonegap1.csv", T=T, auto_size=True,
                       soul_w=4, soul_h=4, physics_mode="c2")
    print(f"baked T={T} shape={bake.B_hazard.shape} init={bake.initial_state} "
          f"phys={bake.metadata.get('physics_mode')} W={bake.W}")
    solve = load_solver(variant)

    solA = solve(bake)
    actsA, xsA = summarize(f"ORIGINAL  [{variant}] T={T}", solA, bake)

    Bm = BakeResult(B_hazard=bake.B_hazard[:, :, ::-1].copy(),
                    platform_table=bake.platform_table,
                    initial_state=bake.initial_state,
                    metadata=bake.metadata)
    solB = solve(Bm)
    actsB, xsB = summarize(f"X-MIRRORED [{variant}] T={T}", solB, Bm)

    # Does the mirrored plan equal the mirror of the original plan?
    mirA_acts = [(-a[0], a[1]) for a in actsA]
    n = min(len(mirA_acts), len(actsB))
    same = sum(1 for i in range(n) if mirA_acts[i] == actsB[i])
    mirA_x = [348 - x for x in xsA]
    xs_same = sum(1 for i in range(min(len(mirA_x), len(xsB))) if mirA_x[i] == xsB[i])
    print(f"\nMIRROR CHECK: mirrored-original action == mirrored-run action for "
          f"{same}/{n} frames; mirrored-original x == mirrored-run x for "
          f"{xs_same}/{len(xsB)} frames")
    print("VERDICT:", "hazard-geometry driven (plan mirrors)" if same > 0.9 * n
          else "STRUCTURAL left preference (mirrored arena still goes left)"
          if sum(1 for a in actsB if a[0] == -1) > 2 * sum(1 for a in actsB if a[0] == 1)
          else "mixed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
