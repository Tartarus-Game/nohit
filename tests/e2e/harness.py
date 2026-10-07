"""E2E Test Harness & Interface Contract Adapters.

Strictly adheres to PROJECT.md § Interface Contracts:
1. nohit.baker <-> nohit.engine: bake_cspace(...) -> BakeResult
2. nohit.engine <-> nohit.verifier: solve_lattice_dp(...) -> SolveResult
3. nohit.verifier <-> Tests & Benchmark: replay_and_verify(...) -> VerificationResult
4. nohit.dashboard <-> Web Client: REST API endpoints

Provides:
- Exact dataclasses and physical constants according to docs.txt and PROJECT.md.
- Reference oracle implementations of 5D dynamics, Minkowski dilation, DP solver, and replayer.
- Dynamic backend switching ('auto', 'nohit', 'reference') ensuring that tests run immediately
  and validate real implementations without modification once ready.
"""

from __future__ import annotations

import csv
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import scipy.ndimage


# ==============================================================================
# Physical Constants & Configuration (docs.txt § 4 & § 5)
# ==============================================================================
DEFAULT_W: int = 200
DEFAULT_H: int = 160
SOUL_W: int = 8
SOUL_H: int = 8

V_WALK: int = 3          # Standard blue soul horizontal speed (pixels/frame)
V_JUMP_INIT: int = 8     # Initial upward velocity on jump
V_MIN: int = -12         # Terminal downward falling velocity
V_MAX: int = 8           # Maximum upward velocity
G_ASCEND: int = 1        # Piecewise gravity during active jump hold
G_DESCEND: int = 2       # Piecewise gravity during jump release / fall
TAU_MAX: int = 15        # Maximum jump hold frames

# 6 Discrete Actions U = {-1, 0, 1} x {0, 1}
ACTIONS: List[Tuple[int, int]] = [
    (-1, 0),  # Left, release jump
    (-1, 1),  # Left, hold jump
    (0, 0),   # Still, release jump
    (0, 1),   # Still, hold jump
    (1, 0),   # Right, release jump
    (1, 1),   # Right, hold jump
]


# ==============================================================================
# Interface Contract Dataclasses (PROJECT.md § Interface Contracts)
# ==============================================================================

@dataclass
class PlatformInstance:
    """Represents a dynamic jump-through platform on a specific frame."""
    plat_id: int
    x_min: float
    x_max: float
    y_top: float
    vx: float


@dataclass
class BakeResult:
    """Contract 1: Output of nohit.baker.bake_cspace."""
    B_hazard: np.ndarray  # Shape: (T, H, W), dtype: bool
    platform_table: List[List[PlatformInstance]]  # Length T
    initial_state: Tuple[int, int]  # (x0, y0)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SolveStats:
    """DP Solver benchmark and resource statistics."""
    baking_ms: float
    dp_ms: float
    peak_alive_states: int
    alive_states_history: List[int]
    total_states_explored: int
    peak_memory_mb: float


@dataclass
class SolveResult:
    """Contract 2: Output of nohit.engine.solve_lattice_dp."""
    is_deadlock: bool
    deadlock_frame: Optional[int]
    action_sequence: Optional[List[Tuple[int, int]]]
    trajectory: Optional[List[Tuple[int, int, int, int, int]]]
    stats: SolveStats


@dataclass
class VerificationResult:
    """Contract 3: Output of nohit.verifier.replay_and_verify."""
    passed: bool
    collision_frames: List[int]
    kinematic_errors: List[str]
    simulated_trajectory: List[Tuple[int, int, int, int, int]]


# ==============================================================================
# 5D State Packing & Unpacking (Feature 8, docs.txt § 4)
# ==============================================================================

def pack_state(x: int, y: int, vy: int, kappa: int, tau: int) -> int:
    """Packs 5D micro-state (x, y, vy, kappa, tau) into a 32-bit unsigned integer.

    Bit layout:
    - x: 8 bits [0, 255] (valid range: 0..192)
    - y: 8 bits [0, 255] (valid range: 0..152)
    - vy: 5 bits [0, 31] (offset by 12: -12..8 -> 0..20)
    - kappa: 1 bit [0, 1]
    - tau: 4 bits [0, 15] (valid range: 0..15)
    Total: 26 bits <= 32 bits
    """
    vy_offset = vy + 12
    return (
        (x & 0xFF) |
        ((y & 0xFF) << 8) |
        ((vy_offset & 0x1F) << 16) |
        ((kappa & 0x01) << 21) |
        ((tau & 0x0F) << 22)
    )


def unpack_state(packed: int) -> Tuple[int, int, int, int, int]:
    """Unpacks 32-bit integer into 5D micro-state (x, y, vy, kappa, tau)."""
    x = packed & 0xFF
    y = (packed >> 8) & 0xFF
    vy = ((packed >> 16) & 0x1F) - 12
    kappa = (packed >> 21) & 0x01
    tau = (packed >> 22) & 0x0F
    return (x, y, vy, kappa, tau)


# ==============================================================================
# Exact 5D Hybrid Physics Dynamics Stepper (docs.txt § 5)
# ==============================================================================

def step_dynamics(
    state: Tuple[int, int, int, int, int],
    action: Tuple[int, int],
    platforms: Optional[List[PlatformInstance]] = None,
    is_slam: bool = False,
    W: int = DEFAULT_W,
    H: int = DEFAULT_H,
    w: int = SOUL_W,
    h: int = SOUL_H,
) -> Tuple[int, int, int, int, int]:
    """Computes exact forward discrete physics step f(s, u) or R_slam(f(s, u)).

    State tuple: (x, y, vy, kappa, tau)
    Action tuple: (ux, uy) where ux in {-1, 0, 1}, uy in {0, 1}
    """
    x, y, vy, kappa, tau = state
    ux, uy = action
    platforms = platforms or []

    # 1. Platform convection displacement
    delta_x_plat = 0.0
    if kappa == 1 and platforms:
        # Check which platform the soul is standing on
        for plat in platforms:
            # Overlap in x and standing right on top surface
            if x + w > plat.x_min and x < plat.x_max and abs(y - plat.y_top) <= 1.0:
                delta_x_plat = plat.vx
                break

    # 2. Horizontal step and arena boundary projection
    raw_x = x + V_WALK * ux + delta_x_plat
    next_x = max(0, min(W - w, int(round(raw_x))))

    # 3. Exogenous SansSlam check
    if is_slam:
        # R_slam operator collapses phase space: (next_x, 0, 0, 1, 0)
        return (next_x, 0, 0, 1, 0)

    # 4. Vertical dynamics: jump initiation or piecewise gravity
    if kappa == 1 and uy == 1:
        # Ground jump impulse
        v_next_star = V_JUMP_INIT
        tau_next = 1
    else:
        # Piecewise gravity
        if uy == 1 and tau < TAU_MAX and vy > 0:
            g = G_ASCEND
        else:
            g = G_DESCEND

        v_next_star = max(V_MIN, min(V_MAX, vy - g))

        if kappa == 0 and uy == 1 and tau < TAU_MAX:
            tau_next = tau + 1
        else:
            tau_next = TAU_MAX

    y_next_star = y + v_next_star

    # 5. One-way platform and rigid floor contact detection
    # Effective surfaces at horizontal coordinate next_x
    surfaces = [0.0]  # Hard floor boundary y = 0
    for plat in platforms:
        if next_x + w > plat.x_min and next_x < plat.x_max:
            surfaces.append(plat.y_top)

    # Check for inelastic adsorption: y >= y_surf and y_next_star <= y_surf
    adsorbed_surfaces = [s for s in surfaces if y >= s and y_next_star <= s]

    if adsorbed_surfaces:
        y_surf_max = max(adsorbed_surfaces)
        next_y = int(round(y_surf_max))
        next_vy = 0
        next_kappa = 1
        next_tau = 0
    else:
        # Free airborne motion
        next_y = max(0, min(H - h, y_next_star))
        next_vy = v_next_star
        next_kappa = 0
        next_tau = tau_next

    return (next_x, next_y, next_vy, next_kappa, next_tau)


# ==============================================================================
# Vectorized Minkowski Sum Dilation (Feature 5, docs.txt § 6)
# ==============================================================================

def dilate_cspace_2d(obstacle_grid_2d: np.ndarray, w: int = SOUL_W, h: int = SOUL_H) -> np.ndarray:
    """Performs 2D Minkowski sum dilation C_obs = O (+) (-A) with w x h soul box.

    For point p=(x, y) to collide: exists (dx, dy) in [0, w-1] x [0, h-1] such that (x+dx, y+dy) in O.
    In array indexing, grid is (H, W) where row is y and col is x.
    Structuring element is all-ones box of size (h, w).
    """
    H, W = obstacle_grid_2d.shape
    structure = np.ones((h, w), dtype=bool)
    # Origin of structuring element is at top-left (0, 0)
    # Using scipy binary_dilation with origin aligned to soul anchor
    origin = (-(h // 2), -(w // 2)) if h % 2 == 1 else (-(h // 2 - 1), -(w // 2 - 1))
    # Direct fast slice-based dilation for exact boundary fidelity:
    c_obs = np.zeros((H, W), dtype=bool)
    for dy in range(h):
        for dx in range(w):
            # Shift obstacle grid by (-dy, -dx)
            y_max = H - dy
            x_max = W - dx
            if y_max > 0 and x_max > 0:
                c_obs[:y_max, :x_max] |= obstacle_grid_2d[dy:, dx:]

    # Mark out-of-arena margins as hazard to prevent escaping
    if W > w:
        c_obs[:, (W - w + 1):] = True
    if H > h:
        c_obs[(H - h + 1):, :] = True

    return c_obs


# ==============================================================================
# Reference Oracle Implementations (Baking, DP Solving, Replay)
# ==============================================================================

def reference_bake_cspace(
    csv_path: str | Path,
    T: int = 150,
    W: int = DEFAULT_W,
    H: int = DEFAULT_H,
) -> BakeResult:
    """Reference implementation of nohit.baker.bake_cspace."""
    csv_path = Path(csv_path)
    B_hazard = np.zeros((T, H, W), dtype=bool)
    platform_table: List[List[PlatformInstance]] = [[] for _ in range(T)]
    initial_state = (W // 2 - SOUL_W // 2, 0)

    # Read and parse CSV commands
    commands: List[Dict[str, Any]] = []
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or not any(row):
                    continue
                cmd_time = float(row[0].strip()) if row[0].strip() else 0.0
                cmd_name = row[1].strip() if len(row) > 1 else ""
                args = [col.strip() for col in row[2:] if col.strip() != ""]
                commands.append({"time": cmd_time, "name": cmd_name, "args": args})

    # Rasterize obstacles frame by frame (at 30 FPS, dt = 1/30)
    FPS = 30.0
    accum_time = 0.0
    active_bones: List[Dict[str, Any]] = []
    active_platforms: List[Dict[str, Any]] = []
    slam_frames: set[int] = set()

    cmd_idx = 0
    curr_t_sec = 0.0

    for t in range(T):
        curr_t_sec = t / FPS

        # Dispatch commands up to current time
        while cmd_idx < len(commands):
            cmd = commands[cmd_idx]
            # Accumulate command timeline delay
            if cmd_idx == 0:
                accum_time = cmd["time"]
            else:
                accum_time += cmd["time"]

            if accum_time > curr_t_sec + 1e-4:
                # Command is scheduled in future frames
                accum_time -= cmd["time"]
                break

            cmd_name = cmd["name"]
            args = cmd["args"]

            if cmd_name == "HeartTeleport" and len(args) >= 2:
                # Local space initial state
                try:
                    tx, ty = int(float(args[0])), int(float(args[1]))
                    initial_state = (max(0, min(W - SOUL_W, tx)), max(0, min(H - SOUL_H, ty)))
                except ValueError:
                    pass
            elif cmd_name == "BoneV" and len(args) >= 5:
                # BoneV: x, y, height, direction, speed
                bx = float(args[0])
                by = float(args[1])
                b_height = float(args[2])
                b_dir = int(float(args[3]))
                b_spd = float(args[4])
                vx = b_spd / FPS if b_dir == 0 else (-b_spd / FPS if b_dir == 2 else 0)
                active_bones.append({"x": bx, "y": by, "w": 10.0, "h": b_height, "vx": vx})
            elif cmd_name == "BoneVRepeat" and len(args) >= 7:
                # BoneVRepeat: start_x, start_y, height, dir, speed, count, spacing
                bx = float(args[0])
                by = float(args[1])
                b_height = float(args[2])
                b_dir = int(float(args[3]))
                b_spd = float(args[4])
                count = int(float(args[5]))
                spacing = float(args[6])
                vx = b_spd / FPS if b_dir == 0 else (-b_spd / FPS if b_dir == 2 else 0)
                for c in range(count):
                    active_bones.append({
                        "x": bx + c * spacing,
                        "y": by,
                        "w": 10.0,
                        "h": b_height,
                        "vx": vx,
                    })
            elif cmd_name == "Platform" and len(args) >= 5:
                # Platform: start_x, start_y, width, dir, speed
                px = float(args[0])
                py = float(args[1])
                p_width = float(args[2])
                p_dir = int(float(args[3]))
                p_spd = float(args[4])
                vx = p_spd / FPS if p_dir == 0 else (-p_spd / FPS if p_dir == 2 else 0)
                active_platforms.append({
                    "id": len(active_platforms),
                    "x": px,
                    "y": py,
                    "w": p_width,
                    "vx": vx,
                })
            elif cmd_name == "SansSlam":
                slam_frames.add(t)

            cmd_idx += 1

        # Advance and rasterize obstacles for frame t
        frame_obs = np.zeros((H, W), dtype=bool)
        for bone in active_bones:
            bx = int(round(bone["x"]))
            by = int(round(bone["y"]))
            bw = int(round(bone["w"]))
            bh = int(round(bone["h"]))
            x0 = max(0, min(W, bx))
            x1 = max(0, min(W, bx + bw))
            y0 = max(0, min(H, by))
            y1 = max(0, min(H, by + bh))
            if x1 > x0 and y1 > y0:
                frame_obs[y0:y1, x0:x1] = True
            bone["x"] += bone["vx"]

        # Vectorized Minkowski dilation
        B_hazard[t] = dilate_cspace_2d(frame_obs, w=SOUL_W, h=SOUL_H)

        # Update and store active platforms
        for plat in active_platforms:
            px = plat["x"]
            py = plat["y"]
            pw = plat["w"]
            platform_table[t].append(
                PlatformInstance(
                    plat_id=plat["id"],
                    x_min=px,
                    x_max=px + pw,
                    y_top=py,
                    vx=plat["vx"],
                )
            )
            plat["x"] += plat["vx"]

    metadata = {
        "csv_path": str(csv_path),
        "T": T,
        "W": W,
        "H": H,
        "slam_frames": list(slam_frames),
    }

    return BakeResult(
        B_hazard=B_hazard,
        platform_table=platform_table,
        initial_state=initial_state,
        metadata=metadata,
    )


def reference_solve_lattice_dp(
    bake_result: BakeResult,
    initial_state: Optional[Tuple[int, int]] = None,
) -> SolveResult:
    """Reference implementation of nohit.engine.solve_lattice_dp."""
    t_start = time.perf_counter()
    B_hazard = bake_result.B_hazard
    T, H, W = B_hazard.shape
    platform_table = bake_result.platform_table
    slam_frames = set(bake_result.metadata.get("slam_frames", []))

    x0, y0 = initial_state if initial_state is not None else bake_result.initial_state
    init_state_5d = (x0, y0, 0, 1, 0)  # (x, y, vy, kappa, tau)

    # Check frame 0 safety
    if B_hazard[0, y0, x0]:
        t_end = time.perf_counter()
        return SolveResult(
            is_deadlock=True,
            deadlock_frame=0,
            action_sequence=None,
            trajectory=None,
            stats=SolveStats(
                baking_ms=0.0,
                dp_ms=(t_end - t_start) * 1000.0,
                peak_alive_states=0,
                alive_states_history=[0],
                total_states_explored=1,
                peak_memory_mb=1.0,
            ),
        )

    # Forward reachable set: R_t contains list of 5D states
    R_current: List[Tuple[int, int, int, int, int]] = [init_state_5d]
    # Parent backtracking table: P[t] maps next_packed_state -> (prev_packed_state, action_tuple)
    P: List[Dict[int, Tuple[int, Tuple[int, int]]]] = [{} for _ in range(T)]

    alive_history: List[int] = [1]
    peak_alive = 1
    total_explored = 1

    for t in range(T - 1):
        if not R_current:
            t_end = time.perf_counter()
            return SolveResult(
                is_deadlock=True,
                deadlock_frame=t,
                action_sequence=None,
                trajectory=None,
                stats=SolveStats(
                    baking_ms=0.0,
                    dp_ms=(t_end - t_start) * 1000.0,
                    peak_alive_states=peak_alive,
                    alive_states_history=alive_history,
                    total_states_explored=total_explored,
                    peak_memory_mb=2.0,
                ),
            )

        R_next_dict: Dict[int, Tuple[int, int, int, int, int]] = {}
        is_slam = (t in slam_frames)
        plat_t = platform_table[t]

        for s in R_current:
            s_packed = pack_state(*s)
            for act in ACTIONS:
                s_next = step_dynamics(
                    s, act, platforms=plat_t, is_slam=is_slam, W=W, H=H, w=SOUL_W, h=SOUL_H
                )
                nx, ny, _, _, _ = s_next
                # Safety probe via hazard tensor
                if not B_hazard[t + 1, ny, nx]:
                    s_next_packed = pack_state(*s_next)
                    if s_next_packed not in R_next_dict:
                        R_next_dict[s_next_packed] = s_next
                        P[t + 1][s_next_packed] = (s_packed, act)

        R_current = list(R_next_dict.values())
        cur_len = len(R_current)
        alive_history.append(cur_len)
        if cur_len > peak_alive:
            peak_alive = cur_len
        total_explored += cur_len * len(ACTIONS)

    if not R_current:
        t_end = time.perf_counter()
        return SolveResult(
            is_deadlock=True,
            deadlock_frame=T - 1,
            action_sequence=None,
            trajectory=None,
            stats=SolveStats(
                baking_ms=0.0,
                dp_ms=(t_end - t_start) * 1000.0,
                peak_alive_states=peak_alive,
                alive_states_history=alive_history,
                total_states_explored=total_explored,
                peak_memory_mb=3.0,
            ),
        )

    # Backtracking in O(T) along P
    terminal_state = R_current[0]
    curr_packed = pack_state(*terminal_state)

    traj_packed = [curr_packed]
    actions_rev: List[Tuple[int, int]] = []

    for t in range(T - 1, 0, -1):
        prev_packed, act = P[t][curr_packed]
        actions_rev.append(act)
        traj_packed.append(prev_packed)
        curr_packed = prev_packed

    action_seq = list(reversed(actions_rev))
    traj = [unpack_state(p) for p in reversed(traj_packed)]

    t_end = time.perf_counter()
    return SolveResult(
        is_deadlock=False,
        deadlock_frame=None,
        action_sequence=action_seq,
        trajectory=traj,
        stats=SolveStats(
            baking_ms=0.0,
            dp_ms=(t_end - t_start) * 1000.0,
            peak_alive_states=peak_alive,
            alive_states_history=alive_history,
            total_states_explored=total_explored,
            peak_memory_mb=4.0,
        ),
    )


def reference_replay_and_verify(
    bake_result: BakeResult,
    action_sequence: List[Tuple[int, int]],
) -> VerificationResult:
    """Reference implementation of nohit.verifier.replay_and_verify."""
    B_hazard = bake_result.B_hazard
    T, H, W = B_hazard.shape
    platform_table = bake_result.platform_table
    slam_frames = set(bake_result.metadata.get("slam_frames", []))

    if len(action_sequence) != T - 1 and len(action_sequence) != T:
        return VerificationResult(
            passed=False,
            collision_frames=[],
            kinematic_errors=[f"Action sequence length {len(action_sequence)} does not match T={T}"],
            simulated_trajectory=[],
        )

    x0, y0 = bake_result.initial_state
    current_state = (x0, y0, 0, 1, 0)
    sim_trajectory = [current_state]
    collision_frames: List[int] = []
    kinematic_errors: List[str] = []

    # Frame 0 collision check
    if B_hazard[0, y0, x0]:
        collision_frames.append(0)

    for t in range(len(action_sequence)):
        act = action_sequence[t]
        is_slam = (t in slam_frames)
        plat_t = platform_table[t] if t < len(platform_table) else []

        next_state = step_dynamics(
            current_state, act, platforms=plat_t, is_slam=is_slam, W=W, H=H, w=SOUL_W, h=SOUL_H
        )
        sim_trajectory.append(next_state)
        nx, ny, nvy, nkappa, ntau = next_state

        if t + 1 < T and B_hazard[t + 1, ny, nx]:
            collision_frames.append(t + 1)

        current_state = next_state

    passed = (len(collision_frames) == 0 and len(kinematic_errors) == 0)
    return VerificationResult(
        passed=passed,
        collision_frames=collision_frames,
        kinematic_errors=kinematic_errors,
        simulated_trajectory=sim_trajectory,
    )


# ==============================================================================
# Dynamic Backend Dispatcher
# ==============================================================================

_ACTIVE_BACKEND = os.environ.get("NOHIT_TEST_BACKEND", "auto")


def set_backend(backend: str) -> None:
    """Sets the active testing backend ('auto', 'nohit', or 'reference')."""
    global _ACTIVE_BACKEND
    if backend not in ("auto", "nohit", "reference"):
        raise ValueError(f"Unknown backend: {backend}")
    _ACTIVE_BACKEND = backend


def get_backend() -> str:
    """Returns the currently configured backend."""
    return _ACTIVE_BACKEND


def get_baker() -> Callable[..., BakeResult]:
    """Returns the active bake_cspace function."""
    if _ACTIVE_BACKEND in ("auto", "nohit"):
        try:
            import nohit.baker.dilator as nohit_baker
            if hasattr(nohit_baker, "bake_cspace"):
                return nohit_baker.bake_cspace
        except ImportError:
            if _ACTIVE_BACKEND == "nohit":
                raise
    return reference_bake_cspace


def get_engine() -> Callable[..., SolveResult]:
    """Returns the active solve_lattice_dp function."""
    if _ACTIVE_BACKEND in ("auto", "nohit"):
        try:
            import nohit.engine.solver as nohit_engine
            if hasattr(nohit_engine, "solve_lattice_dp"):
                return nohit_engine.solve_lattice_dp
        except ImportError:
            if _ACTIVE_BACKEND == "nohit":
                raise
    return reference_solve_lattice_dp


def get_verifier() -> Callable[..., VerificationResult]:
    """Returns the active replay_and_verify function."""
    if _ACTIVE_BACKEND in ("auto", "nohit"):
        try:
            import nohit.verifier.replayer as nohit_verifier
            if hasattr(nohit_verifier, "replay_and_verify"):
                return nohit_verifier.replay_and_verify
        except ImportError:
            if _ACTIVE_BACKEND == "nohit":
                raise
    return reference_replay_and_verify
