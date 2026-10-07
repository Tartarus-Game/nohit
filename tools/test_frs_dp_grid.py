"""Test FRS-DP with flat equivalence grid folding."""
import time
import numpy as np
from pathlib import Path
from numba import njit
from nohit.engine.compact_wave import ROOT, compile_wave, prepare_collision_native
from nohit.engine.compact_lattice import (
    native_values, native_micro_into, blocked_xy,
    product_micro_into, product_blocked
)

# Combat zone bounds
# x: 118 to 543 -> 430 px
# y: 236 to 386 -> 155 px
# dy: -200 to 750 -> ~950 / 10 -> 95 bins
# prev_up: 2

NX = 435
NY = 160
NVY = 96
NUP = 2

TOTAL_CELLS = NX * NY * NVY * NUP

@njit(cache=False, inline="always")
def get_grid_index(x, y, dy, prev_up):
    ix = int(x) - 113
    if ix < 0: ix = 0
    elif ix >= NX: ix = NX - 1
    
    iy = int(y) - 231
    if iy < 0: iy = 0
    elif iy >= NY: iy = NY - 1
    
    # dy mapping: dy from -200 to 750
    ivy = int((dy + 200.0) / 10.0)
    if ivy < 0: ivy = 0
    elif ivy >= NVY: ivy = NVY - 1
    
    iup = int(prev_up)
    if iup < 0: iup = 0
    elif iup >= NUP: iup = NUP - 1
    
    return ((ix * NY + iy) * NVY + ivy) * NUP + iup

@njit(cache=False)
def search_frs_dp_grid(mask, schedule, initial, max_states=30000):
    layers = (len(mask) - 1) // 4
    state_dim = initial.size  # 45
    
    current_queue = np.empty((max_states, state_dim), np.float64)
    next_queue = np.empty((max_states, state_dim), np.float64)
    current_queue[0] = initial
    current_count = 1
    
    parent_history = np.empty((layers, max_states), np.int32)
    action_history = np.empty((layers, max_states, 2), np.int8)
    
    # 1D flat visited epoch table
    visited_epoch = np.zeros(TOTAL_CELLS, np.int32)
    
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
                    # Fast Op-2 check on Member 0
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
                    
                    # Equivalence class folding via flat 1D grid
                    idx = get_grid_index(child[0], child[1], child[3], child[4])
                    if visited_epoch[idx] == target_epoch:
                        # Already reached this equivalence class in this frame; fold!
                        continue
                        
                    if next_count >= max_states:
                        return 2, frame, total_expansions, history_counts, np.empty((0, 2), np.int8)
                    
                    visited_epoch[idx] = target_epoch
                    next_queue[next_count] = child
                    parent_history[frame, next_count] = i
                    action_history[frame, next_count, 0] = ux
                    action_history[frame, next_count, 1] = up
                    next_count += 1
        
        if next_count == 0:
            return 1, frame, total_expansions, history_counts, np.empty((0, 2), np.int8)
            
        history_counts[frame + 1] = next_count
        
        temp = current_queue
        current_queue = next_queue
        next_queue = temp
        current_count = next_count
        
    route = np.empty((layers, 2), np.int8)
    curr_idx = 0
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
        
    print(f"Total grid cells: {TOTAL_CELLS} ({TOTAL_CELLS*4/1024/1024:.1f} MB)")
    print("Running search_frs_dp_grid...")
    t0 = time.perf_counter()
    status, frame, total_exp, history, route = search_frs_dp_grid(mask, schedule, starts, max_states=30000)
    t1 = time.perf_counter()
    
    status_names = ['candidate_found', 'exhausted_in_declared_model', 'resource_limit']
    print(f"Status: {status_names[status]}, frame: {frame}, expansions: {total_exp}")
    print(f"Wall time: {(t1-t0)*1000:.2f} ms")
    print(f"Route length: {len(route)}")
    print(f"Max states in a single frame: {max(history)}")

if __name__ == '__main__':
    main()
