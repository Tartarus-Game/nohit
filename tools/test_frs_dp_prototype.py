"""Prototype for Complete Topological DAG-DP (FRS-DP) with 9-member product dynamics."""
import time
import numpy as np
from pathlib import Path
from numba import njit
from nohit.engine.compact_wave import ROOT, compile_wave, prepare_collision_native
from nohit.engine.compact_lattice import (
    native_values, native_micro_into, blocked_xy, same_state, state_hash,
    product_micro_into, product_blocked
)

@njit(cache=False)
def search_frs_dp(mask, schedule, initial, max_states=30000, max_nodes=1000000):
    """Unified DAG-DP / Forward Reachable Set DP.
    
    - Monotonic forward time layers: 0 to layers-1
    - Double-buffered queues: current_queue and next_queue
    - Strict 9-member product dynamics (45 fields)
    - Hash-based / epoch-based O(1) state folding per frame
    - Action and parent history for O(T) linear backtracking
    """
    layers = (len(mask) - 1) // 4
    state_dim = initial.size  # 45
    
    current_queue = np.empty((max_states, state_dim), np.float64)
    next_queue = np.empty((max_states, state_dim), np.float64)
    current_queue[0] = initial
    current_count = 1
    
    # History tables for linear backtracking
    # parent_history[frame, child_idx] = parent_idx in current_queue
    # action_history[frame, child_idx] = [ux, up]
    parent_history = np.empty((layers, max_states), np.int32)
    action_history = np.empty((layers, max_states, 2), np.int8)
    
    # Hash table for O(1) state folding in the next frame
    hash_size = 1
    while hash_size < max_states * 4:
        hash_size *= 2
    slots = np.empty(hash_size, np.int32)
    epochs = np.zeros(hash_size, np.int32)
    
    history_counts = np.zeros(layers + 1, np.int32)
    history_counts[0] = 1
    
    child = np.empty(state_dim, np.float64)
    total_expansions = 0
    
    for frame in range(layers):
        next_count = 0
        target_epoch = frame + 1
        
        for i in range(current_count):
            total_expansions += 1
            for up in range(2):
                for ux in range(-1, 2):
                    # Fast Op-2 check on Member 0 across 4 microsteps
                    m0_x = current_queue[i, 0]
                    m0_y = current_queue[i, 1]
                    m0_dx = current_queue[i, 2]
                    m0_dy = current_queue[i, 3]
                    m0_prev = current_queue[i, 4]
                    safe = True
                    for micro in range(4):
                        tick = frame * 4 + micro + 1
                        m0_x, m0_y, m0_dx, m0_dy, m0_prev = native_values(
                            m0_x, m0_y, m0_dx, m0_dy, m0_prev, ux, up, schedule[tick]
                        )
                        if blocked_xy(mask, tick, m0_x, m0_y):
                            safe = False
                            break
                    if not safe:
                        continue
                    
                    # Full 9-member product dynamics
                    child[:] = current_queue[i]
                    for micro in range(4):
                        tick = frame * 4 + micro + 1
                        product_micro_into(child, ux, up, schedule[tick], child, tick)
                        if product_blocked(mask, tick, child):
                            safe = False
                            break
                    if not safe:
                        continue
                    
                    # State folding via hash table (O(1))
                    h = state_hash(child)
                    h ^= h >> np.uint64(30)
                    h *= np.uint64(0xbf58476d1ce4e5b9)
                    h ^= h >> np.uint64(27)
                    slot = np.int64(h & np.uint64(hash_size - 1))
                    
                    while epochs[slot] == target_epoch and not same_state(next_queue[slots[slot]], child):
                        slot = (slot + 1) & (hash_size - 1)
                        
                    if epochs[slot] == target_epoch:
                        # Equivalent state already in next_queue; fold!
                        continue
                        
                    if next_count >= max_states:
                        return 2, frame, total_expansions, history_counts, np.empty((0, 2), np.int8)
                    
                    epochs[slot] = target_epoch
                    slots[slot] = next_count
                    next_queue[next_count] = child
                    parent_history[frame, next_count] = i
                    action_history[frame, next_count, 0] = ux
                    action_history[frame, next_count, 1] = up
                    next_count += 1
        
        if next_count == 0:
            # Deadlock reached! 100% complete early termination
            return 1, frame, total_expansions, history_counts, np.empty((0, 2), np.int8)
            
        history_counts[frame + 1] = next_count
        
        # Double-buffer pointer swap
        temp = current_queue
        current_queue = next_queue
        next_queue = temp
        current_count = next_count
        
    # Successfully reached terminal frame! Backtrack linear witness route
    route = np.empty((layers, 2), np.int8)
    curr_idx = 0  # pick first surviving terminal state
    for frame in range(layers - 1, -1, -1):
        route[frame, 0] = action_history[frame, curr_idx, 0]
        route[frame, 1] = action_history[frame, curr_idx, 1]
        curr_idx = parent_history[frame, curr_idx]
        
    return 0, layers, total_expansions, history_counts, route

def main():
    print("Compiling wave...")
    schedule, geometry, initial = compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    mask = prepare_collision_native(geometry, margin_x=1.0, margin_y=2.0)
    starts = np.tile(initial, 9)
    for group in range(3):
        starts[group*15+8] = .75
        starts[group*15+13] = 0.
        
    print("Running search_frs_dp...")
    t0 = time.perf_counter()
    status, frame, total_exp, history, route = search_frs_dp(mask, schedule, starts, max_states=40000)
    t1 = time.perf_counter()
    
    status_names = ['candidate_found', 'exhausted_in_declared_model', 'resource_limit']
    print(f"Status: {status_names[status]}, frame: {frame}, expansions: {total_exp}")
    print(f"Wall time: {(t1-t0)*1000:.2f} ms")
    print(f"Route length: {len(route)}")
    print(f"Max states in a single frame: {max(history)}")

if __name__ == '__main__':
    main()
