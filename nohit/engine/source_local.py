"""Horizontal/vertical candidate search using BTS-order microticks.

Used for Blue Bone when a fixed-x route cannot provide a settling allowance.
Beam/state merging makes this a candidate generator, not an optimality proof.
"""
import math
import time
from functools import lru_cache
import numpy as np
from nohit.common.types import SolveResult, SolveStats
from nohit.engine.source_vertical import source_tick


def solve_source_local(bake, max_states=3600, radius=None, landing_wait_frames=4):
    start = time.perf_counter()
    x0 = float(bake.initial_state[0])
    B = bake.B_hazard
    raw_blue = (bake.metadata or {}).get('B_blue')
    blue = None
    if raw_blue is not None:
        blue = raw_blue.copy()
        blue[:-1] |= raw_blue[1:]
        blue[:-2] |= raw_blue[2:]
        blue[1:] |= raw_blue[:-1]
    # The heart is already resting before the attack starts. Subsequent jumps
    # require whole plan frames at rest, not merely a successful floor probe.
    initial = (x0, .05, 0., 0, 0, landing_wait_frames)
    frontier = {initial: ((0, 0), initial, None)}
    history = [1]
    peak = total = 1
    last = None
    actions = [(0,0),(0,1),(-1,0),(1,0),(-1,1),(1,1)]
    @lru_cache(maxsize=65536)
    def vertical_interval(y, v, previous_up, up):
        # Horizontal alternatives share the same vertical transition. Cache
        # exact float inputs; this does not coarsen physics or prune routes.
        settled = not up and y < .2 and abs(v) < 1e-8
        samples = []
        for _ in range(4):
            y, v, previous_up = source_tick(y, v, previous_up, up)
            settled = settled and y < .2 and abs(v) < 1e-8
            samples.append((y, v, previous_up))
        return tuple(samples), settled
    for frame in range(bake.T - 1):
        # The interval endpoints are identical for every candidate this frame.
        hazard_interval = B[frame] | B[frame+1]
        blue_interval = None if blue is None else blue[frame] | blue[frame+1]
        children = {}
        for cost, state, parent in frontier.values():
            for ux, up in actions:
                x, y, v, previous_up, previous_ux, settled_frames = state
                if up and not previous_up and settled_frames < landing_wait_frames:
                    continue
                safe = True
                samples, settled_interval = vertical_interval(y, v, previous_up, up)
                for y, v, previous_up in samples:
                    x += previous_ux * 150 / 240
                    if x < 0 or x > bake.W-1 or (radius is not None and abs(x-x0) > radius):
                        safe = False
                        break
                    previous_ux = ux
                    if y < 0 or y >= bake.H-1:
                        safe = False
                        break
                    xl, xh, yl, yh = math.floor(x), math.ceil(x), math.floor(y), math.ceil(y)
                    moving = abs(v) > 1e-8 or ux != 0
                    # All surrounding anchors and both ends of the interval.
                    for xx in (xl,xh):
                        for yy in (yl,yh):
                            if hazard_interval[yy,xx] or (
                                moving and blue_interval is not None and blue_interval[yy,xx]):
                                safe = False
                                break
                        if not safe:
                            break
                    if not safe:
                        break
                if not safe:
                    continue
                settled_frames = min(landing_wait_frames, settled_frames+1) if settled_interval else 0
                current = (x,y,v,previous_up,previous_ux,settled_frames)
                new_cost = (cost[0] + int(bool(ux or up)), cost[1] + abs(ux)+up)
                key = (round(x,1),round(y,2),round(v,1),previous_up,previous_ux,settled_frames)
                old = children.get(key)
                if old is None or new_cost < old[0]:
                    children[key] = (new_cost,current,(parent,(ux,up),current))
        if not children:
            last = None
            break
        if len(children)>max_states:
            # Preserve alternative arrival phases across x. A global cheap-
            # input beam discarded every sidestep before its benefit arrived.
            bands = {}
            for key, value in children.items():
                band = round((value[1][0]-x0)/3)
                bands.setdefault(band, []).append((key,value))
            quota = max(1,max_states//len(bands))
            children = {}
            for band in bands.values():
                children.update(sorted(band,key=lambda item:item[1][0])[:quota])
        frontier = children
        history.append(len(frontier))
        peak = max(peak,len(frontier)); total += len(frontier)
        last = min(frontier.values(),key=lambda value:value[0])
    elapsed = (time.perf_counter()-start)*1000
    stats = SolveStats(bake_time_ms=0,dp_solve_time_ms=elapsed,total_time_ms=elapsed,
        peak_alive_states=peak,alive_states_history=history,total_states_explored=total,peak_memory_mb=0)
    if last is None:
        return SolveResult(is_deadlock=True,deadlock_frame=len(history),action_sequence=None,trajectory=None,stats=stats)
    nodes=[]; node=last[2]
    while node:
        nodes.append(node); node=node[0]
    nodes.reverse()
    trajectory=[(x0,.05,0,1,0)]
    trajectory += [(n[2][0],n[2][1],n[2][2]*40/60,int(n[2][1]<1),n[2][3]) for n in nodes]
    return SolveResult(is_deadlock=False,deadlock_frame=None,action_sequence=[n[1] for n in nodes],trajectory=trajectory,stats=stats)
