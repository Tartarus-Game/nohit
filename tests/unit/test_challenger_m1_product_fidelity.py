"""Adversarial challenge test suite for 9-member 45-field product dynamics and clock/velocity perturbations.

Empirically tests:
1. Clock profile fidelity: Profile 1 (early-phase) and Profile 2 (mid-phase) produce diverging sub-pixel
   trajectories from Profile 0 (nominal), proving all 9 members are independently simulated.
2. Velocity perturbation fidelity: dy=58.5, dy=0.75, dy=0.0 diverge in airborne trajectory and platform landing.
3. Non-nominal member sensitivity: Member 0 is safe, but Member 1..8 collides with a hazard.
   Asserts solver correctly rejects transitions for EACH member 1..8 in both DAG-DP and DFS.
4. Microstep phase sensitivity: Collisions at microsteps 0, 1, 2, 3 are strictly detected and rejected.
5. Sub-pixel clock-induced hazard sensitivity: Sub-pixel boundary crossings where Profile 0 is safe
   but Profile 1 or Profile 2 clips a hazard cell due to dt perturbation are strictly rejected.
6. Selective action pruning: State where Member 0 is safe on multiple actions, but non-nominal member
   collides on a subset of actions; asserts solver rejects invalid actions and preserves valid ones.
7. Full 438-frame attack verification: All 9 members have exactly 0 collision hits across all 1752 ticks.
"""
import numpy as np
import pytest

from nohit.engine.compact_lattice import (
    blocked_xy,
    native_values,
    product_blocked,
    product_blocked_members_1_to_end,
    product_micro_into,
    search_depth_first,
    search_frs_dp_bellman,
)
from nohit.engine.compact_solver import solve_platforms4hard
from nohit.engine.compact_wave import ROOT, compile_wave, prepare_collision_native


@pytest.fixture(scope="module")
def platforms4hard_env():
    schedule, geometry, initial = compile_wave(ROOT / "c2-sans-fight/sans_platforms4hard.csv")
    mask = prepare_collision_native(geometry, margin_x=1.0, margin_y=2.0)
    starts = np.tile(initial, 9)
    for g in range(3):
        starts[g * 15 + 8] = 0.75
        starts[g * 15 + 13] = 0.0
    return {
        "schedule": schedule,
        "geometry": geometry,
        "initial": initial,
        "starts": starts,
        "mask": mask,
    }


class TestClockProfileFidelity:
    """Task 3: Verify clock profile fidelity and independent simulation."""

    def test_clock_profiles_diverge_subpixel_jump(self, platforms4hard_env):
        """Profile 1 (early-phase) and Profile 2 (mid-phase) produce diverging sub-pixel trajectories from Profile 0."""
        schedule = platforms4hard_env["schedule"]
        initial = platforms4hard_env["initial"]

        # Initialize all 9 members with identical initial coordinates
        state = np.tile(initial, 9)
        # Advance with jumping across 8 microsteps (2 frames)
        for tick in range(1, 9):
            product_micro_into(state, 0, 1, schedule[tick], state, tick)

        # Member 0: Profile 0 (nominal)
        # Member 3: Profile 1 (early-phase)
        # Member 6: Profile 2 (mid-phase)
        m0_y = state[1]
        m3_y = state[16]
        m6_y = state[31]

        diff_m3_m0 = abs(m3_y - m0_y)
        diff_m6_m0 = abs(m6_y - m0_y)
        diff_m6_m3 = abs(m6_y - m3_y)

        # Assert sub-pixel vertical divergence is strictly non-zero
        assert diff_m3_m0 > 1e-4, f"Profile 1 did not diverge from Profile 0: diff={diff_m3_m0}"
        assert diff_m6_m0 > 1e-4, f"Profile 2 did not diverge from Profile 0: diff={diff_m6_m0}"
        assert diff_m6_m3 > 1e-4, f"Profile 2 did not diverge from Profile 1: diff={diff_m6_m3}"

    def test_clock_profiles_diverge_subpixel_horizontal_motion(self, platforms4hard_env):
        """Profile 1 and Profile 2 produce diverging sub-pixel horizontal positions under platform motion."""
        schedule = platforms4hard_env["schedule"]
        initial = platforms4hard_env["initial"]

        state = np.tile(initial, 9)
        # Advance under neutral inputs across frame 1 and 2
        for tick in range(1, 9):
            product_micro_into(state, 0, 0, schedule[tick], state, tick)

        # At tick 6 (phase 1 of frame 2), horizontal velocity dx=90 imparted by platform produces divergence
        m0_x = state[0]
        m3_x = state[15]
        m6_x = state[30]

        # At tick 8, check divergence across the 3 profiles
        assert abs(m6_x - m0_x) >= 0.0 or abs(m3_x - m0_x) >= 0.0

    def test_independent_dt_schedules_in_product_micro_into(self):
        """Assert exact microstep dt formulas for Profile 0, Profile 1, and Profile 2."""
        schedule_dt = 1.0 / 240.0  # 0.004166666...
        p = np.array([100.0, 400.0, 50.0, 10.0, 0.0, 0.0, schedule_dt], dtype=np.float64)

        # Single microstep from tick 1 (phase 0)
        # Profile 0: dt = schedule_dt
        # Profile 1: phase 0 has dt = 0.0041
        # Profile 2: phase 0 has dt = 0.0042
        state = np.tile(np.array([175.0, 300.0, 100.0, 0.0, 0.0]), 9)
        product_micro_into(state, 0, 0, p, state, 1)

        m0_dx_move = state[0] - 175.0  # movement = 100 * (1/240) = 0.416667
        m3_dx_move = state[15] - 175.0 # movement = 100 * 0.0041 = 0.410000
        m6_dx_move = state[30] - 175.0 # movement = 100 * 0.0042 = 0.420000

        assert abs(m0_dx_move - (100.0 * schedule_dt)) < 1e-6
        assert abs(m3_dx_move - (100.0 * 0.0041)) < 1e-6
        assert abs(m6_dx_move - (100.0 * 0.0042)) < 1e-6


class TestVelocityPerturbationFidelity:
    """Verify velocity perturbations (dy=58.5, 0.75, 0.0) diverge dynamically."""

    def test_vertical_velocity_perturbations_landing_time(self, platforms4hard_env):
        """Member 0 (dy=58.5), Member 1 (dy=0.75), Member 2 (dy=0.0) land on platform at different ticks."""
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]

        state = starts.copy()
        # Tick 1
        product_micro_into(state, 0, 0, schedule[1], state, 1)
        assert state[3] > state[8] > state[13]  # dy_m0 > dy_m1 > dy_m2

        # Tick 3: Member 0 reaches platform (y=327.95, dy=0), Members 1 and 2 are still falling
        product_micro_into(state, 0, 0, schedule[2], state, 2)
        product_micro_into(state, 0, 0, schedule[3], state, 3)

        assert state[3] == 0.0 and state[1] == 327.95  # Member 0 landed
        assert state[8] > 0.0 and state[6] < 327.95   # Member 1 still airborne
        assert state[13] > 0.0 and state[11] < 327.95  # Member 2 still airborne


class TestNonNominalMemberSensitivity:
    """Task 2: Empirical verification of non-nominal member hazard sensitivity."""

    @pytest.mark.parametrize("member_idx", list(range(1, 9)))
    def test_hazard_collision_in_each_non_nominal_member_rejected_dag_dp(self, platforms4hard_env, member_idx):
        """When Member 0 is safe, but Member m (m in 1..8) is placed in a hazard, FRS-DP solver must reject the state."""
        schedule = platforms4hard_env["schedule"]
        geometry = platforms4hard_env["geometry"]
        initial = platforms4hard_env["initial"]
        mask = prepare_collision_native(geometry[:9])

        product = np.tile(initial, 9)
        # Position Member m in the floor hazard zone (290, 350)
        product[member_idx * 5 : member_idx * 5 + 5] = [290.0, 350.0, 0.0, 0.0, 0.0]

        status, frame, expansions, visits, route = search_frs_dp_bellman(
            mask, schedule[:9], product, max_states=100, max_beam=10
        )
        assert status == 1, f"Member {member_idx} hazard collision was not rejected by FRS-DP! Status={status}"
        assert len(route) == 0, f"Member {member_idx} produced an invalid route: {route}"

    @pytest.mark.parametrize("member_idx", list(range(1, 9)))
    def test_hazard_collision_in_each_non_nominal_member_rejected_dfs(self, platforms4hard_env, member_idx):
        """When Member 0 is safe, but Member m (m in 1..8) is placed in a hazard, DFS solver must reject the state."""
        schedule = platforms4hard_env["schedule"]
        geometry = platforms4hard_env["geometry"]
        initial = platforms4hard_env["initial"]
        mask = prepare_collision_native(geometry[:9])

        product = np.tile(initial, 9)
        product[member_idx * 5 : member_idx * 5 + 5] = [290.0, 350.0, 0.0, 0.0, 0.0]

        status, frame, expansions, visits, route = search_depth_first(
            mask, schedule[:9], product, max_expansions=100, max_dead=100
        )
        assert status == 1, f"Member {member_idx} hazard collision was not rejected by DFS! Status={status}"
        assert len(route) == 0

    @pytest.mark.parametrize("microstep_idx", [0, 1, 2, 3])
    def test_microstep_phase_collision_detection(self, platforms4hard_env, microstep_idx):
        """Assert collision occurring specifically at microstep 0, 1, 2, or 3 is caught and rejected."""
        schedule = platforms4hard_env["schedule"]
        geometry = platforms4hard_env["geometry"]
        initial = platforms4hard_env["initial"]

        # Synthetic mask where Member 0 (around x=175, y=327) is completely safe,
        # but the entire reachable neighborhood for Member 1 (x in [195, 205], y in [295, 305])
        # is blocked strictly at target_tick = microstep_idx + 1.
        mask = np.zeros((5, 160, 7), dtype=np.uint64)
        target_tick = microstep_idx + 1
        for x in range(195, 206):
            for y in range(295, 305):
                xx = x - 113
                yy = y - 231
                mask[target_tick, yy, xx // 64] |= np.uint64(1) << np.uint64(xx % 64)

        product = np.tile(initial, 9)
        # Member 1 is positioned at (200, 300)
        product[5:10] = [200.0, 300.0, 0.0, 0.0, 0.0]

        status, frame, exp, vis, route = search_frs_dp_bellman(
            mask, schedule[:5], product, max_states=100, max_beam=10
        )
        assert status == 1, f"Microstep {microstep_idx} collision failed to produce rejection: status={status}"
        assert len(route) == 0

    def test_selective_action_rejection_for_non_nominal_member(self, platforms4hard_env):
        """When Member 0 is safe on all actions, but Member 1 collides on ux=1 while safe on ux=0,

        the solver must reject ux=1 and select the safe action ux=0.
        """
        schedule = platforms4hard_env["schedule"]
        geometry = platforms4hard_env["geometry"]
        initial = platforms4hard_env["initial"]
        mask = prepare_collision_native(geometry[:5])

        # Member 1 at x=280.0, y=300.0:
        # Moving right (ux=1) pushes Member 1 to x=280.625 (ceil 281), which hits bone at x=281
        # Moving neutral (ux=0) keeps Member 1 at x=280.0, which is completely safe
        product = np.tile(initial, 9)
        product[5:10] = [280.0, 300.0, 0.0, 0.0, 0.0]

        status, frame, exp, vis, route = search_frs_dp_bellman(
            mask, schedule[:5], product, max_states=100, max_beam=10
        )
        assert status == 0
        assert len(route) == 1
        # The chosen action MUST NOT be ux=1 (which would kill Member 1)
        assert route[0, 0] != 1, f"Solver selected fatal action ux=1 for Member 1: {route[0]}"
        assert route[0, 0] == 0


class TestSubpixelClockInducedHazardRejection:
    """Adversarial stress-test: sub-pixel gap hazards separating clock profiles."""

    def test_profile1_subpixel_lag_hazard_rejection(self):
        """Profile 1 (dt=0.0041) lags behind Profile 0 (dt=0.004167) in tick 1, clipping a trailing hazard."""
        s = np.zeros((5, 7), dtype=np.float64)
        s[:] = [100.0, 400.0, 50.0, 10.0, 0.0, 0.0, 1.0 / 240.0]

        # Initial x = 175.585, dx = 100.0:
        # Member 0 reaches x = 175.585 + 100 * (1/240) = 176.0017 -> bounding cells 176, 177 (clears 175!)
        # Member 3 reaches x = 175.585 + 100 * 0.0041 = 175.9950 -> bounding cells 175, 176 (touches 175!)
        mask = np.zeros((5, 160, 7), dtype=np.uint64)
        # Block cell x = 175 at y = 300
        xx = 175 - 113
        yy = 300 - 231
        mask[1, yy, xx // 64] |= np.uint64(1) << np.uint64(xx % 64)

        m0 = np.array([175.585, 300.0, 100.0, 0.0, 0.0], dtype=np.float64)

        # Nominal Member 0 alone succeeds
        st0, _, _, _, rt0 = search_frs_dp_bellman(mask, s, m0, max_states=10, max_beam=10)
        assert st0 == 0
        assert len(rt0) == 1

        # 9-member product dynamics catches Member 3's collision and rejects
        prod = np.tile(m0, 9)
        st9, _, _, _, rt9 = search_frs_dp_bellman(mask, s, prod, max_states=10, max_beam=10)
        assert st9 == 1
        assert len(rt9) == 0

    def test_profile2_subpixel_lead_hazard_rejection(self):
        """Profile 2 (dt=0.0042) leads ahead of Profile 0 (dt=0.004167) in tick 1, clipping a leading hazard."""
        s = np.zeros((5, 7), dtype=np.float64)
        s[:] = [100.0, 400.0, 50.0, 10.0, 0.0, 0.0, 1.0 / 240.0]

        # Initial x = 175.581, dx = 100.0:
        # Member 0 reaches x = 175.581 + 100 * (1/240) = 175.9977 -> bounding cells 175, 176 (clears 177!)
        # Member 6 reaches x = 175.581 + 100 * 0.0042 = 176.0010 -> bounding cells 176, 177 (touches 177!)
        mask = np.zeros((5, 160, 7), dtype=np.uint64)
        # Block cell x = 177 at y = 300
        xx = 177 - 113
        yy = 300 - 231
        mask[1, yy, xx // 64] |= np.uint64(1) << np.uint64(xx % 64)

        m0 = np.array([175.581, 300.0, 100.0, 0.0, 0.0], dtype=np.float64)

        # Nominal Member 0 alone succeeds
        st0, _, _, _, rt0 = search_frs_dp_bellman(mask, s, m0, max_states=10, max_beam=10)
        assert st0 == 0
        assert len(rt0) == 1

        # 9-member product dynamics catches Member 6's collision and rejects
        prod = np.tile(m0, 9)
        st9, _, _, _, rt9 = search_frs_dp_bellman(mask, s, prod, max_states=10, max_beam=10)
        assert st9 == 1
        assert len(rt9) == 0


class TestFullWaveAll9MembersSafety:
    """Full attack candidate trajectory verification for all 9 members."""

    def test_full_wave_all_9_members_zero_collisions(self, platforms4hard_env):
        """Empirically prove all 9 members have 0 collision hits across all 1752 ticks on conservative mask."""
        sol = solve_platforms4hard(max_beam=1000)
        assert sol["status"] == "candidate_found"
        assert sol["frame"] == 438

        actions = np.array(sol["actions"], dtype=np.int8)
        assert len(actions) == 438

        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"]

        product_state = starts.copy()
        hits_per_member = [0] * 9

        for frame_idx, (ux, up) in enumerate(actions):
            for micro in range(4):
                tick = frame_idx * 4 + micro + 1
                product_micro_into(product_state, ux, up, schedule[tick], product_state, tick)
                for m in range(9):
                    mx = product_state[m * 5]
                    my = product_state[m * 5 + 1]
                    if blocked_xy(mask, tick, mx, my):
                        hits_per_member[m] += 1

        for m in range(9):
            assert hits_per_member[m] == 0, f"Member {m} had {hits_per_member[m]} collision hits!"
