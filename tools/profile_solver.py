#!/usr/bin/env python3
"""Profiles the no-hazard DP path (the open-arena benchmark) at 30 Hz.

The benchmark is an empty arena with T=150, so it exercises the branch that
expands every alive state across all 7 actions with no obstacle pruning. At
30 Hz the stride is 5 px instead of 2.5 px, so the reachable set is larger and
the step cost grew.
"""

from __future__ import annotations

import cProfile
import pstats
import sys
import time
from io import StringIO
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.common.types import BakeResult  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402

DEFAULT_W, DEFAULT_H = 349, 114
T = 150


def main() -> int:
    B = np.zeros((T, DEFAULT_H, DEFAULT_W), dtype=bool)
    bake = BakeResult(
        B_hazard=B,
        platform_table=[[] for _ in range(T)],
        initial_state=(96, 0),
        metadata={},
    )

    # warm up
    solve_lattice_dp(bake)

    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        res = solve_lattice_dp(bake)
        times.append((time.perf_counter() - t0) * 1000.0)
    print(f"open-arena T={T}: peak={res.stats.peak_alive_states}  "
          f"times={[f'{t:.0f}' for t in times]} ms  min={min(times):.0f} median={sorted(times)[2]:.0f}")

    pr = cProfile.Profile()
    pr.enable()
    solve_lattice_dp(bake)
    pr.disable()
    buf = StringIO()
    pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(18)
    print()
    print(buf.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
