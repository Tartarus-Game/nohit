"""Shared typed data containers for compact wave compilation and dynamics."""
from dataclasses import dataclass
from typing import Any
import numpy as np


class GeometryArray(np.ndarray):
    """Subclass of np.ndarray that carries wave geometry metadata and dual-plane slices."""
    geometry_white: np.ndarray | None
    geometry_blue: np.ndarray | None
    origin_x: int
    origin_y: int
    width: int
    height: int

    def __new__(cls, input_array, geometry_white=None, geometry_blue=None, origin_x=113, origin_y=231, width=435, height=160):
        obj = np.asarray(input_array).view(cls)
        obj.geometry_white = geometry_white
        obj.geometry_blue = geometry_blue
        obj.origin_x = origin_x
        obj.origin_y = origin_y
        obj.width = width
        obj.height = height
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        self.geometry_white = getattr(obj, "geometry_white", None)
        self.geometry_blue = getattr(obj, "geometry_blue", None)
        self.origin_x = getattr(obj, "origin_x", 113)
        self.origin_y = getattr(obj, "origin_y", 231)
        self.width = getattr(obj, "width", 435)
        self.height = getattr(obj, "height", 160)


@dataclass(slots=True)
class CompiledWave:
    """Universal compiled wave data structure returned by compile_wave.

    Supports tuple unpacking:
        schedule, geometry, initial = compile_wave(...)
    as well as property access:
        res.env_schedule, res.platform_table, res.num_platforms, res.geometry_white, res.geometry_blue
    """
    schedule: np.ndarray          # Shape (T, 7): [px, py, pw, ph, pdx, pdy, dt] (legacy compatible)
    geometry: np.ndarray          # Shape (T, K, 4): rectangular hazards [l, t, r, b]
    initial: np.ndarray           # Shape (5,): [x0, y0, dx0, dy0, prev_up]
    env_schedule: np.ndarray      # (T,22): finalArena,mode,gravity,slam,dt,maxfall,teleport,x,y,slamDamage,modePulse,oldArena,midArena
    platform_table: np.ndarray    # (T,K,9): [px,py,pw,ph,pvx,pvy,active,preTimelineActive,preBounceVy]
    num_platforms: np.ndarray     # Shape (T,): count of active platforms (int32)
    geometry_white: np.ndarray    # Shape (T, Kw, 4): white unconditional hazard bboxes
    geometry_blue: np.ndarray     # Shape (T, Kb, 4): blue velocity-dependent hazard bboxes
    origin: tuple[int, int]       # (origin_x, origin_y) wave-enclosing bounding box origin
    dimensions: tuple[int, int]   # (height, width) of wave-enclosing bounding box
    attack_name: str              # CSV filename stem
    total_frames: int             # Total 60Hz nominal frames
    dt: np.ndarray                # Shape (T,)
    geometry_polygons: np.ndarray | None = None  # (T,K,8), convex world-space quad vertices
    source_events: tuple = ()      # (tick, command, nine typed loaded call arguments), source order
    player_dependent: bool = False # True only when explicit observed history was supplied
    pending_target: dict | None = None  # Unbound player observation; never an EndAttack
    complete: bool = True         # False for a prefix stopped before pending_target
    target_history: tuple = ()    # Consumed (tick,line,x,y) observations, in source order
    termination_reason: str | None = None  # endattack / eof_hazards_drained / tick_budget / pending_target
    eof_tick: int | None = None    # EOF does not destroy hazards or invoke EndAttack
    terminal_details: dict | None = None  # Environment completion is not a player invariant proof
    environment_state_keys: tuple = ()  # Opt-in exact post-tick bytes; unresolved observation rows are None

    def __iter__(self):
        """Backward compatibility for: schedule, geometry, initial = compile_wave(...)"""
        return iter((self.schedule, self.geometry, self.initial))

    def __getitem__(self, idx: int):
        return (self.schedule, self.geometry, self.initial)[idx]

    def __len__(self) -> int:
        return 3
