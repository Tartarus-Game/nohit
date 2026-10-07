#!/usr/bin/env python3
"""VERIFY_C scratch: replicate the solver's forward pass + backtrack verbatim
(copied from nohit/engine/solver.py, unchanged) so the terminal-state choice and
the parent chain can be inspected directly. Read-only: nothing under nohit/ is
modified.

Usage: python tools/scratch_C_dp_probe.py <x0> [T] [W] [H]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from nohit.common.constants import ACTIONS, SOUL_W, SOUL_H, V_WALK, V_JUMP_INIT  # noqa: E402
from nohit.common.types import BakeResult  # noqa: E402
from nohit.engine.dynamics import step_dynamics_batch  # noqa: E402
from nohit.engine.state import pack_state, pack_states_array, unpack_state, \
    configure_vy_quantisation, vy_quantisation_for_mode  # noqa: E402

ACT_COST_HORIZONTAL = 0.75
ACT_COST_JUMP = 1.0
MAX_STATES_PER_FRAME = 400_000


def main() -> int:
    x0 = int(sys.argv[1]) if len(sys.argv) > 1 else 174
    T = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    W = int(sys.argv[3]) if len(sys.argv) > 3 else 349
    H = int(sys.argv[4]) if len(sys.argv) > 4 else 114
    y0 = 0
    B_hazard = np.zeros((T, H, W), dtype=bool)
    bake = BakeResult(B_hazard=B_hazard, platform_table=[[] for _ in range(T)],
                      initial_state=(x0, y0),
                      metadata={"slam_frames": [T - 2]})
    meta = bake.metadata
    slam_frames = set(meta.get("slam_frames", []))
    platform_table = bake.platform_table
    has_hazards = bool(np.any(B_hazard))
    print(f"T={T} H={H} W={W} x0={x0} has_hazards={has_hazards} slam_frames={slam_frames}")

    vy0, kappa0, tau0 = 0, 1, 0
    curr_states = np.array([[x0, y0, vy0, kappa0, tau0]], dtype=np.int32)
    curr_packed = np.array([np.uint32(pack_state(x0, y0, vy0, kappa0, tau0))], dtype=np.uint32)
    P_keys, P_parents, P_actions = [], [], []
    actions_arr = np.array(ACTIONS, dtype=np.int8)
    meta2 = meta
    soul_w, soul_h = meta2.get("soul_size", (SOUL_W, SOUL_H))
    v_walk = meta2.get("v_walk", V_WALK)
    v_jump_init = meta2.get("v_jump", V_JUMP_INIT)
    physics_mode = meta2.get("physics_mode", "docs")
    configure_vy_quantisation(vy_quantisation_for_mode(physics_mode))
    curr_vals = np.array([0.0], dtype=np.float32)
    act_indices = np.arange(6, dtype=np.uint8)

    snapshots = {}
    for t in range(T - 1):
        N = len(curr_packed)
        is_slam = (t in slam_frames)
        plat_t = platform_table[t] if t < len(platform_table) else ()
        rep_states = np.repeat(curr_states, 6, axis=0)
        rep_packed = np.repeat(curr_packed, 6)
        rep_vals = np.repeat(curr_vals, 6)
        rep_act_idx = np.tile(act_indices, N)
        rep_ux = actions_arr[rep_act_idx, 0]
        rep_uy = actions_arr[rep_act_idx, 1]
        next_states = step_dynamics_batch(rep_states, rep_ux, rep_uy, platforms=plat_t,
                                         is_slam=is_slam, W=W, H=H, w=soul_w, h=soul_h,
                                         v_walk=v_walk, v_jump_init=v_jump_init,
                                         physics_mode=physics_mode)
        next_x = next_states[:, 0]
        next_y = next_states[:, 1]
        B_t1 = B_hazard[t + 1]
        safe = ~B_t1[next_y, next_x]
        val_states = next_states[safe]
        val_parent = rep_packed[safe]
        val_act = rep_act_idx[safe]
        val_packed = pack_states_array(val_states)
        act_cost = np.abs(rep_ux[safe]) * ACT_COST_HORIZONTAL + rep_uy[safe] * ACT_COST_JUMP
        cand_vals = rep_vals[safe]
        unq_packed, best_idx = np.unique(val_packed, return_index=True)
        curr_vals = cand_vals[best_idx]
        P_keys.append(unq_packed)
        P_parents.append(val_parent[best_idx])
        P_actions.append(val_act[best_idx])
        curr_packed = unq_packed
        curr_states = val_states[best_idx]
        snapshots[t] = dict(
            n_child=len(val_packed), n_alive=len(unq_packed),
            x_min=int(next_x[safe].min()), x_max=int(next_x[safe].max()),
            keys_min=int(unq_packed[0]), keys_max=int(unq_packed[-1]),
            sorted_ok=bool(np.all(unq_packed[1:] >= unq_packed[:-1])),
            init_alive=bool(np.any(unq_packed == np.uint32(pack_state(x0, y0, 0, 1, 0)))),
            vals_all_zero=bool(np.all(curr_vals == 0.0)),
        )
    for t in sorted(snapshots)[-4:]:
        s = snapshots[t]
        print(f"  step {t:>3} -> frame {t+1:>3}: alive={s['n_alive']:>6} "
              f"x_range=[{s['x_min']},{s['x_max']}] min_key={unpack_state(s['keys_min'])} "
              f"sorted={s['sorted_ok']} init_alive={s['init_alive']} "
              f"curr_vals_all_zero={s['vals_all_zero']}")

    best_term_idx = int(np.argmax(curr_vals))
    curr_target = curr_packed[best_term_idx]
    print(f"\nterminal: argmax(curr_vals)={best_term_idx} of {len(curr_vals)}  "
          f"curr_vals[0]={curr_vals[0]!r} max={curr_vals.max()!r} "
          f"all_equal={bool(np.all(curr_vals == curr_vals[0]))}")
    print(f"  curr_packed[0]      = {unpack_state(curr_packed[0])}")
    print(f"  curr_packed[argmax] = {unpack_state(curr_target)}")
    xs = [int(unpack_state(k)[0]) for k in curr_packed]
    print(f"  final alive x range = [{min(xs)}, {max(xs)}]  n={len(xs)}")
    print(f"  initial key present = {bool(np.any(curr_packed == np.uint32(pack_state(x0, y0, 0, 1, 0))))}")

    traj_packed = [curr_target]
    chain = [unpack_state(curr_target)]
    actions_rev = []
    for t_step in range(T - 2, -1, -1):
        idx = np.searchsorted(P_keys[t_step], curr_target)
        p_act = P_actions[t_step][idx]
        p_par = P_parents[t_step][idx]
        actions_rev.append(ACTIONS[p_act])
        traj_packed.append(p_par)
        chain.append(unpack_state(p_par))
        curr_target = p_par
    chain = list(reversed(chain))
    print("\nbacktrack chain (frame: state):")
    for f, s in enumerate(chain):
        print(f"  f={f:>3} {s}  action_into_this_frame="
              f"{actions_rev[::-1][f-1] if f > 0 else None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
