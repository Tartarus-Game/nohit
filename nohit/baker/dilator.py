"""
nohit.baker.dilator
~~~~~~~~~~~~~~~~~~~
Pure NumPy 2D separable slice Minkowski sum binary morphological dilation.
Computes C_obs(t) = O(t) (+) (-A) for an 8x8 soul box in < 100 ms,
producing the 3D Boolean hazard tensor B_hazard in {0, 1}^{T x H x W}.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
import numpy as np

from nohit.common.constants import (
    DEFAULT_W,
    DEFAULT_H,
    DEFAULT_T,
    SOUL_W,
    SOUL_H,
    V_WALK,
    V_JUMP_INIT,
)
from nohit.common.types import BakeResult, PlatformInstance
from nohit.engine.c2spec import (
    HEART_JUMP_STRENGTH as C2_HEART_JUMP_STRENGTH,
    HEARTSPEED as C2_HEARTSPEED,
)


GRAZE_MARGIN_CELLS: int = 1
"""Extra cells added to the Minkowski dilation on every side.

The engine resolves collisions continuously, so a sub-pixel graze still deals
damage. Measured on sans_bonegap1: a bone at local [162.74, 172.74] against a
4x4 hitbox at [172.00, 176.00] overlaps by 0.74 px and DOES hit, but the integer
grid rounds that away and leaves a 1 px safe hole at the heart's cell.

Marking one extra cell dangerous on each side closes that hole. The direction is
deliberate: over-approximating the obstacle set can only turn a solvable wave
into a reported deadlock (loud, debuggable), whereas under-approximating turns
it into silent damage -- the exact failure this whole round is about.
"""


def dilate_cspace(
    obstacle_tensor: np.ndarray,
    soul_w: int = SOUL_W,
    soul_h: int = SOUL_H,
    centered: bool = False,
    **kwargs: Any,
) -> np.ndarray:
    """Performs 2D separable Minkowski sum binary morphological dilation:
        C_obs(t) = O(t) (+) (-A)
    where A is the axis-aligned soul box of dimensions (soul_w, soul_h).
    If centered=True, A is centered at (x, y) with radius rx, ry.
    If centered=False, A is anchored at bottom-left corner (x, y).
    """
    if "w" in kwargs:
        soul_w = kwargs["w"]
    if "h" in kwargs:
        soul_h = kwargs["h"]
    if "centered" in kwargs:
        centered = kwargs["centered"]

    if obstacle_tensor.ndim == 2:
        is_2d = True
        tensor = obstacle_tensor[np.newaxis, ...]
    elif obstacle_tensor.ndim == 3:
        is_2d = False
        tensor = obstacle_tensor
    else:
        raise ValueError(
            f"Input obstacle_tensor must be 2D (H, W) or 3D (T, H, W), "
            f"got ndim={obstacle_tensor.ndim}"
        )

    T, H, W = tensor.shape

    if soul_w <= 0 or soul_h <= 0:
        raise ValueError(f"Soul box dimensions must be positive, got ({soul_w}, {soul_h})")

    tensor = np.asanyarray(tensor, dtype=bool)

    if centered:
        # Centered hitbox dilation: (x, y) is the center of the soul hitbox.
        #
        # GRAZE_MARGIN_CELLS widens the box by one cell per side. The engine
        # resolves collisions continuously, so a sub-pixel graze still deals
        # damage; measured on sans_bonegap1 a 0.74 px overlap hits, but the
        # integer grid rounded it away and left a 1 px safe hole exactly on the
        # heart's cell. Widening can only mark MORE cells dangerous, so it can
        # never hide a real hit -- it can only turn a solvable wave into a
        # reported deadlock, which is the safe direction for a no-hit planner.
        # Dilate each obstacle cell by the hitbox RADIUS, symmetrically.
        #
        # For a 4-wide hitbox the radius is 2, so a bone occupying local cells
        # 162..172 must mark 160..174 deadly.
        #
        # Two earlier formulations under-covered by one cell and were the direct
        # cause of the real-machine heart losing 92 -> 17 HP:
        #   * `(soul_w - 1) // 2` == 1  -> only 161..173, missing the heart's own
        #     cell at 174
        #   * the asymmetric centred set {-2,-1,0,+1} -> 160..173, still one short
        #
        # Live ground truth that pins the required radius: at sans_bonegap1's
        # first damage tick the bone sits at abs [308.76, 318.76] while the
        # heart's 4x4 box starts at abs 318.00 -- a 0.76 px overlap that DOES
        # deal damage -- and in local cells that is bone 162..172 against the
        # heart at 174. Only a symmetric radius of 2 closes that.
        half_w = soul_w // 2 + GRAZE_MARGIN_CELLS
        half_h = soul_h // 2 + GRAZE_MARGIN_CELLS
        dx_shifts = range(-half_w, half_w + 1)
        dy_shifts = range(-half_h, half_h + 1)

        h_pass = np.zeros_like(tensor, dtype=bool)
        for dx in dx_shifts:
            if dx < 0:
                h_pass[:, :, :dx] |= tensor[:, :, -dx:]
            elif dx > 0:
                h_pass[:, :, dx:] |= tensor[:, :, :-dx]
            else:
                h_pass |= tensor

        hazard_tensor = np.zeros_like(tensor, dtype=bool)
        for dy in dy_shifts:
            if dy < 0:
                hazard_tensor[:, :dy, :] |= h_pass[:, -dy:, :]
            elif dy > 0:
                hazard_tensor[:, dy:, :] |= h_pass[:, :-dy, :]
            else:
                hazard_tensor |= h_pass

        return hazard_tensor[0] if is_2d else hazard_tensor

    if H < soul_h or W < soul_w:
        raise ValueError(
            f"Arena dimensions (H={H}, W={W}) cannot be smaller than "
            f"soul box dimensions (soul_h={soul_h}, soul_w={soul_w})"
        )

    # 1. Separable Horizontal OR-Dilation along columns (W, axis 2)
    valid_w = W - soul_w + 1
    h_valid = np.zeros((T, H, valid_w), dtype=bool)
    for dx in range(soul_w):
        h_valid |= tensor[:, :, dx : valid_w + dx]

    # 2. Separable Vertical OR-Dilation along rows (H, axis 1) with Direct Accumulation
    valid_h = H - soul_h + 1
    # Initialize target tensor with True so outer boundaries (x > W-w, y > H-h) are impassable
    hazard_tensor = np.ones((T, H, W), dtype=bool)
    hazard_tensor[:, :valid_h, :valid_w] = False

    for dy in range(soul_h):
        hazard_tensor[:, :valid_h, :valid_w] |= h_valid[:, dy : valid_h + dy, :]

    return hazard_tensor[0] if is_2d else hazard_tensor


def dilate_2d(
    obstacle_mask: np.ndarray,
    soul_w: int = SOUL_W,
    soul_h: int = SOUL_H,
    **kwargs: Any,
) -> np.ndarray:
    """Convenience wrapper for single-frame 2D obstacle array of shape (H, W)."""
    if obstacle_mask.ndim != 2:
        raise ValueError(f"obstacle_mask must be 2D, got shape {obstacle_mask.shape}")
    return dilate_cspace(obstacle_mask, soul_w=soul_w, soul_h=soul_h, **kwargs)


def dilate_3d(
    obstacle_tensor: np.ndarray,
    soul_w: int = SOUL_W,
    soul_h: int = SOUL_H,
    **kwargs: Any,
) -> np.ndarray:
    """Convenience wrapper for 3D obstacle tensor of shape (T, H, W)."""
    if obstacle_tensor.ndim != 3:
        raise ValueError(f"obstacle_tensor must be 3D, got shape {obstacle_tensor.shape}")
    return dilate_cspace(obstacle_tensor, soul_w=soul_w, soul_h=soul_h, **kwargs)


def dilate_cspace_2d(
    obstacle_grid_2d: np.ndarray,
    w: int = SOUL_W,
    h: int = SOUL_H,
) -> np.ndarray:
    """Alias for dilate_2d matching E2E test harness signature."""
    return dilate_2d(obstacle_grid_2d, soul_w=w, soul_h=h)


def pack_hazard_tensor(b_hazard: np.ndarray) -> np.ndarray:
    """Bit-packs Boolean hazard tensor along axis -1 into uint8 array (8x compression)."""
    return np.packbits(b_hazard, axis=-1)


def unpack_hazard_tensor(b_packed: np.ndarray, target_w: int) -> np.ndarray:
    """Unpacks bit-packed uint8 hazard tensor back to boolean array."""
    unpacked = np.unpackbits(b_packed, axis=-1).astype(bool)
    return unpacked[..., :target_w]


def bake_cspace(
    csv_path: str | Path,
    T: int | None = None,
    W: int = DEFAULT_W,
    H: int = DEFAULT_H,
    soul_w: int = SOUL_W,
    soul_h: int = SOUL_H,
    auto_size: bool = False,
    v_walk: int = V_WALK,
    v_jump: int = V_JUMP_INIT,
    physics_mode: str = "docs",
    centered: bool | None = None,
    attack_seed: int | None = None,
) -> BakeResult:
    """End-to-end pipeline: Parses CSV, rasterizes obstacles & platforms, and dilates C-space.

    Generates B_hazard in < 100 ms.

    ``T`` defaults to **None**, which means "cover the entire attack": the
    horizon is taken from the script's own ``EndAttack`` timestamp at the model
    frame rate. This matters a lot -- the legacy default of 150 frames is 2.5 s
    while a real round is ~6.6 s, so every caller that did not explicitly pass a
    horizon solved only the first third of the attack and then let the heart
    stand still for the remaining ~4 s. Only the dashboard API worked around it
    (by probing first); every direct call, test and diagnostic silently
    truncated. Pass an explicit ``T`` only when a shorter horizon is intended.
    """
    from .parser import parse_csv_timeline
    from .rasterizer import rasterize_timeline, RasterizerConfig

    path = Path(csv_path)
    t_start = time.perf_counter()

    if auto_size or physics_mode == "c2":
        physics_mode = "c2"
        if soul_w == SOUL_W:
            soul_w = 4
        if soul_h == SOUL_H:
            soul_h = 4
        # The c2 stepper works in the engine's own units: px per SECOND.
        # HEARTSPEED = 150 px/s and HEART_JUMP_STRENGTH = 180 px/s are the
        # authoritative values (Battle.xml). The previous defaults (5 / 6)
        # were px-per-frame numbers, and 5 px/frame is 300 px/s -- exactly
        # twice the real speed, which is why the planner outran the game.
        if v_walk == V_WALK:
            v_walk = int(C2_HEARTSPEED)
        if v_jump == V_JUMP_INIT:
            v_jump = int(C2_HEART_JUMP_STRENGTH)
        if centered is None:
            centered = True
    else:
        if centered is None:
            centered = False

    # Step 1: Parse CSV (gracefully fall back to empty wave if file does not exist)
    #
    # IMPORTANT: the parser, the rasterizer and the dynamics step must all run at
    # the SAME rate. The solver consumes one hazard frame per step
    # (`B_hazard[t + 1]`), so a mismatch silently walks the danger sequence at
    # the wrong speed -- that bug once looked like "60 Hz is unsolvable".
    from nohit.engine.dynamics import MODEL_FPS as _MODEL_FPS

    if path.is_file():
        t_parse_0 = time.perf_counter()
        commands = parse_csv_timeline(path, fps=int(_MODEL_FPS), attack_seed=attack_seed)
        parse_ms = (time.perf_counter() - t_parse_0) * 1000.0
    else:
        commands = []
        parse_ms = 0.0

    # Resolve the horizon: an explicit T wins, otherwise cover the whole attack.
    # The script's last EndAttack timestamp defines how long the round actually
    # lasts, and the solver must plan for all of it -- a plan that stops early
    # leaves the heart standing in the danmaku for the remainder.
    if T is None:
        end_times = [
            c.time_s for c in commands
            if getattr(c, "cmd_type", "").lower() == "endattack"
        ]
        if end_times:
            duration_s = max(end_times)
        elif commands:
            duration_s = max(c.time_s for c in commands)
        else:
            duration_s = 0.0
        T = int(round(duration_s * _MODEL_FPS)) + 1 if duration_s > 0 else DEFAULT_T
        T = max(1, min(T, 3600))
        parse_ms = 0.0

    # Step 2: Rasterize obstacles into O(t) and dynamic platforms into PlatformTable[t]
    t_raster_0 = time.perf_counter()
    r_config = RasterizerConfig(T=T, W=W, H=H, auto_size=auto_size, FPS=int(_MODEL_FPS))
    raster_res = rasterize_timeline(commands, config=r_config, T=T, W=W, H=H)
    raster_ms = (time.perf_counter() - t_raster_0) * 1000.0

    actual_H, actual_W = raster_res.O.shape[1], raster_res.O.shape[2]

    # Step 3: Pure NumPy separable slice Minkowski dilation C_obs = O (+) (-A)
    t_dilate_0 = time.perf_counter()
    b_hazard = dilate_cspace(raster_res.O, soul_w=soul_w, soul_h=soul_h, centered=centered)
    dilate_ms = (time.perf_counter() - t_dilate_0) * 1000.0

    b_blue = None
    if raster_res.O_blue is not None and np.any(raster_res.O_blue):
        b_blue = dilate_cspace(raster_res.O_blue, soul_w=soul_w, soul_h=soul_h, centered=centered)

    b_orange = None
    if raster_res.O_orange is not None and np.any(raster_res.O_orange):
        b_orange = dilate_cspace(raster_res.O_orange, soul_w=soul_w, soul_h=soul_h, centered=centered)

    total_ms = (time.perf_counter() - t_start) * 1000.0

    metadata: dict[str, Any] = {
        "csv_path": str(path.resolve()),
        "csv_filename": path.name,
        "attack_seed": attack_seed,
        # Frames actually baked (== T). The script's own duration in frames is
        # `attack_duration_frames`, used by callers to size a full-coverage
        # solve instead of the legacy hard-coded 150.
        "duration_frames": T,
        "attack_duration_s": raster_res.metadata.get("duration_s"),
        "attack_duration_frames": raster_res.metadata.get("duration_frames"),
        # The rate everything above was baked at. Exposed so consumers (and
        # tests) never have to assume 30 Hz.
        "FPS": int(_MODEL_FPS),
        "T": T,
        "W": actual_W,
        "H": actual_H,
        "soul_size": (soul_w, soul_h),
        "v_walk": v_walk,
        "v_jump": v_jump,
        "physics_mode": physics_mode,
        "centered": centered,
        "c2_left": raster_res.metadata.get("c2_left"),
        "c2_floor": raster_res.metadata.get("c2_floor"),
        "slam_frames": raster_res.slam_frames,
        "parse_time_ms": round(parse_ms, 3),
        "rasterize_time_ms": round(raster_ms, 3),
        "dilation_time_ms": round(dilate_ms, 3),
        "total_baking_time_ms": round(total_ms, 3),
        "hazard_pixel_density": round(float(np.mean(b_hazard)), 4),
    }
    if b_blue is not None:
        metadata["B_blue"] = b_blue
    if b_orange is not None:
        metadata["B_orange"] = b_orange

    return BakeResult(
        B_hazard=b_hazard,
        platform_table=raster_res.platform_table,
        initial_state=raster_res.initial_heart_pos,
        metadata=metadata,
    )
