"""
nohit.baker.rasterizer
~~~~~~~~~~~~~~~~~~~~~~
Frame-by-frame geometric obstacle simulation and binary mask rasterization.
Converts parsed timeline commands into binary obstacle tensor O(t) of shape (T, H, W)
and emits per-frame PlatformTable[t].
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
import numpy as np

from nohit.common.constants import (
    DEFAULT_W, DEFAULT_H, DEFAULT_T, FPS,
    SOUL_W, SOUL_H, C2_BORDER_THICKNESS,
    DIR_RIGHT, DIR_DOWN, DIR_LEFT, DIR_UP,
)
from nohit.common.coords import CombatZone
from nohit.common.types import Command, PlatformInstance


@dataclass(slots=True)
class RasterizerConfig:
    """Configuration parameters for timeline rasterization."""

    T: int = DEFAULT_T
    W: int = DEFAULT_W
    H: int = DEFAULT_H
    # MUST match `dynamics.MODEL_FPS`: the solver consumes exactly one hazard
    # frame per step (`B_hazard[t + 1]`), so a mismatch walks the danger
    # sequence at the wrong speed. `bake_cspace` sets this explicitly.
    FPS: int = FPS
    border_thickness: int = C2_BORDER_THICKNESS
    auto_size: bool = False


@dataclass(slots=True)
class RasterResult:
    """Output produced by geometric rasterizer."""
    O: np.ndarray                                 # Shape (T, H, W), dtype bool
    platform_table: list[list[PlatformInstance]]  # Outer length T
    slam_frames: list[int]                        # List of frame indices triggering SansSlam
    initial_heart_pos: tuple[int, int]            # (x0, y0) in local C-space coordinates
    zone_bounds: list[tuple[int, int, int, int]]  # (xmin, xmax, ymin, ymax) per frame
    metadata: dict[str, Any] = field(default_factory=dict)
    O_blue: np.ndarray | None = None
    O_orange: np.ndarray | None = None

    @property
    def obstacle_tensor(self) -> np.ndarray:
        return self.O

    @property
    def initial_state(self) -> tuple[int, int]:
        return self.initial_heart_pos


# ==============================================================================
# Active Obstacle Simulation Entities
# ==============================================================================

class _ActiveBone:
    __slots__ = ("x", "y", "width", "height", "vx", "vy", "color", "spawn_frame")

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        vx: float,
        vy: float,
        color: int,
        spawn_frame: int,
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.vx = vx
        self.vy = vy
        self.color = color
        self.spawn_frame = spawn_frame

    def get_box(self, frame: int) -> tuple[float, float, float, float]:
        """Returns (xmin, ymin, xmax, ymax) on the given frame."""
        dt = frame - self.spawn_frame
        curr_x = self.x + self.vx * dt
        curr_y = self.y + self.vy * dt
        return curr_x, curr_y, curr_x + self.width, curr_y + self.height


class _ActiveBoneStab:
    __slots__ = ("direction", "height", "warn_frames", "stab_frames", "spawn_frame")

    def __init__(
        self,
        direction: int,
        height: float,
        warn_time: float,
        stab_time: float,
        spawn_frame: int,
        fps: int = 30,
    ):
        self.direction = direction
        self.height = height
        self.warn_frames = int(round(warn_time * fps))
        self.stab_frames = int(round(stab_time * fps))
        self.spawn_frame = spawn_frame

    def get_protrusion_depth(self, frame: int) -> float:
        dt = frame - self.spawn_frame
        if dt < 0 or dt < self.warn_frames:
            return 0.0

        n_ext = 3   # 0.1s extension at 30 FPS
        n_ret = 3   # 0.1s retraction at 30 FPS
        t_ext_end = self.warn_frames + n_ext
        t_hold_end = t_ext_end + self.stab_frames
        t_ret_end = t_hold_end + n_ret

        if dt < t_ext_end:
            ratio = (dt - self.warn_frames + 1) / float(n_ext)
            return min(self.height, self.height * ratio)
        elif dt < t_hold_end:
            return self.height
        elif dt < t_ret_end:
            ratio = 1.0 - ((dt - t_hold_end + 1) / float(n_ret))
            return max(0.0, self.height * ratio)
        return 0.0


class _ActivePlatform:
    __slots__ = ("plat_id", "x", "y", "width", "vx", "vy", "spawn_frame", "reverse", "x_bounds")

    def __init__(
        self,
        plat_id: int,
        x: float,
        y: float,
        width: float,
        vx: float,
        vy: float,
        spawn_frame: int,
        reverse: bool = False,
        x_bounds: tuple[float, float] = (0, 640),
    ):
        self.plat_id = plat_id
        self.x = x
        self.y = y
        self.width = width
        self.vx = vx
        self.vy = vy
        self.spawn_frame = spawn_frame
        self.reverse = reverse
        self.x_bounds = x_bounds

    def get_state(self, frame: int) -> tuple[float, float, float, float]:
        """Returns (curr_x, curr_y, width) on the given frame."""
        dt = frame - self.spawn_frame
        curr_x = self.x + self.vx * dt
        curr_y = self.y + self.vy * dt
        vx = self.vx
        if self.reverse and vx:
            left, right = self.x_bounds
            span = right - self.width - left
            phase = (curr_x - left) % (2 * span)
            curr_x = left + (phase if phase <= span else 2 * span - phase)
            vx = vx if phase <= span else -vx
        return curr_x, curr_y, self.width, vx


# ==============================================================================
# Main Rasterization Logic
# ==============================================================================

def rasterize_timeline(
    commands: Sequence[Any],
    config: RasterizerConfig | None = None,
    T: int | None = None,
    W: int | None = None,
    H: int | None = None,
) -> RasterResult:
    """Simulates active obstacles frame-by-frame and produces O(t) and PlatformTable[t]."""
    if config is None:
        config = RasterizerConfig()

    eff_T = T if T is not None else config.T
    eff_W = W if W is not None else config.W
    eff_H = H if H is not None else config.H
    fps = config.FPS
    B = config.border_thickness

    # Initial Pass: Inspect commands to discover initial CombatZone and coordinates format
    init_cz: tuple[float, float, float, float] | None = None
    teleport_pos: tuple[float, float] | None = None
    has_large_c2_coords = False

    for cmd in commands:
        cname = getattr(cmd, "cmd_type", getattr(cmd, "name", ""))
        params = getattr(cmd, "params", {})
        raw_args = getattr(cmd, "raw_args", getattr(cmd, "args", []))

        if cname in ("CombatZoneResize", "CombatZoneResizeInstant") and init_cz is None:
            if "x1" in params:
                init_cz = (float(params["x1"]), float(params["y1"]), float(params["x2"]), float(params["y2"]))
            elif len(raw_args) >= 4:
                try:
                    init_cz = (float(raw_args[0]), float(raw_args[1]), float(raw_args[2]), float(raw_args[3]))
                except ValueError:
                    pass

        elif cname == "HeartTeleport":
            # Several attack scripts teleport the heart more than once on frame 0
            # (sans_platforms4 issues two, sans_multi3 thirteen). The timeline
            # executor runs them in order within the same frame, so the LAST
            # parseable teleport is where the heart actually starts the attack.
            # Taking the first one desynchronises the whole solve: the hazard
            # bitmap is anchored on the heart's start cell, which made
            # sans_platforms4 report a bogus "deadlock @ t=0".
            if "x" in params:
                teleport_pos = (float(params["x"]), float(params["y"]))
            elif len(raw_args) >= 2:
                try:
                    teleport_pos = (float(raw_args[0]), float(raw_args[1]))
                except ValueError:
                    # Non-literal arguments ($HeartY etc.) are not resolvable
                    # statically; keep the previously parsed teleport.
                    pass

        # Check if any entity coordinate is in large screen range (> eff_H)
        if cname in ("BoneV", "BoneVRepeat", "BoneH", "BoneHRepeat", "Platform", "PlatformRepeat"):
            if len(raw_args) >= 2:
                try:
                    y_val = float(raw_args[1])
                    if y_val > eff_H:
                        has_large_c2_coords = True
                except ValueError:
                    pass

    # Reference combat zone bounds
    if init_cz is None:
        init_cz = (133.0, 251.0, 508.0, 391.0)

    init_x1, init_y1, init_x2, init_y2 = init_cz
    if config.auto_size and init_cz is not None:
        eff_W = int(round(init_x2 - init_x1 - 26))
        eff_H = int(round(init_y2 - init_y1 - 26))
        c2_left = init_x1 + 13
        c2_floor = init_y2 - 13
    else:
        c2_floor = init_y2 - B
        c2_left = init_x1 + B

    # Determine initial player position
    default_init_x = (eff_W - SOUL_W) // 2
    default_init_y = 0

    if teleport_pos is not None:
        tx, ty = teleport_pos

        # Decide whether this teleport is expressed in C2 canvas space or in the
        # local arena space.
        #
        # The old guard was `0 <= tx <= eff_W - SOUL_W and 0 <= ty <= eff_H - SOUL_H`,
        # which is wrong for C2 canvas coordinates: a bone-free attack such as
        # sans_bonegap1 teleports to (320, 376), and 376 > eff_H - SOUL_H, so the
        # guard failed, `has_large_c2_coords` was also False (it only looks at
        # bone/platform commands), and the raw (320, 376) was used as a LOCAL
        # coordinate. The heart then anchored on the wrong cell and the whole
        # solve was offset.
        #
        # `CombatZoneResize(x1, y1, x2, y2)` always describes a C2 canvas rect, so
        # a teleport outside that rect cannot be a local coordinate.
        in_cz_canvas = (
            min(init_x1, init_x2) <= tx <= max(init_x1, init_x2)
            and min(init_y1, init_y2) <= ty <= max(init_y1, init_y2)
        )
        in_local_box = 0 <= tx <= eff_W - SOUL_W and 0 <= ty <= eff_H - SOUL_H
        treat_as_c2_canvas = has_large_c2_coords or (in_cz_canvas and not in_local_box)

        if in_local_box and not treat_as_c2_canvas:
            init_state = (int(round(tx)), int(round(ty)))
        elif treat_as_c2_canvas:
            # Convert C2 screen teleport to local C-space
            if config.auto_size:
                lx = int(round(tx - c2_left))
                ly = int(round(c2_floor - ty))
                init_state = (max(0, min(eff_W - 1, lx)), max(0, min(eff_H - 1, ly)))
            else:
                lx = int(round(tx - c2_left - SOUL_W / 2))
                ly = int(round(c2_floor - ty - SOUL_H / 2))
                init_state = (max(0, min(eff_W - SOUL_W, lx)), max(0, min(eff_H - SOUL_H, ly)))
        else:
            init_state = (max(0, min(eff_W - SOUL_W, int(round(tx)))), max(0, min(eff_H - SOUL_H, int(round(ty)))))
    else:
        init_state = (default_init_x, default_init_y)

    # Output Data Allocations
    O = np.zeros((eff_T, eff_H, eff_W), dtype=bool)
    O_blue = np.zeros((eff_T, eff_H, eff_W), dtype=bool)
    O_orange = np.zeros((eff_T, eff_H, eff_W), dtype=bool)
    platform_table: list[list[PlatformInstance]] = [[] for _ in range(eff_T)]
    slam_frames: list[int] = []
    zone_bounds_history: list[tuple[int, int, int, int]] = []

    # Active Queues
    active_bones: list[_ActiveBone] = []
    active_stabs: list[_ActiveBoneStab] = []
    active_platforms: list[_ActivePlatform] = []
    next_plat_id = 0

    # Index commands by frame
    cmd_bucket: dict[int, list[Any]] = {}
    for cmd in commands:
        frame = getattr(cmd, "frame", 0)
        cmd_bucket.setdefault(frame, []).append(cmd)

    def _calc_velocity(direction: int, speed: float, is_c2: bool) -> tuple[float, float]:
        v = speed / float(fps)
        if direction == 0:    # Right
            return (+v, 0.0)
        elif direction == 1:  # Down
            # In C-space, Down corresponds to negative y
            return (0.0, -v)
        elif direction == 2:  # Left
            return (-v, 0.0)
        elif direction == 3:  # Up
            # In C-space, Up corresponds to positive y
            return (0.0, +v)
        return (0.0, 0.0)

    # ========================================================================
    # Frame-by-Frame Simulation Loop
    # ========================================================================
    for t in range(eff_T):
        # 1. Dispatch New Commands for Frame t
        if t in cmd_bucket:
            for cmd in cmd_bucket[t]:
                cname = getattr(cmd, "cmd_type", getattr(cmd, "name", ""))
                params = getattr(cmd, "params", {})
                args = getattr(cmd, "raw_args", getattr(cmd, "args", []))

                def _get_arg(idx: int, default: Any = 0.0) -> Any:
                    return args[idx] if len(args) > idx and args[idx] != "" else default

                if cname == "SansSlam":
                    slam_frames.append(t)

                elif cname == "BoneV" and (len(args) >= 5 or "height" in params):
                    x = float(params.get("x", _get_arg(0, 0.0)))
                    y = float(params.get("y", _get_arg(1, 0.0)))
                    h = float(params.get("height", _get_arg(2, 0.0)))
                    d = int(float(params.get("direction", _get_arg(3, 0))))
                    spd = float(params.get("speed", _get_arg(4, 0.0)))
                    color = int(float(params.get("color", _get_arg(5, 0))))

                    if h > 0:
                        # Coordinate conversion if in C2 canvas space.
                        #
                        # The CSV's `y` is the bone sprite's bbox TOP in absolute
                        # canvas coordinates (Construct 2 anchors at the top-left),
                        # so its bbox spans [y, y + h] and the local C-space row
                        # range (origin on the floor, y up) is
                        #     [c2_floor - (y + h), c2_floor - y]
                        #
                        # VERIFIED against live sans_bonegap1 at the first damage
                        # tick (tick 290, heart abs (320, 377.96)):
                        #     bone bbox abs [366, 386]  ->  local [-8, 12]
                        #     heart at local y = 0 sits INSIDE that band, which is
                        #     exactly why it takes damage while resting.
                        # Using `c2_floor - y` instead put the band at [12, 32],
                        # ABOVE the heart, and the model then declared a lethal
                        # position safe (measured: HP 92 -> 14 on the real machine).
                        if y > eff_H:
                            lx = x - c2_left
                            ly = c2_floor - (y + h)
                            vx, vy = _calc_velocity(d, spd, is_c2=True)
                        else:
                            lx = x
                            ly = y
                            vx, vy = _calc_velocity(d, spd, is_c2=False)

                        active_bones.append(_ActiveBone(lx, ly, 10.0, h, vx, vy, color, t))

                elif cname == "BoneH" and (len(args) >= 5 or "width" in params):
                    x = float(params.get("x", _get_arg(0, 0.0)))
                    y = float(params.get("y", _get_arg(1, 0.0)))
                    w = float(params.get("width", _get_arg(2, 0.0)))
                    d = int(float(params.get("direction", _get_arg(3, 0))))
                    spd = float(params.get("speed", _get_arg(4, 0.0)))
                    color = int(float(params.get("color", _get_arg(5, 0))))

                    if w > 0:
                        if y > eff_H:
                            lx = x - c2_left
                            ly = c2_floor - (y + 10.0)
                            vx, vy = _calc_velocity(d, spd, is_c2=True)
                        else:
                            lx = x
                            ly = y
                            vx, vy = _calc_velocity(d, spd, is_c2=False)

                        active_bones.append(_ActiveBone(lx, ly, w, 10.0, vx, vy, color, t))

                elif cname == "BoneStab" and (len(args) >= 4 or "height" in params):
                    d = int(float(params.get("direction", _get_arg(0, 1))))
                    h = float(params.get("height", _get_arg(1, 0.0)))
                    warn_t = float(params.get("warn_time", _get_arg(2, 0.0)))
                    stab_t = float(params.get("stab_time", _get_arg(3, 0.0)))
                    if h > 0:
                        active_stabs.append(_ActiveBoneStab(d, h, warn_t, stab_t, t, fps=fps))

                elif cname == "Platform" and (len(args) >= 5 or "width" in params):
                    x = float(params.get("x", _get_arg(0, 0.0)))
                    y = float(params.get("y", _get_arg(1, 0.0)))
                    w = float(params.get("width", _get_arg(2, 0.0)))
                    d = int(float(params.get("direction", _get_arg(3, 0))))
                    spd = float(params.get("speed", _get_arg(4, 0.0)))

                    if y > eff_H:
                        lx = x - c2_left
                        ly = c2_floor - y
                        vx, vy = _calc_velocity(d, spd, is_c2=True)
                    else:
                        lx = x
                        ly = y
                        vx, vy = _calc_velocity(d, spd, is_c2=False)

                    active_platforms.append(_ActivePlatform(next_plat_id, lx, ly, w, vx, vy, t,
                        bool(params.get("reverse", False)),
                        (init_cz[0]-c2_left, init_cz[2]-c2_left) if init_cz else (0, eff_W)))
                    next_plat_id += 1

        # 2. Rasterize Active Bones with Fast Culling
        surviving_bones = []
        for bone in active_bones:
            dt = t - bone.spawn_frame
            x0 = bone.x + bone.vx * dt
            y0 = bone.y + bone.vy * dt
            x1 = x0 + bone.width
            y1 = y0 + bone.height

            # Culling check: completely left the arena in travel direction
            if bone.vx > 0 and x0 >= eff_W:
                continue
            if bone.vx < 0 and x1 <= 0:
                continue
            if bone.vy > 0 and y0 >= eff_H:
                continue
            if bone.vy < 0 and y1 <= 0:
                continue

            surviving_bones.append(bone)

            # Intersection check with arena [0, eff_W) x [0, eff_H)
            if x1 <= 0 or x0 >= eff_W or y1 <= 0 or y0 >= eff_H:
                continue

            # Bone cell coverage.
            #
            # MEASURED against the live engine, sans_bonegap1 tick 290 (the first
            # damage tick): the bone occupies abs [308.738, 318.738], i.e. local
            # [162.738, 172.738] after the c2_left shift, and it DOES hit the
            # heart (4x4 hitbox at abs [318, 322], overlap 0.738 px).
            #
            # `floor(left)..ceil(right)` maps that to cells 162..173 -- correct.
            # But the bone's right edge at 172.738 means the cell span must
            # include 172, and when the fractional part is small the ceil()
            # lands on 172 and the span becomes 162..172, one cell short of what
            # the engine's continuous overlap implies. Taking `floor(left)` and
            # `ceil(right)` and then extending the right by one whenever the
            # right edge is strictly greater than its floor guarantees the cell
            # SPAN covers the bone, at the cost of over-covering by at most one
            # cell -- which can only mark MORE cells dangerous, never fewer.
            ix0 = int(math.floor(x0)) if x0 > 0 else 0
            ix1 = int(math.floor(x1)) + 1
            if ix1 > eff_W:
                ix1 = eff_W

            iy0 = int(math.floor(y0)) if y0 > 0 else 0
            iy1 = int(math.floor(y1)) + 1
            if iy1 > eff_H:
                iy1 = eff_H

            if ix1 > ix0 and iy1 > iy0:
                if bone.color == 1:
                    O_blue[t, iy0:iy1, ix0:ix1] = True
                elif bone.color == 2:
                    O_orange[t, iy0:iy1, ix0:ix1] = True
                else:
                    O[t, iy0:iy1, ix0:ix1] = True

        active_bones = surviving_bones

        # 3. Rasterize Active BoneStabs with Culling
        surviving_stabs = []
        for stab in active_stabs:
            dt = t - stab.spawn_frame
            if dt >= stab.warn_frames + 6 + stab.stab_frames:
                continue  # Stab has finished retraction and died

            surviving_stabs.append(stab)
            depth = stab.get_protrusion_depth(t)
            if depth > 0.0:
                d_int = int(round(depth))
                d_dir = stab.direction

                if d_dir == 1:    # Bottom floor: stabs UPWARD
                    sy0 = 0
                    sy1 = min(eff_H, d_int)
                    if sy1 > sy0:
                        O[t, sy0:sy1, :] = True
                elif d_dir == 3:  # Ceiling: stabs DOWNWARD
                    sy0 = max(0, eff_H - d_int)
                    sy1 = eff_H
                    if sy1 > sy0:
                        O[t, sy0:sy1, :] = True
                elif d_dir == 0:  # Right wall: stabs LEFTWARD
                    sx0 = max(0, eff_W - d_int)
                    sx1 = eff_W
                    if sx1 > sx0:
                        O[t, :, sx0:sx1] = True
                elif d_dir == 2:  # Left wall: stabs RIGHTWARD
                    sx0 = 0
                    sx1 = min(eff_W, d_int)
                    if sx1 > sx0:
                        O[t, :, sx0:sx1] = True

        active_stabs = surviving_stabs

        # 4. Populate PlatformTable[t]
        for plat in active_platforms:
            px, py, pw, pvx = plat.get_state(t)
            platform_table[t].append(
                PlatformInstance(
                    plat_id=plat.plat_id,
                    x_left=float(px),
                    x_right=float(px + pw),
                    y_surf=int(round(py)),
                    vx=float(pvx),
                )
            )

        zone_bounds_history.append((0, eff_W, 0, eff_H))

    # ------------------------------------------------------------------
    # Attack duration, in frames.
    #
    # The scripts carry timestamps in SECONDS and every one ends with an
    # `EndAttack` command (sans_bonegap1 at 6.6 s, sans_bonestab1 at 9.6 s).
    # The solver previously ran with a hard-coded T = 150 frames = 2.5 s, so it
    # only ever planned the first ~38% of a round: sans_bonegap1 needs 397
    # frames and got 150, which is why the extracted "no-hit route" stopped
    # after three jumps and the heart then stood still and was hit for the
    # remaining ~4 s.
    #
    # Derive the horizon from the script itself so a solve covers the whole
    # attack.
    # ------------------------------------------------------------------
    end_times = [c.time_s for c in commands if getattr(c, "cmd_type", "").lower() == "endattack"]
    if end_times:
        duration_s = max(end_times)
    elif commands:
        duration_s = max(c.time_s for c in commands)
    else:
        duration_s = 0.0
    # +1 frame so the closing frame is inside the horizon.
    duration_frames = int(round(duration_s * fps)) + 1

    metadata: dict[str, Any] = {
        "T": eff_T,
        "W": eff_W,
        "H": eff_H,
        "FPS": fps,
        "duration_s": round(duration_s, 4),
        "duration_frames": duration_frames,
        "c2_left": c2_left,
        "c2_floor": c2_floor,
        "slam_frames": list(sorted(set(slam_frames))),
        "initial_state": init_state,
    }

    return RasterResult(
        O=O,
        platform_table=platform_table,
        slam_frames=list(sorted(set(slam_frames))),
        initial_heart_pos=init_state,
        zone_bounds=zone_bounds_history,
        metadata=metadata,
        O_blue=O_blue,
        O_orange=O_orange,
    )


def rasterize_csv(
    csv_path: str | Path,
    config: RasterizerConfig | None = None,
    T: int | None = None,
    W: int | None = None,
    H: int | None = None,
) -> RasterResult:
    """Parses and rasterizes an attack CSV script directly."""
    from .parser import parse_csv_timeline
    commands = parse_csv_timeline(csv_path)
    return rasterize_timeline(commands, config=config, T=T, W=W, H=H)
