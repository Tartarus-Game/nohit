#!/usr/bin/env python3
"""Profiles one solve and prints the top cumulative-time functions.

A full-round `sans_bonegap1` solve takes ~23 s, which is far too slow for a
"millisecond DP" -- the lattice is only 349 px wide, so the state count should
be in the thousands, not the 14.7 M state-visits this currently performs.

Run:  python tools/profile_solve.py [wave] [--top N]
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wave", nargs="?", default="sans_bonegap1")
    ap.add_argument("--top", type=int, default=18)
    args = ap.parse_args()

    wave = args.wave if args.wave.endswith(".csv") else args.wave + ".csv"

    from nohit.baker.dilator import bake_cspace
    from nohit.engine.solver import solve_lattice_dp

    bake = bake_cspace(GAME / wave, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2")
    print(f"{wave}   T={bake.B_hazard.shape[0]}  arena={bake.B_hazard.shape[2]}x{bake.B_hazard.shape[1]}")

    t0 = time.perf_counter()
    prof = cProfile.Profile()
    prof.enable()
    sol = solve_lattice_dp(bake)
    prof.disable()
    wall = (time.perf_counter() - t0) * 1000.0

    h = sol.stats.alive_states_history
    print(f"wall={wall:.0f}ms  peak_states={max(h):,}  mean={sum(h)/len(h):,.0f}"
          f"  visits={sum(h)/1e6:.2f}M")
    print()
    buf = io.StringIO()
    pstats.Stats(prof, stream=buf).sort_stats("tottime").print_stats(args.top)
    for line in buf.getvalue().splitlines():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
