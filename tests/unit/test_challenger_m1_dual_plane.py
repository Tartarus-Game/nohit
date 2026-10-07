"""Milestone 1 Challenger 2: Dual-Plane C-Space Bitmask Adversarial Verification Suite.

Adversarially stress-tests:
1. mask_white unconditional blocking vs mask_blue motion-dependent lethality.
2. Blue bone velocity gating: stationary points (|v| == 0) MUST be safe, moving (|v| > 0) MUST be lethal.
3. Minkowski sum dilation accuracy against exact Construct 2 AABB formulas.
4. Initial soul coordinate clearance across all 23 canonical waves + sans_spare.
5. Bitmask word boundary straddling, out-of-bounds clipping, and degenerate geometry resilience.
"""

import math
from pathlib import Path
import numpy as np
import pytest

from nohit.engine.compact_types import CompiledWave, GeometryArray
from nohit.engine.compact_wave import (
    ROOT,
    _prepare_collision_plane_njit,
    compile_wave,
    is_point_blocked,
    prepare_collision_dual_native,
)
from tests.unit.test_compact_wave_all import (
    ALL_CANONICAL_WAVES,
    TIER_1_WAVES,
    TIER_2_WAVES,
    TIER_3_WAVES,
    TIER_4_WAVES,
)


def c2_aabb_overlap(
    hx: float,
    hy: float,
    left: float,
    top: float,
    right: float,
    bottom: float,
    soul_rx: float = 2.0,
    soul_ry: float = 2.0,
    margin_x: float = 0.0,
    margin_y: float = 0.0,
) -> bool:
    """Exact Construct 2 AABB overlap formula between dilated player hitbox and hazard rect."""
    hr_x = soul_rx + margin_x
    hr_y = soul_ry + margin_y
    return (
        (hx + hr_x >= left)
        and (hx - hr_x <= right)
        and (hy + hr_y >= top)
        and (hy - hr_y <= bottom)
    )


def is_dual_plane_lethal(
    mask_white: np.ndarray,
    mask_blue: np.ndarray,
    tick: int,
    xpos: float,
    ypos: float,
    vx: float,
    vy: float,
    origin_x: int,
    origin_y: int,
    W: int,
    H: int,
) -> bool:
    """Canonical dual-plane lethality evaluation oracle:

    - mask_white: Unconditionally lethal regardless of velocity.
    - mask_blue: Lethal ONLY IF velocity is non-zero (moving ||v|| > 0).
    """
    if is_point_blocked(mask_white, tick, xpos, ypos, origin_x, origin_y, W, H):
        return True
    if is_point_blocked(mask_blue, tick, xpos, ypos, origin_x, origin_y, W, H):
        if abs(vx) > 1e-8 or abs(vy) > 1e-8:
            return True
    return False


# ============================================================================
# Dimension 1: Plane Separation & Unconditional Blocking
# ============================================================================
class TestDualPlaneSeparationAndUnconditionalBlocking:
    """Adversarial validation of mask_white vs mask_blue separation."""

    def test_pure_white_waves_have_zero_blue_bitmask(self):
        """Waves without blue bones must have identically zero mask_blue across all ticks."""
        pure_white_samples = [
            "sans_bonegap1.csv",
            "sans_bonegap1fast.csv",
            "sans_bonegap2.csv",
            "sans_boneslideh.csv",
            "sans_boneslidev.csv",
            "sans_platforms1.csv",
            "sans_platforms2.csv",
            "sans_platforms3.csv",
            "sans_platforms4.csv",
            "sans_bonestab1.csv",
            "sans_bonestab2.csv",
            "sans_bonestab3.csv",
            "sans_intro.csv",
            "sans_randomblaster1.csv",
            "sans_randomblaster2.csv",
        ]
        for w_name in pure_white_samples:
            csv_path = ROOT / "c2-sans-fight" / w_name
            res = compile_wave(csv_path)
            mask_white, mask_blue = prepare_collision_dual_native(res)

            assert np.any(mask_white > 0), f"Wave {w_name} should have hazards in mask_white"
            assert np.all(mask_blue == 0), (
                f"Wave {w_name} is a pure white wave but mask_blue has non-zero entries!"
            )

    def test_sans_bluebone_plane_isolation(self):
        """In sans_bluebone, verify blue bones are in mask_blue and NOT in mask_white."""
        csv_path = ROOT / "c2-sans-fight/sans_bluebone.csv"
        res = compile_wave(csv_path)
        mask_white, mask_blue = prepare_collision_dual_native(res, margin_x=0.0, margin_y=0.0)

        ox, oy = res.origin
        h, w = res.dimensions

        # Inspect ticks where blue bones exist (e.g. tick 100)
        found_pure_blue_point = False
        for t in range(50, min(len(res.env_schedule), 400)):
            # Check geometry_blue for active boxes
            b_boxes = res.geometry_blue[t]
            for box in b_boxes:
                if not math.isfinite(box[0]):
                    continue
                # Pick center of blue box
                cx = (box[0] + box[2]) / 2.0
                cy = (box[1] + box[3]) / 2.0

                # Only test points that are within arena bounds
                if not (ox <= cx < ox + w and oy <= cy < oy + h):
                    continue

                # Point must be blocked in mask_blue
                assert is_point_blocked(mask_blue, t, cx, cy, ox, oy, w, h), (
                    f"Blue bone center ({cx}, {cy}) at tick {t} not blocked in mask_blue!"
                )
                # If there are no overlapping white bones at this location, must be clear in mask_white
                w_boxes = res.geometry_white[t]
                in_white = False
                for wb in w_boxes:
                    if math.isfinite(wb[0]) and c2_aabb_overlap(cx, cy, wb[0], wb[1], wb[2], wb[3]):
                        in_white = True
                        break
                if not in_white:
                    assert not is_point_blocked(mask_white, t, cx, cy, ox, oy, w, h), (
                        f"Blue bone point ({cx}, {cy}) leaked into mask_white at tick {t}!"
                    )
                    found_pure_blue_point = True

        assert found_pure_blue_point, "Failed to verify at least one isolated blue bone point!"

    def test_synthetic_colocated_and_adjacent_bones_plane_isolation(self):
        """Adversarial synthetic test: co-located white and blue bones bake into their respective planes."""
        T = 5
        H = 100
        W = 200
        words = (W + 63) // 64

        # Box 1: White bone at [50, 40, 70, 60]
        # Box 2: Blue bone at [100, 30, 130, 80]
        # Box 3: Co-located bone at [150, 40, 170, 60] (both white and blue)
        gw = np.full((T, 2, 4), np.nan, dtype=np.float64)
        gb = np.full((T, 2, 4), np.nan, dtype=np.float64)

        for t in range(T):
            gw[t, 0] = [50.0, 40.0, 70.0, 60.0]
            gw[t, 1] = [150.0, 40.0, 170.0, 60.0]

            gb[t, 0] = [100.0, 30.0, 130.0, 80.0]
            gb[t, 1] = [150.0, 40.0, 170.0, 60.0]

        mw = _prepare_collision_plane_njit(gw, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)
        mb = _prepare_collision_plane_njit(gb, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)

        # Point inside Box 1 (White only): (60, 50)
        assert is_point_blocked(mw, 0, 60.0, 50.0, 0, 0, W, H)
        assert not is_point_blocked(mb, 0, 60.0, 50.0, 0, 0, W, H)

        # Point inside Box 2 (Blue only): (115, 55)
        assert not is_point_blocked(mw, 0, 115.0, 55.0, 0, 0, W, H)
        assert is_point_blocked(mb, 0, 115.0, 55.0, 0, 0, W, H)

        # Point inside Box 3 (Co-located): (160, 50)
        assert is_point_blocked(mw, 0, 160.0, 50.0, 0, 0, W, H)
        assert is_point_blocked(mb, 0, 160.0, 50.0, 0, 0, W, H)


# ============================================================================
# Dimension 2: Blue Bone Velocity Gating
# ============================================================================
class TestBlueBoneVelocityGating:
    """Adversarially tests blue bone velocity gating semantics: ||v|| == 0 safe vs ||v|| > 0 lethal."""

    @pytest.fixture
    def synthetic_dual_masks(self):
        T = 2
        H = 120
        W = 300
        words = (W + 63) // 64

        gw = np.full((T, 1, 4), np.nan, dtype=np.float64)
        gb = np.full((T, 1, 4), np.nan, dtype=np.float64)

        # White bone at [50, 40, 80, 80]
        gw[:, 0] = [50.0, 40.0, 80.0, 80.0]
        # Blue bone at [150, 40, 180, 80]
        gb[:, 0] = [150.0, 40.0, 180.0, 80.0]

        mw = _prepare_collision_plane_njit(gw, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)
        mb = _prepare_collision_plane_njit(gb, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)

        return {
            "mw": mw,
            "mb": mb,
            "H": H,
            "W": W,
            "origin_x": 0,
            "origin_y": 0,
            "blue_pt": (165.0, 60.0),
            "white_pt": (65.0, 60.0),
            "free_pt": (250.0, 60.0),
        }

    def test_stationary_inside_blue_bone_is_strictly_safe(self, synthetic_dual_masks):
        d = synthetic_dual_masks
        bx, by = d["blue_pt"]

        # Assert point is truly inside mask_blue and outside mask_white
        assert is_point_blocked(d["mb"], 0, bx, by, d["origin_x"], d["origin_y"], d["W"], d["H"])
        assert not is_point_blocked(d["mw"], 0, bx, by, d["origin_x"], d["origin_y"], d["W"], d["H"])

        # Stationary state (vx = 0, vy = 0)
        is_lethal = is_dual_plane_lethal(
            d["mw"], d["mb"], 0, bx, by, 0.0, 0.0, d["origin_x"], d["origin_y"], d["W"], d["H"]
        )
        assert not is_lethal, "Stationary soul inside blue bone MUST be declared safe!"

    @pytest.mark.parametrize(
        "vx,vy",
        [
            (1e-6, 0.0),           # Sub-epsilon micro velocity X
            (-1e-6, 0.0),          # Negative sub-epsilon
            (0.0, 1e-6),           # Sub-epsilon micro velocity Y
            (0.0, -1e-6),          # Negative sub-epsilon Y
            (0.001, 0.0),          # Small positive X
            (-0.001, 0.0),         # Small negative X
            (0.0, 0.001),          # Small positive Y
            (0.0, -0.001),         # Small negative Y
            (150.0, 0.0),          # Max right walk
            (-150.0, 0.0),         # Max left walk
            (0.0, -180.0),         # Initial jump upward
            (0.0, 540.0),          # Mid-fall gravity downward
            (0.0, 750.0),          # Terminal velocity fall
            (150.0, -180.0),       # Diagonal jump-right
            (-150.0, 750.0),       # Diagonal fall-left
        ],
    )
    def test_moving_inside_blue_bone_is_strictly_lethal(self, synthetic_dual_masks, vx, vy):
        d = synthetic_dual_masks
        bx, by = d["blue_pt"]

        is_lethal = is_dual_plane_lethal(
            d["mw"], d["mb"], 0, bx, by, vx, vy, d["origin_x"], d["origin_y"], d["W"], d["H"]
        )
        assert is_lethal, f"Moving soul (vx={vx}, vy={vy}) inside blue bone MUST be declared lethal!"

    @pytest.mark.parametrize(
        "vx,vy",
        [
            (0.0, 0.0),
            (150.0, 0.0),
            (0.0, -180.0),
            (150.0, 750.0),
        ],
    )
    def test_white_bone_is_unconditionally_lethal(self, synthetic_dual_masks, vx, vy):
        d = synthetic_dual_masks
        wx, wy = d["white_pt"]

        is_lethal = is_dual_plane_lethal(
            d["mw"], d["mb"], 0, wx, wy, vx, vy, d["origin_x"], d["origin_y"], d["W"], d["H"]
        )
        assert is_lethal, f"White bone point MUST be lethal regardless of velocity (vx={vx}, vy={vy})!"

    @pytest.mark.parametrize(
        "vx,vy",
        [
            (0.0, 0.0),
            (150.0, 0.0),
            (0.0, -180.0),
            (150.0, 750.0),
        ],
    )
    def test_free_space_is_strictly_safe(self, synthetic_dual_masks, vx, vy):
        d = synthetic_dual_masks
        fx, fy = d["free_pt"]

        is_lethal = is_dual_plane_lethal(
            d["mw"], d["mb"], 0, fx, fy, vx, vy, d["origin_x"], d["origin_y"], d["W"], d["H"]
        )
        assert not is_lethal, f"Free space point MUST be safe regardless of velocity (vx={vx}, vy={vy})!"


# ============================================================================
# Dimension 3: Minkowski Sum Dilation Accuracy vs Construct 2 AABB Formulas
# ============================================================================
class TestMinkowskiDilationAccuracyConstruct2:
    """Adversarially verifies pixel-level boundary dilation against Construct 2 AABB formulas."""

    def test_isolated_bone_exact_boundary_pixels_zero_margin(self):
        """Verifies exact 4x4 hitbox (radius 2.0) dilation boundaries on an isolated bone."""
        H = 80
        W = 100
        words = (W + 63) // 64
        geom = np.full((1, 1, 4), np.nan, dtype=np.float64)

        # Bone bbox: [30.0, 20.0, 40.0, 50.0]
        left, top, right, bottom = 30.0, 20.0, 40.0, 50.0
        geom[0, 0] = [left, top, right, bottom]

        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)

        # Construct 2 overlap range with 4x4 hitbox (rx=2, ry=2):
        # x in [left - 2, right + 2] = [28, 42]
        # y in [top - 2, bottom + 2] = [18, 52]

        # Exhaustive verification of all integer pixels in [20..50] x [10..60]
        for y in range(10, 61):
            for x in range(20, 51):
                expected_overlap = (28 <= x <= 42) and (18 <= y <= 52)
                actual_blocked = is_point_blocked(mask, 0, float(x), float(y), 0, 0, W, H)
                assert actual_blocked == expected_overlap, (
                    f"Pixel ({x}, {y}): expected {expected_overlap}, got {actual_blocked} "
                    f"against bone [{left}, {top}, {right}, {bottom}]"
                )

    def test_isolated_bone_exact_boundary_pixels_with_custom_margin(self):
        """Verifies dilation boundaries with margin_x=1.0, margin_y=2.0."""
        H = 80
        W = 100
        words = (W + 63) // 64
        geom = np.full((1, 1, 4), np.nan, dtype=np.float64)

        left, top, right, bottom = 30.0, 20.0, 40.0, 50.0
        geom[0, 0] = [left, top, right, bottom]

        mx = 1.0
        my = 2.0
        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, mx, my, 2.0, 2.0)

        # Dilated range:
        # x in [left - 2 - 1, right + 2 + 1] = [27, 43]
        # y in [top - 2 - 2, bottom + 2 + 2] = [16, 54]
        for y in range(10, 61):
            for x in range(20, 51):
                expected_overlap = (27 <= x <= 43) and (16 <= y <= 54)
                actual_blocked = is_point_blocked(mask, 0, float(x), float(y), 0, 0, W, H)
                assert actual_blocked == expected_overlap, (
                    f"Margin pixel ({x}, {y}): expected {expected_overlap}, got {actual_blocked}"
                )

    def test_subpixel_conservative_safety_property(self):
        """Empirically stress-tests 10,000 sub-pixel continuous coordinates:

        The discrete C-space mask MUST NEVER produce a false negative (miss a collision).
        """
        H = 100
        W = 120
        words = (W + 63) // 64
        geom = np.full((1, 1, 4), np.nan, dtype=np.float64)
        left, top, right, bottom = 40.25, 30.75, 55.50, 65.25
        geom[0, 0] = [left, top, right, bottom]

        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)

        rng = np.random.default_rng(12345)
        # Sample points in a wide bounding box around the bone
        xs = rng.uniform(30.0, 70.0, size=10000)
        ys = rng.uniform(20.0, 80.0, size=10000)

        false_negatives = 0
        for i in range(10000):
            x, y = xs[i], ys[i]
            c2_hit = c2_aabb_overlap(x, y, left, top, right, bottom, 2.0, 2.0)
            bitmask_blocked = is_point_blocked(mask, 0, x, y, 0, 0, W, H)

            if c2_hit and not bitmask_blocked:
                false_negatives += 1

        assert false_negatives == 0, (
            f"Found {false_negatives} false negatives where Construct 2 declared collision "
            f"but C-space bitmask declared safe! Violates conservative safety theorem."
        )

    def test_64bit_word_boundary_straddling(self):
        """Hazard spanning x=60 to x=68 straddles uint64 word 0 (bits 0..63) and word 1 (bits 64..127).

        Asserts seamless bit continuity across the 64-bit word boundary.
        """
        H = 30
        W = 128
        words = 2
        geom = np.full((1, 1, 4), np.nan, dtype=np.float64)
        geom[0, 0] = [60.0, 10.0, 68.0, 20.0]

        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)

        # With rx=2, ry=2:
        # x range: [60 - 2, 68 + 2] = [58, 70]
        # In word 0: bits 58..63 must be 1.
        # In word 1: bits 0..6 (coordinates 64..70) must be 1.
        for y in range(10 - 2, 20 + 2 + 1):
            for x in range(50, 80):
                expected = (58 <= x <= 70)
                actual = is_point_blocked(mask, 0, float(x), float(y), 0, 0, W, H)
                assert actual == expected, (
                    f"Word boundary pixel ({x}, {y}): expected {expected}, got {actual}"
                )

    def test_multi_word_full_span_hazard(self):
        """Large hazard spanning across 4 words (x=20 to x=220 in W=256)."""
        H = 20
        W = 256
        words = 4
        geom = np.full((1, 1, 4), np.nan, dtype=np.float64)
        geom[0, 0] = [20.0, 5.0, 220.0, 15.0]

        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)

        # Expected x range: [18, 222]
        for x in [17, 18, 63, 64, 127, 128, 191, 192, 222, 223]:
            expected = (18 <= x <= 222)
            actual = is_point_blocked(mask, 0, float(x), 10.0, 0, 0, W, H)
            assert actual == expected, f"Multi-word span at x={x}: expected {expected}, got {actual}"


# ============================================================================
# Dimension 4: Initial Soul Clearance Across All Canonical Waves
# ============================================================================
class TestInitialSoulClearanceAllWaves:
    """Adversarially asserts that initial soul spawn coordinates are NEVER pre-blocked."""

    @pytest.mark.parametrize("wave_name", ALL_CANONICAL_WAVES)
    def test_initial_soul_clearance_zero_and_conservative_margin(self, wave_name):
        """Initial soul coordinates must be unblocked on BOTH mask_white and mask_blue."""
        csv_path = ROOT / "c2-sans-fight" / wave_name
        res = compile_wave(csv_path)

        init_x, init_y = res.initial[0], res.initial[1]
        ox, oy = res.origin
        h, w = res.dimensions

        # Test 1: Zero margin
        mw0, mb0 = prepare_collision_dual_native(res, margin_x=0.0, margin_y=0.0)
        assert not is_point_blocked(mw0, 0, init_x, init_y, ox, oy, w, h), (
            f"Wave {wave_name}: Initial state ({init_x}, {init_y}) is blocked in mask_white at tick 0 (zero margin)!"
        )
        assert not is_point_blocked(mb0, 0, init_x, init_y, ox, oy, w, h), (
            f"Wave {wave_name}: Initial state ({init_x}, {init_y}) is blocked in mask_blue at tick 0 (zero margin)!"
        )

        # Test 2: Conservative margin (margin_x=1.0, margin_y=2.0)
        mw, mb = prepare_collision_dual_native(res, margin_x=1.0, margin_y=2.0)
        assert not is_point_blocked(mw, 0, init_x, init_y, ox, oy, w, h), (
            f"Wave {wave_name}: Initial state ({init_x}, {init_y}) is blocked in mask_white at tick 0 (conservative margin)!"
        )
        assert not is_point_blocked(mb, 0, init_x, init_y, ox, oy, w, h), (
            f"Wave {wave_name}: Initial state ({init_x}, {init_y}) is blocked in mask_blue at tick 0 (conservative margin)!"
        )

        # Test 3: Dual-plane lethality oracle with stationary and moving velocity
        assert not is_dual_plane_lethal(mw, mb, 0, init_x, init_y, 0.0, 0.0, ox, oy, w, h), (
            f"Wave {wave_name}: Stationary initial soul declared lethal at tick 0!"
        )
        assert not is_dual_plane_lethal(mw, mb, 0, init_x, init_y, 150.0, 0.0, ox, oy, w, h), (
            f"Wave {wave_name}: Moving initial soul declared lethal at tick 0!"
        )

    @pytest.mark.parametrize("wave_name", ALL_CANONICAL_WAVES)
    def test_initial_soul_within_combat_zone_bounds(self, wave_name):
        """Initial soul coordinates must be comfortably within the tick-0 combat zone."""
        csv_path = ROOT / "c2-sans-fight" / wave_name
        res = compile_wave(csv_path)

        init_x, init_y = res.initial[0], res.initial[1]
        cz0 = res.env_schedule[0, 0:4]  # [left, top, right, bottom]

        # Player hitbox radius is 2, sprite is 8x8 or 16x16
        # Soul position must be strictly between combat zone boundaries
        assert cz0[0] <= init_x <= cz0[2], (
            f"Wave {wave_name}: init_x={init_x} is outside combat zone X bounds [{cz0[0]}, {cz0[2]}]"
        )
        assert cz0[1] <= init_y <= cz0[3], (
            f"Wave {wave_name}: init_y={init_y} is outside combat zone Y bounds [{cz0[1]}, {cz0[3]}]"
        )

    def test_platforms4_soul_placed_safely_on_platform_surface(self):
        """In sans_platforms4 and sans_platforms4hard, row 6 teleports soul to (175, 327) on the platform."""
        for p_name in ["sans_platforms4.csv", "sans_platforms4hard.csv"]:
            res = compile_wave(ROOT / "c2-sans-fight" / p_name)
            assert abs(res.initial[0] - 175.0) < 1e-4, f"{p_name} init_x should be 175.0, got {res.initial[0]}"
            assert abs(res.initial[1] - 327.0) < 1e-4, f"{p_name} init_y should be 327.0, got {res.initial[1]}"

            # Platform at tick 0 is at (151, 336), width 31
            # Soul Y=327 is exactly 9px above platform top Y=336 (resting on platform)
            mw, _ = prepare_collision_dual_native(res, margin_x=1.0, margin_y=2.0)
            ox, oy = res.origin
            h, w = res.dimensions
            assert not is_point_blocked(mw, 0, 175.0, 327.0, ox, oy, w, h)


# ============================================================================
# Dimension 5: Adversarial Edge Cases and Robustness
# ============================================================================
class TestAdversarialEdgeCasesAndRobustness:
    """Stress tests corner cases: empty geometry, NaN/Inf boxes, degenerate geometries."""

    def test_empty_geometry_produces_clean_zero_bitmasks(self):
        T, H, W = 10, 50, 100
        words = (W + 63) // 64
        geom = np.full((T, 0, 4), np.nan, dtype=np.float64)

        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)
        assert mask.shape == (T, H, words)
        assert np.all(mask == 0)
        assert not is_point_blocked(mask, 0, 25.0, 25.0, 0, 0, W, H)

    def test_all_nan_and_inf_geometry_ignored_cleanly(self):
        T, H, W = 5, 50, 100
        words = (W + 63) // 64
        geom = np.full((T, 3, 4), np.nan, dtype=np.float64)
        geom[0, 0] = [np.nan, 10.0, 20.0, 30.0]
        geom[0, 1] = [np.inf, -np.inf, np.nan, 0.0]
        geom[0, 2] = [-np.inf, 0.0, 10.0, 10.0]

        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)
        assert np.all(mask == 0)

    def test_out_of_bounds_hazard_boxes_properly_clipped(self):
        """BBoxes completely outside arena bounds (e.g. left < -100, right < 0) or beyond W."""
        T, H, W = 2, 50, 100
        words = (W + 63) // 64
        geom = np.full((T, 4, 4), np.nan, dtype=np.float64)

        # Far left
        geom[0, 0] = [-200.0, 10.0, -100.0, 30.0]
        # Far right
        geom[0, 1] = [500.0, 10.0, 600.0, 30.0]
        # Far top
        geom[0, 2] = [20.0, -200.0, 40.0, -100.0]
        # Far bottom
        geom[0, 3] = [20.0, 300.0, 40.0, 400.0]

        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)
        assert np.all(mask == 0), "Out of bounds hazards should be cleanly clipped with zero entries!"

    def test_inverted_coordinates_box_skipped_cleanly(self):
        """Malformed box where left > right or top > bottom."""
        T, H, W = 2, 50, 100
        words = (W + 63) // 64
        geom = np.full((T, 2, 4), np.nan, dtype=np.float64)
        geom[0, 0] = [50.0, 20.0, 30.0, 40.0]  # left > right
        geom[0, 1] = [20.0, 40.0, 40.0, 10.0]  # top > bottom

        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)
        assert np.all(mask == 0), "Inverted boxes should result in x1 < x0 or y1 < y0 and be skipped!"

    def test_massive_hazard_stress_density(self):
        """Stress-tests 500 simultaneous hazards at 1 tick."""
        T, H, W = 1, 100, 200
        words = (W + 63) // 64
        geom = np.full((T, 500, 4), np.nan, dtype=np.float64)

        rng = np.random.default_rng(999)
        for i in range(500):
            x = rng.uniform(10.0, 170.0)
            y = rng.uniform(10.0, 80.0)
            geom[0, i] = [x, y, x + 8.0, y + 8.0]

        mask = _prepare_collision_plane_njit(geom, 0, 0, H, W, words, 0.0, 0.0, 0.0, 2.0, 2.0)
        assert mask.shape == (1, 100, words)
        # Should have significant coverage without crashing or memory corruption
        assert np.sum(mask > 0) > 0
