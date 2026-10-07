#!/usr/bin/env python3
"""Cheap proof-of-concept: does sub-pixel position actually unblock the deadlock?

Trick: rasterize at 10x scale (arena W*10, H*10) and feed the solver a step
displacement of HEARTSPEED/60*10 = 25 units per frame. That is exactly the
geometry a 1/10-px model would produce, but it needs no change to dynamics.py or
state.py -- so it can be run before committing to the 64-bit refactor.

If the scaled solve is solvable, the 1-px position quantisation was the blocker
and the refactor is justified. If it still deadlocks at a similar frame, the
problem is elsewhere (hazard geometry / collision model), and widening the key
would not have helped.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"


def scale_bake(bake, factor: int):
    """Nearest-neighbour upsample of the hazard tensor + scaled platforms."""
    B = bake.B_hazard
    T, H, W = B.shape
    Bs = np.repeat(np.repeat(B, factor, axis=1), factor, axis=2)

    plat_table = []
    for frame in bake.platform_table:
        row = []
        for p in frame:
            row.append(
                type(p)(
                    plat_id=getattr(p, "plat_id", 0),
                    x_left=float(getattr(p, "x_left", getattr(p, "x_min", 0.0))) * factor,
                    x_right=float(getattr(p, "x_right", getattr(p, "x_max", 0.0))) * factor,
                    y_surf=int(getattr(p, "y_surf", getattr(p, "y_top", 0))) * factor,
                    vx=float(getattr(p, "vx", 0.0)) * factor / factor,
                )
            )
        plat_table.append(row)

    init = (bake.initial_state[0] * factor, bake.initial_state[1] * factor)
    meta = dict(bake.metadata or {})
    meta["soul_size"] = tuple(s * factor for s in meta.get("soul_size", (4, 4)))
    return Bs, plat_table, init, meta


def main() -> int:
    from nohit.common.types import BakeResult

    waves = sys.argv[1:] or ["sans_bonegap1", "sans_spare", "sans_bluebone"]
    FACTOR = 10

    print("=" * 78)
    print(f"1/{FACTOR} px resolution experiment (arena x{FACTOR}, step {150 / 60 * FACTOR:.0f} units/frame)")
    print("=" * 78)

    for wave in waves:
        bake = bake_cspace(
            GAME / f"{wave}.csv", T=199, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2"
        )
        Bs, plat, init, meta = scale_bake(bake, FACTOR)

        # Scale the arena bounds so the solver's W/H cover the upsampled grid.
        scaled = BakeResult(
            B_hazard=Bs,
            platform_table=plat,
            initial_state=init,
            metadata=meta,
        )
        # The solver reads W/H from B_hazard.shape, and the step displacement
        # comes from metadata v_walk; set it so 150 px/s / 60 * FACTOR holds.
        scaled.metadata["v_walk"] = 150 * FACTOR
        scaled.metadata["v_jump"] = 180 * FACTOR
        scaled.metadata["soul_size"] = (4 * FACTOR, 4 * FACTOR)

        t0 = time.perf_counter()
        try:
            sol = solve_lattice_dp(scaled)
            ms = (time.perf_counter() - t0) * 1000
            print(f"  {wave:<18} deadlock={sol.is_deadlock!s:<6} at={sol.deadlock_frame!s:<6} "
                  f"peak={sol.stats.peak_alive_states:<8} dp={ms:8.1f} ms")
        except Exception as exc:  # noqa: BLE001
            print(f"  {wave:<18} ERROR {type(exc).__name__}: {exc}")

    print()
    print("  reference (1 px model, same T):")
    for wave in waves:
        bake = bake_cspace(
            GAME / f"{wave}.csv", T=199, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2"
        )
        sol = solve_lattice_dp(bake)
        print(f"  {wave:<18} deadlock={sol.is_deadlock!s:<6} at={sol.deadlock_frame!s:<6} "
              f"peak={sol.stats.peak_alive_states}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
