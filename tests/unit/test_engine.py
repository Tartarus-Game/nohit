"""
tests/unit/test_engine.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive unit test suite covering nohit.engine:
- Feature 8 (STATE_PACKING): 32-bit compact bit packing, scalar and vectorized.
- Feature 9 (DISCRETE_ACTIONS): 6-element control space and bijection.
- Feature 10 (HORIZONTAL_DYNAMICS): Walking speed v_walk and platform convection.
- Feature 11 (PIECEWISE_GRAVITY): Jump initiation impulse and piecewise gravity.
- Feature 12 (INELASTIC_LANDING): Floor and one-way platform surface adsorption.
- Feature 13 (SANS_SLAM_OPERATOR): Exogenous SansSlam phase space collapse.
- Feature 14 (BUCKET_DEDUP): Vectorized compact micro-state deduplication.
- Feature 15 (DEADLOCK_EARLY_STOP): Early stop on empty alive set.
- Feature 16 (BACKTRACK_ACTION_EXTRACTION): Linear O(T) action extraction.
- Performance & Resource Constraints: < 500 ms for T=150, < 100 MB RAM.
"""

from __future__ import annotations

import time
import unittest
import numpy as np

from nohit.common.constants import (
    ACTIONS,
    DEFAULT_W,
    DEFAULT_H,
    SOUL_W,
    SOUL_H,
    SOUL_MAX_X,
    SOUL_MAX_Y,
    V_WALK,
    V_JUMP_INIT,
    V_MIN,
    V_MAX,
    G_ASCEND,
    G_DESCEND,
    TAU_MAX,
)
from nohit.common.types import (
    Action,
    ALL_ACTIONS,
    BakeResult,
    PlatformInstance,
    SolveResult,
    SolveStats,
    State,
)
from nohit.engine.state import (
    pack_state,
    unpack_state,
    unpack_state_to_state,
    pack_states_vec,
    pack_states_array,
    unpack_states_vec,
    unpack_states_to_array,
)
from nohit.engine.dynamics import (
    step_dynamics,
    step_dynamics_batch,
)
from nohit.engine.solver import solve_lattice_dp


class TestStatePackingAndActions(unittest.TestCase):
    """Feature 8 (STATE_PACKING) and Feature 9 (DISCRETE_ACTIONS)."""

    def test_scalar_packing_lossless_roundtrip(self):
        test_states = [
            (0, 0, -12, 0, 0),
            (192, 152, 8, 1, 15),
            (96, 76, 0, 1, 7),
            (50, 100, -5, 0, 10),
            (120, 20, 4, 1, 1),
            (0, 152, -12, 1, 0),
            (192, 0, 8, 0, 15),
        ]
        for s in test_states:
            packed = pack_state(*s)
            self.assertIsInstance(packed, int)
            self.assertGreaterEqual(packed, 0)
            self.assertLess(packed, 1 << 32)
            recovered = unpack_state(packed)
            self.assertEqual(recovered, s, f"Mismatch for state {s}: got {recovered}")

    def test_pack_with_tuple_or_state_object(self):
        s_tuple = (96, 40, -2, 1, 5)
        s_obj = State(*s_tuple)
        p1 = pack_state(s_tuple)
        p2 = pack_state(s_obj)
        p3 = pack_state(*s_tuple)
        self.assertEqual(p1, p2)
        self.assertEqual(p1, p3)
        recovered_state = unpack_state_to_state(p1)
        self.assertEqual(recovered_state, s_obj)

    def test_vectorized_packing_roundtrip(self):
        N = 1000
        rng = np.random.default_rng(42)
        x = rng.integers(0, SOUL_MAX_X + 1, size=N, dtype=np.int32)
        y = rng.integers(0, SOUL_MAX_Y + 1, size=N, dtype=np.int32)
        vy = rng.integers(V_MIN, V_MAX + 1, size=N, dtype=np.int32)
        kappa = rng.integers(0, 2, size=N, dtype=np.int32)
        tau = rng.integers(0, TAU_MAX + 1, size=N, dtype=np.int32)

        packed = pack_states_vec(x, y, vy, kappa, tau)
        self.assertEqual(packed.shape, (N,))
        self.assertEqual(packed.dtype, np.uint32)

        rx, ry, rvy, rkappa, rtau = unpack_states_vec(packed)
        np.testing.assert_array_equal(x, rx)
        np.testing.assert_array_equal(y, ry)
        np.testing.assert_array_equal(vy, rvy)
        np.testing.assert_array_equal(kappa, rkappa)
        np.testing.assert_array_equal(tau, rtau)

    def test_pack_states_array_and_unpack_to_array(self):
        states = np.array([
            [0, 0, -12, 0, 0],
            [192, 152, 8, 1, 15],
            [96, 76, 0, 1, 7],
            [50, 100, -5, 0, 10],
        ], dtype=np.int32)

        packed = pack_states_array(states)
        self.assertEqual(len(packed), 4)
        recovered = unpack_states_to_array(packed)
        np.testing.assert_array_equal(states, recovered)

    def test_empty_vectorized_packing(self):
        empty = np.empty((0, 5), dtype=np.int32)
        packed = pack_states_array(empty)
        self.assertEqual(len(packed), 0)
        recovered = unpack_states_to_array(packed)
        self.assertEqual(recovered.shape, (0, 5))

    def test_f9_discrete_actions_space(self):
        self.assertEqual(len(ACTIONS), 6)
        expected = [(-1, 0), (-1, 1), (0, 0), (0, 1), (1, 0), (1, 1)]
        self.assertEqual(ACTIONS, expected)
        for idx, (ux, uy) in enumerate(ACTIONS):
            act = Action.from_index(idx)
            self.assertEqual(act.ux, ux)
            self.assertEqual(act.uy, uy)
            self.assertEqual(act.action_index, idx)
            self.assertEqual(act.to_tuple(), (ux, uy))


class TestHorizontalDynamicsAndConvection(unittest.TestCase):
    """Feature 10 (HORIZONTAL_DYNAMICS) and boundary interactions."""

    def test_walk_displacements(self):
        state = (100, 0, 0, 1, 0)
        # Walk right
        s_right = step_dynamics(state, (1, 0))
        self.assertEqual(s_right[0], 100 + V_WALK)
        # Walk left
        s_left = step_dynamics(state, (-1, 0))
        self.assertEqual(s_left[0], 100 - V_WALK)
        # Stand still
        s_still = step_dynamics(state, (0, 0))
        self.assertEqual(s_still[0], 100)

    def test_arena_horizontal_boundaries_clamping(self):
        # Left boundary clamping at 0
        s_left = step_dynamics((1, 0, 0, 1, 0), (-1, 0))
        self.assertEqual(s_left[0], 0)
        s_left2 = step_dynamics((0, 0, 0, 1, 0), (-1, 0))
        self.assertEqual(s_left2[0], 0)

        # Right boundary clamping at SOUL_MAX_X (192)
        max_x = DEFAULT_W - SOUL_W
        s_right = step_dynamics((max_x - 1, 0, 0, 1, 0), (1, 0))
        self.assertEqual(s_right[0], max_x)
        s_right2 = step_dynamics((max_x, 0, 0, 1, 0), (1, 0))
        self.assertEqual(s_right2[0], max_x)

    def test_platform_convection_grounded_vs_airborne(self):
        plat = PlatformInstance(plat_id=1, x_min=50.0, x_max=150.0, y_top=30.0, vx=4.0)

        # Grounded on platform (kappa = 1) -> convection applied
        s_ground = (80, 30, 0, 1, 0)
        s_conv = step_dynamics(s_ground, (1, 0), platforms=[plat])
        self.assertEqual(s_conv[0], 80 + V_WALK + 4)

        # Airborne at same coordinate (kappa = 0) -> NO convection applied
        s_air = (80, 30, 0, 0, 5)
        s_no_conv = step_dynamics(s_air, (1, 0), platforms=[plat])
        self.assertEqual(s_no_conv[0], 80 + V_WALK)

    def test_platform_convection_wall_clamping(self):
        max_x = DEFAULT_W - SOUL_W
        plat = PlatformInstance(plat_id=1, x_min=150.0, x_max=220.0, y_top=0.0, vx=10.0)
        state = (188, 0, 0, 1, 0)
        # 188 + 3 + 10 = 201 -> clamped to 192
        s_next = step_dynamics(state, (1, 0), platforms=[plat])
        self.assertEqual(s_next[0], max_x)

    def test_batch_horizontal_dynamics_matches_scalar(self):
        states = np.array([
            [100, 0, 0, 1, 0],
            [1, 0, 0, 1, 0],
            [191, 0, 0, 1, 0],
            [80, 30, 0, 1, 0],
        ], dtype=np.int32)
        plat = PlatformInstance(plat_id=1, x_min=50.0, x_max=150.0, y_top=30.0, vx=4.0)

        for act in ACTIONS:
            batch_next = step_dynamics_batch(states, act[0], act[1], platforms=[plat])
            for i, s in enumerate(states):
                scalar_next = step_dynamics(tuple(s), act, platforms=[plat])
                self.assertEqual(tuple(batch_next[i]), scalar_next)


class TestPiecewiseGravityAndJump(unittest.TestCase):
    """Feature 11 (PIECEWISE_GRAVITY) and vertical dynamics."""

    def test_ground_jump_impulse(self):
        ground = (96, 0, 0, 1, 0)
        jumped = step_dynamics(ground, (0, 1))
        self.assertEqual(jumped[2], V_JUMP_INIT)  # 8
        self.assertEqual(jumped[3], 0)            # airborne
        self.assertEqual(jumped[4], 1)            # tau = 1
        self.assertEqual(jumped[1], 8)            # y = 0 + 8 = 8

    def test_ascending_vs_descending_gravity(self):
        # Ascending while holding jump: gravity = G_ASCEND (1)
        air_hold = (96, 20, 7, 0, 2)
        s_hold = step_dynamics(air_hold, (0, 1))
        self.assertEqual(s_hold[2], 7 - G_ASCEND)  # 6
        self.assertEqual(s_hold[4], 3)             # tau increments to 3

        # Jump released mid-air: gravity = G_DESCEND (2)
        s_rel = step_dynamics(air_hold, (0, 0))
        self.assertEqual(s_rel[2], 7 - G_DESCEND)  # 5
        self.assertEqual(s_rel[4], TAU_MAX)        # tau forced to TAU_MAX (15)

    def test_terminal_falling_velocity_saturation(self):
        state = (96, 140, 0, 0, TAU_MAX)
        for _ in range(10):
            state = step_dynamics(state, (0, 0))
            self.assertGreaterEqual(state[2], V_MIN)
        self.assertEqual(state[2], V_MIN)

    def test_tau_counter_saturation(self):
        state = (96, 50, 6, 0, 14)
        s1 = step_dynamics(state, (0, 1))
        self.assertEqual(s1[4], 15)
        # Next frame with tau=15 uses G_DESCEND
        s2 = step_dynamics(s1, (0, 1))
        self.assertEqual(s2[4], 15)
        self.assertEqual(s2[2], s1[2] - G_DESCEND)

    def test_ceiling_clamping(self):
        max_y = DEFAULT_H - SOUL_H  # 152
        high = (96, 150, 8, 0, 1)
        s_next = step_dynamics(high, (0, 1))
        self.assertEqual(s_next[1], max_y)


class TestInelasticLandingAndSurfaces(unittest.TestCase):
    """Feature 12 (INELASTIC_LANDING) on floor and dynamic platforms."""

    def test_floor_landing_adsorption(self):
        falling = (96, 5, -8, 0, TAU_MAX)
        landed = step_dynamics(falling, (0, 0))
        self.assertEqual(landed[1], 0)
        self.assertEqual(landed[2], 0)
        self.assertEqual(landed[3], 1)
        self.assertEqual(landed[4], 0)

    def test_platform_landing_adsorption(self):
        plat = PlatformInstance(plat_id=1, x_min=80.0, x_max=120.0, y_top=40.0, vx=0.0)
        falling = (96, 45, -10, 0, TAU_MAX)
        landed = step_dynamics(falling, (0, 0), platforms=[plat])
        self.assertEqual(landed[1], 40)
        self.assertEqual(landed[2], 0)
        self.assertEqual(landed[3], 1)
        self.assertEqual(landed[4], 0)

    def test_one_way_jumpthrough_platform_from_below(self):
        plat = PlatformInstance(plat_id=1, x_min=80.0, x_max=120.0, y_top=25.0, vx=0.0)
        # Jumping from y=20 upward with vy=8 -> y_next_star = 28 > 25
        # Since y=20 < 25 (from below), soul passes through without landing
        s_jump = (96, 20, 8, 0, 1)
        s_next = step_dynamics(s_jump, (0, 1), platforms=[plat])
        self.assertGreater(s_next[1], 25)
        self.assertEqual(s_next[3], 0)  # still airborne

    def test_stacked_platforms_highest_surface_selected(self):
        plat_low = PlatformInstance(plat_id=1, x_min=50.0, x_max=150.0, y_top=20.0, vx=0.0)
        plat_high = PlatformInstance(plat_id=2, x_min=50.0, x_max=150.0, y_top=45.0, vx=0.0)
        falling = (96, 50, -10, 0, TAU_MAX)
        # Trajectory crosses both y=45, y=20, and y=0
        landed = step_dynamics(falling, (0, 0), platforms=[plat_low, plat_high])
        self.assertEqual(landed[1], 45)  # snaps to highest surface y=45
        self.assertEqual(landed[3], 1)

    def test_immediate_jump_retrigger_after_landing(self):
        falling = (96, 4, -8, 0, TAU_MAX)
        landed = step_dynamics(falling, (0, 0))
        self.assertEqual(landed[1], 0)
        self.assertEqual(landed[3], 1)
        re_jump = step_dynamics(landed, (0, 1))
        self.assertEqual(re_jump[2], V_JUMP_INIT)
        self.assertEqual(re_jump[3], 0)


class TestSansSlamOperator(unittest.TestCase):
    """Feature 13 (SANS_SLAM_OPERATOR)."""

    def test_sans_slam_collapses_all_vertical_dimensions(self):
        states = [
            (50, 100, 6, 0, 5),
            (80, 40, -10, 0, 12),
            (120, 140, 0, 0, 15),
            (10, 0, 0, 1, 0),
        ]
        for s in states:
            slam_res = step_dynamics(s, (0, 0), is_slam=True)
            self.assertEqual(slam_res, (s[0], 0, 0, 1, 0))

    def test_sans_slam_with_horizontal_movement(self):
        state = (100, 80, 4, 0, 3)
        # Move right during slam: next_x = 100 + V_WALK = 103
        slam_res = step_dynamics(state, (1, 0), is_slam=True)
        self.assertEqual(slam_res, (100 + V_WALK, 0, 0, 1, 0))

    def test_batch_sans_slam_matches_scalar(self):
        states = np.array([
            [50, 100, 6, 0, 5],
            [80, 40, -10, 0, 12],
            [120, 140, 0, 0, 15],
        ], dtype=np.int32)
        batch_out = step_dynamics_batch(states, 1, 0, is_slam=True)
        for i, s in enumerate(states):
            scalar_out = step_dynamics(tuple(s), (1, 0), is_slam=True)
            self.assertEqual(tuple(batch_out[i]), scalar_out)


class TestSolverFRSAndDedup(unittest.TestCase):
    """Features 14 (BUCKET_DEDUP), 15 (DEADLOCK_EARLY_STOP), 16 (BACKTRACK_ACTION_EXTRACTION)."""

    def test_f14_bucket_deduplication(self):
        # Wave of 10 frames in empty arena
        B_hazard = np.zeros((10, 160, 200), dtype=bool)
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(10)],
            initial_state=(96, 0),
        )
        sol = solve_lattice_dp(bake_res)
        self.assertFalse(sol.is_deadlock)
        # Verify deduplication kept alive count bounded
        self.assertLess(sol.stats.peak_alive_states, 2000)
        self.assertEqual(len(sol.stats.alive_states_history), 10)

    def test_f15_frame_zero_spawn_deadlock(self):
        B_hazard = np.zeros((10, 160, 200), dtype=bool)
        B_hazard[0, 0, 96] = True  # Obstacle at spawn location
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(10)],
            initial_state=(96, 0),
        )
        sol = solve_lattice_dp(bake_res)
        self.assertTrue(sol.is_deadlock)
        self.assertEqual(sol.deadlock_frame, 0)
        self.assertIsNone(sol.action_sequence)
        self.assertIsNone(sol.trajectory)

    def test_f15_mid_wave_inescapable_deadlock(self):
        B_hazard = np.zeros((10, 160, 200), dtype=bool)
        # Block the entire arena on frame 4
        B_hazard[4:, :, :] = True
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(10)],
            initial_state=(96, 0),
        )
        sol = solve_lattice_dp(bake_res)
        self.assertTrue(sol.is_deadlock)
        self.assertLessEqual(sol.deadlock_frame, 4)
        self.assertIsNone(sol.action_sequence)

    def test_f16_backtrack_action_and_trajectory_lengths(self):
        T = 20
        B_hazard = np.zeros((T, 160, 200), dtype=bool)
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
        )
        sol = solve_lattice_dp(bake_res)
        self.assertFalse(sol.is_deadlock)
        self.assertIsNotNone(sol.action_sequence)
        self.assertIsNotNone(sol.trajectory)
        self.assertEqual(len(sol.action_sequence), T - 1)
        self.assertEqual(len(sol.trajectory), T)

    def test_f16_trajectory_kinematic_consistency_with_actions(self):
        # Simulate forward along the extracted actions to verify they reproduce trajectory
        T = 15
        B_hazard = np.zeros((T, 160, 200), dtype=bool)
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
        )
        sol = solve_lattice_dp(bake_res)
        curr = sol.trajectory[0]
        self.assertEqual(curr[:2], (96, 0))

        for t in range(T - 1):
            act = sol.action_sequence[t]
            next_sim = step_dynamics(curr, act)
            self.assertEqual(next_sim, sol.trajectory[t + 1], f"Kinematic mismatch at step {t}")
            curr = next_sim

    def test_edge_cases_duration(self):
        # T = 0
        B_hazard_0 = np.zeros((0, 160, 200), dtype=bool)
        bake_0 = BakeResult(B_hazard_0, [], (96, 0))
        sol_0 = solve_lattice_dp(bake_0)
        self.assertFalse(sol_0.is_deadlock)
        self.assertEqual(sol_0.action_sequence, [])
        self.assertEqual(sol_0.trajectory, [])

        # T = 1
        B_hazard_1 = np.zeros((1, 160, 200), dtype=bool)
        bake_1 = BakeResult(B_hazard_1, [[]], (96, 0))
        sol_1 = solve_lattice_dp(bake_1)
        self.assertFalse(sol_1.is_deadlock)
        self.assertEqual(sol_1.action_sequence, [])
        self.assertEqual(len(sol_1.trajectory), 1)
        self.assertEqual(sol_1.trajectory[0][:2], (96, 0))


class TestPerformanceAndResourceConstraints(unittest.TestCase):
    """Performance Acceptance Criteria: DP solve time < 500 ms for T=150, peak RAM < 100 MB."""

    def test_benchmark_t150_performance_and_memory(self):
        T = 150
        B_hazard = np.zeros((T, DEFAULT_H, DEFAULT_W), dtype=bool)
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
        )

        t0 = time.perf_counter()
        sol = solve_lattice_dp(bake_res)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0

        self.assertFalse(sol.is_deadlock)
        self.assertEqual(len(sol.action_sequence), T - 1)
        self.assertEqual(len(sol.trajectory), T)

        # Performance constraint: < 500 ms
        self.assertLess(elapsed_ms, 500.0, f"DP solve took {elapsed_ms:.2f} ms (limit: 500 ms)")
        self.assertLess(sol.stats.dp_ms, 500.0)

        # Memory constraint: < 100 MB
        self.assertLess(sol.stats.peak_memory_mb, 100.0, f"Peak memory {sol.stats.peak_memory_mb} MB (limit: 100 MB)")
        self.assertGreater(sol.stats.peak_memory_mb, 0.0)

    def test_sans_slam_phase_space_collapse(self):
        # Wave with SansSlam at frame 3
        T = 6
        B_hazard = np.zeros((T, DEFAULT_H, DEFAULT_W), dtype=bool)
        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
            metadata={"slam_frames": [3]},
        )
        sol = solve_lattice_dp(bake_res)
        self.assertFalse(sol.is_deadlock)
        # At frame 4 (after slam at frame 3), alive states must be <= 193
        if len(sol.stats.alive_states_history) > 4:
            states_after_slam = sol.stats.alive_states_history[4]
            self.assertLessEqual(states_after_slam, 193)


if __name__ == "__main__":
    unittest.main()
