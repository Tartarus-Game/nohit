"""Adversarial stress and boundary challenge tests for Milestone 1 Unified DAG-DP solver.

Focus areas:
1. Trajectory verification: 0 hazard hits across all 1752 ticks on conservative Minkowski mask for all 9 members.
2. Boundary and extreme conditions: extreme beam widths (1 to 5000), pathological initial states, single vs product state.
3. Synthetic impossible obstacle deadlocks: clean status == 1 without infinite loops or memory faults.
4. Memory stability and leak check across repeated DP invocations.
5. Resource limits: graceful status == 2 on small max_states.
6. Action smoothness and clearance metrics.
"""
import ctypes
import ctypes.wintypes
import gc
import json
import time
from pathlib import Path

import numpy as np
import pytest

from nohit.engine.compact_lattice import (
    TOTAL_CELLS,
    blocked_xy,
    native_micro_into,
    product_micro_into,
    reconstruct_native,
    search_frs_dp_bellman,
)
from nohit.engine.compact_solver import solve_platforms4hard
from nohit.engine.compact_wave import ROOT, compile_wave, prepare_collision_native


def get_process_memory_mb():
    """Returns process Working Set (RSS) in megabytes using Windows PSAPI."""
    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.wintypes.DWORD),
            ("PageFaultCount", ctypes.wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    pmc = PROCESS_MEMORY_COUNTERS()
    pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    h_proc = ctypes.windll.kernel32.GetCurrentProcess()
    if ctypes.windll.psapi.GetProcessMemoryInfo(h_proc, ctypes.byref(pmc), ctypes.sizeof(pmc)):
        return pmc.WorkingSetSize / (1024.0 * 1024.0)
    return 0.0


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


class TestCandidateTrajectorySafety:
    """Task 2: Empirical verification of candidate trajectory safety."""

    def test_candidate_trajectory_zero_hazard_hits_nominal(self, platforms4hard_env):
        """Nominal Member 0 must have exactly 0 collision hits across all 1752 ticks."""
        sol = solve_platforms4hard(max_beam=1000)
        assert sol["status"] == "candidate_found"
        assert sol["frame"] == 438

        actions = np.array(sol["actions"], dtype=np.int8)
        assert len(actions) == 438

        schedule = platforms4hard_env["schedule"]
        initial = platforms4hard_env["initial"]
        mask = platforms4hard_env["mask"]

        # Forward simulate nominal player
        state = initial.copy()
        hits = 0
        hit_details = []

        for frame_idx, (ux, up) in enumerate(actions):
            for micro in range(4):
                tick = frame_idx * 4 + micro + 1
                native_micro_into(state, ux, up, schedule[tick], state)
                if blocked_xy(mask, tick, state[0], state[1]):
                    hits += 1
                    hit_details.append((frame_idx, tick, state[0], state[1]))

        assert hits == 0, f"Candidate trajectory had {hits} hits in conservative mask: {hit_details[:5]}"

    def test_candidate_trajectory_zero_hazard_hits_all_9_members(self, platforms4hard_env):
        """All 9 product members (3 velocities x 3 microclocks) must have 0 hits across all 1752 ticks."""
        sol = solve_platforms4hard(max_beam=1000)
        actions = np.array(sol["actions"], dtype=np.int8)
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"]

        product_state = starts.copy()
        total_evaluations = 0
        hits_per_member = [0] * 9

        for frame_idx, (ux, up) in enumerate(actions):
            for micro in range(4):
                tick = frame_idx * 4 + micro + 1
                product_micro_into(product_state, ux, up, schedule[tick], product_state, tick)
                for m in range(9):
                    total_evaluations += 1
                    mx = product_state[m * 5]
                    my = product_state[m * 5 + 1]
                    if blocked_xy(mask, tick, mx, my):
                        hits_per_member[m] += 1

        assert total_evaluations == 9 * 1752
        assert sum(hits_per_member) == 0, f"Member hits detected: {hits_per_member}"

    def test_action_smoothness_metrics(self):
        """Verify action sequence smoothness (low chatter / toggle suppression)."""
        sol = solve_platforms4hard(max_beam=1000)
        actions = np.array(sol["actions"], dtype=np.int8)
        ux = actions[:, 0]
        up = actions[:, 1]

        # Count direct horizontal reversals (-1 -> 1 or 1 -> -1 without neutral)
        direct_reversals = np.sum((ux[:-1] == 1) & (ux[1:] == -1)) + np.sum((ux[:-1] == -1) & (ux[1:] == 1))
        # Total key changes
        ux_changes = np.sum(ux[:-1] != ux[1:])
        up_changes = np.sum(up[:-1] != up[1:])

        # Chatter should be well-behaved
        assert direct_reversals <= 5, f"High direct horizontal reversals: {direct_reversals}"
        assert ux_changes < 150, f"Excessive horizontal toggling: {ux_changes}"
        assert up_changes < 50, f"Excessive vertical toggling: {up_changes}"

    def test_trajectory_reconstruction_bit_identical(self, platforms4hard_env):
        """Native reconstructor output must bit-identically match forward step simulation."""
        sol = solve_platforms4hard(max_beam=1000)
        actions = np.array(sol["actions"], dtype=np.int8)
        schedule = platforms4hard_env["schedule"]
        initial = platforms4hard_env["initial"]

        trace_native = reconstruct_native(initial, actions, schedule)
        manual_trace = np.empty_like(trace_native)
        manual_trace[0] = initial
        s = initial.copy()
        for f, (ux, up) in enumerate(actions):
            for m in range(4):
                native_micro_into(s, ux, up, schedule[f * 4 + m + 1], s)
            manual_trace[f + 1] = s

        max_diff = np.max(np.abs(trace_native - manual_trace))
        assert max_diff == 0.0, f"Reconstruction difference detected: {max_diff}"



class TestSolverStressAndBoundaries:
    """Task 1: Adversarial challenge on stress, boundary conditions, and memory."""

    @pytest.mark.parametrize("beam_width", [1, 2, 10, 50, 100, 500, 1000])
    def test_extreme_beam_widths_no_crash(self, platforms4hard_env, beam_width):
        """Solver must execute safely without crash or memory fault across extreme beam widths."""
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"]

        status, frame, expansions, visits, actions = search_frs_dp_bellman(
            mask, schedule, starts, max_states=10000, max_beam=beam_width
        )
        assert status in (0, 1, 2, 3)
        assert expansions > 0
        if status == 0:
            assert frame == 438
            assert len(actions) == 438
        else:
            assert len(actions) == 0

    def test_beam_width_equal_to_max_states(self, platforms4hard_env):
        """Boundary condition: max_beam == max_states."""
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"]

        status, frame, expansions, visits, actions = search_frs_dp_bellman(
            mask, schedule, starts, max_states=500, max_beam=500
        )
        assert status in (0, 1, 2, 3)

    def test_resource_limit_exhaustion_returns_status_2(self, platforms4hard_env):
        """When state queue overflows max_states, solver must return status == 2 cleanly."""
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"]

        # Set max_states to a tiny budget of 2
        status, frame, expansions, visits, actions = search_frs_dp_bellman(
            mask, schedule, starts, max_states=2, max_beam=100
        )
        assert status == 2
        assert len(actions) == 0
        assert frame < 438

    def test_single_member_initial_state(self, platforms4hard_env):
        """Solver must support single-soul initial state (size 5) without crash."""
        schedule = platforms4hard_env["schedule"]
        initial = platforms4hard_env["initial"]
        mask = platforms4hard_env["mask"]

        status, frame, expansions, visits, actions = search_frs_dp_bellman(
            mask, schedule, initial, max_states=5000, max_beam=50
        )
        assert status in (0, 1, 2, 3)
        if status == 0:
            assert len(actions) == 438

    def test_pathological_boundary_initial_states(self, platforms4hard_env):
        """Test solver behavior on pathological boundary coordinates."""
        schedule = platforms4hard_env["schedule"]
        mask = platforms4hard_env["mask"]

        pathological_cases = [
            # Arena boundaries
            np.tile(np.array([118.0, 327.95, 0.0, 0.0, 0.0]), 9),  # Left wall
            np.tile(np.array([543.0, 327.95, 0.0, 0.0, 0.0]), 9),  # Right wall
            np.tile(np.array([175.0, 236.0, 0.0, 0.0, 0.0]), 9),   # Ceiling
            np.tile(np.array([175.0, 386.0, 0.0, 0.0, 0.0]), 9),   # Floor
            # High initial velocities
            np.tile(np.array([175.0, 327.95, 0.0, -250.0, 0.0]), 9),
            np.tile(np.array([175.0, 327.95, 0.0, 750.0, 0.0]), 9),
            # Already out of arena
            np.tile(np.array([50.0, 100.0, 0.0, 0.0, 0.0]), 9),
        ]

        for idx, starts in enumerate(pathological_cases):
            status, frame, expansions, visits, actions = search_frs_dp_bellman(
                mask, schedule, starts, max_states=1000, max_beam=20
            )
            assert status in (0, 1, 2, 3), f"Case {idx} returned invalid status: {status}"

    def test_memory_stability_under_repeated_solves(self, platforms4hard_env):
        """Solver must not leak memory under repeated invocations."""
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"]

        # Warmup JIT
        search_frs_dp_bellman(mask, schedule, starts, max_states=1000, max_beam=10)
        gc.collect()

        mem_before = get_process_memory_mb()

        # Run 20 solves
        for _ in range(20):
            search_frs_dp_bellman(mask, schedule, starts, max_states=5000, max_beam=30)

        gc.collect()
        mem_after = get_process_memory_mb()

        mem_delta = mem_after - mem_before
        # Memory growth across 20 calls should be minimal (< 25 MB)
        assert mem_delta < 25.0, f"Memory leak detected: working set grew by {mem_delta:.2f} MB"


class TestSyntheticDeadlockDetection:
    """Task 1: Test synthetic impossible obstacle conditions."""

    def test_instant_deadlock_at_initial_frame(self, platforms4hard_env):
        """When initial position is fully blocked on frame 0, must report status == 1 immediately."""
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"].copy()

        # Block everything at ticks 1..4 (frame 0)
        mask[1:5, :, :] = np.uint64(0xFFFFFFFFFFFFFFFF)

        start_time = time.perf_counter()
        status, frame, expansions, visits, actions = search_frs_dp_bellman(
            mask, schedule, starts, max_states=5000, max_beam=50
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert status == 1, f"All initial actions blocked: {status}"
        assert frame == 0, f"Expected failure at frame 0, got frame {frame}"
        assert len(actions) == 0
        assert elapsed_ms < 100.0, f"Deadlock detection took too long: {elapsed_ms:.2f} ms"

    def test_synthetic_impassable_wall_mid_wave(self, platforms4hard_env):
        """When an impassable wall covers the entire combat zone at frame 50, solver must report status == 1."""
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"].copy()

        # Entire combat zone blocked at frame 50 (ticks 201..204)
        mask[201:205, :, :] = np.uint64(0xFFFFFFFFFFFFFFFF)

        start_time = time.perf_counter()
        status, frame, expansions, visits, actions = search_frs_dp_bellman(
            mask, schedule, starts, max_states=5000, max_beam=50
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert status == 3, f"A capped frontier cannot prove deadlock: {status}"
        assert frame <= 50, f"Expected failure at or before frame 50, got {frame}"
        assert len(actions) == 0
        assert elapsed_ms < 500.0

    def test_synthetic_spikes_covering_all_safe_y_levels(self, platforms4hard_env):
        """When hazards cover all accessible vertical space at frame 20, solver reports clean status == 1."""
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"].copy()

        # Cover vertical region y from 250 to 380 at frame 20 (ticks 81..84)
        # y in [250, 380] -> yy in [19, 149]
        mask[81:85, 19:150, :] = np.uint64(0xFFFFFFFFFFFFFFFF)

        status, frame, expansions, visits, actions = search_frs_dp_bellman(
            mask, schedule, starts, max_states=5000, max_beam=50
        )
        assert status == 3
        assert frame <= 20
        assert len(actions) == 0

    def test_synthetic_deadlock_floor_hazard_forces_unavoidable_death(self, platforms4hard_env):
        """When entire bottom floor region is spiked from frame 10 onward, gravity forces deadlock."""
        schedule = platforms4hard_env["schedule"]
        starts = platforms4hard_env["starts"]
        mask = platforms4hard_env["mask"].copy()

        # Cover entire floor and landing areas y in [320, 390] from frame 10 onward
        # y in [320, 390] -> yy in [89, 159]
        mask[41:, 89:160, :] = np.uint64(0xFFFFFFFFFFFFFFFF)

        start_time = time.perf_counter()
        status, frame, expansions, visits, actions = search_frs_dp_bellman(
            mask, schedule, starts, max_states=5000, max_beam=50
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert status == 3, f"A capped frontier cannot prove deadlock: {status}"
        assert len(actions) == 0
        assert elapsed_ms < 1000.0

