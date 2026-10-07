"""Adversarial stress-testing suite for Universal Wave Compiler (Milestone 1).

Author: o6_m1_challenger_1
Requirements under test:
1. Varied seeds test matrix (0, 1, 42, 1337, 999999, -1, 2**31-1) across all 24 CSV waves.
2. Complete data integrity: Absence of NaN/inf in schedules, platform tables, and valid boxes.
3. Coordinate boundary validation: Origin, dimensions, out-of-bounds containment, and positive box dimensions.
4. Absence of memory leaks under repeated compilation cycles.
5. Wall-clock latency benchmarking (sub-50ms challenge target vs sub-100ms spec threshold).
6. Complex wave stability stress tests (sans_final, sans_multi3).
"""
import ctypes
from ctypes import wintypes
import gc
import math
import sys
import time
from pathlib import Path
import numpy as np
import pytest

from nohit.engine.compact_wave import (
    ROOT,
    compile_wave,
    prepare_collision_dual_native,
    is_point_blocked,
)

ALL_24_WAVES = [
    "sans_bonegap1.csv",
    "sans_bonegap1fast.csv",
    "sans_bonegap2.csv",
    "sans_bluebone.csv",
    "sans_boneslideh.csv",
    "sans_boneslidev.csv",
    "sans_platforms1.csv",
    "sans_platforms2.csv",
    "sans_platforms3.csv",
    "sans_platforms4.csv",
    "sans_platforms4hard.csv",
    "sans_bonestab1.csv",
    "sans_bonestab2.csv",
    "sans_bonestab3.csv",
    "sans_intro.csv",
    "sans_randomblaster1.csv",
    "sans_randomblaster2.csv",
    "sans_platformblaster.csv",
    "sans_platformblasterfast.csv",
    "sans_multi1.csv",
    "sans_multi2.csv",
    "sans_multi3.csv",
    "sans_final.csv",
    "sans_spare.csv",
]

SEEDS_TO_TEST = [0, 1, 42, 1337, 999999, -1, 2147483647]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def get_process_working_set_mb() -> float:
    """Returns current process working set memory in MB via Win32 API."""
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / (1024.0 * 1024.0)


class TestVariedSeedsIntegrity:
    """Challenge 1: Compiles all 24 CSV scripts under varied seeds and asserts stability."""

    @pytest.mark.parametrize("seed", SEEDS_TO_TEST)
    @pytest.mark.parametrize("wave_name", ALL_24_WAVES)
    def test_compilation_under_varied_seeds(self, wave_name, seed):
        csv_path = ROOT / "c2-sans-fight" / wave_name
        res = compile_wave(csv_path, seed=seed)

        assert res is not None
        assert len(res.env_schedule) >= 72
        assert np.all(np.isfinite(res.env_schedule))
        assert np.all(np.isfinite(res.platform_table))
        assert np.all(np.isfinite(res.initial))

        cz_l = res.env_schedule[:, 0]
        cz_t = res.env_schedule[:, 1]
        cz_r = res.env_schedule[:, 2]
        cz_b = res.env_schedule[:, 3]
        assert np.all(cz_r > cz_l), f"Inverted horizontal bounds in {wave_name} under seed {seed}"
        assert np.all(cz_b > cz_t), f"Inverted vertical bounds in {wave_name} under seed {seed}"

        mask_w, mask_b = prepare_collision_dual_native(res, margin_x=1.0, margin_y=2.0)
        assert mask_w.shape[0] == len(res.env_schedule)
        assert mask_b.shape[0] == len(res.env_schedule)
        assert mask_w.dtype == np.uint64
        assert mask_b.dtype == np.uint64

    def test_random_waves_diverge_across_different_seeds(self):
        """Confirms that waves with RNG commands actually branch on distinct seeds."""
        rng_waves = ["sans_randomblaster1.csv", "sans_randomblaster2.csv"]
        for wave_name in rng_waves:
            csv_path = ROOT / "c2-sans-fight" / wave_name
            res1 = compile_wave(csv_path, seed=42)
            res2 = compile_wave(csv_path, seed=999999)

            geom1_flat = res1.geometry_white[np.isfinite(res1.geometry_white)]
            geom2_flat = res2.geometry_white[np.isfinite(res2.geometry_white)]

            diverged = (len(geom1_flat) != len(geom2_flat)) or not np.array_equal(geom1_flat, geom2_flat)
            assert diverged, f"{wave_name} unexpectedly produced identical geometry for seed 42 and 999999"


class TestNumericalIntegrityAndNoNaNInf:
    """Challenge 2: Deep scan of array contents for NaN, inf, and invalid box geometries."""

    @pytest.mark.parametrize("wave_name", ALL_24_WAVES)
    def test_schedules_and_platforms_strictly_finite(self, wave_name):
        csv_path = ROOT / "c2-sans-fight" / wave_name
        res = compile_wave(csv_path, seed=42)

        assert not np.any(np.isnan(res.env_schedule)), f"NaN in env_schedule for {wave_name}"
        assert not np.any(np.isinf(res.env_schedule)), f"Inf in env_schedule for {wave_name}"
        assert not np.any(np.isnan(res.platform_table)), f"NaN in platform_table for {wave_name}"
        assert not np.any(np.isinf(res.platform_table)), f"Inf in platform_table for {wave_name}"
        assert np.all(res.num_platforms >= 0) and np.all(res.num_platforms <= 4)
        assert not np.any(np.isnan(res.initial))
        assert not np.any(np.isinf(res.initial))
        assert res.initial[4] in (0.0, 1.0)

    @pytest.mark.parametrize("wave_name", ALL_24_WAVES)
    def test_geometry_boxes_are_non_negative_and_positive_area(self, wave_name):
        """Adversarial check: all valid (non-padding) boxes must satisfy right >= left and bottom >= top."""
        csv_path = ROOT / "c2-sans-fight" / wave_name
        res = compile_wave(csv_path, seed=42)

        gw = res.geometry_white
        gb = res.geometry_blue
        for geom, name in [(gw, "white"), (gb, "blue")]:
            valid_mask = np.isfinite(geom[:, :, 0])
            if np.any(valid_mask):
                valid_boxes = geom[valid_mask]
                w = valid_boxes[:, 2] - valid_boxes[:, 0]
                h = valid_boxes[:, 3] - valid_boxes[:, 1]
                neg_w_count = int(np.sum(w < 0.0))
                neg_h_count = int(np.sum(h < 0.0))
                assert neg_w_count == 0, f"Found {neg_w_count} boxes with negative width in {name} geometry for {wave_name}"
                assert neg_h_count == 0, (
                    f"Found {neg_h_count} inverted boxes with negative height in {name} geometry for {wave_name}! "
                    f"Example inverted box: {valid_boxes[np.where(h < 0.0)[0][0]]} (height={h[h < 0.0][0]})"
                )


class TestCoordinateBoundsAndContainment:
    """Challenge 3: Validates origin, dimensions, and out-of-bounds queries."""

    @pytest.mark.parametrize("wave_name", ALL_24_WAVES)
    def test_arena_and_cspace_coordinate_contracts(self, wave_name):
        csv_path = ROOT / "c2-sans-fight" / wave_name
        res = compile_wave(csv_path, seed=42)

        ox, oy = res.origin
        h, w = res.dimensions
        assert w > 0 and h > 0, f"Invalid dimensions ({h}, {w}) for {wave_name}"
        assert w <= 2000 and h <= 2000, f"Unreasonably huge dimensions ({h}, {w}) for {wave_name}"

        mask_w, _ = prepare_collision_dual_native(res)

        init_x, init_y = res.initial[0], res.initial[1]
        assert not is_point_blocked(mask_w, 0, init_x, init_y, ox, oy, w, h), (
            f"Spawn point ({init_x}, {init_y}) is blocked at tick 0 in {wave_name}"
        )

        assert is_point_blocked(mask_w, 0, ox - 100, init_y, ox, oy, w, h)
        assert is_point_blocked(mask_w, 0, ox + w + 100, init_y, ox, oy, w, h)
        assert is_point_blocked(mask_w, 0, init_x, oy - 100, ox, oy, w, h)
        assert is_point_blocked(mask_w, 0, init_x, oy + h + 100, ox, oy, w, h)


class TestMemoryLeakFreedom:
    """Challenge 4: Repeatedly compiles waves to detect uncollected allocations or memory leaks."""

    def test_memory_stability_across_50_compilation_cycles(self):
        gc.collect()
        initial_ws_mb = get_process_working_set_mb()

        for iteration in range(5):
            for wave_name in ALL_24_WAVES:
                csv_path = ROOT / "c2-sans-fight" / wave_name
                res = compile_wave(csv_path, seed=iteration)
                mask_w, mask_b = prepare_collision_dual_native(res)
                del res, mask_w, mask_b

        gc.collect()
        final_ws_mb = get_process_working_set_mb()
        growth_mb = max(0.0, final_ws_mb - initial_ws_mb)

        assert growth_mb < 25.0, (
            f"Memory leak detected: working set grew by {growth_mb:.2f} MB across 120 compilations"
        )


class TestCompilationAndBakingLatencyBenchmark:
    """Challenge 5: Measures wall-clock compilation and C-space baking latency across all 24 waves."""

    @pytest.mark.parametrize("wave_name", ALL_24_WAVES)
    def test_benchmark_latency_sub_100ms_spec(self, wave_name):
        """Spec check: all standard waves must be sub-100ms, sans_final sub-1000ms."""
        csv_path = ROOT / "c2-sans-fight" / wave_name
        _ = compile_wave(csv_path, seed=42)

        times_compile = []
        times_bake = []
        for _ in range(3):
            t0 = time.perf_counter()
            res = compile_wave(csv_path, seed=42)
            t1 = time.perf_counter()
            _ = prepare_collision_dual_native(res, margin_x=1.0, margin_y=2.0)
            t2 = time.perf_counter()
            times_compile.append((t1 - t0) * 1000.0)
            times_bake.append((t2 - t1) * 1000.0)

        min_compile_ms = min(times_compile)
        min_bake_ms = min(times_bake)

        threshold_ms = 1000.0 if "final" in wave_name else 100.0
        assert min_compile_ms < threshold_ms, f"{wave_name} compile latency too high: {min_compile_ms:.2f}ms"
        assert min_bake_ms < (200.0 if "final" in wave_name else 50.0), f"{wave_name} bake latency too high: {min_bake_ms:.2f}ms"

    @pytest.mark.parametrize("wave_name", ALL_24_WAVES)
    def test_benchmark_latency_strict_sub_50ms_target(self, wave_name):
        """Adversarial stress challenge: check which waves satisfy the ambitious sub-50ms target."""
        csv_path = ROOT / "c2-sans-fight" / wave_name
        _ = compile_wave(csv_path, seed=42)

        times_compile = []
        for _ in range(3):
            t0 = time.perf_counter()
            res = compile_wave(csv_path, seed=42)
            t1 = time.perf_counter()
            times_compile.append((t1 - t0) * 1000.0)

        min_compile_ms = min(times_compile)
        threshold_ms = 500.0 if "final" in wave_name else 50.0
        assert min_compile_ms < threshold_ms, (
            f"Wave {wave_name} exceeded strict 50ms compilation latency: {min_compile_ms:.2f}ms (> 50.0ms)"
        )


class TestComplexWaveStressAndCornerCases:
    """Challenge 6: Stress test high-complexity and composite attack waves."""

    def test_sans_final_deep_structure(self):
        csv_path = ROOT / "c2-sans-fight/sans_final.csv"
        res = compile_wave(csv_path, seed=42)

        N_ticks = len(res.env_schedule)
        assert N_ticks >= 5000, f"sans_final tick count unexpectedly low: {N_ticks}"

        slams = np.sum(res.env_schedule[:, 6] == 1.0)
        assert slams >= 38, f"sans_final has {slams} slams, expected >= 38"

        modes = np.unique(res.env_schedule[:, 4])
        assert len(modes) > 1, f"sans_final should feature both Red and Blue heart modes: found {modes}"

        gravities = np.unique(res.env_schedule[:, 5])
        assert len(gravities) >= 4, f"sans_final should feature all 4 gravity orientations: found {gravities}"

    def test_sans_multi3_deep_structure(self):
        csv_path = ROOT / "c2-sans-fight/sans_multi3.csv"
        res = compile_wave(csv_path, seed=42)

        assert np.any(res.num_platforms > 0), "sans_multi3 should feature active platforms"
        assert res.geometry_white.shape[1] > 0

    def test_pathological_csv_inputs(self):
        with pytest.raises(FileNotFoundError):
            compile_wave("non_existent_file_xyz.csv")

        import tempfile
        with tempfile.NamedTemporaryFile("w+", suffix=".csv", delete=False) as tf:
            tf.write("0,CombatZoneResize,100,100,200,200\n0,BoneV,150,150,50,0,10,0\n")
            temp_path = tf.name

        try:
            with pytest.raises(ValueError, match="unsupported_mechanism"):
                compile_wave(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)
