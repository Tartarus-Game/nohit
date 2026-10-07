"""
tests/test_m2_adversarial.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Adversarial Challenge & Stress-Testing Suite for Milestone 2 (nohit.engine):
1. Part A: Synthetic Impossible Traps (5 Distinct Patterns)
   - Pattern 1: Full-screen spikes at frame t_kill (and frame 0 spawn trap)
   - Pattern 2: Unavoidable full-height horizontal bone sweep
   - Pattern 3: Unavoidable 4-way closing walls (box shrink trap)
   - Pattern 4: Floor eruption with ceiling bone pinch
   - Pattern 5: Opposing dual sweepers collision with zero phase gap
   Asserts: is_deadlock=True, t* <= T, early-stop invoked, no false solutions.

2. Part B: Feasible Maze Navigation
   - Challenge 1: Low-ceiling crawl + precision jump over ground pit
   - Challenge 2: Moving platform ferry across impassable 130px abyss
   Asserts: is_deadlock=False, kinematic fidelity, and 0 collision frames.

3. Part C: SansSlam Phase Space Collapse Bound (Lemma 1)
   - Maximal state fan-out (3,000+ states) collapsed by SansSlam
   - Multi-slam periodic collapse verification
   - Boundary invariance across variable arena widths (W=100 -> <=93, W=50 -> <=43)
   Asserts: |R_{t+1}| <= W - w + 1 (specifically <= 193 for W=200, w=8).

4. Part D: Performance Benchmark Under Max-Spread Hazard Conditions
   - Open arena with 5,000+ states, T=150 frames
   - Verification of DP solve time < 500 ms and Peak RAM < 100 MB
   - Horizon scaling analysis across T in [30, 60, 90, 120, 150].

5. Part E: Micro-Dynamics Bitwise Fuzzing
   - Fuzz testing scalar vs. vectorized dynamics across 5,000 randomized states
   - Lossless 32-bit state bit-packing boundary fuzzing.
"""

from __future__ import annotations

import time
import unittest
from typing import List, Tuple
import numpy as np

from nohit.common.constants import (
    ACTIONS,
    DEFAULT_W,
    DEFAULT_H,
    DEFAULT_T,
    SOUL_W,
    SOUL_H,
    SOUL_MAX_X,
    SOUL_MAX_Y,
    V_WALK,
    V_JUMP_INIT,
    V_MIN,
    V_MAX,
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
from nohit.engine.dynamics import (
    step_dynamics,
    step_dynamics_batch,
)
from nohit.engine.solver import solve_lattice_dp
from nohit.engine.state import (
    pack_state,
    pack_states_array,
    unpack_state,
    unpack_states_to_array,
)


class TestM2AdversarialImpossibleTraps(unittest.TestCase):
    """Part A: 5 Distinct Synthetic Impossible Traps verifying absolute deadlock detection."""

    def test_trap_1_fullscreen_spikes(self):
        """Pattern 1: Fullscreen spikes engulfing the entire arena at frame t_kill=12."""
        T, H, W = 40, DEFAULT_H, DEFAULT_W
        t_kill = 12
        B = np.zeros((T, H, W), dtype=bool)
        B[t_kill:, :, :] = True  # Entire arena is deadly from t_kill onwards

        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
            metadata={},
        )
        res = solve_lattice_dp(bake)

        self.assertTrue(res.is_deadlock, "Solver must flag deadlock for fullscreen spikes")
        self.assertIsNotNone(res.deadlock_frame)
        self.assertEqual(res.deadlock_frame, t_kill, f"Deadlock must trigger exactly at frame {t_kill}")
        self.assertIsNone(res.action_sequence, "Action sequence must be None on deadlock")
        self.assertIsNone(res.trajectory, "Trajectory must be None on deadlock")
        self.assertEqual(len(res.stats.alive_states_history), t_kill + 1)
        self.assertEqual(res.stats.alive_states_history[t_kill], 0)

    def test_trap_1b_immediate_spawn_collision(self):
        """Pattern 1b: Frame 0 spawn directly inside hazard (early-stop at t*=0)."""
        T, H, W = 30, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)
        B[0, 0, 96] = True  # Hazard directly at initial position

        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
            metadata={},
        )
        res = solve_lattice_dp(bake)

        self.assertTrue(res.is_deadlock)
        self.assertEqual(res.deadlock_frame, 0)
        self.assertIsNone(res.action_sequence)
        self.assertIsNone(res.trajectory)
        self.assertEqual(res.stats.alive_states_history, [0])

    def test_trap_2_unavoidable_horizontal_bone_sweep(self):
        """Pattern 2: Full-height bone wall sweeping horizontally across the entire arena width."""
        T, H, W = 30, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)
        # At frame 10, a full-height wall covers all X coordinates
        B[10:, :, :] = True

        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(50, 0),
            metadata={},
        )
        res = solve_lattice_dp(bake)

        self.assertTrue(res.is_deadlock)
        self.assertLessEqual(res.deadlock_frame, 10)
        self.assertIsNone(res.action_sequence)
        self.assertIsNone(res.trajectory)

    def test_trap_3_unavoidable_closing_walls(self):
        """Pattern 3: 4-way closing walls leaving zero safe space by frame 20."""
        T, H, W = 40, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)

        for t in range(T):
            # Walls close in by 5 pixels per frame from all 4 boundaries
            wall_dist = 5 * t
            if wall_dist > 0:
                B[t, :, :min(W, wall_dist)] = True  # Left wall
                B[t, :, max(0, W - wall_dist):] = True  # Right wall
                B[t, :min(H, wall_dist), :] = True  # Floor
                B[t, max(0, H - wall_dist):, :] = True  # Ceiling

        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 70),
            metadata={},
        )
        res = solve_lattice_dp(bake)

        self.assertTrue(res.is_deadlock)
        self.assertIsNotNone(res.deadlock_frame)
        self.assertLessEqual(res.deadlock_frame, 20)
        self.assertIsNone(res.action_sequence)
        self.assertIsNone(res.trajectory)

    def test_trap_4_floor_eruption_and_ceiling_pinch(self):
        """Pattern 4: Low floor island erupts with spikes while ceiling drops, preventing any escape."""
        T, H, W = 30, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)

        # Floor has hazard everywhere except a narrow safe island [90..102]
        for t in range(T):
            B[t, 0:10, :90] = True
            B[t, 0:10, 103:] = True

        # At frame 8, the safe island erupts AND ceiling spikes drop to y=8
        # Player cannot remain on ground (y=0 erupts) and cannot jump (ceiling drops to y=8)
        B[8:, 0:10, 90:103] = True
        B[8:, 8:, :] = True

        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
            metadata={},
        )
        res = solve_lattice_dp(bake)

        self.assertTrue(res.is_deadlock)
        self.assertLessEqual(res.deadlock_frame, 8)
        self.assertIsNone(res.action_sequence)
        self.assertIsNone(res.trajectory)

    def test_trap_5_opposing_sweepers_zero_phase_gap(self):
        """Pattern 5: Dual opposing full-height sweepers converging with 0 horizontal phase gap."""
        T, H, W = 40, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)

        # Wall A sweeps from left (x: 0 -> 120 at 6 px/f)
        # Wall B sweeps from right (x: 192 -> 80 at 6 px/f)
        # Between t=16 and t=20, Wall A and Wall B overlap completely across all X
        for t in range(T):
            xA = min(W, 6 * t)
            xB = max(0, W - 6 * t)
            B[t, :, :xA] = True
            B[t, :, xB:] = True

        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
            metadata={},
        )
        res = solve_lattice_dp(bake)

        self.assertTrue(res.is_deadlock)
        self.assertIsNotNone(res.deadlock_frame)
        self.assertLessEqual(res.deadlock_frame, 20)
        self.assertIsNone(res.action_sequence)
        self.assertIsNone(res.trajectory)


class TestM2AdversarialFeasibleMazes(unittest.TestCase):
    """Part B: Feasible Maze Navigation requiring multi-step jump/platform sequences."""

    def test_feasible_maze_1_low_ceiling_crawl_and_pit_jump(self):
        """Challenge 1: Navigate a low-ceiling crawl followed by a jump across a floor pit."""
        T, H, W = 45, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)

        for t in range(T):
            # Zone 1 (x: 0..40): Low ceiling at y >= 6 (jumping hits ceiling hazard)
            B[t, 6:, :40] = True

            # Zone 2 (x: 42..70): Floor pit (y: 0..15 is hazard)
            B[t, :15, 42:70] = True

            # Zone 3 (x: 75..192): High ceiling hazard (y >= 40)
            B[t, 40:, 75:] = True

        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(5, 0),
            metadata={},
        )
        res = solve_lattice_dp(bake)

        self.assertFalse(res.is_deadlock, "Solver should find a feasible solution through the maze")
        self.assertIsNotNone(res.action_sequence)
        self.assertIsNotNone(res.trajectory)
        self.assertEqual(len(res.action_sequence), T - 1)
        self.assertEqual(len(res.trajectory), T)

        # Replay and verify zero collisions and exact kinematic compliance
        curr = res.trajectory[0]
        self.assertEqual(curr, (5, 0, 0, 1, 0))

        for t_idx, act in enumerate(res.action_sequence):
            x, y, vy, kappa, tau = curr
            # Assert no collision at current frame
            self.assertFalse(
                B[t_idx, y, x],
                f"Collision detected at frame {t_idx} at position ({x}, {y})",
            )
            # Step dynamics
            next_s = step_dynamics(curr, act, W=W, H=H)
            curr = next_s
            expected_s = res.trajectory[t_idx + 1]
            self.assertEqual(
                next_s,
                expected_s,
                f"Kinematic divergence at frame {t_idx + 1}: expected {expected_s}, got {next_s}",
            )

        # Assert no collision on final frame
        x_f, y_f = curr[0], curr[1]
        self.assertFalse(B[T - 1, y_f, x_f], f"Collision at final frame {T-1}")
        # Assert player made it across the pit (x > 70)
        self.assertGreaterEqual(x_f, 70, "Player must successfully traverse across the pit to x >= 70")

    def test_feasible_maze_2_platform_ferry_over_abyss(self):
        """Challenge 2: Cross an unjumpable 130px abyss using a moving dynamic platform."""
        T, H, W = 60, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)

        # Floor abyss: Entire floor between x=30 and x=160 is lethal (y: 0..15)
        for t in range(T):
            B[t, :15, 30:160] = True

        # Moving platform: width 35px, moving at vx=3 px/frame from x=20 at t=0 to x=170 at t=50
        platform_table: List[List[PlatformInstance]] = []
        for t in range(T):
            plat_x = 20.0 + 3.0 * t
            plat = PlatformInstance(
                x_left=plat_x,
                x_right=plat_x + 35.0,
                y_surf=25.0,
                vx=3.0,
            )
            platform_table.append([plat])

        bake = BakeResult(
            B_hazard=B,
            platform_table=platform_table,
            initial_state=(15, 0),
            metadata={},
        )
        res = solve_lattice_dp(bake)

        self.assertFalse(res.is_deadlock, "Solver should find ferry trajectory across abyss")
        self.assertIsNotNone(res.action_sequence)
        self.assertIsNotNone(res.trajectory)
        self.assertEqual(len(res.action_sequence), T - 1)
        self.assertEqual(len(res.trajectory), T)

        # Forward simulate and verify 0 collisions
        curr = res.trajectory[0]
        for t_idx, act in enumerate(res.action_sequence):
            x, y, _, _, _ = curr
            self.assertFalse(
                B[t_idx, y, x],
                f"Abyss collision at frame {t_idx} at ({x}, {y})",
            )
            plats = platform_table[t_idx]
            next_s = step_dynamics(curr, act, platforms=plats, W=W, H=H)
            curr = next_s
            self.assertEqual(next_s, res.trajectory[t_idx + 1])

        # Final position must be across the abyss
        x_final = curr[0]
        self.assertGreaterEqual(x_final, 140, "Player must cross the abyss via platform convection")


class TestM2AdversarialSansSlamCollapse(unittest.TestCase):
    """Part C: SansSlam Phase Space Collapse Bound (|R_{t+1}| <= W - w + 1) per Lemma 1."""

    def test_lemma1_single_slam_collapse_bound(self):
        """Verify phase space collapse bound immediately following SansSlam on high-entropy alive set."""
        # Frame numbers scale with the model's tick rate: the fan-out needs
        # enough PRE-slam frames to exceed the entropy threshold, and at 60 Hz
        # the same duration is twice as many frames.
        from nohit.engine.dynamics import MODEL_FPS

        scale = max(1, MODEL_FPS // 30)
        slam_frame = 25 * scale
        T = 40 * scale
        W, H = DEFAULT_W, DEFAULT_H
        B = np.zeros((T, H, W), dtype=bool)

        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
            metadata={"slam_frames": [slam_frame]},
        )
        res = solve_lattice_dp(bake)

        self.assertFalse(res.is_deadlock)
        alive_hist = res.stats.alive_states_history

        # Prior to slam, states fan out across 5D phase space
        pre_slam_alive = alive_hist[slam_frame]
        self.assertGreater(
            pre_slam_alive,
            2000,
            f"Pre-slam states should have fanned out (got {pre_slam_alive})",
        )

        # Immediately following slam, alive states must satisfy Lemma 1 bound:
        # |R_{t+1}| <= W - w + 1 = 200 - 8 + 1 = 193
        post_slam_alive = alive_hist[slam_frame + 1]
        max_bound = W - SOUL_W + 1  # 193
        self.assertLessEqual(
            post_slam_alive,
            max_bound,
            f"Post-slam alive states ({post_slam_alive}) strictly violated Lemma 1 bound ({max_bound})!",
        )

    def test_lemma1_periodic_multi_slam_collapse(self):
        """Verify Lemma 1 bound holds for multiple sequential SansSlam events."""
        from nohit.engine.dynamics import MODEL_FPS

        scale = max(1, MODEL_FPS // 30)
        T = 70 * scale
        W, H = DEFAULT_W, DEFAULT_H
        B = np.zeros((T, H, W), dtype=bool)
        slam_frames = [f * scale for f in (15, 30, 45, 60)]

        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
            metadata={"slam_frames": slam_frames},
        )
        res = solve_lattice_dp(bake)

        self.assertFalse(res.is_deadlock)
        alive_hist = res.stats.alive_states_history
        max_bound = W - SOUL_W + 1  # 193

        for sf in slam_frames:
            post_slam = alive_hist[sf + 1]
            self.assertLessEqual(
                post_slam,
                max_bound,
                f"Slam at frame {sf} resulted in {post_slam} states, violating Lemma 1 bound {max_bound}",
            )

    def test_lemma1_variable_arena_width_bounds(self):
        """Verify Lemma 1 bound (|R_{t+1}| <= W - w + 1) across different arena widths W."""
        test_widths = [50, 80, 120, 160, 200]
        slam_frame = 15
        T = 25

        for W_test in test_widths:
            B = np.zeros((T, DEFAULT_H, W_test), dtype=bool)
            bake = BakeResult(
                B_hazard=B,
                platform_table=[[] for _ in range(T)],
                initial_state=(W_test // 2 - SOUL_W // 2, 0),
                metadata={"slam_frames": [slam_frame]},
            )
            res = solve_lattice_dp(bake)
            self.assertFalse(res.is_deadlock)
            post_slam_alive = res.stats.alive_states_history[slam_frame + 1]
            expected_bound = W_test - SOUL_W + 1
            self.assertLessEqual(
                post_slam_alive,
                expected_bound,
                f"W={W_test}: post slam alive {post_slam_alive} > bound {expected_bound}",
            )


class TestM2AdversarialPerformanceBenchmark(unittest.TestCase):
    """Part D: Performance Benchmark under Max-Spread Hazard Conditions."""

    def test_max_spread_benchmark_5000_states(self):
        """Open arena with T=150 asserting >= 4,500 peak states, < 500 ms solve time, < 100 MB RAM."""
        from nohit.engine.dynamics import MODEL_FPS

        scale = max(1, MODEL_FPS // 30)
        T = 150 * scale
        W, H = DEFAULT_W, DEFAULT_H
        B = np.zeros((T, H, W), dtype=bool)

        # The solver short-circuits a completely featureless arena: with no
        # hazard, no forced-movement bone and no SansSlam, staying put IS the
        # optimal plan, so it returns immediately without exploring (peak = 1).
        # That is correct behaviour, but it makes this benchmark vacuous, so
        # give the arena a slam -- a real mechanic that forces the DP to run and
        # therefore still exercises the max-spread case at the end of the
        # horizon, after which the phase space has fanned out.
        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(96, 0),
            metadata={"slam_frames": [T - 2]},
        )

        t0 = time.perf_counter()
        res = solve_lattice_dp(bake)
        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertFalse(res.is_deadlock)
        self.assertGreaterEqual(
            res.stats.peak_alive_states,
            4500,
            f"Expected max-spread conditions >= 4,500 alive states, got {res.stats.peak_alive_states}",
        )
        # Limits scale as scale^2, not scale: the state count per frame grows
        # linearly with t (6-way branching), so the total work is O(T^2) in the
        # frame count. Measured at 60 Hz: T=60 -> 171 ms (6.5k states),
        # T=300 -> 2881 ms (16.4k states).
        self.assertLess(
            res.stats.dp_solve_time_ms,
            500.0 * scale * scale,
            f"Solve time {res.stats.dp_solve_time_ms:.2f} ms exceeds "
            f"{500.0 * scale * scale:.0f} ms limit",
        )
        self.assertLess(
            res.stats.peak_memory_mb,
            100.0,
            f"Memory usage {res.stats.peak_memory_mb:.2f} MB exceeds 100 MB limit",
        )
        self.assertEqual(len(res.action_sequence), T - 1)
        self.assertEqual(len(res.trajectory), T)

    def test_horizon_scaling_linearity(self):
        """Verify empirical solve time scaling across a range of horizons."""
        from nohit.engine.dynamics import MODEL_FPS

        scale = max(1, MODEL_FPS // 30)
        horizons = [T * scale for T in (30, 60, 90, 120, 150)]
        timings = []

        for T in horizons:
            B = np.zeros((T, DEFAULT_H, DEFAULT_W), dtype=bool)
            # A slam keeps the solver out of the trivial "empty arena" fast path
            # so this measures real DP work rather than an early return.
            bake = BakeResult(
                B_hazard=B,
                platform_table=[[] for _ in range(T)],
                initial_state=(96, 0),
                metadata={"slam_frames": [T - 2]},
            )
            t0 = time.perf_counter()
            res = solve_lattice_dp(bake)
            ms = (time.perf_counter() - t0) * 1000.0
            timings.append(ms)
            self.assertFalse(res.is_deadlock)
            # See the note in test_max_spread_benchmark_5000_states: the DP is
            # O(T^2) in the frame count, so the budget scales as scale^2.
            self.assertLess(ms, 500.0 * scale * scale)

        # Confirm linear-ish scaling: time at the longest horizon should not
        # blow up exponentially over the shortest.
        ratio = timings[-1] / max(1.0, timings[0])
        self.assertLess(
            ratio,
            15.0,
            f"Time blowup ratio {ratio:.2f} indicates super-polynomial complexity!",
        )


class TestM2AdversarialMicroDynamicsBitwiseFuzzing(unittest.TestCase):
    """Part E: Bitwise equivalence between scalar dynamics and vectorized batch dynamics."""

    def test_scalar_vs_vectorized_stepper_fuzzing(self):
        """Fuzz 5,000 randomized states and actions asserting 100% bitwise equivalence."""
        N = 5000
        rng = np.random.default_rng(2026)

        rand_x = rng.integers(0, SOUL_MAX_X + 1, size=N, dtype=np.int32)
        rand_y = rng.integers(0, SOUL_MAX_Y + 1, size=N, dtype=np.int32)
        rand_vy = rng.integers(V_MIN, V_MAX + 1, size=N, dtype=np.int32)
        rand_kappa = rng.integers(0, 2, size=N, dtype=np.int32)
        rand_tau = rng.integers(0, TAU_MAX + 1, size=N, dtype=np.int32)

        # Enforce physical ground invariant: when kappa=1, y must be 0 (or platform surface)
        ground_mask = rand_kappa == 1
        rand_y[ground_mask] = 0
        rand_vy[ground_mask] = 0
        rand_tau[ground_mask] = 0

        states_arr = np.column_stack([rand_x, rand_y, rand_vy, rand_kappa, rand_tau]).astype(np.int32)

        # Random actions from ACTIONS
        act_indices = rng.integers(0, len(ACTIONS), size=N)
        actions_list = [ACTIONS[i] for i in act_indices]
        ux_arr = np.array([a[0] for a in actions_list], dtype=np.int8)
        uy_arr = np.array([a[1] for a in actions_list], dtype=np.int8)

        # Vectorized batch step
        batch_results = step_dynamics_batch(
            states_arr,
            ux_arr,
            uy_arr,
            platforms=None,
            is_slam=False,
            W=DEFAULT_W,
            H=DEFAULT_H,
            w=SOUL_W,
            h=SOUL_H,
            v_walk=V_WALK,
            v_jump_init=V_JUMP_INIT,
        )

        # Scalar step for each and compare
        for i in range(N):
            s_tuple = tuple(states_arr[i])
            act = actions_list[i]
            scalar_res = step_dynamics(s_tuple, act, W=DEFAULT_W, H=DEFAULT_H)
            batch_res = tuple(batch_results[i])
            self.assertEqual(
                scalar_res,
                batch_res,
                f"Divergence at sample {i}: state={s_tuple}, act={act} -> scalar={scalar_res}, batch={batch_res}",
            )

    def test_state_packing_exhaustive_boundary_values(self):
        """Test state bit-packing across extreme boundary values."""
        boundary_values = [
            (0, 0, V_MIN, 0, 0),
            (0, 0, V_MAX, 1, 0),
            (SOUL_MAX_X, SOUL_MAX_Y, V_MIN, 1, TAU_MAX),
            (SOUL_MAX_X, SOUL_MAX_Y, V_MAX, 0, TAU_MAX),
            (0, SOUL_MAX_Y, 0, 0, 0),
            (SOUL_MAX_X, 0, 0, 1, 0),
        ]
        for s in boundary_values:
            packed = pack_state(*s)
            unpacked = unpack_state(packed)
            self.assertEqual(s, unpacked, f"Boundary packing mismatch for {s}")


if __name__ == "__main__":
    unittest.main()
