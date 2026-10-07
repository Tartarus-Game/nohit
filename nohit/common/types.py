"""
nohit.common.types
~~~~~~~~~~~~~~~~~~
Core typed domain models, 32-bit micro-state bit-packing, discrete control actions,
dynamic platform representations, and inter-subsystem data contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence
import numpy as np

# Dynamic compatibility base classes with E2E harness if present in environment
try:
    from tests.e2e.harness import PlatformInstance as _HarnessPlatformInstance
except (ImportError, Exception):
    class _HarnessPlatformInstance:
        pass

try:
    from tests.e2e.harness import BakeResult as _HarnessBakeResult
except (ImportError, Exception):
    class _HarnessBakeResult:
        pass

try:
    from tests.e2e.harness import SolveResult as _HarnessSolveResult
except (ImportError, Exception):
    class _HarnessSolveResult:
        pass

try:
    from tests.e2e.harness import VerificationResult as _HarnessVerificationResult
except (ImportError, Exception):
    class _HarnessVerificationResult:
        pass


# ==============================================================================
# 5D Discrete Micro-State s = (x, y, vy, kappa, tau)
# ==============================================================================
@dataclass(slots=True, frozen=True)
class State:
    """Five-dimensional discrete physical micro-state vector.

    Attributes:
        x: Horizontal position [0, W - w] (0..192)
        y: Vertical position [0, H - h] (0..152)
        vy: Vertical discrete velocity [v_min, v_max] (-12..+8)
        kappa: Ground support flag (1 = on floor/platform, 0 = airborne)
        tau: Jump key hold frame counter [0, tau_max] (0..15)
    """
    x: int
    y: int
    vy: int
    kappa: int
    tau: int

    def to_tuple(self) -> tuple[int, int, int, int, int]:
        return (self.x, self.y, self.vy, self.kappa, self.tau)

    def __iter__(self) -> Iterator[int]:
        yield self.x
        yield self.y
        yield self.vy
        yield self.kappa
        yield self.tau

    def __getitem__(self, index: int) -> int:
        if index == 0:
            return self.x
        elif index == 1:
            return self.y
        elif index == 2:
            return self.vy
        elif index == 3:
            return self.kappa
        elif index == 4:
            return self.tau
        raise IndexError(f"State index out of range: {index}")

    def __len__(self) -> int:
        return 5

    def pack(self) -> int:
        """Encodes state into a compact 32-bit unsigned integer key.

        Bit allocation:
          bits 0..7:   x [0..192] (8 bits)
          bits 8..15:  y [0..152] (8 bits)
          bits 16..20: vy + 12 [0..20] (5 bits)
          bit 21:      kappa [0..1] (1 bit)
          bits 22..25: tau [0..15] (4 bits)
          bits 26..31: unused (0)
        Total width: 26 bits <= 32 bits.
        """
        vy_offset = (self.vy + 12) & 0x1F
        return (
            (self.x & 0xFF)
            | ((self.y & 0xFF) << 8)
            | (vy_offset << 16)
            | ((self.kappa & 0x01) << 21)
            | ((self.tau & 0x0F) << 22)
        )

    @classmethod
    def unpack(cls, key: int) -> State:
        """Decodes 32-bit packed key into State instance."""
        x = key & 0xFF
        y = (key >> 8) & 0xFF
        vy = ((key >> 16) & 0x1F) - 12
        kappa = (key >> 21) & 0x01
        tau = (key >> 22) & 0x0F
        return cls(x=x, y=y, vy=vy, kappa=kappa, tau=tau)


# ==============================================================================
# Discrete Control Action u = (ux, uy)
# ==============================================================================
@dataclass(slots=True, frozen=True)
class Action:
    """Discrete control action primitive.

    Attributes:
        ux: Horizontal input in {-1 (Left), 0 (None), 1 (Right)}
        uy: Vertical jump input in {0 (Release), 1 (Hold Jump)}
    """
    ux: int
    uy: int

    def to_tuple(self) -> tuple[int, int]:
        return (self.ux, self.uy)

    def __iter__(self) -> Iterator[int]:
        yield self.ux
        yield self.uy

    def __getitem__(self, index: int) -> int:
        if index == 0:
            return self.ux
        elif index == 1:
            return self.uy
        raise IndexError(f"Action index out of range: {index}")

    def __len__(self) -> int:
        return 2

    @property
    def action_index(self) -> int:
        """Maps (ux, uy) to discrete index in range 0..5."""
        return (self.ux + 1) * 2 + self.uy

    @classmethod
    def from_index(cls, idx: int) -> Action:
        """Reconstructs Action from discrete index in range 0..5."""
        if not (0 <= idx <= 5):
            raise ValueError(f"Action index must be in [0, 5], got {idx}")
        ux = (idx // 2) - 1
        uy = idx % 2
        return cls(ux=ux, uy=uy)


ALL_ACTIONS: tuple[Action, ...] = tuple(Action.from_index(i) for i in range(6))


# ==============================================================================
# Dynamic Moving Platform Topology Instance
# ==============================================================================
class PlatformInstance(_HarnessPlatformInstance):
    """Represents a dynamic jump-through platform active on frame t.

    Supports both C-space local attributes (x_left, x_right, y_surf)
    and E2E harness compatibility properties (x_min, x_max, y_top).
    """
    __slots__ = ("plat_id", "x_left", "x_right", "y_surf", "vx")

    def __init__(
        self,
        plat_id: int = 0,
        x_left: float | None = None,
        x_right: float | None = None,
        y_surf: int | float | None = None,
        vx: float = 0.0,
        x_min: float | None = None,
        x_max: float | None = None,
        y_top: float | None = None,
    ):
        self.plat_id = int(plat_id)
        self.x_left = float(x_left if x_left is not None else (x_min if x_min is not None else 0.0))
        self.x_right = float(x_right if x_right is not None else (x_max if x_max is not None else 0.0))
        self.y_surf = int(round(y_surf if y_surf is not None else (y_top if y_top is not None else 0.0)))
        self.vx = float(vx)

    @property
    def x_min(self) -> float:
        return self.x_left

    @x_min.setter
    def x_min(self, val: float) -> None:
        self.x_left = float(val)

    @property
    def x_max(self) -> float:
        return self.x_right

    @x_max.setter
    def x_max(self, val: float) -> None:
        self.x_right = float(val)

    @property
    def y_top(self) -> float:
        return float(self.y_surf)

    @y_top.setter
    def y_top(self, val: float) -> None:
        self.y_surf = int(round(val))

    def is_supporting(self, soul_x: int, soul_w: int = 8) -> bool:
        """Determines if soul horizontal interval [soul_x, soul_x + soul_w] overlaps platform."""
        return (soul_x + soul_w > self.x_left) and (soul_x < self.x_right)

    def __repr__(self) -> str:
        return (
            f"PlatformInstance(id={self.plat_id}, bounds=[{self.x_left:.1f}, {self.x_right:.1f}], "
            f"y_surf={self.y_surf}, vx={self.vx:.2f})"
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, (PlatformInstance, _HarnessPlatformInstance)):
            return False
        return (
            getattr(other, "plat_id", None) == self.plat_id and
            abs(getattr(other, "x_min", 0.0) - self.x_min) < 1e-4 and
            abs(getattr(other, "x_max", 0.0) - self.x_max) < 1e-4 and
            abs(getattr(other, "y_top", 0.0) - self.y_top) < 1e-4 and
            abs(getattr(other, "vx", 0.0) - self.vx) < 1e-4
        )


# ==============================================================================
# Parsed Attack Command AST Node
# ==============================================================================
@dataclass(slots=True)
class Command:
    """Timeline command AST node emitted by parser."""
    frame: int
    time_s: float
    cmd_type: str
    params: dict[str, Any]
    raw_args: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.cmd_type

    @property
    def args(self) -> list[str]:
        return self.raw_args


# ==============================================================================
# Subsystem Result Contracts (PROJECT.md § Interface Contracts)
# ==============================================================================
class BakeResult(_HarnessBakeResult):
    """Contract 1: Output produced by nohit.baker.bake_cspace."""
    __slots__ = ("B_hazard", "platform_table", "initial_state", "metadata")

    def __init__(
        self,
        B_hazard: np.ndarray,
        platform_table: list[list[PlatformInstance]],
        initial_state: tuple[int, int],
        metadata: dict[str, Any] | None = None,
    ):
        self.B_hazard = B_hazard
        self.platform_table = platform_table
        self.initial_state = initial_state
        self.metadata = metadata if metadata is not None else {}

    def packed_tensor(self) -> np.ndarray:
        """Returns bit-packed uint8 hazard tensor along horizontal axis."""
        return np.packbits(self.B_hazard, axis=-1)

    @property
    def T(self) -> int:
        return int(self.B_hazard.shape[0])

    @property
    def H(self) -> int:
        return int(self.B_hazard.shape[1])

    @property
    def W(self) -> int:
        return int(self.B_hazard.shape[2])

    @property
    def obstacle_tensor(self) -> np.ndarray:
        return self.B_hazard

    def __repr__(self) -> str:
        return (
            f"BakeResult(T={self.T}, H={self.H}, W={self.W}, "
            f"initial_state={self.initial_state}, "
            f"platforms_total={sum(len(p) for p in self.platform_table)})"
        )


@dataclass(slots=True)
class SolveStats:
    """Performance telemetry and phase space statistics."""
    bake_time_ms: float = 0.0
    dp_solve_time_ms: float = 0.0
    total_time_ms: float = 0.0
    peak_alive_states: int = 0
    alive_states_history: list[int] = field(default_factory=list)
    total_states_explored: int = 0
    peak_memory_mb: float = 0.0
    operator_prepare_ms: float = 0.0
    operator_search_ms: float = 0.0
    operator_reconstruct_ms: float = 0.0

    @property
    def baking_ms(self) -> float:
        return self.bake_time_ms

    @property
    def dp_ms(self) -> float:
        return self.dp_solve_time_ms


@dataclass(slots=True)
class SolveResult(_HarnessSolveResult):
    """Contract 2: Output produced by nohit.engine.solve_lattice_dp."""
    is_deadlock: bool
    deadlock_frame: int | None
    action_sequence: list[tuple[int, int]] | None
    trajectory: list[tuple[int, int, int, int, int]] | None
    stats: SolveStats


@dataclass(slots=True)
class VerificationResult(_HarnessVerificationResult):
    """Contract 3: Output produced by nohit.verifier.replay_and_verify."""
    passed: bool
    collision_frames: list[int]
    kinematic_errors: list[str]
    simulated_trajectory: list[tuple[int, int, int, int, int]]
