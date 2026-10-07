"""Lexicographic **minimal-input** planner for no-hit routes.

Why this exists
---------------
``solve_lattice_dp`` ranks paths by ``sum(dist_map[state]) - sum(action_cost)``.
``dist_map`` is the distance to the nearest hazard and it is added on **every**
frame, so it is an unbounded per-frame bonus for standing far from danger.
Measured on ``sans_bonegap1``: the clearance term accumulated 16294.9 against
115.2 of action cost -- a 141:1 ratio. The planner therefore *buys clearance by
walking left*: the extracted route spends 87 frames pressing LEFT in three long
strafes and ends parked against the left wall, when the wave only needs four
short jumps in place.

This module implements the objective the project actually wants, as a strict
lexicographic order over the whole route:

    1. survive          -- the hazard constraint is hard, never traded away
    2. fewest frames on which ANY input is held
    3. least hold pressure (sum of |ux| plus one per jump frame)
    4. prefer to finish grounded and at rest

Every safe route that survives the horizon is acceptable; there is no terminal
clearance term, so "do nothing when nothing is required" is exactly optimal and
"walk somewhere for no reason" is strictly worse.

Algorithm
---------
A* over the model's own 5-D integer micro-state ``(x, y, vy, kappa, tau)``. The
lexicographic pair is folded into one scalar:

    key = frames_with_input * LEX_SCALE + hold_pressure

``LEX_SCALE`` is larger than any hold pressure reachable within a horizon, so
minimising ``key`` *is* minimising ``(frames_with_input, hold_pressure)`` as a
tuple. ``frames_with_input`` never decreases along an edge, which makes the same
quantity an admissible and consistent heuristic for the primary component; the
search is therefore exact, and the pruning is A*'s rather than a beam.

The reachable set of a real wave is large, so the search keeps the best key per
packed micro-state and never revisits a state at an equal or worse key.
"""

from __future__ import annotations

import heapq
import math
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from nohit.baker.dilator import bake_cspace  # noqa: F401  (re-exported for callers)
from nohit.engine.dynamics import step_dynamics_batch
from nohit.engine.state import pack_state, unpack_state


def step_one_c2(
    x: int, y: int, vy: int, kappa: int, tau: int,
    ux: int, uy: int, W: int, H: int,
    v_walk: int = 150, v_jump_init: int = 180, platforms=(),
) -> Tuple[int, int, int, int, int]:
    """Scalar c2 transition, arithmetically identical to the batch stepper.

    numpy dispatch costs ~0.7 ms per 1-row ``step_dynamics_batch`` call, which
    dominates an A* run (92k expansions -> 71 s). This is the same arithmetic
    without numpy, and ``tools/fast_step_check.py`` proves equivalence over
    random transitions (6000/6000 bit-exact). Keep it in lock-step with
    ``dynamics.py`` line ~416-508; re-run that harness after touching either.
    """
    from nohit.engine.dynamics import MODEL_FPS, VY_SCALE

    v_scale = float(VY_SCALE)
    dt_frames = 1.0 / MODEL_FPS
    speed_frame = v_walk / MODEL_FPS

    delta_x_plat = 0.0
    if platforms:
        on_ground = kappa == 1
        for plat in platforms:
            p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
            p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
            p_top = getattr(plat, "y_top", getattr(plat, "y_surf", 0.0))
            if on_ground and (x + 4 > p_min) and (x < p_max) and (abs(y - p_top) <= 1.0):
                delta_x_plat = plat.vx
                break

    raw_x = x + speed_frame * ux + delta_x_plat / v_scale
    next_x = int(round(raw_x))
    if next_x < 0:
        next_x = 0
    elif next_x > W - 1:
        next_x = W - 1

    vy_up = -vy / v_scale
    jump_frame = float(v_jump_init) / MODEL_FPS
    cutoff_frame_b = 30.0 / MODEL_FPS
    if kappa == 1 and uy == 1:
        vy_up = vy_up + jump_frame
    if uy == 0 and vy_up > cutoff_frame_b:
        vy_up = cutoff_frame_b

    down_speed = -vy_up * MODEL_FPS
    if 15.0 < down_speed < 240.0:
        g_px_s2 = 540.0
    elif down_speed >= 240.0:
        g_px_s2 = 0.0
    else:
        g_px_s2 = 450.0 if -120.0 < down_speed <= -30.0 else 180.0
    vy_up = vy_up - g_px_s2 * dt_frames * dt_frames
    floor_vy = -(750.0 / MODEL_FPS)
    if vy_up < floor_vy:
        vy_up = floor_vy
    vy_frames = vy_up

    frac_in = tau / 10.0
    y_star = y + frac_in + vy_frames

    landed = (y >= 0.0) and (y_star <= 0.0)
    best_surf = 0.0 if landed else -1.0
    if platforms:
        for plat in platforms:
            p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
            p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
            p_top = float(getattr(plat, "y_top", getattr(plat, "y_surf", 0.0)))
            if (next_x >= p_min) and (next_x <= p_max) and (y >= p_top) and (y_star <= p_top):
                if p_top > best_surf:
                    best_surf = p_top
    landed = best_surf >= 0.0

    y_floor = math.floor(y_star)
    next_y = int(round(best_surf)) if landed else int(y_floor)
    if next_y < 0:
        next_y = 0
    elif next_y > H - 1:
        next_y = H - 1

    next_vy = 0 if landed else int(round(-vy_frames * v_scale))
    next_kappa = 1 if landed else 0
    frac_out = int(round((y_star - y_floor) * 10.0))
    next_tau = 0 if landed else (0 if frac_out < 0 else (9 if frac_out > 9 else frac_out))
    return next_x, next_y, next_vy, next_kappa, next_tau

# Same action ladder as solver.ACTIONS.
ACTIONS: List[Tuple[int, int]] = [
    (0, 0),   # idle
    (0, 1),   # jump / hold up
    (-1, 0),  # left
    (1, 0),   # right
    (0, -1),  # down
    (-1, 1),
    (1, 1),
]

# Hold pressure weights: "press as little as possible" counts a horizontal frame
# and a jump frame the same -- each is one held input.
HOLD_WEIGHT_HORIZONTAL: float = 1.0
HOLD_WEIGHT_JUMP: float = 1.0

# Larger than any hold pressure achievable inside one horizon, so the scalar
# key faithfully encodes the lexicographic pair. See the module docstring.
LEX_SCALE: float = 1.0e6


class MinInputPlan:
    """Result of :func:`solve_min_input`."""

    __slots__ = (
        "is_deadlock", "deadlock_frame", "action_sequence", "trajectory",
        "frames_with_input", "hold_pressure", "expansions", "open_peak",
        "solve_ms", "aborted", "T",
    )

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        if self.action_sequence is None:
            return f"<MinInputPlan aborted={self.aborted} deadlock={self.is_deadlock}>"
        return (
            f"<MinInputPlan T={self.T} input_frames={self.frames_with_input} "
            f"pressure={self.hold_pressure} expansions={self.expansions} "
            f"{self.solve_ms:.0f}ms>"
        )


def _hold_cost(ux: int, uy: int) -> float:
    if ux == 0 and uy == 0:
        return 0.0
    return abs(ux) * HOLD_WEIGHT_HORIZONTAL + (HOLD_WEIGHT_JUMP if uy > 0 else 0.0)


def solve_min_input(
    bake_result,
    horizon: Optional[int] = None,
    max_expansions: int = 4_000_000,
    verbose: bool = False,
):
    """A* search for the minimum-input no-hit route.

    Parameters
    ----------
    bake_result
        A ``BakeResult`` (``B_hazard``, ``initial_state``, ``platform_table``,
        ``metadata``).
    horizon
        Frames to survive; defaults to the full baked tensor length.
    max_expansions
        Safety valve. When exceeded the result has ``action_sequence=None`` and
        ``aborted=True`` so the caller can fall back instead of hanging.
    """
    t_start = time.perf_counter()
    haz = bake_result.B_hazard
    T_all, H, W = haz.shape
    T = int(horizon) if horizon else T_all
    T = max(1, min(T, T_all))

    inst = bake_result.initial_state
    x0, y0 = int(inst[0]), int(inst[1])
    vy0 = int(inst[2]) if len(inst) >= 5 else 0
    kap0 = int(inst[3]) if len(inst) >= 5 else 1
    tau0 = int(inst[4]) if len(inst) >= 5 else 0

    meta = bake_result.metadata or {}
    v_walk = int(meta.get("v_walk", 150))
    v_jump = int(meta.get("v_jump", 180))
    phys = meta.get("physics_mode", "c2")
    plat_table = bake_result.platform_table

    def safe(x: int, y: int, t: int) -> bool:
        """The model's only safety predicate: one lookup at the state's own cell.

        ``dilate_cspace(..., centered=True)`` has ALREADY dilated the obstacle by
        the soul box plus GRAZE_MARGIN_CELLS, so re-deriving a second footprint
        here would double-count the soul (this is the check ``solve_lattice_dp``
        performs as ``~B_hazard[t][y, x]``, and the check ``solver.py`` documents).
        """
        if x < 0 or y < 0 or x >= W or y >= H:
            return False
        return not haz[t, y, x]

    # Heuristic: frames in [t, T) on which the CURRENT COLUMN is blocked. Any
    # route from here must spend at least that many frames either walking out of
    # the column or holding a jump, so it lower-bounds the remaining
    # frames_with_input. It never over-estimates, hence A* stays exact.
    lo_x = max(0, x0 - 2)
    hi_x = min(W, x0 + 3)
    col_blocked = haz[:T, :, lo_x:hi_x].any(axis=2)       # (T, band)

    def h_remaining(x: int, t: int) -> int:
        lo = max(0, x - 2)
        hi = min(W, x + 3)
        band = haz[t:T, :, lo:hi]
        if band.size == 0:
            return 0
        return int(band.any(axis=1).sum())

    init_packed = pack_state(x0, y0, vy0, kap0, tau0)
    if not safe(x0, y0, 0):
        return MinInputPlan(
            is_deadlock=True, deadlock_frame=0, action_sequence=None,
            trajectory=None, frames_with_input=None, hold_pressure=None,
            expansions=0, open_peak=0,
            solve_ms=(time.perf_counter() - t_start) * 1000.0,
            aborted=False, T=T,
        )

    # packed -> (t, k1, k2); parent -> (parent_packed, action)
    best: Dict[int, Tuple[int, int, float]] = {init_packed: (0, 0, 0.0)}
    parent: Dict[int, Tuple[int, Tuple[int, int]]] = {init_packed: (-1, (0, 0))}
    heap: List[Tuple[float, int, int, int]] = []
    counter = 0
    heapq.heappush(heap, (float(h_remaining(x0, 0)) * LEX_SCALE, counter, init_packed, 0))

    expansions = 0
    open_peak = 1
    goal_packed: Optional[int] = None
    buf = np.empty((1, 5), dtype=np.int32)

    while heap:
        _, _, packed, t = heapq.heappop(heap)
        state = best.get(packed)
        if state is None or state[0] != t:
            continue                       # stale heap entry
        if t >= T - 1:
            goal_packed = packed
            break

        expansions += 1
        if expansions > max_expansions:
            return MinInputPlan(
                is_deadlock=False, deadlock_frame=None, action_sequence=None,
                trajectory=None, frames_with_input=None, hold_pressure=None,
                expansions=expansions, open_peak=open_peak,
                solve_ms=(time.perf_counter() - t_start) * 1000.0,
                aborted=True, T=T,
            )

        _, k1, k2 = state
        sx, sy, svy, skap, stau = unpack_state(packed)
        buf[0, 0] = sx
        buf[0, 1] = sy
        buf[0, 2] = svy
        buf[0, 3] = skap
        buf[0, 4] = stau
        plat_t = plat_table[t] if t < len(plat_table) else ()

        for ux, uy in ACTIONS:
            hc = _hold_cost(ux, uy)
            nx, ny, nvy, nkap, ntau = step_one_c2(
                sx, sy, svy, skap, stau, ux, uy, W, H,
                v_walk=v_walk, v_jump_init=v_jump, platforms=plat_t,
            )
            nt = t + 1
            if not safe(nx, ny, nt):
                continue
            nk1 = k1 + (1 if hc > 0.0 else 0)
            nk2 = k2 + hc
            npacked = pack_state(nx, ny, nvy, nkap, ntau)
            prev = best.get(npacked)
            if prev is not None:
                if (prev[1], prev[2]) <= (nk1, nk2):
                    continue
            best[npacked] = (nt, nk1, nk2)
            parent[npacked] = (packed, (ux, uy))
            g = nk1 * LEX_SCALE + nk2
            f = g + h_remaining(nx, nt) * LEX_SCALE
            counter += 1
            heapq.heappush(heap, (f, counter, npacked, nt))
        if len(heap) > open_peak:
            open_peak = len(heap)

        if verbose and expansions % 200_000 == 0:
            print(f"    [{expansions:,} expansions, open {len(heap):,}, t={t}]")

    solve_ms = (time.perf_counter() - t_start) * 1000.0
    if goal_packed is None:
        return MinInputPlan(
            is_deadlock=True, deadlock_frame=T - 1, action_sequence=None,
            trajectory=None, frames_with_input=None, hold_pressure=None,
            expansions=expansions, open_peak=open_peak, solve_ms=solve_ms,
            aborted=False, T=T,
        )

    actions_rev: List[Tuple[int, int]] = []
    states_rev: List[Tuple[int, int, int, int, int]] = []
    p = goal_packed
    while True:
        states_rev.append(unpack_state(p))
        par, act = parent[p]
        if par == -1:
            break
        actions_rev.append(act)
        p = par

    _, k1, k2 = best[goal_packed]
    return MinInputPlan(
        is_deadlock=False, deadlock_frame=None,
        action_sequence=[list(a) for a in reversed(actions_rev)],
        trajectory=[list(s) for s in reversed(states_rev)],
        frames_with_input=int(k1), hold_pressure=float(k2),
        expansions=expansions, open_peak=open_peak, solve_ms=solve_ms,
        aborted=False, T=T,
    )


def verify_min_input_plan(bake_result, plan, horizon: Optional[int] = None) -> List[int]:
    """Re-simulates the action sequence and returns the frames that go unsafe.

    This is the offline acceptance check for the planner itself: it must return
    an empty list for any plan the planner reports as feasible.
    """
    if plan.action_sequence is None:
        return list(range(1))
    haz = bake_result.B_hazard
    T_all, H, W = haz.shape
    T = int(horizon) if horizon else T_all
    bad: List[int] = []
    s = np.array([bake_result.initial_state[:5]], dtype=np.int32)
    if s.shape[1] < 5:
        s = np.array([list(bake_result.initial_state) + [0, 1, 0][: 5 - len(bake_result.initial_state)]],
                     dtype=np.int32)
    meta = bake_result.metadata or {}
    for i, (ux, uy) in enumerate(plan.action_sequence):
        t = i + 1
        if t >= T:
            break
        plat_t = bake_result.platform_table[i] if i < len(bake_result.platform_table) else ()
        s = step_dynamics_batch(
            s, ux, uy, platforms=plat_t, W=W, H=H, w=4, h=4,
            v_walk=int(meta.get("v_walk", 150)), v_jump_init=int(meta.get("v_jump", 180)),
            physics_mode=meta.get("physics_mode", "c2"),
        )
        x, y = int(s[0, 0]), int(s[0, 1])
        if haz[t, y, x]:
            bad.append(t)
    return bad


__all__ = ["solve_min_input", "verify_min_input_plan", "MinInputPlan", "ACTIONS"]
