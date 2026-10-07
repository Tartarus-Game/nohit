"""Candidate generator for a fixed-x blue-heart round using BTS event order.

This is intentionally a narrow calibration path for bonegap1, not an assertion
of general solvability or global optimality. Only real-game HP accepts a route.
"""
from __future__ import annotations

import math
import time

import numpy as np

from nohit.common.types import SolveResult, SolveStats


def source_tick(y, down_speed, previous_up, up, dt=1 / 240):
    # CustomMovement.tick runs BEFORE the movement event sheet. A solid
    # vertical step is rolled back, rather than snapped to a mathematical floor.
    displacement = down_speed * dt
    steps = max(1, math.floor(abs(displacement) + 0.5))
    start = y
    for sub in range(1, steps + 1):
        new_y = start - displacement * sub / steps
        if new_y <= 0:
            y = start - displacement * (sub - 1) / steps
            down_speed = 0.0
            break
        y = new_y

    # Battle.xml HeartJump: rising VPad edge AND HeartCheckSolid(0,1).
    if up and not previous_up and y < 1.0:
        down_speed -= 180.0
    # Release cutoff is an EDGE, not a level condition.
    if previous_up and not up and down_speed < -30.0:
        down_speed = -30.0
    # Gravity is a non-static local, initialized on each event-sheet scope.
    if 15.0 < down_speed < 240.0:
        gravity = 540.0
    elif -30.0 < down_speed <= 15.0:
        gravity = 180.0
    elif -120.0 < down_speed <= -30.0:
        gravity = 450.0
    elif down_speed <= -120.0:
        gravity = 180.0
    else:
        gravity = 0.0
    # HeartCheckSolid(0,0.2) gates gravity while resting on the floor.
    if y >= 0.2:
        down_speed = min(750.0, down_speed + gravity * dt)
    return y, down_speed, up


def solve_source_vertical(bake, max_states=6000):
    """Minimize held-input frames among retained fixed-x candidate states.

    State merging and the frontier cap mean this is not an exact optimality
    certificate. Each transition uses four real-engine-order microticks.
    """
    started = time.perf_counter()
    x = int(bake.initial_state[0])
    B = bake.B_hazard
    blue = (bake.metadata or {}).get("B_blue")
    if blue is not None:
        # Real-game traces showed up to ~70ms of residual falling speed after
        # the first floor rollback. Require settling BEFORE the blue bone,
        # with 33ms lookahead in addition to the two-frame interval checks.
        source_blue = blue
        blue = np.zeros_like(source_blue)
        for offset in range(-1, 3):
            if offset < 0:
                blue[-offset:] |= source_blue[:offset]
            elif offset > 0:
                blue[:-offset] |= source_blue[offset:]
            else:
                blue |= source_blue
    # Zone resizing pauses the timeline while the real heart settles. The
    # first acceptance tick measures a resting heart, ~0.02px above the floor.
    frontier = {(0.0, 0.0, 0): ((0, 0), (0.05, 0.0, 0), None)}
    history = [1]
    peak = total = 1
    final = None
    for frame in range(bake.T - 1):
        children = {}
        for cost, state, parent in frontier.values():
            for up in (0, 1):
                current = state
                safe = True
                for _ in range(4):
                    current = source_tick(*current, up)
                    y = current[0]
                    if y < 0 or y >= bake.H - 1:
                        safe = False
                        break
                    lo, hi = math.floor(y), math.ceil(y)
                    # Cover the entire interval, not merely its endpoint.
                    if B[frame, lo, x] or B[frame, hi, x] or B[frame + 1, lo, x] or B[frame + 1, hi, x]:
                        safe = False
                        break
                    if blue is not None and abs(current[1]) > 1e-8:
                        if blue[frame, lo, x] or blue[frame, hi, x] or blue[frame + 1, lo, x] or blue[frame + 1, hi, x]:
                            safe = False
                            break
                if not safe:
                    continue
                next_cost = (cost[0] + up, cost[1] + (up != state[2]))
                key = (round(current[0], 2), round(current[1], 1), current[2])
                old = children.get(key)
                if old is None or next_cost < old[0]:
                    node = (parent, up, current)
                    children[key] = (next_cost, current, node)
        if not children:
            final = None
            break
        if len(children) > max_states:
            kept = sorted(children.items(), key=lambda item: item[1][0])[:max_states]
            children = dict(kept)
        frontier = children
        history.append(len(frontier))
        peak = max(peak, len(frontier))
        total += len(frontier)
        final = min(frontier.values(), key=lambda value: value[0])
    elapsed = (time.perf_counter() - started) * 1000
    stats = SolveStats(bake_time_ms=0, dp_solve_time_ms=elapsed, total_time_ms=elapsed,
                      peak_alive_states=peak, alive_states_history=history,
                      total_states_explored=total, peak_memory_mb=0)
    if final is None:
        return SolveResult(is_deadlock=True, deadlock_frame=len(history),
                           action_sequence=None, trajectory=None, stats=stats)
    nodes = []
    node = final[2]
    while node:
        nodes.append(node)
        node = node[0]
    nodes.reverse()
    actions = [(0, node[1]) for node in nodes]
    trajectory = [(x, 0.05, 0, 1, 0)]
    trajectory += [(x, node[2][0], node[2][1] * 40 / 60,
                    int(node[2][0] < 1), node[2][2]) for node in nodes]
    return SolveResult(is_deadlock=False, deadlock_frame=None, action_sequence=actions,
                       trajectory=trajectory, stats=stats)
