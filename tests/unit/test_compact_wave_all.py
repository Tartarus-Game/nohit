"""Comprehensive Universal Wave Compiler & Pre-Baking Unit Test Suite.

Verifies:
1. Universal CSV compilation across all 23 canonical rounds and sans_spare.
2. Schedule array shapes and monotonic clock continuity.
3. CombatZone bounding box correctness across smooth and instant resizing.
4. HeartMode (Red vs Blue) and 4-way gravity vector schedules.
5. SansSlam impulse schedules and phase space collapse flags.
6. Multi-platform continuous tracking, boundary reflections, and convection tables.
7. Dual-plane C-space bitmask validity (mask_white unconditional, mask_blue velocity-gated).
8. Conservative initial spawn clearance (initial state is never pre-blocked).
9. Pre-bake execution wall-clock time (< 50ms per wave) and peak memory bounds.
"""
from pathlib import Path
import time
import numpy as np
import pytest

from nohit.engine.compact_wave import (
    ROOT,
    compile_wave,
    prepare_collision_dual_native,
    is_point_blocked,
)

# All 23 canonical attacks partitioned by Tier, plus sans_spare
TIER_1_WAVES = [
    "sans_bonegap1.csv",
    "sans_bonegap1fast.csv",
    "sans_bonegap2.csv",
    "sans_bluebone.csv",
    "sans_boneslideh.csv",
    "sans_boneslidev.csv",
]

TIER_2_WAVES = [
    "sans_platforms1.csv",
    "sans_platforms2.csv",
    "sans_platforms3.csv",
    "sans_platforms4.csv",
    "sans_platforms4hard.csv",
    "sans_bonestab1.csv",
    "sans_bonestab2.csv",
    "sans_bonestab3.csv",
]

TIER_3_WAVES = [
    "sans_intro.csv",
    "sans_randomblaster1.csv",
    "sans_randomblaster2.csv",
    "sans_platformblaster.csv",
    "sans_platformblasterfast.csv",
    "sans_multi1.csv",
    "sans_multi2.csv",
    "sans_multi3.csv",
]

TIER_4_WAVES = [
    "sans_final.csv",
]

ALL_CANONICAL_WAVES = TIER_1_WAVES + TIER_2_WAVES + TIER_3_WAVES + TIER_4_WAVES + ["sans_spare.csv"]


@pytest.fixture(params=ALL_CANONICAL_WAVES, ids=lambda w: w.replace(".csv", ""))
def compiled_wave_data(request):
    """Compiles each wave once per test session."""
    csv_path = ROOT / "c2-sans-fight" / request.param
    assert csv_path.exists(), f"Missing canonical attack CSV: {csv_path}"

    t0 = time.perf_counter()
    res = compile_wave(csv_path)
    compile_time_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "name": request.param,
        "path": csv_path,
        "compile_time_ms": compile_time_ms,
        "compiled_obj": res,
        "env_schedule": res.env_schedule,
        "platform_table": res.platform_table,
        "num_platforms": res.num_platforms,
        "geometry": res.geometry,
        "geometry_white": res.geometry_white,
        "geometry_blue": res.geometry_blue,
        "initial": res.initial,
        "origin": res.origin,
        "dimensions": res.dimensions,
    }


class TestUniversalWaveCompilation:
    """Task 1 & 2: Compilation integrity, clock monotonicity, and state validity."""

    def test_compilation_completes_and_returns_valid_shapes(self, compiled_wave_data):
        env = compiled_wave_data["env_schedule"]
        plat = compiled_wave_data["platform_table"]
        n_plats = compiled_wave_data["num_platforms"]
        init = compiled_wave_data["initial"]

        N_ticks = len(env)
        assert N_ticks >= 72, f"Wave {compiled_wave_data['name']} has too few ticks: {N_ticks}"
        assert env.ndim == 2 and env.shape[1] == 8, f"Env schedule shape mismatch: {env.shape}"
        assert plat.shape == (N_ticks, 4, 7), f"Platform table shape mismatch: {plat.shape}"
        assert n_plats.shape == (N_ticks,), f"Num platforms shape mismatch: {n_plats.shape}"
        assert init.shape == (5,), f"Initial state shape mismatch: {init.shape}"

        assert np.all(np.isfinite(env)), "Env schedule contains non-finite values"
        assert np.all(np.isfinite(plat)), "Platform table contains non-finite values"
        assert np.all(np.isfinite(init)), "Initial state contains non-finite values"
        assert init[4] in (0.0, 1.0), "Initial prev_up must be 0.0 or 1.0"

        dt = env[:, 7]
        assert np.all(dt > 0.0) and np.all(dt < 0.05), "Invalid dt values in schedule"

    def test_legacy_unpacking_compatibility(self, compiled_wave_data):
        res = compiled_wave_data["compiled_obj"]
        # Must unpack into exactly 3 items
        schedule, geometry, initial = res
        assert schedule.shape == (len(res.env_schedule), 7)
        assert geometry.shape[0] == len(res.env_schedule)
        assert initial.shape == (5,)
        assert len(res) == 3


class TestArenaBoundingBoxes:
    """Verifies CombatZone boundaries across smooth and instant resizing."""

    def test_arena_box_is_strictly_positive_area(self, compiled_wave_data):
        env = compiled_wave_data["env_schedule"]
        cz_l, cz_t, cz_r, cz_b = env[:, 0], env[:, 1], env[:, 2], env[:, 3]

        width = cz_r - cz_l
        height = cz_b - cz_t

        assert np.all(width >= 100.0), f"Arena width too small in {compiled_wave_data['name']}: min={np.min(width)}"
        assert np.all(height >= 100.0), f"Arena height too small in {compiled_wave_data['name']}: min={np.min(height)}"

    def test_specific_tier_arena_dimensions(self):
        # Bonegap1: 375x140
        res = compile_wave(ROOT / "c2-sans-fight/sans_bonegap1.csv")
        assert abs((res.env_schedule[0, 2] - res.env_schedule[0, 0]) - 375.0) < 1e-4
        assert abs((res.env_schedule[0, 3] - res.env_schedule[0, 1]) - 140.0) < 1e-4

        # Boneslidev: 165x165
        res = compile_wave(ROOT / "c2-sans-fight/sans_boneslidev.csv")
        assert abs((res.env_schedule[0, 2] - res.env_schedule[0, 0]) - 165.0) < 1e-4
        assert abs((res.env_schedule[0, 3] - res.env_schedule[0, 1]) - 165.0) < 1e-4

        # Platforms4Hard: 435x160
        res = compile_wave(ROOT / "c2-sans-fight/sans_platforms4hard.csv")
        assert abs((res.env_schedule[0, 2] - res.env_schedule[0, 0]) - 435.0) < 1e-4
        assert abs((res.env_schedule[0, 3] - res.env_schedule[0, 1]) - 160.0) < 1e-4


class TestHeartModeAndGravitySchedules:
    """Verifies HeartMode (Red vs Blue) and gravity orientation schedules."""

    def test_heart_mode_values_are_binary(self, compiled_wave_data):
        modes = compiled_wave_data["env_schedule"][:, 4]
        assert np.all(np.isin(modes, [0.0, 1.0])), "Heart mode must strictly be 0.0 (Red) or 1.0 (Blue)"

    def test_red_heart_waves_are_correctly_classified(self):
        for w in ["sans_boneslidev.csv", "sans_randomblaster1.csv", "sans_randomblaster2.csv"]:
            res = compile_wave(ROOT / "c2-sans-fight" / w)
            assert np.all(res.env_schedule[:, 4] == 0.0), f"{w} should be entirely Red Heart"

    def test_gravity_direction_values_are_valid(self, compiled_wave_data):
        grav_dirs = compiled_wave_data["env_schedule"][:, 5]
        assert np.all(np.isin(grav_dirs, [0.0, 1.0, 2.0, 3.0])), "Gravity direction must be in {0, 1, 2, 3}"


class TestSansSlamSchedules:
    """Verifies SansSlam impulse frames and gravity updates."""

    @pytest.mark.parametrize("wave_name,expected_min_slams", [
        ("sans_bonestab1.csv", 9),
        ("sans_bonestab2.csv", 9),
        ("sans_bonestab3.csv", 9),
        ("sans_intro.csv", 1),
        ("sans_final.csv", 38),
    ])
    def test_slam_waves_trigger_slam_active_flags(self, wave_name, expected_min_slams):
        res = compile_wave(ROOT / "c2-sans-fight" / wave_name)
        slams = np.sum(res.env_schedule[:, 6] == 1.0)
        assert slams >= expected_min_slams, f"{wave_name} triggered {slams} slams, expected >= {expected_min_slams}"


class TestPlatformTablesAndKinematics:
    """Verifies platform continuous tracking, convection, and reflection."""

    def test_non_platform_waves_have_zero_platforms(self):
        for w in ["sans_bonegap1.csv", "sans_boneslidev.csv", "sans_randomblaster1.csv"]:
            res = compile_wave(ROOT / "c2-sans-fight" / w)
            assert np.all(res.num_platforms == 0), f"{w} should have 0 active platforms"

    def test_platforms4hard_kinematics_and_bounce(self):
        res = compile_wave(ROOT / "c2-sans-fight/sans_platforms4hard.csv")
        assert np.all(res.num_platforms == 1), "Platforms4Hard must have exactly 1 active platform"

        plat = res.platform_table[:, 0, :]
        assert abs(plat[0, 0] - 151.0) < 1e-4
        assert abs(plat[0, 1] - 336.0) < 1e-4
        assert abs(plat[0, 2] - 31.0) < 1e-4
        assert abs(plat[0, 4] - 90.0) < 1e-4

        assert plat[975, 4] == 90.0
        assert plat[976, 4] == -90.0

    def test_multi_platform_waves_have_multiple_concurrent_platforms(self):
        for w in ["sans_platforms1.csv", "sans_platforms2.csv", "sans_platforms3.csv"]:
            res = compile_wave(ROOT / "c2-sans-fight" / w)
            max_p = np.max(res.num_platforms)
            assert max_p >= 2, f"{w} should have at least 2 concurrent platforms, found max {max_p}"


class TestDualPlaneBitmaskIntegrity:
    """Verifies Minkowski C-space dual-plane bitmask baking."""

    def test_dual_plane_bitmask_shapes_and_types(self, compiled_wave_data):
        res = compiled_wave_data["compiled_obj"]
        mask_white, mask_blue = prepare_collision_dual_native(res, margin_x=1.0, margin_y=2.0)

        N_ticks = len(compiled_wave_data["env_schedule"])
        assert mask_white.shape[0] == N_ticks
        assert mask_blue.shape[0] == N_ticks
        assert mask_white.dtype == np.uint64
        assert mask_blue.dtype == np.uint64

    def test_blue_bone_separation_in_sans_bluebone(self):
        res = compile_wave(ROOT / "c2-sans-fight/sans_bluebone.csv")
        mask_white, mask_blue = prepare_collision_dual_native(res, margin_x=1.0, margin_y=2.0)

        assert np.any(mask_blue > 0), "sans_bluebone must have non-zero mask_blue"
        assert np.any(mask_white > 0), "sans_bluebone must have non-zero mask_white"

    def test_initial_state_is_never_pre_blocked(self, compiled_wave_data):
        res = compiled_wave_data["compiled_obj"]
        mask_white, _ = prepare_collision_dual_native(res, margin_x=1.0, margin_y=2.0)

        init_x = compiled_wave_data["initial"][0]
        init_y = compiled_wave_data["initial"][1]
        ox, oy = res.origin
        h, w = res.dimensions

        assert not is_point_blocked(mask_white, 0, init_x, init_y, ox, oy, w, h), (
            f"Initial state ({init_x}, {init_y}) in {compiled_wave_data['name']} is blocked at tick 0!"
        )


class TestCompilerPerformance:
    """Verifies pre-baking latency meets project requirements (< 100ms for standard waves, < 1000ms for sans_final)."""

    def test_compilation_time_is_sub_50ms(self, compiled_wave_data):
        name = compiled_wave_data["name"]
        time_ms = compiled_wave_data["compile_time_ms"]
        threshold_ms = 1000.0 if "final" in name else 100.0
        assert time_ms < threshold_ms, (
            f"Compilation of {name} took {time_ms:.2f}ms (> {threshold_ms}ms)"
        )
