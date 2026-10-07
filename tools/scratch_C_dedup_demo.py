#!/usr/bin/env python3
"""VERIFY_C scratch: micro-demonstration of the two tie-breaking mechanisms in
the handed (audit-start) solver revision.

(1) dedup tie-break:  solver.py (handed) line 411
        unq_packed, best_idx = np.unique(val_packed, return_index=True)
    `return_index` yields the FIRST occurrence in the candidate array, and that
    array is ordered (parent-major, action-index-minor). ACTIONS[0] = (-1,0).

(2) terminal tie-break: solver.py (handed) line 448
        best_term_idx = int(np.argmax(curr_vals))
    with all values tied, argmax returns 0 and curr_packed is key-sorted
    ascending, so the pick is the state with the smallest packed key.

Read-only: nothing under nohit/ is written.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from nohit.common.constants import ACTIONS  # noqa: E402
from nohit.engine.dynamics import step_dynamics_batch  # noqa: E402
from nohit.engine.state import pack_state, pack_states_array, unpack_state  # noqa: E402


def main() -> int:
    print("ACTIONS as defined in nohit/common/constants.py:108-115")
    for i, a in enumerate(ACTIONS):
        print(f"  index {i}: (ux={a[0]:+d}, uy={a[1]})"
              f"{'   <-- LEFT' if a[0] == -1 else ''}")
    print("=> (-1,0) [LEFT] is index 0; (+1,0) [RIGHT] is index 4.")

    print("\n(1) candidate array order + np.unique(return_index=True)")
    for parent_x in (0, 3, 174):
        parent = np.array([[parent_x, 0, 0, 1, 0]], dtype=np.int32)
        rep = np.repeat(parent, 6, axis=0)
        idx = np.arange(6, dtype=np.uint8)
        ux = np.array([ACTIONS[i][0] for i in idx], dtype=np.int8)
        uy = np.array([ACTIONS[i][1] for i in idx], dtype=np.int8)
        nxt = step_dynamics_batch(rep, ux, uy, W=349, H=114, w=8, h=8,
                                 v_walk=3, v_jump_init=8, physics_mode="docs")
        keys = pack_states_array(nxt)
        unq, first = np.unique(keys, return_index=True)
        collisions = len(keys) - len(unq)
        print(f"  parent x={parent_x}: 6 candidates -> {len(unq)} unique keys "
              f"({collisions} collisions)")
        for j in range(6):
            print(f"      cand[{j}] action={tuple(int(v) for v in ACTIONS[j])!s:<8} "
                  f"-> state {tuple(int(v) for v in nxt[j])} key={int(keys[j])}")
        kept = [(int(first[k]), tuple(int(v) for v in ACTIONS[int(first[k])]),
                 unpack_state(int(unq[k]))) for k in range(len(unq))]
        print(f"      np.unique(return_index=True) kept:")
        for fi, act, st in kept:
            print(f"        first-occurrence index {fi} -> action {act} -> state {st}")

    print("\n(2) terminal tie-break on an all-tied value array")
    demo = np.array([pack_state(x, 0, 0, 1, 0) for x in (174, 171, 3, 0)],
                    dtype=np.uint32)
    order = np.argsort(demo)
    sorted_keys = demo[order]
    vals = np.zeros(4, dtype=np.float32)
    print("  curr_packed (key-sorted, as np.unique/argsort produce it):")
    for k in sorted_keys:
        print(f"    key={int(k)} -> {unpack_state(int(k))}")
    print(f"  curr_vals = {vals}  -> np.argmax = {int(np.argmax(vals))}")
    print(f"  curr_packed[argmax] = {unpack_state(int(sorted_keys[int(np.argmax(vals))]))}")
    print("  i.e. the x smallest state wins whenever the values tie.")
    print("\n  packed key = x | (y<<9) | ((vy+500)<<17) | (kappa<<27) | (tau<<28),")
    print("  so for a fixed (y, vy, kappa, tau) the key is monotone in x:")
    for x in (0, 3, 174, 341):
        print(f"    x={x:>3} -> key {pack_state(x, 0, 0, 1, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
