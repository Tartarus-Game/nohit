"""
nohit.common.constants
~~~~~~~~~~~~~~~~~~~~~~
Physics constants, spatial grid limits, bit-packing layouts, and control alphabet.
Anchored to docs.txt and Construct 2 reverse engineering specifications.
"""

from __future__ import annotations

# ==============================================================================
# Spatial Grid & Soul Hitbox Bounds (docs.txt § 4 & § 5)
# ==============================================================================
DEFAULT_W: int = 200
ARENA_WIDTH: int = 200
DEFAULT_H: int = 160
ARENA_HEIGHT: int = 160

SOUL_W: int = 8
SOUL_WIDTH: int = 8
SOUL_H: int = 8
SOUL_HEIGHT: int = 8

# Maximum coordinate indices for bottom-left reference point of soul box
SOUL_MAX_X: int = ARENA_WIDTH - SOUL_WIDTH   # 192 (0..192)
SOUL_MAX_Y: int = ARENA_HEIGHT - SOUL_HEIGHT  # 152 (0..152)

# Discrete spatial grid dimensions
NUM_X_CELLS: int = SOUL_MAX_X + 1  # 193
NUM_Y_CELLS: int = SOUL_MAX_Y + 1  # 153

# ==============================================================================
# Temporal & Discrete Simulation Constants
# ==============================================================================
FPS: int = 30
FRAME_DURATION_S: float = 1.0 / 30.0
DEFAULT_T: int = 150  # 5.0 seconds standard round

# ==============================================================================
# Micro-dynamics Parameters (docs.txt § 5)
# ==============================================================================
V_WALK: int = 3          # Blue soul horizontal speed (px/frame) matching docs.txt blue soul and test suite
V_JUMP_INIT: int = 8     # Initial upward jump impulse velocity (px/frame) matching docs.txt blue soul and test suite
V_MIN: int = -12         # Terminal downward falling velocity
V_MAX: int = 8           # Maximum upward vertical velocity
NUM_VY_CELLS: int = V_MAX - V_MIN + 1  # 21 discrete levels (-12..8)
V_OFFSET: int = 12       # Offset to map vy to non-negative range [0, 20]

G_ASCEND: int = 1        # Piecewise gravity during active jump hold (uy=1, tau < tau_max, vy > 0)
G_DESCEND: int = 2       # Piecewise gravity during jump release or descent
TAU_MAX: int = 15        # Maximum jump hold counter frames (0..15)
NUM_TAU_CELLS: int = TAU_MAX + 1  # 16 discrete levels
NUM_KAPPA_CELLS: int = 2          # Ground support boolean flag (0 or 1)

# ==============================================================================
# Theoretical Phase Space Capacity Bounds (docs.txt Lemma 1)
# ==============================================================================
TOTAL_STATE_CAPACITY: int = (
    NUM_X_CELLS * NUM_Y_CELLS * NUM_VY_CELLS * NUM_KAPPA_CELLS * NUM_TAU_CELLS
)  # 193 * 153 * 21 * 2 * 16 = 19,843,776

# SansSlam induces phase space dissipation collapsing capacity to <= W - w + 1
SLAM_COLLAPSE_BOUND: int = NUM_X_CELLS  # 193

# ==============================================================================
# Construct 2 Engine Geometry Specifications
# ==============================================================================
C2_CANVAS_W: int = 640
C2_CANVAS_H: int = 480
C2_BORDER_THICKNESS: int = 5
C2_BONE_V_WIDTH: int = 10
C2_BONE_H_HEIGHT: int = 10
C2_PLATFORM_HEIGHT: int = 7
C2_MAX_FALL_SPEED: float = 750.0  # px/s

# ==============================================================================
# Construct 2 Enums & Control Actions
# ==============================================================================
# Clockwise directions
DIR_RIGHT: int = 0
DIR_DOWN: int = 1
DIR_LEFT: int = 2
DIR_UP: int = 3

# Bone color types
BONE_WHITE: int = 0
BONE_BLUE: int = 1
BONE_ORANGE: int = 2

# Soul modes
HEART_MODE_RED: int = 0
HEART_MODE_BLUE: int = 1

# Control actions U = {-1, 0, 1} x {0, 1}
UX_LEFT: int = -1
UX_NONE: int = 0
UX_RIGHT: int = 1

UY_RELEASE: int = 0
UY_HOLD: int = 1

ACTION_LEFT_RELEASE: int = 0   # (-1, 0)
ACTION_LEFT_HOLD: int = 1      # (-1, 1)
ACTION_NONE_RELEASE: int = 2   # ( 0, 0)
ACTION_NONE_HOLD: int = 3      # ( 0, 1)
ACTION_RIGHT_RELEASE: int = 4  # (+1, 0)
ACTION_RIGHT_HOLD: int = 5     # (+1, 1)

ACTIONS: list[tuple[int, int]] = [
    (-1, 0),
    (-1, 1),
    (0, 0),
    (0, 1),
    (1, 0),
    (1, 1),
]
