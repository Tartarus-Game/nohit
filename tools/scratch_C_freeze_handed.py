#!/usr/bin/env python3
"""VERIFY_C scratch: reconstruct the solver revision that was on disk when this
audit started (19216 bytes, read at session start) and verify the
reconstruction byte-for-byte against the recorded size.

The live file changed at 03:34:31 (19216 -> 21013 bytes) mid-audit. The live
revision differs from the audit-start revision ONLY inside the no-hazard
`else:` dedup block of solve_lattice_dp (verified by side-by-side read of both
revisions); this script puts that block back and checks the result is exactly
19216 bytes / 486 lines, which pins the reconstruction.

Writes tools/scratch_C_solver_handed.py. Nothing under nohit/ is touched.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "nohit" / "engine" / "solver.py"
OUT = ROOT / "tools" / "scratch_C_solver_handed.py"

NEW_BLOCK = '''        else:
            # Open arena: no obstacles at all. Every survivor is equally safe, so
            # the ONLY thing to rank by is input cost -- and ties must not be
            # broken by action index.
            #
            # `np.unique(val_packed, return_index=True)` looks like a drop-in
            # dedup, but `return_index` yields the FIRST occurrence in the
            # CANDIDATE array, and that array is built as
            # `np.repeat(states, 6)` x `np.tile(arange(6), N)`, so within one
            # state the candidates sit in action-index order. Action index 0 is
            # `ux = -1` (LEFT), so the dedup silently kept the left-moving parent.
            #
            # Measured consequence: on a completely EMPTY arena the extracted
            # path pressed (-1,0) on all 149 frames and parked the heart against
            # the left wall from any start x (50 -> 0, 174 -> 0, 320 -> 0). There
            # was nothing to dodge, so that was pure artefact -- and on
            # sans_bonegap1 it is why the plan ran left into the corner.
            #
            # Rank by accumulated value first (cheapest route wins), then by
            # packed state so `P_keys` stays sorted: the O(T) backtracking uses
            # `np.searchsorted(P_keys[t], target)` and a non-monotone key array
            # makes it return a bogus index (it crashed with IndexError before
            # this tie-break was added).
            cand_vals = rep_vals[safe] - act_cost
            # Descending value -> descending uint32 rank, so lexsort picks the
            # cheapest parent for each packed state. Built in float64 then
            # converted (a uint64 view of a float would be meaningless).
            top = float(np.abs(cand_vals).max()) if len(cand_vals) else 0.0
            rank = (cand_vals - cand_vals.min()) / (top + 1e-9)
            combo = ((1.0 - rank) * 4294967295.0).astype(np.uint64)
            order = np.lexsort((combo, val_packed))
            s_packed = val_packed[order]
            mask = np.empty(len(order), dtype=bool)
            mask[0] = True
            mask[1:] = s_packed[1:] != s_packed[:-1]
            best_idx = order[mask]
            unq_packed = val_packed[best_idx]
            curr_vals = cand_vals[best_idx]
'''

OLD_BLOCK = '''        else:
            # Open arena: no obstacles at all, so there is nothing to trade off
            # and every survivor is equally safe. Keep the high-throughput
            # dedup path (the min-action sort here cost ~40% of the whole solve
            # on the open-arena benchmarks while changing nothing meaningful).
            cand_vals = rep_vals[safe]
            unq_packed, best_idx = np.unique(val_packed, return_index=True)
            curr_vals = cand_vals[best_idx]
'''


def main() -> int:
    text = LIVE.read_text(encoding="utf-8")
    print("live file  :", LIVE)
    print("live bytes :", len(text.encode()), " sha256:",
          hashlib.sha256(text.encode()).hexdigest())
    if NEW_BLOCK not in text:
        print("!! new block not found verbatim; aborting")
        return 1
    restored = text.replace(NEW_BLOCK, OLD_BLOCK)
    OUT.write_text(restored, encoding="utf-8", newline="")
    b = OUT.read_text(encoding="utf-8").encode()
    print("\nrestored   :", OUT)
    print("restored bytes:", len(b), " (audit-start revision was 19216)")
    print("restored lines:", restored.count("\n") + (0 if restored.endswith("\n") else 1))
    print("sha256     :", hashlib.sha256(b).hexdigest())
    print("byte-size match with audit-start revision:", len(b) == 19216)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
