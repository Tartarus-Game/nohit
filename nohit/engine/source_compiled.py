"""Compiled candidate search. Acceptance still belongs to the running game.

Array parents replace Python ancestor objects. The packed key has the same
position/velocity resolution as the source XY candidate generator.
"""
import math
import time
import numpy as np
from numba import njit, prange, get_num_threads, set_num_threads
from nohit.common.types import SolveResult, SolveStats


@njit(cache=True, inline='always')
def _tick(y, v, previous_up, up):
    displacement = v / 240.0
    steps = max(1, int(math.floor(abs(displacement) + .5)))
    start = y
    for sub in range(1, steps + 1):
        next_y = start - displacement * sub / steps
        if next_y <= 0:
            y = start - displacement * (sub - 1) / steps
            v = 0.0
            break
        y = next_y
    if up and not previous_up and y < 1.0:
        v -= 180.0
    if previous_up and not up and v < -30.0:
        v = -30.0
    gravity = 0.0
    if 15.0 < v < 240.0:
        gravity = 540.0
    elif -30.0 < v <= 15.0:
        gravity = 180.0
    elif -120.0 < v <= -30.0:
        gravity = 450.0
    elif v <= -120.0:
        gravity = 180.0
    if y >= .2:
        v = min(750.0, v + gravity / 240.0)
    return y, v, up


@njit(cache=True)
def _clearance(hazards):
    # Spatial chessboard distance, capped at 8px. Time uncertainty was already
    # included in the hazard intervals. Two linear passes avoid Python loops.
    T, H, W = hazards.shape
    result = np.empty((T, H, W), np.uint8)
    for t in range(T):
        for y in range(H):
            for x in range(W):
                d = 0 if hazards[t, y, x] else 8
                if y:
                    d = min(d, int(result[t, y-1, x]) + 1)
                    if x:
                        d = min(d, int(result[t, y-1, x-1]) + 1)
                    if x+1 < W:
                        d = min(d, int(result[t, y-1, x+1]) + 1)
                if x:
                    d = min(d, int(result[t, y, x-1]) + 1)
                result[t, y, x] = d
        for y in range(H-1, -1, -1):
            for x in range(W-1, -1, -1):
                d = int(result[t, y, x])
                if y+1 < H:
                    d = min(d, int(result[t, y+1, x]) + 1)
                    if x:
                        d = min(d, int(result[t, y+1, x-1]) + 1)
                    if x+1 < W:
                        d = min(d, int(result[t, y+1, x+1]) + 1)
                if x+1 < W:
                    d = min(d, int(result[t, y, x+1]) + 1)
                result[t, y, x] = d
    return result


@njit(cache=True)
def _band_select(costs, bands, band_order, band_count, band_slots, limit):
    """Exact stable quota selection without sorting all candidate costs."""
    quota = max(1, limit // band_count)
    band_ids = np.empty(band_slots, np.int32)
    for b in range(band_count):
        band_ids[band_order[b]] = b
    heaps = np.empty((band_count, quota), np.int32)
    sizes = np.zeros(band_count, np.int32)
    for j in range(len(costs)):
        b = band_ids[bands[j]]
        size = sizes[b]
        if size < quota:
            pos = size
            sizes[b] += 1
            while pos:
                parent = (pos - 1) // 2
                other = heaps[b, parent]
                if costs[other] > costs[j] or (costs[other] == costs[j] and other > j):
                    break
                heaps[b, pos] = other
                pos = parent
            heaps[b, pos] = j
        else:
            other = heaps[b, 0]
            if costs[j] > costs[other] or (costs[j] == costs[other] and j > other):
                continue
            pos = 0
            while 2 * pos + 1 < quota:
                child = 2 * pos + 1
                if child + 1 < quota:
                    left, right = heaps[b, child], heaps[b, child + 1]
                    if costs[right] > costs[left] or (costs[right] == costs[left] and right > left):
                        child += 1
                other = heaps[b, child]
                if costs[j] > costs[other] or (costs[j] == costs[other] and j > other):
                    break
                heaps[b, pos] = other
                pos = child
            heaps[b, pos] = j
    chosen = np.empty(int(sizes.sum()), np.int64)
    n = 0
    for b in range(band_count):
        for i in range(sizes[b]):
            chosen[n] = heaps[b, i]
            n += 1
    # Candidate index is the original stable tie breaker.
    chosen.sort()
    order = np.argsort(costs[chosen], kind='mergesort')
    return chosen[order[:limit]]


@njit(cache=True)
def _search(hazards, blues, white_clearance, blue_clearance, has_blue, x0, max_states, wait_frames, phase_diversity, platforms, y0, v0, operator=0):
    intervals, H, W = hazards.shape
    T = intervals + 1
    blue_rest_frames = 6 if has_blue else 0
    settle_cap = max(wait_frames, blue_rest_frames)
    states = np.empty((T, max_states, 7), np.float64)
    parents = np.empty((T, max_states), np.int32)
    moves = np.empty((T, max_states, 2), np.int8)
    costs = np.zeros(max_states, np.int64)
    states[0, 0] = np.array([x0, y0, v0, 0., 0., float(settle_cap) if v0 == 0 else 0., 8.])
    margin_weight = 8192 * (T + 1) * 2
    history = np.zeros(T, np.int32)
    history[0] = 1
    count = 1
    capacity = max_states * 6
    candidate_states = np.empty((capacity, 7), np.float64)
    candidate_parents = np.empty(capacity, np.int32)
    candidate_moves = np.empty((capacity, 2), np.int8)
    candidate_costs = np.empty(capacity, np.int64)
    candidate_bands = np.empty(capacity, np.int32)
    # 3px X bands preserve lateral alternatives before their benefit arrives.
    height_bands = (H + 3) // 4
    band_slots = (W + 3) * (height_bands * 3 if phase_diversity else 1)
    band_order = np.empty(band_slots, np.int32)
    band_seen = np.zeros(band_slots, np.int8)
    band_kept = np.zeros(band_slots, np.int32)
    samples = np.empty((4, 3), np.float64)
    vertical_samples = np.empty((4, 3), np.float64)
    table_size = 1
    while table_size < capacity * 4:
        table_size *= 2
    table_keys = np.empty(table_size, np.int64)
    table_epochs = np.zeros(table_size, np.int32)
    table_values = np.empty(table_size, np.int32)
    table_mask = np.uint64(table_size - 1)
    for frame in range(intervals):
        if operator != 2:
            table_keys[:] = -1
        candidates = 0
        for i in range(count):
            for up in range(2):
                y, v = states[frame, i, 1], states[frame, i, 2]
                previous_up = int(states[frame, i, 3])
                settled_frames = int(states[frame, i, 5])
                if up and not previous_up and settled_frames < wait_frames:
                    continue
                if operator == 2 and platforms.shape[1] == 0:
                    for sub in range(4):
                        y, v, previous_up = _tick(y, v, previous_up, up)
                        vertical_samples[sub, 0] = y
                        vertical_samples[sub, 1] = v
                        vertical_samples[sub, 2] = previous_up
                for direction in range(3):
                    ux = 0 if direction == 0 else (-1 if direction == 1 else 1)
                    x = states[frame, i, 0]
                    y, v = states[frame, i, 1], states[frame, i, 2]
                    previous_up = int(states[frame, i, 3])
                    previous_ux = int(states[frame, i, 4])
                    margin = int(states[frame, i, 6])
                    safe = True
                    settled = not up
                    for sub in range(4):
                        ground = 0.0
                        carry = 0.0
                        for pi in range(platforms.shape[1]):
                            pl = platforms[frame, pi]
                            left = pl[0] + pl[3] * sub / 240.0
                            if left - 7 < x < pl[1] + pl[3] * sub / 240.0 + 7 and abs(y-pl[2]) < 1.2 and abs(v) < 1e-8:
                                ground = pl[2]
                                carry = pl[3]
                                break
                        old_y = y
                        if operator == 2 and platforms.shape[1] == 0:
                            y, v = vertical_samples[sub, 0], vertical_samples[sub, 1]
                            previous_up = int(vertical_samples[sub, 2])
                        else:
                            y, v, previous_up = _tick(y-ground, v, previous_up, up)
                            y += ground
                        x += (previous_ux * 150.0 + carry) / 240.0
                        previous_ux = ux
                        for pi in range(platforms.shape[1]):
                            pl = platforms[frame, pi]
                            left = pl[0] + pl[3] * (sub+1) / 240.0
                            right = pl[1] + pl[3] * (sub+1) / 240.0
                            if v >= 0 and old_y >= pl[2] and y <= pl[2] and left-7 < x < right+7:
                                y = pl[2]
                                v = 0.0
                                ground = y
                                break
                        settled = settled and abs(y-ground)<.2 and abs(v)<1e-8
                        samples[sub, 0] = y
                        samples[sub, 1] = v
                        samples[sub, 2] = previous_up
                        if y < 0 or y >= H-1:
                            safe = False
                            break
                        if x < 0 or x > W - 1:
                            safe = False
                            break
                        sy, sv = samples[sub, 0], samples[sub, 1]
                        xl, xh = int(math.floor(x)), int(math.ceil(x))
                        yl, yh = int(math.floor(sy)), int(math.ceil(sy))
                        # Real floor rollbacks can leave residual speed after
                        # the candidate reaches zero. Keep blue bones forbidden
                        # during a full resting allowance, not only while moving.
                        moving = abs(sv) > 1e-8 or ux != 0 or settled_frames < blue_rest_frames
                        if operator:
                            shift = ((xh - xl) + 2 * (yh - yl)) * 4
                            local_margin = (int(white_clearance[frame, yl, xl]) >> shift) & 15
                            if has_blue and moving:
                                local_margin = min(local_margin, (int(blue_clearance[frame, yl, xl]) >> shift) & 15)
                            margin = min(margin, local_margin)
                            if local_margin == 0:
                                safe = False
                                break
                            continue
                        margin = min(margin, int(white_clearance[frame, yl, xl]),
                            int(white_clearance[frame, yl, xh]), int(white_clearance[frame, yh, xl]),
                            int(white_clearance[frame, yh, xh]))
                        if has_blue and moving:
                            margin = min(margin, int(blue_clearance[frame, yl, xl]),
                                int(blue_clearance[frame, yl, xh]), int(blue_clearance[frame, yh, xl]),
                                int(blue_clearance[frame, yh, xh]))
                        if (hazards[frame, yl, xl] or hazards[frame, yl, xh] or
                            hazards[frame, yh, xl] or hazards[frame, yh, xh]):
                            safe = False
                            break
                        if has_blue and moving and (blues[frame, yl, xl] or blues[frame, yl, xh] or
                            blues[frame, yh, xl] or blues[frame, yh, xh]):
                            safe = False
                            break
                    next_settled = min(settle_cap, settled_frames + 1) if settled else 0
                    if not safe:
                        continue
                    # 12 x bits, 14 y bits, 14 velocity bits, 6 mode bits.
                    qx = int(round(x * 10.0))
                    qy = int(round(y * 100.0))
                    qv = int(round(v * 10.0)) + 2048
                    key = np.int64(qx) | (np.int64(qy) << 12) | (np.int64(qv) << 26)
                    key |= np.int64(previous_up | ((ux + 1) << 1) | (next_settled << 3)) << 40
                    new_cost = costs[i] + (8192 if ux or up else 0) + abs(ux) + up
                    # Maximise the route's weakest clearance before minimising
                    # input time. One lost margin pixel outweighs all inputs.
                    new_cost += (int(states[frame, i, 6]) - margin) * margin_weight
                    # A preallocated open-addressed table avoids per-frame
                    # dictionary allocation and boxing in the native kernel.
                    hashed = np.uint64(key)
                    hashed ^= hashed >> np.uint64(30)
                    hashed *= np.uint64(0xbf58476d1ce4e5b9)
                    hashed ^= hashed >> np.uint64(27)
                    hashed *= np.uint64(0x94d049bb133111eb)
                    hashed ^= hashed >> np.uint64(31)
                    slot = np.int64(hashed & table_mask)
                    while ((table_epochs[slot] == frame + 1 if operator == 2 else table_keys[slot] != -1)
                           and table_keys[slot] != key):
                        slot = (slot + 1) & (table_size - 1)
                    occupied = table_epochs[slot] == frame + 1 if operator == 2 else table_keys[slot] != -1
                    old = table_values[slot] if occupied else -1
                    if old >= 0 and candidate_costs[old] <= new_cost:
                        continue
                    if old < 0:
                        old = candidates
                        table_keys[slot] = key
                        table_epochs[slot] = frame + 1
                        table_values[slot] = old
                        candidates += 1
                    candidate_states[old, 0] = x
                    candidate_states[old, 1] = y
                    candidate_states[old, 2] = v
                    candidate_states[old, 3] = previous_up
                    candidate_states[old, 4] = ux
                    candidate_states[old, 5] = next_settled
                    candidate_states[old, 6] = margin
                    candidate_costs[old] = new_cost
                    candidate_parents[old] = i
                    candidate_moves[old, 0] = ux
                    candidate_moves[old, 1] = up
        if candidates == 0:
            return states, parents, moves, history, frame + 1, 0
        if candidates <= max_states:
            chosen = np.arange(candidates)
        else:
            band_seen[:] = 0
            band_kept[:] = 0
            band_count = 0
            for j in range(candidates):
                band = int(round((candidate_states[j, 0] - x0) / 3.0)) + W // 2
                if phase_diversity:
                    y, v = candidate_states[j, 1], candidate_states[j, 2]
                    phase = 0 if y < .2 and abs(v) < 1e-8 else (1 if v < 0 else 2)
                    x_band = int(round((candidate_states[j, 0] - x0) / 24.0)) + W // 2
                    band = (x_band * height_bands + int(y // 4)) * 3 + phase
                candidate_bands[j] = band
                if not band_seen[band]:
                    band_seen[band] = 1
                    band_order[band_count] = band
                    band_count += 1
            quota = max(1, max_states // band_count)
            if operator == 2:
                chosen = _band_select(candidate_costs[:candidates], candidate_bands,
                                      band_order, band_count, band_slots, max_states)
            else:
                ordered = np.argsort(candidate_costs[:candidates], kind='mergesort')
                chosen = np.empty(max_states, np.int64)
                kept = 0
                # Global cost order is enough for each band's cheapest quota.
                for pos in range(candidates):
                    j = ordered[pos]
                    band = candidate_bands[j]
                    if band_kept[band] < quota and kept < max_states:
                        chosen[kept] = j
                        kept += 1
                        band_kept[band] += 1
                chosen = chosen[:kept]
        count = len(chosen)
        for k in range(count):
            j = chosen[k]
            states[frame + 1, k] = candidate_states[j]
            parents[frame + 1, k] = candidate_parents[j]
            moves[frame + 1, k] = candidate_moves[j]
            costs[k] = candidate_costs[j]
        history[frame + 1] = count
    best = 0
    for i in range(1, count):
        if costs[i] < costs[best]:
            best = i
    return states, parents, moves, history, 0, best


def solve_source_compiled(bake, max_states=512, landing_wait_frames=4,
                          spatial_margin=2, timing_margin_frames=2, phase_diversity=False, initial_vy=0., operator="baseline"):
    started = time.perf_counter()
    if operator not in ("baseline", "a", "b"):
        raise ValueError("operator must be baseline, a or b")
    if max_states < 1 or landing_wait_frames < 0 or landing_wait_frames > 7:
        raise ValueError("max_states must be positive and landing_wait_frames in 0..7 (packed key)")
    # Late game ticks can skip one or two scheduled input frames. Reject
    # routes near the corresponding time/position uncertainty boundaries.
    raw_hazard = bake.B_hazard
    guarded = raw_hazard.copy()
    for offset in range(1, timing_margin_frames + 1):
        guarded[:-offset] |= raw_hazard[offset:]
        guarded[offset:] |= raw_hazard[:-offset]
    if spatial_margin:
        horizontal = guarded.copy()
        for offset in range(1, spatial_margin + 1):
            horizontal[:, :, :-offset] |= guarded[:, :, offset:]
            horizontal[:, :, offset:] |= guarded[:, :, :-offset]
        guarded = horizontal.copy()
        for offset in range(1, spatial_margin + 1):
            guarded[:, :-offset] |= horizontal[:, offset:]
            guarded[:, offset:] |= horizontal[:, :-offset]
    hazards = np.ascontiguousarray(guarded[:-1] | guarded[1:])
    raw = (bake.metadata or {}).get('B_blue')
    has_blue = raw is not None
    if has_blue:
        blue = raw.copy()
        blue[:-1] |= raw[1:]
        blue[:-2] |= raw[2:]
        blue[1:] |= raw[:-1]
        blues = np.ascontiguousarray(blue[:-1] | blue[1:])
    else:
        blues = np.zeros((1, 1, 1), dtype=np.bool_)
    platform_count = max((len(p) for p in bake.platform_table), default=0)
    platform_array = np.zeros((bake.T, platform_count, 4), np.float64)
    for frame, items in enumerate(bake.platform_table):
        for i, p in enumerate(items):
            # Source snaps the 16px heart to Platform1.BBoxTop - 8.05.
            platform_array[frame, i] = (p.x_left, p.x_right, p.y_surf + 8.05, p.vx * 60)
    if operator == "baseline":
        white_clearance, blue_clearance = _clearance(hazards), _clearance(blues)
    else:
        previous_threads = get_num_threads()
        try:
            set_num_threads(min(8, previous_threads))
            white_clearance = _clearance_anchors(hazards)
            blue_clearance = _clearance_anchors(blues)
        finally:
            set_num_threads(previous_threads)
    prepared = time.perf_counter()
    states, parents, moves, history, deadlock, best = _search(
        hazards, blues, white_clearance, blue_clearance, has_blue,
        float(bake.initial_state[0]), max_states, landing_wait_frames, phase_diversity,
        platform_array, float(bake.initial_state[1]) if platform_array.shape[1] else .05, float(initial_vy),
        {"baseline": 0, "a": 1, "b": 2}[operator])
    searched = time.perf_counter()
    actions, trajectory = [], []
    if not deadlock:
        for frame in range(bake.T - 1, -1, -1):
            s = states[frame, best]
            trajectory.append((s[0], s[1], s[2] * 40 / 60, int(s[1] < 1), int(s[3])))
            if frame:
                actions.append(tuple(int(v) for v in moves[frame, best]))
                best = int(parents[frame, best])
        actions.reverse()
        trajectory.reverse()
    elapsed = (time.perf_counter() - started) * 1000
    stats = SolveStats(bake_time_ms=0, dp_solve_time_ms=elapsed, total_time_ms=elapsed,
        peak_alive_states=int(history.max()), alive_states_history=history[history > 0].tolist(),
        total_states_explored=int(history.sum()), peak_memory_mb=states.nbytes / 1048576)
    stats.operator_prepare_ms = (prepared - started) * 1000
    stats.operator_search_ms = (searched - prepared) * 1000
    stats.operator_reconstruct_ms = (time.perf_counter() - searched) * 1000
    return SolveResult(is_deadlock=bool(deadlock), deadlock_frame=int(deadlock) if deadlock else None,
        action_sequence=None if deadlock else actions, trajectory=None if deadlock else trajectory, stats=stats)


@njit(cache=True)
def _anchor_clearance(distance):
    """Pack single, horizontal, vertical and quad minima into four nibbles."""
    T, H, W = distance.shape
    result = np.empty((T, H, W), np.uint16)
    for t in range(T):
        for y in range(H):
            yy = min(y + 1, H - 1)
            for x in range(W):
                xx = min(x + 1, W - 1)
                a = int(distance[t, y, x])
                h = min(a, int(distance[t, y, xx]))
                v = min(a, int(distance[t, yy, x]))
                q = min(h, v, int(distance[t, yy, xx]))
                result[t, y, x] = a | (h << 4) | (v << 8) | (q << 12)
    return result


@njit(cache=True, parallel=True)
def _clearance_anchors(hazards):
    """Frames are independent; each worker owns its distance scratch buffer."""
    T, H, W = hazards.shape
    result = np.empty((T, H, W), np.uint16)
    for t in prange(T):
        distance = _clearance(hazards[t:t+1])
        result[t] = _anchor_clearance(distance)[0]
    return result
