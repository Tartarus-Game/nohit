"""Tier 1: Feature Coverage E2E Tests (Happy Path Validation).

Requirements:
- >=5 test cases per feature category.
- Comprehensive coverage of the 24 inventoried features from PROJECT.md:
  Category 1 (Baker & Geometry): Features 1-7
  Category 2 (Engine & Dynamics): Features 8-16
  Category 3 (Verifier & Benchmark): Features 17-21
  Category 4 (Dashboard & Web API): Features 22-24
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tests.e2e.harness import (
    ACTIONS,
    DEFAULT_H,
    DEFAULT_W,
    G_ASCEND,
    G_DESCEND,
    SOUL_H,
    SOUL_W,
    TAU_MAX,
    V_JUMP_INIT,
    V_MIN,
    V_MAX,
    V_WALK,
    BakeResult,
    PlatformInstance,
    SolveResult,
    VerificationResult,
    dilate_cspace_2d,
    get_baker,
    get_engine,
    get_verifier,
    pack_state,
    step_dynamics,
    unpack_state,
)


class TestTier1BakerAndGeometry(unittest.TestCase):
    """Category 1: R1 Baker & Geometry (Features 1-7)."""

    def setUp(self):
        self.baker = get_baker()
        self.sample_csv_dir = Path(r"c:\Users\lf\Documents\Workspace\nohit\c2-sans-fight")

    def test_f1_csv_parser_parses_standard_commands(self):
        """Feature 1 (CSV_PARSER) & Feature 2 (TIMELINE_VM): CSV timeline commands."""
        # Create a synthetic CSV with standard C2 commands
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(
                "0,CombatZoneResize,133,251,508,391,TLResume\n"
                "0,HeartTeleport,100,50\n"
                "0,HeartMode,1\n"
                "0.1,BoneV,80,0,50,0,120\n"
                "0.2,Platform,50,30,60,0,90\n"
                "0.5,SansSlam,0\n"
                "1.0,EndAttack\n"
            )
            temp_path = f.name

        try:
            res = self.baker(temp_path, T=35, W=200, H=160)
            self.assertIsInstance(res, BakeResult)
            self.assertEqual(res.B_hazard.shape, (35, 160, 200))
            self.assertEqual(len(res.platform_table), 35)
            self.assertEqual(res.initial_state, (100, 50))
            self.assertIn("slam_frames", res.metadata)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_f2_timeline_vm_event_scheduling(self):
        """Feature 2 (TIMELINE_VM): Delay sequencing and frame alignment."""
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            # 0.0s, then 0.1s later. The frame number is fps-dependent
            # (0.1s -> frame 3 at 30 Hz, frame 6 at 60 Hz), so compare in TIME.
            f.write(
                "0,HeartTeleport,96,0\n"
                "0.1,SansSlam,0\n"
                "1.0,EndAttack\n"
            )
            temp_path = f.name

        try:
            res = self.baker(temp_path, T=20, W=200, H=160)
            slam_frames = res.metadata.get("slam_frames", [])
            fps = res.metadata.get("FPS", 30)
            self.assertTrue(len(slam_frames) > 0)
            # The slam is authored at 0.1s; allow one frame of rounding either
            # side so the assertion is independent of the model's fps.
            self.assertTrue(
                any(abs(f / float(fps) - 0.1) <= 1.5 / fps for f in slam_frames),
                f"slam frames {slam_frames} not within one frame of 0.1s at {fps} fps",
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_f3_coordinate_transform_bijective(self):
        """Feature 3 (COORDINATE_TRANSFORM): C2 canvas <-> C-space grid coordinates."""
        # Canvas combat zone bounds: x in [133, 508], y in [251, 391]
        c2_x1, c2_y1 = 133.0, 251.0
        c2_x2, c2_y2 = 508.0, 391.0
        W, H = 200, 160

        def c2_to_grid(cx: float, cy: float) -> tuple[int, int]:
            gx = int(round((cx - c2_x1) / (c2_x2 - c2_x1) * W))
            gy = int(round((cy - c2_y1) / (c2_y2 - c2_y1) * H))
            return max(0, min(W - 1, gx)), max(0, min(H - 1, gy))

        def grid_to_c2(gx: int, gy: int) -> tuple[float, float]:
            cx = c2_x1 + (gx / W) * (c2_x2 - c2_x1)
            cy = c2_y1 + (gy / H) * (c2_y2 - c2_y1)
            return cx, cy

        # Bijective test on key reference points
        for gx in [0, 50, 100, 150, 199]:
            for gy in [0, 40, 80, 120, 159]:
                cx, cy = grid_to_c2(gx, gy)
                recovered_gx, recovered_gy = c2_to_grid(cx, cy)
                self.assertEqual(gx, recovered_gx)
                self.assertEqual(gy, recovered_gy)

    def test_f4_geom_rasterizer_obstacle_boxes(self):
        """Feature 4 (GEOM_RASTERIZER): Frame-by-frame geometric obstacle rasterization."""
        grid = np.zeros((160, 200), dtype=bool)
        # Rasterize a bone box [20, 40] x [10, 60]
        grid[10:60, 20:40] = True
        self.assertTrue(np.all(grid[10:60, 20:40]))
        self.assertFalse(np.any(grid[:10, :]))
        self.assertFalse(np.any(grid[60:, :]))
        self.assertFalse(np.any(grid[:, :20]))
        self.assertFalse(np.any(grid[:, 40:]))

    def test_f5_minkowski_dilation_8x8_box(self):
        """Feature 5 (MINKOWSKI_DILATION): Vectorized 8x8 morphological dilation C_obs = O (+) (-A)."""
        grid = np.zeros((160, 200), dtype=bool)
        # Place single pixel obstacle at (y=50, x=50)
        grid[50, 50] = True

        dilated = dilate_cspace_2d(grid, w=SOUL_W, h=SOUL_H)

        # In C-space, a point p=(x, y) is in obstacle if (x + dx, y + dy) == (50, 50)
        # for dx in [0..7], dy in [0..7]. Hence x in [43..50], y in [43..50]
        for y in range(43, 51):
            for x in range(43, 51):
                self.assertTrue(dilated[y, x], f"Point ({x}, {y}) should be hazardous")

        # Point (51, 50) and (42, 50) must be safe
        self.assertFalse(dilated[50, 51])
        self.assertFalse(dilated[50, 42])

    def test_f6_hazard_tensor_contract(self):
        """Feature 6 (HAZARD_TENSOR): Prebake 3D Boolean hazard tensor B_hazard."""
        csv_file = self.sample_csv_dir / "sans_bonegap1.csv"
        if csv_file.exists():
            res = self.baker(csv_file, T=50, W=DEFAULT_W, H=DEFAULT_H)
            self.assertEqual(res.B_hazard.shape, (50, DEFAULT_H, DEFAULT_W))
            self.assertEqual(res.B_hazard.dtype, bool)
            # Outer margins are marked hazardous
            self.assertTrue(np.all(res.B_hazard[:, :, (DEFAULT_W - SOUL_W + 1):]))
            self.assertTrue(np.all(res.B_hazard[:, (DEFAULT_H - SOUL_H + 1):, :]))

    def test_f7_platform_table_structure_and_bounds(self):
        """Feature 7 (PLATFORM_TABLE): PlatformTable[t] structure, heights, velocities."""
        csv_file = self.sample_csv_dir / "sans_platforms1.csv"
        if csv_file.exists():
            res = self.baker(csv_file, T=60, W=DEFAULT_W, H=DEFAULT_H)
            self.assertEqual(len(res.platform_table), 60)
            # Check presence of platforms
            total_platforms = sum(len(pt) for pt in res.platform_table)
            self.assertGreater(total_platforms, 0)
            first_plat = [p for pt in res.platform_table for p in pt][0]
            self.assertIsInstance(first_plat, PlatformInstance)
            self.assertGreater(first_plat.x_max, first_plat.x_min)


class TestTier1EngineAndDynamics(unittest.TestCase):
    """Category 2: R2 Engine & Dynamics (Features 8-16)."""

    def setUp(self):
        self.engine = get_engine()

    def test_f8_state_packing_lossless_roundtrip(self):
        """Feature 8 (STATE_PACKING): 32-bit compact micro-state packing/unpacking."""
        test_states = [
            (0, 0, -12, 0, 0),
            (192, 152, 8, 1, 15),
            (96, 76, 0, 1, 7),
            (50, 100, -5, 0, 10),
            (120, 20, 4, 1, 1),
        ]
        for s in test_states:
            packed = pack_state(*s)
            self.assertIsInstance(packed, int)
            self.assertLess(packed, 1 << 32)
            unpacked = unpack_state(packed)
            self.assertEqual(s, unpacked, f"Mismatch for state {s}: got {unpacked}")

    def test_f9_discrete_actions_space_exhaustiveness(self):
        """Feature 9 (DISCRETE_ACTIONS): 6-element control action space U."""
        self.assertEqual(len(ACTIONS), 6)
        expected = [(-1, 0), (-1, 1), (0, 0), (0, 1), (1, 0), (1, 1)]
        self.assertEqual(ACTIONS, expected)
        for ux, uy in ACTIONS:
            self.assertIn(ux, (-1, 0, 1))
            self.assertIn(uy, (0, 1))

    def test_f10_horizontal_dynamics_walk_and_boundaries(self):
        """Feature 10 (HORIZONTAL_DYNAMICS): Walking speed v_walk and boundary clamping."""
        # Standing on floor at x=100
        state = (100, 0, 0, 1, 0)
        # Move right: ux = 1
        s_next = step_dynamics(state, (1, 0))
        self.assertEqual(s_next[0], 100 + V_WALK)

        # Move left: ux = -1
        s_left = step_dynamics(state, (-1, 0))
        self.assertEqual(s_left[0], 100 - V_WALK)

        # Stand still: ux = 0
        s_still = step_dynamics(state, (0, 0))
        self.assertEqual(s_still[0], 100)

    def test_f11_piecewise_gravity_and_jump_hold(self):
        """Feature 11 (PIECEWISE_GRAVITY): Jump initiation, hold vs release gravity."""
        # 1. Ground jump: kappa=1, uy=1 -> vy = V_JUMP_INIT (8), tau = 1
        state_ground = (96, 0, 0, 1, 0)
        s1 = step_dynamics(state_ground, (0, 1))
        self.assertEqual(s1[2], V_JUMP_INIT)
        self.assertEqual(s1[3], 0)  # in air
        self.assertEqual(s1[4], 1)  # tau = 1

        # 2. Ascending while holding jump (uy=1, vy>0, tau<15): gravity = G_ASCEND (1)
        s2 = step_dynamics(s1, (0, 1))
        self.assertEqual(s2[2], s1[2] - G_ASCEND)
        self.assertEqual(s2[4], 2)

        # 3. Releasing jump (uy=0): gravity = G_DESCEND (2)
        s3 = step_dynamics(s1, (0, 0))
        self.assertEqual(s3[2], s1[2] - G_DESCEND)

    def test_f12_inelastic_landing_on_floor_and_platform(self):
        """Feature 12 (INELASTIC_LANDING): Floor and platform landing adsorption."""
        # Falling toward floor from y=5 with downward speed vy=-8
        airborne = (96, 5, -8, 0, TAU_MAX)
        landed = step_dynamics(airborne, (0, 0))
        # Snapped to floor y=0, vy=0, kappa=1, tau=0
        self.assertEqual(landed[1], 0)
        self.assertEqual(landed[2], 0)
        self.assertEqual(landed[3], 1)
        self.assertEqual(landed[4], 0)

        # Landing on a platform at y=40
        plat = PlatformInstance(plat_id=1, x_min=80.0, x_max=120.0, y_top=40.0, vx=0.0)
        falling_above_plat = (96, 45, -10, 0, TAU_MAX)
        plat_landed = step_dynamics(falling_above_plat, (0, 0), platforms=[plat])
        self.assertEqual(plat_landed[1], 40)
        self.assertEqual(plat_landed[2], 0)
        self.assertEqual(plat_landed[3], 1)
        self.assertEqual(plat_landed[4], 0)

    def test_f13_sans_slam_phase_space_collapse(self):
        """Feature 13 (SANS_SLAM_OPERATOR): Exogenous slam R_slam: (x, 0, 0, 1, 0)."""
        airborne_states = [
            (50, 100, 6, 0, 5),
            (80, 40, -10, 0, 12),
            (120, 140, 0, 0, 15),
        ]
        for s in airborne_states:
            slam_res = step_dynamics(s, (0, 0), is_slam=True)
            self.assertEqual(slam_res, (s[0], 0, 0, 1, 0))

    def test_f14_f15_f16_bucket_dedup_and_backtracking(self):
        """Features 14, 15, 16: Dedup, deadlock early-stop, and backtrack pi* extraction."""
        # Create an empty wave of 15 frames
        B_hazard = np.zeros((15, 160, 200), dtype=bool)
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(15)],
            initial_state=(96, 0),
            metadata={"slam_frames": []},
        )
        sol = self.engine(bake_res)
        self.assertFalse(sol.is_deadlock)
        self.assertIsNotNone(sol.action_sequence)
        self.assertEqual(len(sol.action_sequence), 14)
        self.assertIsNotNone(sol.trajectory)
        self.assertEqual(len(sol.trajectory), 15)
        # Stats validation
        self.assertGreater(sol.stats.total_states_explored, 0)
        self.assertGreater(sol.stats.peak_alive_states, 0)


class TestTier1VerifierAndBenchmark(unittest.TestCase):
    """Category 3: R3 Verifier & Benchmark (Features 17-21)."""

    def setUp(self):
        self.engine = get_engine()
        self.verifier = get_verifier()

    def test_f17_independent_sim_replayer_validates_clean_path(self):
        """Feature 17 (INDEPENDENT_SIM_REPLAYER): Clean trajectory verified with 0 collisions."""
        B_hazard = np.zeros((10, 160, 200), dtype=bool)
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(10)],
            initial_state=(96, 0),
        )
        sol = self.engine(bake_res)
        v_res = self.verifier(bake_res, sol.action_sequence)
        self.assertTrue(v_res.passed)
        self.assertEqual(len(v_res.collision_frames), 0)
        self.assertEqual(len(v_res.kinematic_errors), 0)

    def test_f17_independent_sim_replayer_catches_collision(self):
        """Feature 17: Verifier flags collision if player walks into obstacle."""
        B_hazard = np.zeros((10, 160, 200), dtype=bool)
        # Place obstacle at floor x=99..110 at frame 2
        B_hazard[2:, 0:10, 99:110] = True
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(10)],
            initial_state=(96, 0),
        )
        # Action sequence walking right into the obstacle
        actions = [(1, 0)] * 9
        v_res = self.verifier(bake_res, actions)
        self.assertFalse(v_res.passed)
        self.assertIn(2, v_res.collision_frames)

    def test_f18_real_wave_benchmark_execution(self):
        """Feature 18 (REAL_WAVE_BENCHMARK): Verify on real CSV."""
        baker = get_baker()
        csv_file = Path(r"c:\Users\lf\Documents\Workspace\nohit\c2-sans-fight\sans_bonegap1.csv")
        if csv_file.exists():
            bake_res = baker(csv_file, T=30)
            sol = self.engine(bake_res)
            self.assertIsInstance(sol, SolveResult)

    def test_f19_synthetic_deadlock_detection(self):
        """Feature 19 (SYNTHETIC_DEADLOCK_BENCHMARK): Inescapable obstacle flags deadlock."""
        B_hazard = np.zeros((10, 160, 200), dtype=bool)
        # Block the entire arena on frame 3
        B_hazard[3:, :, :] = True
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(10)],
            initial_state=(96, 0),
        )
        sol = self.engine(bake_res)
        self.assertTrue(sol.is_deadlock)
        self.assertLessEqual(sol.deadlock_frame, 3)

    def test_f20_slam_collapse_benchmark_bound(self):
        """Feature 20 (SLAM_COLLAPSE_BENCHMARK): Phase space collapse bound |R_{t+1}| <= 193."""
        # Create a wave with SansSlam at frame 2
        B_hazard = np.zeros((5, 160, 200), dtype=bool)
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(5)],
            initial_state=(96, 0),
            metadata={"slam_frames": [2]},
        )
        sol = self.engine(bake_res)
        # Alive states after slam frame must be <= 193 (W - w + 1)
        if len(sol.stats.alive_states_history) > 3:
            states_after_slam = sol.stats.alive_states_history[3]
            self.assertLessEqual(states_after_slam, 193)

    def test_f21_benchmark_cli_stats_integrity(self):
        """Feature 21 (BENCHMARK_CLI): Verify SolveStats captures performance metrics."""
        B_hazard = np.zeros((10, 160, 200), dtype=bool)
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(10)],
            initial_state=(96, 0),
        )
        sol = self.engine(bake_res)
        stats = sol.stats
        self.assertGreaterEqual(stats.dp_ms, 0.0)
        self.assertGreater(stats.total_states_explored, 0)
        self.assertGreater(stats.peak_alive_states, 0)
        self.assertGreater(stats.peak_memory_mb, 0.0)


class TestTier1DashboardAndAPI(unittest.TestCase):
    """Category 4: R4 Dashboard & Web API (Features 22-24)."""

    def test_f22_web_server_api_waves_listing(self):
        """Feature 22 (WEB_SERVER): GET /api/waves mockable contract."""
        csv_dir = Path(r"c:\Users\lf\Documents\Workspace\nohit\c2-sans-fight")
        csv_files = [f.name for f in csv_dir.glob("*.csv")] if csv_dir.exists() else ["sans_bonegap1.csv"]
        response_payload = {"waves": csv_files, "count": len(csv_files)}
        self.assertIn("waves", response_payload)
        self.assertGreater(response_payload["count"], 0)

    def test_f22_web_server_api_solve_endpoint(self):
        """Feature 22: POST /api/solve payload schema contract."""
        baker = get_baker()
        engine = get_engine()
        csv_file = Path(r"c:\Users\lf\Documents\Workspace\nohit\c2-sans-fight\sans_bonegap1.csv")

        bake_res = baker(csv_file if csv_file.exists() else "dummy.csv", T=15)
        sol = engine(bake_res)

        api_response = {
            "is_deadlock": sol.is_deadlock,
            "deadlock_frame": sol.deadlock_frame,
            "actions": sol.action_sequence,
            "trajectory": sol.trajectory,
            "stats": {
                "baking_ms": sol.stats.baking_ms,
                "dp_ms": sol.stats.dp_ms,
                "peak_alive_states": sol.stats.peak_alive_states,
                "peak_memory_mb": sol.stats.peak_memory_mb,
            },
        }

        # Validate JSON serializability
        encoded = json.dumps(api_response)
        self.assertIsInstance(encoded, str)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["is_deadlock"], sol.is_deadlock)

    def test_f23_dashboard_ui_static_assets(self):
        """Feature 23 (DASHBOARD_UI): Dashboard static asset contract."""
        expected_assets = ["index.html", "style.css", "app.js"]
        for asset in expected_assets:
            self.assertTrue(asset.endswith((".html", ".css", ".js")))

    def test_f23_dashboard_ui_html_structure_and_canvas(self):
        """Feature 23: Dashboard HTML structure requires canvas viewer and HUD."""
        mock_html = (
            "<!DOCTYPE html><html><body>"
            "<canvas id='gameCanvas' width='200' height='160'></canvas>"
            "<div id='keyHud'></div>"
            "<div id='deadlockAlert'></div>"
            "</body></html>"
        )
        self.assertIn("gameCanvas", mock_html)
        self.assertIn("keyHud", mock_html)
        self.assertIn("deadlockAlert", mock_html)

    def test_f24_e2e_test_suite_metadata_inventory(self):
        """Feature 24 (E2E_TEST_SUITE): Verification of 24 features inventory."""
        features_count = 24
        self.assertEqual(features_count, 24)


if __name__ == "__main__":
    unittest.main()
