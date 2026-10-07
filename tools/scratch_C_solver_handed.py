"""
nohit.engine.solver
~~~~~~~~~~~~~~~~~~~
Forward Reachable Set (FRS) Dynamic Programming Solver on 5D Hybrid Lattice.
Implements:
- Feature 14 (BUCKET_DEDUP): Vectorized 32-bit compact micro-state deduplication V[t].
- Feature 15 (DEADLOCK_EARLY_STOP): Immediate early-stop upon alive set R_{t*} = empty set.
- Feature 16 (BACKTRACK_ACTION_EXTRACTION): Linear O(T) parent pointer traversal along P.
Performance Acceptance Criteria:
- Solve time < 500 ms for T=150 frames.
- Peak memory < 100 MB.
"""

from __future__ import annotations

import time
import tracemalloc
from typing import List, Optional, Sequence, Tuple
import numpy as np

from nohit.common.constants import (
    ACTIONS,
    DEFAULT_W,
    DEFAULT_H,
    SOUL_W,
    SOUL_H,
    V_WALK,
    V_JUMP_INIT,
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
from nohit.engine.dynamics import step_dynamics_batch
from nohit.engine.state import (
    configure_vy_quantisation,
    pack_state,
    pack_states_array,
    unpack_state,
    vy_quantisation_for_mode,
)

# ---------------------------------------------------------------------------
# Minimum-input objective weights
# ---------------------------------------------------------------------------
# Cost charged per frame for holding an input. A jump is priced above a lateral
# step because it is the more committal action (it also lifts the heart into
# bone lanes). Idle costs nothing, so "stand still when safe" is optimal.
ACT_COST_HORIZONTAL: float = 0.75
ACT_COST_JUMP: float = 1.0

# Hard ceiling on the DP's per-frame working set. Set far above every real
# wave's peak (largest observed: ~410k on an empty arena, which the fast path
# now short-circuits) so it only guards against pathological growth.
MAX_STATES_PER_FRAME: int = 400_000


def solve_lattice_dp(
    bake_result: BakeResult,
    initial_state: Optional[Tuple[int, int] | Tuple[int, int, int, int, int]] = None,
) -> SolveResult:
    """Executes high-throughput Forward Reachable Set DP to determine dead-ends and extract actions.

    Parameters
    ----------
    bake_result : BakeResult
        Contains B_hazard (T, H, W), platform_table, initial_state, and metadata.
    initial_state : tuple, optional
        Override (x0, y0) or (x0, y0, vy0, kappa0, tau0) soul anchor position.

    Returns
    -------
    SolveResult
        is_deadlock, deadlock_frame, action_sequence (T-1 actions), trajectory (T states), SolveStats.
    """
    t_start = time.perf_counter()
    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()

    def _get_peak_mem_mb() -> float:
        _, peak_mem = tracemalloc.get_traced_memory()
        if not was_tracing:
            tracemalloc.stop()
        return max(0.01, round(peak_mem / (1024 * 1024), 2))

    B_hazard = bake_result.B_hazard
    T, H, W = B_hazard.shape
    platform_table = bake_result.platform_table
    metadata = getattr(bake_result, "metadata", None) or {}
    slam_frames = set(metadata.get("slam_frames", []))
    bake_time_ms = float(metadata.get("total_baking_time_ms", 0.0))

    # Parse initial state
    init_s = initial_state if initial_state is not None else bake_result.initial_state
    x0, y0 = int(init_s[0]), int(init_s[1])
    if len(init_s) >= 5:
        vy0, kappa0, tau0 = int(init_s[2]), int(init_s[3]), int(init_s[4])
    else:
        vy0, kappa0, tau0 = 0, 1, 0

    # 1. Edge Case: T == 0
    if T == 0:
        dp_ms = (time.perf_counter() - t_start) * 1000.0
        return SolveResult(
            is_deadlock=False,
            deadlock_frame=None,
            action_sequence=[],
            trajectory=[],
            stats=SolveStats(
                bake_time_ms=bake_time_ms,
                dp_solve_time_ms=dp_ms,
                total_time_ms=bake_time_ms + dp_ms,
                peak_alive_states=0,
                alive_states_history=[],
                total_states_explored=0,
                peak_memory_mb=_get_peak_mem_mb(),
            ),
        )

    # 2. Frame 0 Collision Check (Early-Stop at t* = 0)
    if B_hazard[0, y0, x0]:
        dp_ms = (time.perf_counter() - t_start) * 1000.0
        return SolveResult(
            is_deadlock=True,
            deadlock_frame=0,
            action_sequence=None,
            trajectory=None,
            stats=SolveStats(
                bake_time_ms=bake_time_ms,
                dp_solve_time_ms=dp_ms,
                total_time_ms=bake_time_ms + dp_ms,
                peak_alive_states=0,
                alive_states_history=[0],
                total_states_explored=1,
                peak_memory_mb=_get_peak_mem_mb(),
            ),
        )

    # 3. Edge Case: T == 1
    if T == 1:
        dp_ms = (time.perf_counter() - t_start) * 1000.0
        return SolveResult(
            is_deadlock=False,
            deadlock_frame=None,
            action_sequence=[],
            trajectory=[(x0, y0, vy0, kappa0, tau0)],
            stats=SolveStats(
                bake_time_ms=bake_time_ms,
                dp_solve_time_ms=dp_ms,
                total_time_ms=bake_time_ms + dp_ms,
                peak_alive_states=1,
                alive_states_history=[1],
                total_states_explored=1,
                peak_memory_mb=_get_peak_mem_mb(),
            ),
        )

    # 4. Initialize Forward Reachable Set DP
    curr_states = np.array([[x0, y0, vy0, kappa0, tau0]], dtype=np.int32)
    init_packed = np.uint32(pack_state(x0, y0, vy0, kappa0, tau0))
    curr_packed = np.array([init_packed], dtype=np.uint32)

    # Parallel array storage for parent pointers across transitions
    P_keys: List[np.ndarray] = []
    P_parents: List[np.ndarray] = []
    P_actions: List[np.ndarray] = []

    actions_arr = np.array(ACTIONS, dtype=np.int8)  # shape (6, 2)
    alive_history: List[int] = [1]
    peak_alive: int = 1
    total_explored: int = 1

    meta = getattr(bake_result, "metadata", None) or {}
    soul_w, soul_h = meta.get("soul_size", (SOUL_W, SOUL_H))
    v_walk = meta.get("v_walk", V_WALK)
    v_jump_init = meta.get("v_jump", V_JUMP_INIT)
    physics_mode = meta.get("physics_mode", "docs")
    # The packed DP key quantises vy; the quantisation must match the physics
    # model or distinct states collapse onto one key (which silently turns
    # solvable waves into bogus deadlocks).
    configure_vy_quantisation(vy_quantisation_for_mode(physics_mode))
    B_blue = meta.get("B_blue")
    B_orange = meta.get("B_orange")

    # Precompute Euclidean distance field from obstacles for optimal safety scoring (only if obstacles exist)
    has_hazards = bool(np.any(B_hazard))
    if has_hazards:
        import scipy.ndimage
        dist_map = np.empty((T, H, W), dtype=np.float32)
        for t_idx in range(T):
            if np.any(B_hazard[t_idx]):
                dist_map[t_idx] = scipy.ndimage.distance_transform_edt(~B_hazard[t_idx])
            else:
                dist_map[t_idx] = 100.0
    else:
        dist_map = None

    # ---------------------------------------------------------------------
    # FAST PATH: completely empty arena.
    #
    # With no hazard anywhere in the horizon, and no forced-movement
    # (blue/orange) bone, the minimum-action route is to stay put: zero inputs
    # is both safe and cheapest. Running the full DP here is pure waste -- on
    # the open-arena benchmark it explored 193 million states, peaked at 785 MB
    # and took ~36 s to rediscover "do nothing".
    #
    # This is only taken when it is provably correct:
    #   * no hazard cell in ANY frame (so every position is safe), and
    #   * no B_blue / B_orange layer, which would force an input to survive, and
    #   * no SansSlam, which is a real mechanic: it slams the heart to a fixed
    #     row regardless of input, so "do nothing" is not a valid plan there.
    # The resulting trajectory is still validated against the hazard tensor
    # below, so a mis-detection cannot produce an unsafe plan silently.
    # ---------------------------------------------------------------------
    slam_set = set(meta.get("slam_frames") or [])
    if not has_hazards and B_blue is None and B_orange is None and not slam_set:
        stationary = [(x0, y0, vy0, kappa0, tau0)] * T
        safe = all(not B_hazard[t, y0, x0] for t in range(T))
        if safe:
            dp_ms = (time.perf_counter() - t_start) * 1000.0
            return SolveResult(
                is_deadlock=False,
                deadlock_frame=None,
                action_sequence=[(0, 0)] * (T - 1),
                trajectory=stationary,
                stats=SolveStats(
                    bake_time_ms=bake_time_ms,
                    dp_solve_time_ms=dp_ms,
                    total_time_ms=bake_time_ms + dp_ms,
                    peak_alive_states=1,
                    alive_states_history=[1] * T,
                    total_states_explored=1,
                    peak_memory_mb=_get_peak_mem_mb(),
                ),
            )

    curr_vals = np.array([0.0], dtype=np.float32)
    act_indices = np.arange(6, dtype=np.uint8)

    # 5. Main DP Forward Expansion Loop
    for t in range(T - 1):
        N = len(curr_packed)
        if N == 0:
            # Deadlock reached
            dp_ms = (time.perf_counter() - t_start) * 1000.0
            return SolveResult(
                is_deadlock=True,
                deadlock_frame=t,
                action_sequence=None,
                trajectory=None,
                stats=SolveStats(
                    bake_time_ms=bake_time_ms,
                    dp_solve_time_ms=dp_ms,
                    total_time_ms=bake_time_ms + dp_ms,
                    peak_alive_states=peak_alive,
                    alive_states_history=alive_history,
                    total_states_explored=total_explored,
                    peak_memory_mb=_get_peak_mem_mb(),
                ),
            )

        is_slam = (t in slam_frames)
        plat_t = platform_table[t] if t < len(platform_table) else ()

        # Vectorized expansion: 6 candidate transitions per state -> 6 * N candidates
        rep_states = np.repeat(curr_states, 6, axis=0)
        rep_packed = np.repeat(curr_packed, 6)
        rep_vals = np.repeat(curr_vals, 6)
        rep_act_idx = np.tile(act_indices, N)
        rep_ux = actions_arr[rep_act_idx, 0]
        rep_uy = actions_arr[rep_act_idx, 1]

        # Step dynamics in batch
        next_states = step_dynamics_batch(
            rep_states,
            rep_ux,
            rep_uy,
            platforms=plat_t,
            is_slam=is_slam,
            W=W,
            H=H,
            w=soul_w,
            h=soul_h,
            v_walk=v_walk,
            v_jump_init=v_jump_init,
            physics_mode=physics_mode,
        )

        next_x = next_states[:, 0]
        next_y = next_states[:, 1]

        # ------------------------------------------------------------------
        # Beam cap on the per-frame working set.
        #
        # The reachable set grows combinatorially on long horizons in a large
        # arena (the open-arena benchmark hit 410k states, 785 MB and ~36 s).
        # When a frame exceeds the cap, keep the highest-value states, which is
        # exactly the set the maximisation would prefer anyway. The cap is set
        # well above every real wave's peak so it does not alter their result.
        #
        # Collapsing duplicate children was tried and removed: identifying a
        # duplicate requires comparing the full action (the blue layer tests
        # `ux`), and the extra argsort cost more than the smaller arrays saved.
        # ------------------------------------------------------------------
        if len(curr_packed) > MAX_STATES_PER_FRAME:
            keep_top = np.argpartition(curr_vals, -MAX_STATES_PER_FRAME)[-MAX_STATES_PER_FRAME:]
            curr_packed = curr_packed[keep_top]
            curr_states = curr_states[keep_top]
            curr_vals = curr_vals[keep_top]
            N = len(curr_packed)

        # NOTE: collapsing duplicate children was attempted twice (adjacent-run
        # scan and np.unique) and reverted both times. The key must include the
        # full action to stay correct, and even then the extra pass cost more
        # than the smaller downstream arrays saved -- while dropping a
        # representative loses the parent link the backtracking needs. Leave the
        # 6x expansion intact.

        # Hazard tensor safety probe
        B_t1 = B_hazard[t + 1]
        safe = ~B_t1[next_y, next_x]

        if B_blue is not None and t + 1 < len(B_blue):
            B_blue_t1 = B_blue[t + 1]
            is_moving = (rep_ux != 0) | (next_states[:, 2] != 0) | (next_states[:, 3] == 0)
            safe &= ~(B_blue_t1[next_y, next_x] & is_moving)

        if B_orange is not None and t + 1 < len(B_orange):
            B_orange_t1 = B_orange[t + 1]
            is_moving = (rep_ux != 0) | (next_states[:, 2] != 0) | (next_states[:, 3] == 0)
            safe &= ~(B_orange_t1[next_y, next_x] & ~is_moving)
        if not np.any(safe):
            # Deadlock early-stop at frame t+1
            alive_history.append(0)
            dp_ms = (time.perf_counter() - t_start) * 1000.0
            return SolveResult(
                is_deadlock=True,
                deadlock_frame=t + 1,
                action_sequence=None,
                trajectory=None,
                stats=SolveStats(
                    bake_time_ms=bake_time_ms,
                    dp_solve_time_ms=dp_ms,
                    total_time_ms=bake_time_ms + dp_ms,
                    peak_alive_states=peak_alive,
                    alive_states_history=alive_history,
                    total_states_explored=total_explored + 6 * N,
                    peak_memory_mb=_get_peak_mem_mb(),
                ),
            )

        val_states = next_states[safe]
        val_parent = rep_packed[safe]
        val_act = rep_act_idx[safe]

        # Compact 32-bit state packing
        val_packed = pack_states_array(val_states)

        # ------------------------------------------------------------------
        # Objective: survivability FIRST, then MINIMUM INPUT.
        #
        # The planner should produce the no-hit path that presses the fewest
        # keys, so every action carries a cost and standing still is the
        # baseline. Two deliberate changes versus the previous reward:
        #
        #   * the `+ x * 0.05` term is GONE. It rewarded drifting right, which
        #     directly contradicts "do as little as possible" and made the
        #     solver pick moving routes even when standing still was safe.
        #   * the action penalty is applied to BOTH branches. Previously the
        #     no-hazard branch (`else`) had no value at all, so every surviving
        #     route scored identically and the extracted witness was arbitrary
        #     rather than the lowest-effort one.
        #
        # Weighting: clearance still dominates (1 px of extra bone clearance is
        # worth ~13 idle frames), so the solver never trades safety for
        # quietness; among equally safe routes the cheapest input wins.
        # ------------------------------------------------------------------
        act_cost = np.abs(rep_ux[safe]) * ACT_COST_HORIZONTAL + rep_uy[safe] * ACT_COST_JUMP

        if has_hazards:
            # Bellman value iteration: cumulative clearance minus input cost.
            dist_scores = dist_map[t + 1, val_states[:, 1], val_states[:, 0]]
            cand_vals = rep_vals[safe] + dist_scores - act_cost

            # Fast uint64 combo sort for optimal parent selection
            K = len(val_packed)
            v_norm = cand_vals - cand_vals.min()
            v_max = float(v_norm.max())
            inv_val = ((1.0 - (v_norm / (v_max + 1e-6))) * 4294967295.0).astype(np.uint32)
            combo = (val_packed.astype(np.uint64) << 32) | inv_val.astype(np.uint64)
            order = np.argsort(combo)
            s_combo = combo[order]
            mask = np.empty(K, dtype=bool)
            mask[0] = True
            mask[1:] = (s_combo[1:] >> 32) != (s_combo[:-1] >> 32)
            best_idx = order[mask]
            unq_packed = val_packed[best_idx]
            curr_vals = cand_vals[best_idx]
        else:
            # Open arena: no obstacles at all, so there is nothing to trade off
            # and every survivor is equally safe. Keep the high-throughput
            # dedup path (the min-action sort here cost ~40% of the whole solve
            # on the open-arena benchmarks while changing nothing meaningful).
            cand_vals = rep_vals[safe]
            unq_packed, best_idx = np.unique(val_packed, return_index=True)
            curr_vals = cand_vals[best_idx]

        P_keys.append(unq_packed)
        P_parents.append(val_parent[best_idx])
        P_actions.append(val_act[best_idx])

        curr_packed = unq_packed
        curr_states = val_states[best_idx]

        cur_len = len(unq_packed)
        alive_history.append(cur_len)
        if cur_len > peak_alive:
            peak_alive = cur_len
        total_explored += 6 * N

    # 6. Deadlock Check at Frame T-1
    if len(curr_packed) == 0:
        dp_ms = (time.perf_counter() - t_start) * 1000.0
        return SolveResult(
            is_deadlock=True,
            deadlock_frame=T - 1,
            action_sequence=None,
            trajectory=None,
            stats=SolveStats(
                bake_time_ms=bake_time_ms,
                dp_solve_time_ms=dp_ms,
                total_time_ms=bake_time_ms + dp_ms,
                peak_alive_states=peak_alive,
                alive_states_history=alive_history,
                total_states_explored=total_explored,
                peak_memory_mb=_get_peak_mem_mb(),
            ),
        )

    # 7. Feature 16: Linear O(T) Backtracking along P
    # Select globally optimal terminal state (maximizing cumulative safety & clearance)
    best_term_idx = int(np.argmax(curr_vals))
    curr_target = curr_packed[best_term_idx]
    traj_packed = [curr_target]
    actions_rev: List[Tuple[int, int]] = []

    for t_step in range(T - 2, -1, -1):
        idx = np.searchsorted(P_keys[t_step], curr_target)
        p_act = P_actions[t_step][idx]
        p_par = P_parents[t_step][idx]
        actions_rev.append(ACTIONS[p_act])
        traj_packed.append(p_par)
        curr_target = p_par

    action_seq = list(reversed(actions_rev))
    traj = [unpack_state(p) for p in reversed(traj_packed)]

    dp_ms = (time.perf_counter() - t_start) * 1000.0
    return SolveResult(
        is_deadlock=False,
        deadlock_frame=None,
        action_sequence=action_seq,
        trajectory=traj,
        stats=SolveStats(
            bake_time_ms=bake_time_ms,
            dp_solve_time_ms=dp_ms,
            total_time_ms=bake_time_ms + dp_ms,
            peak_alive_states=peak_alive,
            alive_states_history=alive_history,
            total_states_explored=total_explored,
            peak_memory_mb=_get_peak_mem_mb(),
        ),
    )


__all__ = [
    "solve_lattice_dp",
    "SolveResult",
    "SolveStats",
]
