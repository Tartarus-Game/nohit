#!/usr/bin/env python3
"""Checks whether widening the DP key to 64 bits (needed for sub-pixel
positions) actually costs anything, and how much precision the arena allows.

Current key: 32 bits, position quantised to 1 px.
Wanted:      sub-pixel position. At 1/10 px the arena indexes need 12 (x) + 11
             (y) bits, so 32 bits is not enough and the key must widen.
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402


def bench_key_width() -> None:
    print("=" * 74)
    print("1. uint32 vs uint64 key: 排序/去重成本")
    print("=" * 74)
    rng = np.random.default_rng(0)
    n = 2_000_000
    for dtype in (np.uint32, np.uint64):
        keys = rng.integers(0, 1 << (32 if dtype is np.uint32 else 40), n).astype(dtype)
        t0 = time.perf_counter()
        combo = (keys << np.array(32, dtype=dtype)) | keys.astype(dtype)
        order = np.argsort(combo)
        _ = combo[order]
        dt = (time.perf_counter() - t0) * 1000
        print(f"  {np.dtype(dtype).name:>7}: argsort+index {n:,} keys = {dt:7.1f} ms")
    print("  (the solver's inner step sorts ~10^5-10^6 keys per frame)")


def arena_bits() -> None:
    print()
    print("=" * 74)
    print("2. 竞技场尺寸 -> 子像素所需的 bit 数")
    print("=" * 74)
    print(f"  {'分辨率':<12}{'x 格数':<12}{'x bits':<9}{'y 格数':<12}{'y bits':<9}{'合计(含vy10+k1+t4)'}")
    for denom in (1, 2, 4, 8, 10, 16):
        xmax = 409 * denom
        ymax = 179 * denom
        xb = max(1, math.ceil(math.log2(xmax + 1)))
        yb = max(1, math.ceil(math.log2(ymax + 1)))
        total = xb + yb + 10 + 1 + 4
        flag = "  <- 超出 32 位" if total > 32 else ""
        print(f"  1/{denom:<10}{xmax:<12}{xb:<9}{ymax:<12}{yb:<9}{total}{flag}")


def solvability_by_precision() -> None:
    print()
    print("=" * 74)
    print("3. 精度是否真的是 bonegap1 死锁的原因")
    print("=" * 74)
    print("  用不同 T 求解（T 越大 = 时间上更精细，但位置仍是 1 px）:")
    for T in (199, 398, 796):
        bake = bake_cspace(
            Path(__file__).resolve().parent.parent / "c2-sans-fight" / "sans_bonegap1.csv",
            T=T, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2",
        )
        t0 = time.perf_counter()
        sol = solve_lattice_dp(bake)
        ms = (time.perf_counter() - t0) * 1000
        print(f"    T={T:<5} deadlock={sol.is_deadlock!s:<6} at={sol.deadlock_frame!s:<6} "
              f"peak={sol.stats.peak_alive_states:<7} dp={ms:7.1f} ms")
    print("  若三种 T 都在早期死锁，说明瓶颈是位置/几何的 1 px 量化，不是时间步长。")


def main() -> int:
    bench_key_width()
    arena_bits()
    solvability_by_precision()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
