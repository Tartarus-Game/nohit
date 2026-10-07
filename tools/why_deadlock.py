#!/usr/bin/env python3
"""Why does the solver deadlock at frame 117 on sans_bonegap1?

Dumps, for the frames around the deadlock, the free (non-hazard) cells in the
heart's row band, so it is clear whether the heart ran out of space or whether
the solver lost the path for another reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"


def main() -> int:
    bake = bake_cspace(
        GAME / "sans_bonegap1.csv", T=199, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2"
    )
    B = bake.B_hazard
    T, H, W = B.shape
    print(f"arena {W}x{H}  init={bake.initial_state}")
    sol = solve_lattice_dp(bake)
    print(f"solver: deadlock={sol.is_deadlock} at={sol.deadlock_frame}\n")

    x0, y0 = bake.initial_state
    for t in (100, 110, 115, 116, 117, 118, 120, 130):
        if t >= T:
            continue
        row = B[t]
        # free columns anywhere in the arena
        free_cols = np.where(~row.any(axis=0))[0]
        # free columns at the heart's own row band (y .. y+3)
        band = row[y0 : y0 + 4, :]
        free_band = np.where(~band.any(axis=0))[0]
        # contiguous runs of free columns in the band
        runs = []
        if len(free_band):
            start = free_band[0]
            prev = free_band[0]
            for c in free_band[1:]:
                if c != prev + 1:
                    runs.append((start, prev))
                    start = c
                prev = c
            runs.append((start, prev))
        print(f"  t={t:>3}  危险格={row.sum():>6}  全高空闲列={len(free_cols):>4}  "
              f"心脏行(y={y0})空闲列={len(free_band):>4}  连续段={runs[:6]}")

    print()
    print("骨头在 t=117 覆盖的 x 区间（按 danger 行的连通块）:")
    row = B[117]
    cols = np.where(row.any(axis=0))[0]
    if len(cols):
        blocks = []
        s = cols[0]
        p = cols[0]
        for c in cols[1:]:
            if c != p + 1:
                blocks.append((s, p))
                s = c
            p = c
        blocks.append((s, p))
        print(f"  {len(blocks)} 个危险列块: {blocks}")
        gaps = [(blocks[i][1] + 1, blocks[i + 1][0] - 1) for i in range(len(blocks) - 1)]
        print(f"  块间空隙: {[g for g in gaps if g[1] >= g[0]]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
