"""
tests/test_m1_adversarial.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Adversarial challenge and stress-testing suite for Milestone 1 (C-space Hazard Baker):
1. Minkowski Sum Dilation Mathematical Correctness vs. Brute-Force Ground Truth Oracle
2. Boundary Collision Masking and Impassable Margins (x=0, x=W-w, y=0, y=H-h)
3. Edge-Case, Malformed, and Pathological CSV Handling (empty, zero delays, negative coords, invalid commands)
4. High Load & Stress Scaling Performance
"""

import math
import os
import tempfile
import time
import unittest
from pathlib import Path
import numpy as np

from nohit.baker import (
    bake_cspace,
    dilate_cspace,
    dilate_2d,
    dilate_3d,
    pack_hazard_tensor,
    unpack_hazard_tensor,
    BakeResult,
    AttackScriptParser,
    rasterize_timeline,
    RasterizerConfig,
)
from nohit.common.constants import DEFAULT_W, DEFAULT_H, DEFAULT_T, SOUL_W, SOUL_H
from nohit.common.types import Command, PlatformInstance


def brute_force_minkowski_oracle_2d(
    O: np.ndarray,
    soul_w: int = SOUL_W,
    soul_h: int = SOUL_H,
) -> np.ndarray:
    """Exact point-by-point brute-force ground truth oracle for 2D C-space dilation:
        C_obs(y, x) = True iff soul [x, x+w) x [y, y+h) overlaps any True pixel in O,
        OR (y, x) is outside [0, H-h] x [0, W-w].
    """
    H, W = O.shape
    C_obs = np.ones((H, W), dtype=bool)  # Impassable by default (outer bounds)
    valid_w = W - soul_w + 1
    valid_h = H - soul_h + 1

    for y in range(valid_h):
        for x in range(valid_w):
            C_obs[y, x] = np.any(O[y : y + soul_h, x : x + soul_w])

    return C_obs


def brute_force_minkowski_oracle_3d(
    O: np.ndarray,
    soul_w: int = SOUL_W,
    soul_h: int = SOUL_H,
) -> np.ndarray:
    """Exact 3D ground truth oracle iterating frame-by-frame."""
    T, H, W = O.shape
    out = np.zeros((T, H, W), dtype=bool)
    for t in range(T):
        out[t] = brute_force_minkowski_oracle_2d(O[t], soul_w=soul_w, soul_h=soul_h)
    return out


class TestMinkowskiGroundTruthOracle(unittest.TestCase):
    """Empirically validates pure NumPy separable dilation against brute-force ground truth."""

    def test_random_obstacle_fields_various_densities(self):
        """Tests 20 random obstacle fields across densities from 0% to 100%."""
        rng = np.random.default_rng(1337)
        densities = [0.0, 0.001, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 0.80, 1.0]

        for density in densities:
            for soul_size in [(8, 8), (1, 1), (4, 4), (12, 6)]:
                sw, sh = soul_size
                O = (rng.random((160, 200)) < density)

                dilated = dilate_2d(O, soul_w=sw, soul_h=sh)
                oracle = brute_force_minkowski_oracle_2d(O, soul_w=sw, soul_h=sh)

                diff = np.where(dilated != oracle)
                mismatches = len(diff[0])
                self.assertEqual(
                    mismatches, 0,
                    f"Mismatch between dilate_2d and brute-force oracle at density={density}, "
                    f"soul=({sw},{sh}): {mismatches} mismatching pixels"
                )

    def test_3d_batch_tensor_vs_oracle(self):
        """Tests 3D tensor against 3D ground truth oracle."""
        rng = np.random.default_rng(2026)
        T, H, W = 10, 50, 60
        sw, sh = 6, 8
        O = (rng.random((T, H, W)) < 0.08)

        dilated_3d = dilate_3d(O, soul_w=sw, soul_h=sh)
        oracle_3d = brute_force_minkowski_oracle_3d(O, soul_w=sw, soul_h=sh)

        self.assertTrue(
            np.array_equal(dilated_3d, oracle_3d),
            "dilate_3d does not match 3D brute force oracle"
        )

    def test_single_pixel_at_all_extremes(self):
        """Places single-pixel obstacles at each extreme corner and verifies exact dilation footprint."""
        H, W = 160, 200
        sw, sh = 8, 8

        corners = [
            (0, 0),                    # Bottom-left
            (0, W - 1),                # Bottom-right
            (H - 1, 0),                # Top-left
            (H - 1, W - 1),            # Top-right
            (H // 2, W // 2),          # Interior center
        ]

        for oy, ox in corners:
            O = np.zeros((H, W), dtype=bool)
            O[oy, ox] = True

            dilated = dilate_2d(O, soul_w=sw, soul_h=sh)
            oracle = brute_force_minkowski_oracle_2d(O, soul_w=sw, soul_h=sh)

            self.assertTrue(
                np.array_equal(dilated, oracle),
                f"Mismatch for single-pixel obstacle at ({oy}, {ox})"
            )

            expected_hazard_box_x = (max(0, ox - sw + 1), min(W - sw, ox))
            expected_hazard_box_y = (max(0, oy - sh + 1), min(H - sh, oy))

            if expected_hazard_box_x[0] <= expected_hazard_box_x[1] and expected_hazard_box_y[0] <= expected_hazard_box_y[1]:
                subgrid = dilated[
                    expected_hazard_box_y[0] : expected_hazard_box_y[1] + 1,
                    expected_hazard_box_x[0] : expected_hazard_box_x[1] + 1,
                ]
                self.assertTrue(np.all(subgrid), f"Obstacle footprint incomplete at ({oy}, {ox})")

    def test_minkowski_union_and_subset_properties(self):
        """Verifies formal morphological properties: Distributivity and Monotonicity."""
        rng = np.random.default_rng(999)
        O1 = (rng.random((160, 200)) < 0.05)
        O2 = (rng.random((160, 200)) < 0.05)

        D1 = dilate_2d(O1)
        D2 = dilate_2d(O2)
        D_union = dilate_2d(O1 | O2)

        # Distributivity: (A | B) (+) K == (A (+) K) | (B (+) K)
        self.assertTrue(
            np.array_equal(D_union, D1 | D2),
            "Minkowski dilation violates distributivity over union"
        )

        # Monotonicity: O1 <= (O1 | O2) implies D1 <= D_union
        self.assertTrue(
            np.all((D_union & D1) == D1),
            "Minkowski dilation violates monotonicity"
        )


class TestBoundaryCollisionMasking(unittest.TestCase):
    """Stress-tests boundary collision masking at x=0, x=W-w, y=0, y=H-h and out-of-bounds margins."""

    def setUp(self):
        self.W = DEFAULT_W   # 200
        self.H = DEFAULT_H   # 160
        self.w = SOUL_W      # 8
        self.h = SOUL_H      # 8
        self.max_x = self.W - self.w  # 192
        self.max_y = self.H - self.h  # 152

    def test_completely_empty_arena_boundaries(self):
        """In an empty arena, all valid positions [0, max_y] x [0, max_x] MUST be safe (False),
        and ALL margin positions (x > max_x or y > max_y) MUST be hazard (True).
        """
        O = np.zeros((self.H, self.W), dtype=bool)
        B = dilate_2d(O, soul_w=self.w, soul_h=self.h)

        # 1. Interior and inner boundary lines must be 100% free
        self.assertFalse(np.any(B[: self.max_y + 1, : self.max_x + 1]))

        # Check the 4 exact boundary points
        self.assertFalse(B[0, 0], "Corner (0, 0) should be free in empty arena")
        self.assertFalse(B[0, self.max_x], f"Corner (0, {self.max_x}) should be free")
        self.assertFalse(B[self.max_y, 0], f"Corner ({self.max_y}, 0) should be free")
        self.assertFalse(B[self.max_y, self.max_x], f"Corner ({self.max_y}, {self.max_x}) should be free")

        # 2. Outer margins must be 100% True (hazard/wall)
        # Right margin: x from max_x + 1 (193) to W - 1 (199)
        self.assertTrue(np.all(B[:, self.max_x + 1 :]))
        # Top margin: y from max_y + 1 (153) to H - 1 (159)
        self.assertTrue(np.all(B[self.max_y + 1 :, :]))

    def test_single_pixel_on_exact_arena_boundaries(self):
        """Test obstacle placement exactly on arena walls and verify correct masking."""
        # 1. Obstacle at Left Wall (x=0, y=50)
        O = np.zeros((self.H, self.W), dtype=bool)
        O[50, 0] = True
        B = dilate_2d(O, soul_w=self.w, soul_h=self.h)
        # Soul at x=0 touches x=0..7 -> touches obstacle -> Hazard
        self.assertTrue(B[50, 0])
        # Soul at x=1 covers x=1..8 -> does NOT touch x=0 -> Free
        self.assertFalse(B[50, 1])

        # 2. Obstacle at Right Wall (x=W-1=199, y=50)
        O = np.zeros((self.H, self.W), dtype=bool)
        O[50, self.W - 1] = True
        B = dilate_2d(O, soul_w=self.w, soul_h=self.h)
        # Soul at max_x=192 covers x=192..199 -> touches x=199 -> Hazard
        self.assertTrue(B[50, self.max_x])
        # Soul at x=191 covers x=191..198 -> does NOT touch x=199 -> Free
        self.assertFalse(B[50, self.max_x - 1])

        # 3. Obstacle at Floor (y=0, x=50)
        O = np.zeros((self.H, self.W), dtype=bool)
        O[0, 50] = True
        B = dilate_2d(O, soul_w=self.w, soul_h=self.h)
        # Soul at y=0 covers y=0..7 -> touches y=0 -> Hazard
        self.assertTrue(B[0, 50])
        # Soul at y=1 covers y=1..8 -> does NOT touch y=0 -> Free
        self.assertFalse(B[1, 50])

        # 4. Obstacle at Ceiling (y=H-1=159, x=50)
        O = np.zeros((self.H, self.W), dtype=bool)
        O[self.H - 1, 50] = True
        B = dilate_2d(O, soul_w=self.w, soul_h=self.h)
        # Soul at max_y=152 covers y=152..159 -> touches y=159 -> Hazard
        self.assertTrue(B[self.max_y, 50])
        # Soul at y=151 covers y=151..158 -> does NOT touch y=159 -> Free
        self.assertFalse(B[self.max_y - 1, 50])


class TestEdgeCaseCSVs(unittest.TestCase):
    """Adversarial testing on edge-case, corrupt, and pathological CSV scripts."""

    def test_completely_empty_csv_string_and_file(self):
        """Empty CSV should parse cleanly and bake a valid BakeResult."""
        parser = AttackScriptParser()
        parsed = parser.parse_text("")
        self.assertEqual(len(parsed.commands), 0)

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("")
            tmp_path = f.name

        try:
            res = bake_cspace(tmp_path, T=60, W=200, H=160)
            self.assertIsInstance(res, BakeResult)
            self.assertEqual(res.B_hazard.shape, (60, 160, 200))
            self.assertEqual(len(res.platform_table), 60)
            self.assertTrue(all(len(p) == 0 for p in res.platform_table))
            # Valid arena interior must be safe
            self.assertFalse(np.any(res.B_hazard[:, :153, :193]))
            # Outer margins must be impassable
            self.assertTrue(np.all(res.B_hazard[:, 153:, :]))
            self.assertTrue(np.all(res.B_hazard[:, :, 193:]))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_csv_with_whitespace_and_empty_rows(self):
        """CSV containing only whitespace, newlines, empty commas."""
        content = "\n\n   \t  \n,,,,\n , , , \n\n"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            res = bake_cspace(tmp_path, T=30)
            self.assertIsInstance(res, BakeResult)
            self.assertEqual(res.B_hazard.shape, (30, 160, 200))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_csv_with_unknown_command_names_ignored_gracefully(self):
        """Unknown or unhandled command names should be ignored without crashing."""
        content = (
            "0.0,UnknownCommandXYZ,1,2,3,4,5\n"
            "0.1,AnotherWeirdOpcode,foo,bar\n"
            "0.2,CustomDummyAction,999\n"
            "0.5,BoneV,50,50,30,0,10\n"  # Valid command
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            res = bake_cspace(tmp_path, T=40)
            self.assertIsInstance(res, BakeResult)
            self.assertEqual(res.B_hazard.shape, (40, 160, 200))
            # The valid bone should have been rasterized
            self.assertTrue(np.any(res.B_hazard[15:30, :, :]))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_csv_with_malformed_numeric_arguments_reproduces_value_error(self):
        """Adversarial Challenge: When known commands receive non-numeric strings,
        rasterizer.py lines 296, 319, 338, 345 raise unhandled ValueError because
        float(...) is called without try-except in the per-frame dispatch loop.
        """
        content = "0.0,BoneV,not_a_number,50,40,0,10\n"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            # Empirically verify that this triggers ValueError in current worker implementation
            with self.assertRaises(ValueError):
                bake_cspace(tmp_path, T=10)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_zero_width_platform_ghost_support(self):
        """Adversarial Challenge: Platform with width=0 is accepted and provides ghost support."""
        content = "0.0,Platform,50,40,0,0,0\n"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            res = bake_cspace(tmp_path, T=5)
            self.assertEqual(len(res.platform_table[0]), 1)
            plat = res.platform_table[0][0]
            self.assertEqual(plat.x_min, 50.0)
            self.assertEqual(plat.x_max, 50.0)
            # Empirically verify that soul [45, 53] is erroneously reported as supported by width=0 platform
            self.assertTrue(
                plat.is_supporting(45, soul_w=8),
                "Zero-width platform should not support soul, but is_supporting evaluates to True"
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_csv_with_zero_delays_and_simultaneous_commands(self):
        """Large burst of commands all at delay 0.0 (scheduled simultaneously at frame 0)."""
        lines = []
        for i in range(50):
            lines.append(f"0.0,BoneV,{20 + i * 2},30,20,0,0")
        lines.append("0.0,Platform,10,40,80,0,0")
        lines.append("0.0,SansSlam,1")
        content = "\n".join(lines)

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            res = bake_cspace(tmp_path, T=20)
            self.assertEqual(res.B_hazard.shape, (20, 160, 200))
            self.assertIn(0, res.metadata.get("slam_frames", []))
            self.assertEqual(len(res.platform_table[0]), 1)
            # Bone obstacles should be present on frame 0
            self.assertTrue(np.any(res.B_hazard[0, :, :]))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_csv_with_negative_coordinates(self):
        """Entities spawned at negative coordinates entering or leaving the arena."""
        content = (
            # Bone spawned at negative x, traveling right into arena (+vx)
            "0.0,BoneV,-50,40,30,0,60\n"
            # Bone spawned at negative y, traveling up into arena (+vy)
            "0.0,BoneH,50,-30,40,3,60\n"
            # Bone spawned off-screen moving away
            "0.0,BoneV,-100,50,20,2,60\n"
            # Moving platform entering from negative x
            "0.0,Platform,-60,50,100,0,30\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            res = bake_cspace(tmp_path, T=60)
            self.assertIsInstance(res, BakeResult)
            self.assertEqual(res.B_hazard.shape, (60, 160, 200))
            # On frame 0, negative entities are mostly outside arena
            # As frames advance, they enter arena and create hazards
            self.assertTrue(np.any(res.B_hazard[30, :, :]))
            # Verify platform table contains platform instances
            self.assertTrue(len(res.platform_table[30]) > 0)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_csv_with_extreme_values_and_overflow_protection(self):
        """Extremely large coordinates or counts should not cause integer overflow or crash."""
        content = (
            "0.0,BoneV,1000000,1000000,1000000,0,1000000\n"
            "0.0,Platform,1000000,1000000,1000000,0,1000000\n"
            "0.0,BoneVRepeat,0,0,20,0,10,0,10\n"     # count = 0
            "0.0,BoneVRepeat,0,0,20,0,10,-5,10\n"    # count = -5
            "0.0,BoneStab,1,0,0.1,0.1\n"             # height = 0
            "0.0,BoneStab,99,20,0.1,0.1\n"           # invalid direction = 99
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            res = bake_cspace(tmp_path, T=10)
            self.assertEqual(res.B_hazard.shape, (10, 160, 200))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_timeline_vm_infinite_loop_and_math_exceptions(self):
        """TimelineVM handles infinite jumps (max_steps cap), division by zero, and modulo by zero."""
        parser = AttackScriptParser(fps=30)

        # 1. Division and modulo by zero
        vm_script = [
            "0.0,SET,$a,10",
            "0.0,DIV,$b,$a,0",    # Div by zero -> 0.0
            "0.0,MOD,$c,$a,0",    # Mod by zero -> 0.0
            "0.0,EndAttack",
        ]
        cmds = parser._execute_vm(vm_script, max_frames=30)
        self.assertGreater(len(cmds), 0)

        # 2. Infinite jump loop: JMPABS back to line 1
        inf_loop_script = [
            "0.0,SET,$x,1",
            "0.0,ADD,$x,$x,1",
            "0.0,JMPABS,2",       # Loop back to line 2
        ]
        t0 = time.perf_counter()
        cmds_loop = parser._execute_vm(inf_loop_script, max_frames=30)
        t_elapsed = time.perf_counter() - t0
        # Should terminate at max_steps (50000) in < 0.2s without hanging
        self.assertLess(t_elapsed, 0.5)


class TestStressAndScalingPerformance(unittest.TestCase):
    """Stress tests high entity counts and long timeline horizons."""

    def test_high_density_entity_burst(self):
        """Simulates 300 active bones in flight across 150 frames."""
        lines = ["0.0,CombatZoneResize,133,251,508,391"]
        # Spawn 300 bones staggered over 150 frames
        for i in range(300):
            delay = 0.02
            x = (i * 17) % 200
            y = (i * 13) % 120
            h = 10 + (i % 40)
            d = (i % 4)
            spd = 30.0 + (i % 60)
            lines.append(f"{delay:.2f},BoneV,{x},{y},{h},{d},{spd}")

        content = "\n".join(lines)
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            t0 = time.perf_counter()
            res = bake_cspace(tmp_path, T=150, W=200, H=160)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            self.assertIsInstance(res, BakeResult)
            self.assertEqual(res.B_hazard.shape, (150, 160, 200))
            # Total baking under high entity load should remain < 250 ms
            self.assertLess(
                elapsed_ms, 250.0,
                f"High-density stress baking took {elapsed_ms:.2f} ms (expected < 250 ms)"
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_long_horizon_baking(self):
        """Tests T=450 frames (15 seconds) long duration."""
        csv_text = "0.0,BoneVRepeat,0,0,30,0,60,20,15"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(csv_text)
            tmp_path = f.name

        try:
            t0 = time.perf_counter()
            res = bake_cspace(tmp_path, T=450, W=200, H=160)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            self.assertEqual(res.B_hazard.shape, (450, 160, 200))
            # Pure NumPy dilation should scale linearly O(T)
            self.assertLess(
                elapsed_ms, 300.0,
                f"Long horizon baking (T=450) took {elapsed_ms:.2f} ms"
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_bitpack_roundtrip_arbitrary_widths(self):
        """Verifies bit-packing and unpacking on both standard (W=200) and arbitrary non-aligned widths."""
        for target_w in [1, 7, 8, 9, 15, 16, 17, 197, 200, 203]:
            rng = np.random.default_rng(42 + target_w)
            original = (rng.random((5, 20, target_w)) > 0.5)

            packed = pack_hazard_tensor(original)
            unpacked = unpack_hazard_tensor(packed, target_w)

            self.assertTrue(
                np.array_equal(original, unpacked),
                f"Bitpack roundtrip failed for width {target_w}"
            )


if __name__ == "__main__":
    unittest.main()
