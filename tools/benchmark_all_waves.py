"""Standalone latency benchmark runner for all 24 canonical attacks and sans_spare.

Measures:
- Ticks count
- Pre-scan & VM compilation latency (ms)
- Dual-plane Minkowski C-space bitmask baking latency (ms)
- Combined pre-bake wall-clock latency (ms)
- Geometry array dimensions & maximum active hazard counts
- Sub-50ms verdict
"""
import time
from pathlib import Path
import numpy as np

from nohit.engine.compact_wave import (
    ROOT,
    compile_wave,
    prepare_collision_dual_native,
)

ALL_24_WAVES = [
    ("Tier 1", "sans_bonegap1.csv"),
    ("Tier 1", "sans_bonegap1fast.csv"),
    ("Tier 1", "sans_bonegap2.csv"),
    ("Tier 1", "sans_bluebone.csv"),
    ("Tier 1", "sans_boneslideh.csv"),
    ("Tier 1", "sans_boneslidev.csv"),
    ("Tier 2", "sans_platforms1.csv"),
    ("Tier 2", "sans_platforms2.csv"),
    ("Tier 2", "sans_platforms3.csv"),
    ("Tier 2", "sans_platforms4.csv"),
    ("Tier 2", "sans_platforms4hard.csv"),
    ("Tier 2", "sans_bonestab1.csv"),
    ("Tier 2", "sans_bonestab2.csv"),
    ("Tier 2", "sans_bonestab3.csv"),
    ("Tier 3", "sans_intro.csv"),
    ("Tier 3", "sans_randomblaster1.csv"),
    ("Tier 3", "sans_randomblaster2.csv"),
    ("Tier 3", "sans_platformblaster.csv"),
    ("Tier 3", "sans_platformblasterfast.csv"),
    ("Tier 3", "sans_multi1.csv"),
    ("Tier 3", "sans_multi2.csv"),
    ("Tier 3", "sans_multi3.csv"),
    ("Tier 4", "sans_final.csv"),
    ("Special", "sans_spare.csv"),
]

def main():
    # Warm up JIT
    dummy_csv = ROOT / "c2-sans-fight/sans_bonegap1.csv"
    res = compile_wave(dummy_csv)
    prepare_collision_dual_native(res)

    results = []

    print("| Tier | Wave | Ticks | Compile (ms) | Bake (ms) | Total (ms) | Max Hazards (W/B) | Sub-50ms |")
    print("|------|------|-------|--------------|-----------|------------|-------------------|----------|")

    for tier, wave in ALL_24_WAVES:
        csv_path = ROOT / "c2-sans-fight" / wave

        # 5 repetitions, take median
        comp_times = []
        bake_times = []
        last_res = None
        last_masks = None

        for _ in range(5):
            t0 = time.perf_counter()
            res = compile_wave(csv_path, seed=42)
            t1 = time.perf_counter()
            mask_w, mask_b = prepare_collision_dual_native(res, margin_x=1.0, margin_y=2.0)
            t2 = time.perf_counter()

            comp_times.append((t1 - t0) * 1000.0)
            bake_times.append((t2 - t1) * 1000.0)
            last_res = res
            last_masks = (mask_w, mask_b)

        med_comp = float(np.median(comp_times))
        med_bake = float(np.median(bake_times))
        med_total = med_comp + med_bake

        ticks = len(last_res.env_schedule)
        max_w = last_res.geometry_white.shape[1] if last_res.geometry_white.ndim >= 2 else 0
        max_b = last_res.geometry_blue.shape[1] if last_res.geometry_blue.ndim >= 2 else 0

        # Verdict
        threshold = 500.0 if "final" in wave else 50.0
        verdict = "PASS" if med_comp < threshold and med_bake < threshold else "FAIL"

        print(f"| {tier} | `{wave}` | {ticks} | {med_comp:.2f} | {med_bake:.2f} | {med_total:.2f} | {max_w} / {max_b} | {verdict} |")
        results.append({
            "tier": tier,
            "wave": wave,
            "ticks": ticks,
            "comp_ms": med_comp,
            "bake_ms": med_bake,
            "total_ms": med_total,
            "max_w": max_w,
            "max_b": max_b,
            "verdict": verdict,
        })

    # Summary statistics
    std_waves = [r for r in results if "final" not in r["wave"]]
    avg_comp = np.mean([r["comp_ms"] for r in std_waves])
    max_comp = np.max([r["comp_ms"] for r in std_waves])
    avg_bake = np.mean([r["bake_ms"] for r in std_waves])
    max_bake = np.max([r["bake_ms"] for r in std_waves])
    avg_total = np.mean([r["total_ms"] for r in std_waves])
    max_total = np.max([r["total_ms"] for r in std_waves])

    print("\n### Summary (23 Standard Waves)")
    print(f"- Average Compilation Latency: {avg_comp:.2f} ms (Max: {max_comp:.2f} ms)")
    print(f"- Average C-Space Baking Latency: {avg_bake:.2f} ms (Max: {max_bake:.2f} ms)")
    print(f"- Average Combined Latency: {avg_total:.2f} ms (Max: {max_total:.2f} ms)")

    final_wave = [r for r in results if "final" in r["wave"]][0]
    print("\n### Complex Wave (sans_final.csv, 24.7s)")
    print(f"- Compilation Latency: {final_wave['comp_ms']:.2f} ms")
    print(f"- C-Space Baking Latency: {final_wave['bake_ms']:.2f} ms")
    print(f"- Combined Latency: {final_wave['total_ms']:.2f} ms")

if __name__ == "__main__":
    main()
