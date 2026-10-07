#!/usr/bin/env python3
"""Solves every wave in PARALLEL and reports a one-line summary per wave.

The sequential sweep takes many minutes because a full-round solve costs
seconds-to-minutes per wave (`sans_boneslideh` alone is ~4 minutes). Each wave is
completely independent -- it bakes its own hazard tensor and runs its own DP, and
writes nothing -- so `ProcessPoolExecutor` parallelises it cleanly with no shared
state.

Usage:
    python tools/solve_all_parallel.py [--workers N] [--waves a,b,c] [--verify]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"


def solve_one(wave: str, verify: bool) -> dict:
    """Bake + solve (and optionally replay) a single wave. Runs in a worker."""
    t0 = time.perf_counter()
    try:
        from nohit.baker.dilator import bake_cspace
        from nohit.engine.solver import solve_lattice_dp

        bake = bake_cspace(GAME / wave, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2")
        T = bake.B_hazard.shape[0]
        sol = solve_lattice_dp(bake)
        ms = (time.perf_counter() - t0) * 1000.0

        if sol.is_deadlock:
            return {"wave": wave, "T": T, "status": f"DL@{sol.deadlock_frame}",
                    "ms": ms, "pid": os.getpid()}

        nz = sum(1 for a in sol.action_sequence if a[0] or a[1])
        xs = [p[0] for p in sol.trajectory]
        ys = [p[1] for p in sol.trajectory]
        row = {
            "wave": wave, "T": T, "status": "no", "nz": nz, "ms": ms,
            "x": (min(xs), max(xs)), "y": (min(ys), max(ys)), "pid": os.getpid(),
        }
        if verify:
            from nohit.verifier.replayer import replay_and_verify

            row["replay"] = "PASS" if replay_and_verify(bake, sol.action_sequence).passed else "FAIL"
        return row
    except Exception as exc:  # a worker must never kill the whole sweep
        return {"wave": wave, "status": f"ERROR {type(exc).__name__}: {exc}",
                "ms": (time.perf_counter() - t0) * 1000.0, "pid": os.getpid()}


DEFAULT_WAVES = [
    "sans_bonegap1", "sans_bluebone", "sans_bonestab1", "sans_bonestab2",
    "sans_bonestab3", "sans_boneslidev", "sans_boneslideh", "sans_spare",
    "sans_intro", "sans_platforms1", "sans_platforms2", "sans_gravityzone",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=0,
                    help="parallel workers (default: cpu_count - 1, min 1)")
    ap.add_argument("--waves", default="", help="comma separated wave names (no .csv)")
    ap.add_argument("--verify", action="store_true", help="also run replay_and_verify")
    args = ap.parse_args()

    waves = [w.strip() for w in args.waves.split(",") if w.strip()] or DEFAULT_WAVES
    waves = [w if w.endswith(".csv") else w + ".csv" for w in waves]
    waves = [w for w in waves if (GAME / w).is_file()]

    nw = args.workers or max(1, (os.cpu_count() or 2) - 1)
    wall0 = time.perf_counter()
    print(f"{len(waves)} waves on {nw} workers (cpu_count={os.cpu_count()})"
          f"{'  +replay' if args.verify else ''}", flush=True)
    print(f"{'wave':<20}{'T':>5}{'status':>10}{'nz':>6}{'x range':>14}{'y range':>12}"
          f"{'replay':>8}{'ms':>9}", flush=True)

    rows: list[dict] = []
    with cf.ProcessPoolExecutor(max_workers=nw) as pool:
        futs = {pool.submit(solve_one, w, args.verify): w for w in waves}
        for fut in cf.as_completed(futs):
            r = fut.result()
            rows.append(r)
            if "nz" in r:
                print(f"{r['wave']:<20}{r['T']:>5}{r['status']:>10}{r['nz']:>6}"
                      f"{str(r['x']):>14}{str(r['y']):>12}{r.get('replay','-'):>8}"
                      f"{r['ms']:>9.0f}", flush=True)
            else:
                print(f"{r['wave']:<20}{'-':>5}{r['status']:>10}{'-':>6}{'-':>14}"
                      f"{'-':>12}{'-':>8}{r['ms']:>9.0f}", flush=True)

    wall = time.perf_counter() - wall0
    cpu = sum(r["ms"] for r in rows) / 1000.0
    ok = sum(1 for r in rows if r["status"] == "no" and r.get("replay", "PASS") == "PASS")
    print(f"\n{ok}/{len(rows)} solvable+verified   wall={wall:.1f}s   cpu={cpu:.1f}s"
          f"   speedup={cpu / wall if wall else 0:.1f}x", flush=True)
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
