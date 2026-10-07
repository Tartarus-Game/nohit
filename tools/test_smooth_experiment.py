"""Test input smoothness penalty on route quality and search performance."""
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
def search_smooth(mask, schedule, initial, smoothness_weight=0.1, max_expansions=10000000, max_dead=4000000, anticipation=12):
    layers = (len(mask)-1)//4
    stack = np.empty((layers+1, initial.size), np.float64)
    stack[0] = initial
    children = np.empty((layers, 6, initial.size), np.float64)
    choices = np.empty((layers, 6, 2), np.int8)
    scores = np.empty((layers, 6), np.float64)
    counts = np.full(layers, -1, np.int32)
    cursors = np.zeros(layers, np.int32)
    route = np.empty((layers, 2), np.int8)
    visits = np.zeros(layers+1, np.int64)
    size = 1
    while size < max_dead * 4:
        size *= 2
    dead_depth = np.full(size, -1, np.int32)
    dead_state = np.empty((max_dead, initial.size), np.float64)
    dead_ids = np.empty(size, np.int32)
    dead_count = 0
    depth = 0
    expansions = 0
    child = np.empty(initial.size, np.float64)
    forecast = np.empty(5, np.float64)

    while depth >= 0:
        if depth == layers:
            return 0, depth, expansions, visits, route.copy()
        if counts[depth] < 0:
            if expansions >= max_expansions:
                return 2, depth, expansions, visits, route[:0].copy()
            expansions += 1
            visits[depth] += 1
            n = 0
            
            # Previous action for input smoothness
            prev_ux = np.int8(0)
            prev_up = np.int8(0)
            if depth > 0:
                prev_ux = route[depth-1, 0]
                prev_up = route[depth-1, 1]
                
            for up in range(2):
                for ux in range(-1, 2):
                    child[:] = stack[depth]
                    safe = True
                    for micro in range(4):
                        tick = depth * 4 + micro + 1
                        product_micro_into(child, ux, up, schedule[tick], child, tick)
                        if product_blocked(mask, tick, child):
                            safe = False
                            break
                    if not safe:
                        continue
                    duplicate = False
                    for j in range(n):
                        if same_state(children[depth, j], child):
                            duplicate = True
                            break
                    if duplicate:
                        continue
                    children[depth, n] = child
                    choices[depth, n, 0] = ux
                    choices[depth, n, 1] = up
                    p = schedule[(depth+1)*4]
                    
                    # Base score: platform center and floor preference
                    target_x = p[0] + p[2]/2
                    scores[depth, n] = abs(child[0] - target_x) + max(0., child[1] - 327.95) * 3 + up * .01
                    
                    # R6: Input smoothness penalty
                    if depth > 0:
                        change_pen = 0.0
                        if ux != prev_ux:
                            change_pen += smoothness_weight
                        if up != prev_up:
                            change_pen += smoothness_weight
                        scores[depth, n] += change_pen
                    
                    # OP-1: Member 0 anticipation rollout
                    if anticipation > 0:
                        forecast[0] = child[0]
                        forecast[1] = child[1]
                        forecast[2] = child[2]
                        forecast[3] = child[3]
                        forecast[4] = child[4]
                        horizon = min(anticipation * 4, len(mask) - 1 - tick)
                        survived = 0
                        for ahead in range(1, horizon + 1):
                            future = tick + ahead
                            native_micro_into(forecast, 0, up, schedule[future], forecast)
                            if blocked_xy(mask, future, forecast[0], forecast[1]):
                                break
                            survived += 1
                        scores[depth, n] += 1000 * (horizon - survived)
                    
                    if depth == 0:
                        if ux != 0 or up != 0:
                            scores[depth, n] += 1000000
                    n += 1
            
            # Sort
            for j in range(1, n):
                k = j
                while k > 0 and scores[depth, k] < scores[depth, k-1]:
                    v = scores[depth, k-1]
                    scores[depth, k-1] = scores[depth, k]
                    scores[depth, k] = v
                    c = children[depth, k-1].copy()
                    children[depth, k-1] = children[depth, k]
                    children[depth, k] = c
                    act = choices[depth, k-1].copy()
                    choices[depth, k-1] = choices[depth, k]
                    choices[depth, k] = act
                    k -= 1
            counts[depth] = n
            cursors[depth] = 0
            
        if cursors[depth] >= counts[depth]:
            h = state_hash(stack[depth]) ^ np.uint64(depth * 1099511628211)
            h ^= h >> np.uint64(30)
            h *= np.uint64(0xbf58476d1ce4e5b9)
            slot = np.int64(h & np.uint64(size - 1))
            while dead_depth[slot] >= 0 and not (dead_depth[slot] == depth and same_state(dead_state[dead_ids[slot]], stack[depth])):
                slot = (slot + 1) & (size - 1)
            if dead_depth[slot] < 0:
                if dead_count >= max_dead:
                    return 2, depth, expansions, visits, route[:0].copy()
                dead_depth[slot] = depth
                dead_ids[slot] = dead_count
                dead_state[dead_count] = stack[depth]
                dead_count += 1
            counts[depth] = -1
            depth -= 1
            continue
            
        j = cursors[depth]
        cursors[depth] += 1
        child = children[depth, j]
        h = state_hash(child) ^ np.uint64((depth + 1) * 1099511628211)
        h ^= h >> np.uint64(30)
        h *= np.uint64(0xbf58476d1ce4e5b9)
        slot = np.int64(h & np.uint64(size - 1))
        while dead_depth[slot] >= 0 and not (dead_depth[slot] == depth + 1 and same_state(dead_state[dead_ids[slot]], child)):
            slot = (slot + 1) & (size - 1)
        if dead_depth[slot] >= 0:
            continue
        stack[depth + 1] = child
        route[depth] = choices[depth, j]
        depth += 1
        if depth < layers:
            counts[depth] = -1
            
    return 1, 0, expansions, visits, route[:0].copy()

def count_key_changes(route):
    ux_changes = 0
    up_changes = 0
    for i in range(1, len(route)):
        if route[i][0] != route[i-1][0]:
            ux_changes += 1
        if route[i][1] != route[i-1][1]:
            up_changes += 1
    return ux_changes, up_changes

def main():
    schedule, geometry, initial = compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    mask = prepare_collision_native(geometry, margin_x=1.0, margin_y=2.0)
    starts = np.tile(initial, 9)
    for group in range(3):
        starts[group*15+8] = .75
        starts[group*15+13] = 0.
        
    for weight in [0.0, 0.05, 0.1]:
        print(f'Testing smoothness_weight={weight}...')
        t0 = time.perf_counter()
        status, frame, expansions, visits, route = search_smooth(
            mask, schedule, starts, smoothness_weight=weight, max_expansions=10000000, max_dead=4000000, anticipation=12
        )
        t1 = time.perf_counter()
        if len(route) > 0:
            ux_ch, up_ch = count_key_changes(route)
            print(f'weight={weight}: status={status}, expansions={expansions}, time={t1-t0:.2f}s, ux_ch={ux_ch}, up_ch={up_ch}, total_ch={ux_ch+up_ch}')
        else:
            print(f'weight={weight}: status={status}, frame={frame}, expansions={expansions}, time={t1-t0:.2f}s')

if __name__ == '__main__':
    main()
