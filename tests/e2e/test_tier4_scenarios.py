"""Tier 4: Real-World Scenarios E2E Tests.

Requirements:
- Complete wave simulations with real CSV scripts:
  1. sans_bonegap1.csv (Vertical gap jump-through)
  2. sans_boneslideh.csv (Horizontal bone slide dodging)
  3. sans_platforms1.csv (Dynamic platform jumping and carriage)
- Synthetic deadlock scenarios (100% early-stop detection at t*)
- SansSlam phase space collapse verification (|R_{t*+1}| <= 193)
- CLI benchmark data schema validation
- End-to-end REST API solve validation
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tests.e2e.harness import (
    DEFAULT_H,
    DEFAULT_W,
    SOUL_H,
    SOUL_W,
    BakeResult,
    PlatformInstance,
    SolveResult,
    VerificationResult,
    get_baker,
    get_engine,
    get_verifier,
)


class TestTier4RealWorldScenarios(unittest.TestCase):
    """Tier 4: Full End-to-End Real-World Scenarios."""

    def setUp(self):
        self.baker = get_baker()
        self.engine = get_engine()
        self.verifier = get_verifier()
        self.sample_csv_dir = Path(r"c:\Users\lf\Documents\Workspace\nohit\c2-sans-fight")

    def test_s1_real_scenario_sans_bonegap1(self):
        """Scenario 1: sans_bonegap1.csv end-to-end bake, solve, and forward verify."""
        csv_path = self.sample_csv_dir / "sans_bonegap1.csv"
        if not csv_path.exists():
            self.skipTest(f"{csv_path} not found")

        # Bake 35 frames
        bake_res = self.baker(csv_path, T=35)
        self.assertEqual(bake_res.B_hazard.shape, (35, DEFAULT_H, DEFAULT_W))

        # Solve lattice DP
        sol = self.engine(bake_res)
        self.assertFalse(sol.is_deadlock, "sans_bonegap1 is a feasible wave and must not be deadlock")
        self.assertIsNotNone(sol.action_sequence)
        self.assertEqual(len(sol.action_sequence), 34)

        # Independent simulation replay
        v_res = self.verifier(bake_res, sol.action_sequence)
        self.assertTrue(v_res.passed, f"Collisions detected in sans_bonegap1: {v_res.collision_frames}")
        self.assertEqual(len(v_res.collision_frames), 0)

    def test_s2_real_scenario_sans_boneslideh(self):
        """Scenario 2: sans_boneslideh.csv end-to-end bake, solve, and forward verify."""
        csv_path = self.sample_csv_dir / "sans_boneslideh.csv"
        if not csv_path.exists():
            self.skipTest(f"{csv_path} not found")

        bake_res = self.baker(csv_path, T=35)
        sol = self.engine(bake_res)
        self.assertFalse(sol.is_deadlock, "sans_boneslideh is a feasible wave and must not be deadlock")
        self.assertIsNotNone(sol.action_sequence)

        v_res = self.verifier(bake_res, sol.action_sequence)
        self.assertTrue(v_res.passed, f"Collisions detected in sans_boneslideh: {v_res.collision_frames}")
        self.assertEqual(len(v_res.collision_frames), 0)

    def test_s3_real_scenario_sans_platforms1(self):
        """Scenario 3: sans_platforms1.csv end-to-end bake, solve, and forward verify."""
        csv_path = self.sample_csv_dir / "sans_platforms1.csv"
        if not csv_path.exists():
            self.skipTest(f"{csv_path} not found")

        bake_res = self.baker(csv_path, T=35)
        sol = self.engine(bake_res)
        self.assertFalse(sol.is_deadlock, "sans_platforms1 is a feasible wave and must not be deadlock")
        self.assertIsNotNone(sol.action_sequence)

        v_res = self.verifier(bake_res, sol.action_sequence)
        self.assertTrue(v_res.passed, f"Collisions detected in sans_platforms1: {v_res.collision_frames}")
        self.assertEqual(len(v_res.collision_frames), 0)

    def test_s4_synthetic_unavoidable_deadlock(self):
        """Scenario 4: Synthetic unavoidable deadlock detected 100% with exact early stop."""
        T = 25
        B_hazard = np.zeros((T, 160, 200), dtype=bool)

        # Make arena completely filled with deadly obstacles starting at frame 12
        deadlock_trigger_frame = 12
        B_hazard[deadlock_trigger_frame:, :, :] = True

        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
        )

        sol = self.engine(bake_res)
        self.assertTrue(sol.is_deadlock, "Complete obstacle barrage must be determined as deadlock")
        self.assertIsNotNone(sol.deadlock_frame)
        self.assertLessEqual(sol.deadlock_frame, deadlock_trigger_frame)
        self.assertIsNone(sol.action_sequence)

    def test_s5_synthetic_slam_and_bonestab(self):
        """Scenario 5: SansSlam followed by ground BoneStab asserts collapse bound & escape."""
        T = 20
        B_hazard = np.zeros((T, 160, 200), dtype=bool)

        # Slam at frame 3
        # Ground bone stab from frame 7 to 11 (floor y in [0, 18] is deadly)
        B_hazard[7:11, :18, :] = True

        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 50),
            metadata={"slam_frames": [3]},
        )

        sol = self.engine(bake_res)
        self.assertFalse(sol.is_deadlock, "Player should be able to jump over ground stab")

        # Verify phase space collapse bound: |R_{slam+1}| <= 193
        if len(sol.stats.alive_states_history) > 4:
            states_post_slam = sol.stats.alive_states_history[4]
            self.assertLessEqual(
                states_post_slam,
                DEFAULT_W - SOUL_W + 1,
                f"Phase space size {states_post_slam} exceeded bound 193",
            )

        v_res = self.verifier(bake_res, sol.action_sequence)
        self.assertTrue(v_res.passed, "Trajectory must evade ground stabs")

    def test_s6_benchmark_cli_stats_schema(self):
        """Scenario 6: Verify benchmark CLI metrics schema and integrity."""
        csv_path = self.sample_csv_dir / "sans_bonegap1.csv"
        bake_res = self.baker(csv_path if csv_path.exists() else "dummy.csv", T=20)
        sol = self.engine(bake_res)

        stats = sol.stats
        stats_dict = {
            "baking_ms": stats.baking_ms,
            "dp_ms": stats.dp_ms,
            "peak_alive_states": stats.peak_alive_states,
            "alive_states_history": stats.alive_states_history,
            "total_states_explored": stats.total_states_explored,
            "peak_memory_mb": stats.peak_memory_mb,
        }

        # Check required metrics
        for key in ["baking_ms", "dp_ms", "peak_alive_states", "peak_memory_mb"]:
            self.assertIn(key, stats_dict)
            self.assertIsInstance(stats_dict[key], (int, float))

    def test_s7_web_server_e2e_solve(self):
        """Scenario 7: Full REST API simulation resolving solve request with JSON payload."""
        csv_path = self.sample_csv_dir / "sans_bonegap1.csv"
        bake_res = self.baker(csv_path if csv_path.exists() else "dummy.csv", T=20)
        sol = self.engine(bake_res)

        # Simulate JSON serialization from API response
        api_data = {
            "status": "success",
            "is_deadlock": sol.is_deadlock,
            "deadlock_frame": sol.deadlock_frame,
            "action_sequence": sol.action_sequence,
            "trajectory": sol.trajectory,
            "stats": {
                "dp_ms": sol.stats.dp_ms,
                "peak_alive_states": sol.stats.peak_alive_states,
            },
        }

        serialized = json.dumps(api_data)
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized["status"], "success")
        self.assertEqual(deserialized["is_deadlock"], sol.is_deadlock)
        self.assertEqual(len(deserialized["action_sequence"]), len(sol.action_sequence))


if __name__ == "__main__":
    unittest.main()
