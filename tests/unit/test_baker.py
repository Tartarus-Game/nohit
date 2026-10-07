"""
tests/unit/test_baker.py
~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive unit test suite for nohit.baker:
- Parser & TimelineVM execution
- Obstacle & dynamic platform rasterization
- Pure NumPy separable Minkowski dilation
- Top-level `bake_cspace` pipeline and performance thresholds (< 100 ms)
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
    dilate_cspace_2d,
    pack_hazard_tensor,
    unpack_hazard_tensor,
    BakeResult,
    PlatformInstance,
    AttackScriptParser,
    ParsedAttack,
    parse_attack,
    parse_csv_timeline,
    RasterizerConfig,
    RasterResult,
    rasterize_csv,
    rasterize_timeline,
)
from nohit.common.constants import DEFAULT_W, DEFAULT_H, DEFAULT_T, SOUL_W, SOUL_H
from nohit.common.types import Command


class TestParser(unittest.TestCase):
    """Verifies CSV parsing, repeat command expansion, and TimelineVM bytecode evaluation."""

    def setUp(self):
        self.parser = AttackScriptParser(fps=30)
        self.sample_dir = Path(r"<repo>\c2-sans-fight")

    def test_linear_script_with_trailing_commas(self):
        csv_text = (
            "0,CombatZoneResize,133,251,508,391,TLResume,,,\n"
            "0,HeartTeleport,320,376,,,,,\n"
            "0,HeartMode,1,,,,,,\n"
            "0.2,BoneV,100,50,40,0,120\n"
            "0.5,SansSlam,1\n"
            "1.0,EndAttack\n"
        )
        parsed = self.parser.parse_text(csv_text, max_frames=60)
        self.assertIsNotNone(parsed.initial_zone)
        self.assertEqual(parsed.initial_zone.x1, 133.0)
        self.assertEqual(parsed.initial_heart_pos, (320.0, 376.0))
        self.assertEqual(parsed.initial_heart_mode, 1)
        # Delay accumulation: 0 + 0 + 0 + 0.2 = 0.2s -> frame 6
        # + 0.5s = 0.7s -> frame 21
        bone_cmds = [c for c in parsed.commands if c.cmd_type == "BoneV"]
        self.assertEqual(len(bone_cmds), 1)
        self.assertEqual(bone_cmds[0].frame, 6)
        self.assertIn(21, parsed.slam_frames)

    def test_bone_repeat_expansion(self):
        csv_text = "0.2,BoneVRepeat,100,50,30,0,120,4,20,0\n"
        parsed = self.parser.parse_text(csv_text, expand_repeats=True)
        bone_cmds = [c for c in parsed.commands if c.cmd_type == "BoneV"]
        self.assertEqual(len(bone_cmds), 4)
        # Dir 0 (Right, angle 0 deg): cos=1, sin=0 -> xi = start_x - spacing * i
        expected_xs = [100.0, 80.0, 60.0, 40.0]
        for i, cmd in enumerate(bone_cmds):
            self.assertEqual(cmd.params["x"], expected_xs[i])
            self.assertEqual(cmd.params["height"], 30.0)
            self.assertEqual(cmd.params["speed"], 120.0)

    def test_platform_repeat_expansion(self):
        csv_text = "0.1,PlatformRepeat,200,60,50,2,90,3,30\n"
        parsed = self.parser.parse_text(csv_text, expand_repeats=True)
        plat_cmds = [c for c in parsed.commands if c.cmd_type == "Platform"]
        self.assertEqual(len(plat_cmds), 3)
        # Dir 2 (Left, angle 180 deg): cos=-1 -> xi = start_x - (-1)*spacing*i = start_x + spacing*i
        expected_xs = [200.0, 230.0, 260.0]
        for i, cmd in enumerate(plat_cmds):
            self.assertEqual(cmd.params["x"], expected_xs[i])

    def test_timeline_vm_arithmetic_and_loop(self):
        # A simple counting loop using SET, ADD, JMPE, JMPABS
        csv_text = (
            "0,SET,$Counter,0\n"
            "0,SET,$Limit,5\n"
            "# Line 3: loop start\n"
            "0.1,BoneV,$Counter,0,20,0,60\n"
            "0,ADD,$Counter,$Counter,10\n"
            "0,JMPE,8,$Counter,$Limit\n"  # If Counter == Limit, jump to end
            "0,JMPABS,3\n"               # Else jump back to line 3
            "# Line 8: end\n"
            "0,EndAttack\n"
        )
        parsed = self.parser.parse_text(csv_text, max_frames=60)
        bone_cmds = [c for c in parsed.commands if c.cmd_type == "BoneV"]
        self.assertGreater(len(bone_cmds), 0)

    def test_real_wave_file_parsing(self):
        csv_file = self.sample_dir / "sans_bonegap1.csv"
        if csv_file.is_file():
            parsed = self.parser.parse_file(csv_file, expand_repeats=True)
            self.assertIsNotNone(parsed.initial_zone)
            self.assertEqual(parsed.initial_zone.x1, 133.0)
            bone_cmds = [c for c in parsed.commands if c.cmd_type == "BoneV"]
            self.assertGreater(len(bone_cmds), 0)


class TestRasterizer(unittest.TestCase):
    """Verifies geometric obstacle rasterization and platform table generation."""

    def test_single_bone_motion(self):
        # Bone starting at x=10, y=10, height=20, moving right at 60 px/s (2 px/frame)
        commands = [
            Command(frame=0, time_s=0.0, cmd_type="BoneV", params={"x": 10.0, "y": 10.0, "height": 20.0, "direction": 0, "speed": 60.0, "color": 0}),
        ]
        res = rasterize_timeline(commands, T=10, W=100, H=80)
        self.assertEqual(res.O.shape, (10, 80, 100))
        # At t=0: x in [10..20], y in [10..30]
        self.assertTrue(np.all(res.O[0, 10:30, 10:20]))
        # At t=5: x moved by 2*5 = 10 px -> x in [20..30], y in [10..30]
        self.assertTrue(np.all(res.O[5, 10:30, 20:30]))

    def test_zero_size_bone_produces_no_hazard(self):
        commands = [
            Command(frame=0, time_s=0.0, cmd_type="BoneV", params={"x": 50.0, "y": 50.0, "height": 0.0, "direction": 0, "speed": 100.0, "color": 0}),
        ]
        res = rasterize_timeline(commands, T=5, W=100, H=80)
        self.assertFalse(np.any(res.O))

    def test_bonestab_phases(self):
        # BoneStab: dir=1 (bottom wall), height=30, warn_time=0.2s (6 frames), stab_time=0.2s (6 frames)
        commands = [
            Command(frame=0, time_s=0.0, cmd_type="BoneStab", params={"direction": 1, "height": 30.0, "warn_time": 0.2, "stab_time": 0.2}),
        ]
        res = rasterize_timeline(commands, T=20, W=100, H=80)
        # Warning phase (frames 0..5): zero hazard
        for t in range(6):
            self.assertFalse(np.any(res.O[t]), f"Frame {t} should be warning without hazard")

        # Extending phase (frames 6..8): hazard emerges
        self.assertTrue(np.any(res.O[7]))

        # Holding phase (frames 9..14): max depth 30 pixels from bottom
        self.assertTrue(np.all(res.O[10, 0:30, :]))
        self.assertFalse(np.any(res.O[10, 30:, :]))

    def test_platform_table_and_offscreen_retention(self):
        commands = [
            Command(frame=0, time_s=0.0, cmd_type="Platform", params={"x": 50.0, "y": 30.0, "width": 40.0, "direction": 0, "speed": 300.0}),
        ]
        res = rasterize_timeline(commands, T=15, W=100, H=80)
        self.assertEqual(len(res.platform_table), 15)
        # Platform should never be rasterized into lethal mask O
        self.assertFalse(np.any(res.O))
        # Platform must be recorded in platform_table across all frames
        for t in range(15):
            self.assertEqual(len(res.platform_table[t]), 1)
            p = res.platform_table[t][0]
            self.assertEqual(p.y_surf, 30)
            self.assertEqual(p.vx, 10.0)  # 300 / 30 = 10 px/frame
        # At t=14, x_min = 50 + 10 * 14 = 190 > W (100)
        self.assertGreater(res.platform_table[14][0].x_min, 100)


class TestDilator(unittest.TestCase):
    """Verifies Minkowski sum morphological dilation and memory/bitpacking operations."""

    def test_point_obstacle_interior(self):
        H, W = 160, 200
        w, h = 8, 8
        O = np.zeros((H, W), dtype=bool)
        y0, x0 = 50, 60
        O[y0, x0] = True

        B = dilate_2d(O, soul_w=w, soul_h=h)
        # Check interior valid arena [0..152, 0..192]
        interior = B[: H - h + 1, : W - w + 1]
        self.assertEqual(np.sum(interior), 64)
        # Exactly [50-7..50, 60-7..60] is True
        expected = np.zeros((H - h + 1, W - w + 1), dtype=bool)
        expected[y0 - h + 1 : y0 + 1, x0 - w + 1 : x0 + 1] = True
        self.assertTrue(np.array_equal(interior, expected))

    def test_point_at_origin(self):
        H, W = 160, 200
        O = np.zeros((H, W), dtype=bool)
        O[0, 0] = True

        B = dilate_2d(O, soul_w=8, soul_h=8)
        interior = B[: 153, : 193]
        self.assertTrue(interior[0, 0])
        self.assertEqual(np.sum(interior), 1)

    def test_empty_obstacle_field_has_outer_hazard_margins(self):
        H, W = 160, 200
        O = np.zeros((H, W), dtype=bool)
        B = dilate_2d(O, soul_w=8, soul_h=8)
        # Interior is completely free
        self.assertFalse(np.any(B[: 153, : 193]))
        # Outer margins are blocked
        self.assertTrue(np.all(B[153:, :]))
        self.assertTrue(np.all(B[:, 193:]))

    def test_solid_rectangle_dilation_area(self):
        H, W = 160, 200
        O = np.zeros((H, W), dtype=bool)
        # Obstacle of size 10 x 12
        O[40:50, 50:62] = True
        B = dilate_2d(O, soul_w=8, soul_h=8)
        interior = B[: 153, : 193]
        # Dilated area: (10 + 8 - 1) x (12 + 8 - 1) = 17 x 19 = 323 pixels
        self.assertEqual(np.sum(interior), 17 * 19)

    def test_distributive_over_union(self):
        H, W = 160, 200
        O1 = np.zeros((H, W), dtype=bool)
        O2 = np.zeros((H, W), dtype=bool)
        O1[20:30, 20:30] = True
        O2[25:35, 25:35] = True

        B_union = dilate_2d(O1 | O2, soul_w=8, soul_h=8)
        B_sep = dilate_2d(O1, soul_w=8, soul_h=8) | dilate_2d(O2, soul_w=8, soul_h=8)
        self.assertTrue(np.array_equal(B_union, B_sep))

    def test_2d_and_3d_consistency(self):
        T, H, W = 3, 160, 200
        np.random.seed(42)
        O = (np.random.rand(T, H, W) < 0.05).astype(bool)

        B_3d = dilate_3d(O, soul_w=8, soul_h=8)
        for t in range(T):
            B_2d = dilate_2d(O[t], soul_w=8, soul_h=8)
            self.assertTrue(np.array_equal(B_3d[t], B_2d))

    def test_bitpack_roundtrip(self):
        T, H, W = 5, 160, 200
        np.random.seed(123)
        O = (np.random.rand(T, H, W) < 0.1).astype(bool)
        B = dilate_3d(O, soul_w=8, soul_h=8)

        packed = pack_hazard_tensor(B)
        self.assertEqual(packed.shape, (T, H, 25))
        unpacked = unpack_hazard_tensor(packed, target_w=W)
        self.assertTrue(np.array_equal(B, unpacked))

    def test_invalid_dimension_raises(self):
        O = np.zeros((160, 200), dtype=bool)
        with self.assertRaises(ValueError):
            dilate_2d(O, soul_w=0, soul_h=8)
        with self.assertRaises(ValueError):
            dilate_2d(O, soul_w=201, soul_h=8)
        with self.assertRaises(ValueError):
            dilate_2d(np.zeros((2, 3, 4, 5)), soul_w=8, soul_h=8)


class TestBakePipeline(unittest.TestCase):
    """Verifies end-to-end `bake_cspace` pipeline and engineering performance requirements."""

    def setUp(self):
        self.sample_dir = Path(r"<repo>\c2-sans-fight")

    def test_bake_real_wave_bonegap1_performance(self):
        csv_file = self.sample_dir / "sans_bonegap1.csv"
        if not csv_file.is_file():
            self.skipTest(f"{csv_file} not found")

        res = bake_cspace(csv_file, T=150, W=DEFAULT_W, H=DEFAULT_H, soul_w=8, soul_h=8)
        self.assertIsInstance(res, BakeResult)
        self.assertEqual(res.B_hazard.shape, (150, 160, 200))
        self.assertEqual(res.B_hazard.dtype, bool)
        self.assertEqual(len(res.platform_table), 150)

        # Performance Assertion: entire prebaking pipeline must finish in < 100 ms
        total_baking_ms = res.metadata["total_baking_time_ms"]
        dilation_ms = res.metadata["dilation_time_ms"]
        self.assertLess(total_baking_ms, 100.0, f"Total baking time {total_baking_ms:.2f}ms exceeded 100ms threshold")
        self.assertLess(dilation_ms, 30.0, f"Dilation time {dilation_ms:.2f}ms exceeded 30ms limit")

        # Boundary checks
        self.assertTrue(np.all(res.B_hazard[:, 153:, :]))
        self.assertTrue(np.all(res.B_hazard[:, :, 193:]))

    def test_bake_real_wave_platforms1(self):
        csv_file = self.sample_dir / "sans_platforms1.csv"
        if not csv_file.is_file():
            self.skipTest(f"{csv_file} not found")

        res = bake_cspace(csv_file, T=60, W=DEFAULT_W, H=DEFAULT_H)
        self.assertEqual(len(res.platform_table), 60)
        total_platforms = sum(len(plats) for plats in res.platform_table)
        self.assertGreater(total_platforms, 0)
        self.assertLess(res.metadata["total_baking_time_ms"], 100.0)

    def test_nonexistent_csv_handled_gracefully(self):
        res = bake_cspace("non_existent_file_xyz.csv", T=5, W=DEFAULT_W, H=DEFAULT_H)
        self.assertEqual(res.B_hazard.shape, (5, DEFAULT_H, DEFAULT_W))
        self.assertEqual(len(res.platform_table), 5)


if __name__ == "__main__":
    unittest.main()
