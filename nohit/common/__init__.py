"""
nohit.common
~~~~~~~~~~~~
Common constants, data types, and coordinate conversion utilities.
"""

from __future__ import annotations

from .constants import (
    DEFAULT_W,
    ARENA_WIDTH,
    DEFAULT_H,
    ARENA_HEIGHT,
    SOUL_W,
    SOUL_WIDTH,
    SOUL_H,
    SOUL_HEIGHT,
    SOUL_MAX_X,
    SOUL_MAX_Y,
    NUM_X_CELLS,
    NUM_Y_CELLS,
    FPS,
    FRAME_DURATION_S,
    DEFAULT_T,
    V_WALK,
    V_JUMP_INIT,
    V_MIN,
    V_MAX,
    NUM_VY_CELLS,
    V_OFFSET,
    G_ASCEND,
    G_DESCEND,
    TAU_MAX,
    NUM_TAU_CELLS,
    NUM_KAPPA_CELLS,
    TOTAL_STATE_CAPACITY,
    SLAM_COLLAPSE_BOUND,
    C2_CANVAS_W,
    C2_CANVAS_H,
    C2_BORDER_THICKNESS,
    C2_BONE_V_WIDTH,
    C2_BONE_H_HEIGHT,
    C2_PLATFORM_HEIGHT,
    C2_MAX_FALL_SPEED,
    DIR_RIGHT,
    DIR_DOWN,
    DIR_LEFT,
    DIR_UP,
    BONE_WHITE,
    BONE_BLUE,
    BONE_ORANGE,
    HEART_MODE_RED,
    HEART_MODE_BLUE,
    UX_LEFT,
    UX_NONE,
    UX_RIGHT,
    UY_RELEASE,
    UY_HOLD,
    ACTIONS,
)

from .types import (
    State,
    Action,
    ALL_ACTIONS,
    PlatformInstance,
    Command,
    BakeResult,
    SolveStats,
    SolveResult,
    VerificationResult,
)

from .coords import (
    CombatZone,
    c2_to_cspace_point,
    cspace_to_c2_point,
    c2_to_cspace_box,
    cspace_to_c2_box,
    c2_to_cspace_velocity,
    cspace_to_c2_velocity,
    c2_to_grid,
    grid_to_c2,
)

__all__ = [
    # Constants
    "DEFAULT_W", "ARENA_WIDTH", "DEFAULT_H", "ARENA_HEIGHT",
    "SOUL_W", "SOUL_WIDTH", "SOUL_H", "SOUL_HEIGHT",
    "SOUL_MAX_X", "SOUL_MAX_Y", "NUM_X_CELLS", "NUM_Y_CELLS",
    "FPS", "FRAME_DURATION_S", "DEFAULT_T",
    "V_WALK", "V_JUMP_INIT", "V_MIN", "V_MAX", "NUM_VY_CELLS", "V_OFFSET",
    "G_ASCEND", "G_DESCEND", "TAU_MAX", "NUM_TAU_CELLS", "NUM_KAPPA_CELLS",
    "TOTAL_STATE_CAPACITY", "SLAM_COLLAPSE_BOUND",
    "C2_CANVAS_W", "C2_CANVAS_H", "C2_BORDER_THICKNESS",
    "C2_BONE_V_WIDTH", "C2_BONE_H_HEIGHT", "C2_PLATFORM_HEIGHT", "C2_MAX_FALL_SPEED",
    "DIR_RIGHT", "DIR_DOWN", "DIR_LEFT", "DIR_UP",
    "BONE_WHITE", "BONE_BLUE", "BONE_ORANGE",
    "HEART_MODE_RED", "HEART_MODE_BLUE",
    "UX_LEFT", "UX_NONE", "UX_RIGHT", "UY_RELEASE", "UY_HOLD",
    "ACTIONS", "ALL_ACTIONS",
    # Types
    "State", "Action", "PlatformInstance", "Command", "BakeResult",
    "SolveStats", "SolveResult", "VerificationResult",
    # Coords
    "CombatZone", "c2_to_cspace_point", "cspace_to_c2_point",
    "c2_to_cspace_box", "cspace_to_c2_box",
    "c2_to_cspace_velocity", "cspace_to_c2_velocity",
    "c2_to_grid", "grid_to_c2",
]
