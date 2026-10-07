"""
nohit.engine.c2step
~~~~~~~~~~~~~~~~~~~
Authoritative Construct 2 player stepper.

Implements the per-frame semantics described in :mod:`nohit.engine.c2spec`
rather than the "position += 5 px" shortcut used by
:mod:`nohit.engine.dynamics`:

  * velocity state (``dx``, ``dy`` in px/s) carried between ticks;
  * displacement ``dx*dt`` / ``dy*dt``, split into ``round(|d|/pxPerStep)``
    sub-steps with a collision probe at EVERY sub-position (swept contact);
  * fixed frame order: solid probe -> speed assignment -> platform probe/snap ->
    horizontal step -> reset cancelStep -> vertical step;
  * the 4-segment gravity ladder with its hold band;
  * fractional landing via ``PLATFORM_LAND_OFFSET``.

State layout
------------
``(x, y, dx, dy, kappa, gravity, facing)`` where

  ``x, y``      heart centre, in the same C-space frame as the rasterizer
                (``x = c2_x - c2_left``, ``y = c2_floor - c2_y``);
  ``dx, dy``    CustomMovement velocities, px/s, in C-space sign convention
                (``dy`` negative == falling);
  ``kappa``     1 while resting on floor/platform, 0 while airborne;
  ``gravity``   last applied gravity, px/s^2 (retained across the hold band);
  ``facing``    cosmetic angle in degrees (90 = facing down), kept so the
                caller can reproduce the source's DownSpeed component.
"""

from __future__ import annotations

from typing import Sequence, Tuple

from nohit.common.types import PlatformInstance
from nohit.engine import c2spec

C2State = Tuple[float, float, float, float, int, float, float]

__all__ = [
    "C2State",
    "initial_state",
    "step_c2",
]


def initial_state(x: float, y: float) -> C2State:
    """Resting state: no velocity, on the ground, no accumulated gravity."""
    return (float(x), float(y), 0.0, 0.0, 1, c2spec.GRAVITY_INITIAL, 90.0)


def _solids_at(
    x: float,
    y: float,
    platforms: Sequence[PlatformInstance],
    arena_w: float,
    arena_h: float,
) -> bool:
    """Stand-in for ``HeartCheckSolid`` -- true when the heart centre is outside
    the arena or inside a platform's solid span.

    The real function overlaps the 4x4 ``PlayerHitbox`` against
    ``CombatZoneBorder`` and ``Platform1``. Using the centre against the platform
    span is the same contract the rasterizer already assumes for floor/ceiling
    contacts.
    """
    if x < 0.0 or x > arena_w or y < 0.0 or y > arena_h:
        return True
    for plat in platforms:
        p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
        p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
        p_top = getattr(plat, "y_top", getattr(plat, "y_surf", 0.0))
        if p_min <= x <= p_max and y <= p_top:
            return True
    return False


def step_c2(
    state: C2State,
    ux: int,
    uy: int,
    *,
    platforms: Sequence[PlatformInstance] | None = None,
    dt: float = 1.0 / c2spec.FPS_NOMINAL,
    arena_w: float = 1.0e9,
    arena_h: float = 1.0e9,
    heart_speed: float = c2spec.HEARTSPEED,
    jump_strength: float = c2spec.HEART_JUMP_STRENGTH,
    jump_hold_cutoff: float = c2spec.HEART_JUMPHOLD_CUTOFF,
    max_fall_speed: float = c2spec.MAX_FALL_SPEED_DEFAULT,
    is_blue: bool = True,
    is_slam: bool = False,
) -> C2State:
    """Advances one tick with the authoritative semantics.

    Parameters
    ----------
    state
        ``(x, y, dx, dy, kappa, gravity, facing)``.
    ux, uy
        Discrete control, ``-1/0/1``. Under ``is_blue`` the heart's facing axis
        (``facing``) decides which of ``ux``/``uy`` is the "walk" axis and which
        is the "jump" axis: the source only ever moves along the facing axis.
    is_blue
        ``False`` reproduces ``HEARTMODE_RED`` (angle-locked 4-way movement with
        ``dy`` forced to 0 when facing down/up); ``True`` reproduces
        ``HEARTMODE_BLUE`` (gravity along the facing axis).
    is_slam
        ``SansSlam`` resets the heart to the arena origin with the slam speeds,
        matching the source's ``Set speed(1/2, cos/sin(angle)*MaxFallSpeed)``.
    """
    x, y, dx, dy, kappa, gravity, facing = state
    plat = tuple(platforms) if platforms else ()
    angle = facing % 360.0
    ax_cos = _cos(angle)
    ax_sin = _sin(angle)

    if is_slam:
        return (0.0, 0.0, ax_cos * max_fall_speed, ax_sin * max_fall_speed, 0, gravity, facing)

    # ---- 1/2. speed assignment -------------------------------------------
    if is_blue:
        # DownSpeed = the velocity component along the facing axis.
        down_speed = dx * ax_cos + dy * ax_sin
        g = c2spec.gravity_for_down_speed(down_speed)
        if g is not None:
            gravity = g

        # 12.9: a solid slightly ahead suppresses the gravity term entirely.
        probe_x = ax_cos * 0.2
        probe_y = -ax_sin * 0.2  # C-space y is inverted vs C2 screen y
        if not _solids_at(x + probe_x, y + probe_y, plat, arena_w, arena_h):
            dx += ax_cos * gravity * dt
            dy -= ax_sin * gravity * dt

        # MaxFallSpeed clamp along the facing axis.
        if angle == 90.0:      # C2 "down" -> C-space -y
            if dy < -max_fall_speed:
                dy = -max_fall_speed
        elif angle == 270.0:
            if dy > max_fall_speed:
                dy = max_fall_speed
        elif angle in (0.0, 180.0):
            if abs(dx) > max_fall_speed:
                dx = max_fall_speed if dx > 0 else -max_fall_speed

        # Jump / walk along the facing axis.
        moving_axis = abs(dx) if angle in (0.0, 180.0) else abs(dy)
        if uy != 0:
            # jump press: impulse if not blocked
            if not _solids_at(x + ax_cos * 0.2, y - ax_sin * 0.2, plat, arena_w, arena_h):
                if angle in (0.0, 180.0):
                    dx -= ax_cos * jump_strength
                else:
                    dy += ax_sin * jump_strength
        elif ux != 0:
            if angle in (0.0, 180.0):
                dx += ax_cos * heart_speed * ux
            else:
                dy -= ax_sin * heart_speed * ux
        _ = moving_axis
    else:
        # HEARTMODE_RED: angle locked to 90 (facing down).
        dy = 0.0
        dx = heart_speed * ux
        _ = uy, kappa, jump_hold_cutoff

    # ---- 3. platform probe and fractional snap ----------------------------
    for plat_i in plat:
        p_min = getattr(plat_i, "x_min", getattr(plat_i, "x_left", 0.0))
        p_max = getattr(plat_i, "x_max", getattr(plat_i, "x_right", 0.0))
        p_top = float(getattr(plat_i, "y_top", getattr(plat_i, "y_surf", 0.0)))
        halo = c2spec.PLATFORM_LAND_OFFSET
        if p_min <= x <= p_max and abs(y - p_top) <= halo and dy <= 0.0:
            y = p_top + halo
            dx = float(getattr(plat_i, "vx", 0.0))
            dy = float(getattr(plat_i, "vy", 0.0)) if hasattr(plat_i, "vy") else 0.0
            kappa = 1
            break

    # ---- 4. horizontal step (swept, cancellable) --------------------------
    mx = dx * dt
    my = -dy * dt  # C-space y grows upward, C2 dy grows downward
    x, dx, blocked_x = _swept_axis(
        x, y, mx, plat, arena_w, arena_h, axis="x"
    )
    if blocked_x:
        dx = 0.0
        kappa = 1

    # ---- 6. vertical step --------------------------------------------------
    y, dy_after, blocked_y = _swept_axis(
        x, y, my, plat, arena_w, arena_h, axis="y"
    )
    if blocked_y:
        dy = 0.0
        kappa = 1
    else:
        kappa = 0
    _ = dy_after

    return (x, y, dx, dy, kappa, gravity, facing)


def _swept_axis(
    x: float,
    y: float,
    move: float,
    platforms: Sequence[PlatformInstance],
    arena_w: float,
    arena_h: float,
    *,
    axis: str,
) -> tuple[float, float, bool]:
    """Moves the heart along one axis in ``pxPerStep`` sub-steps, probing each
    sub-position; returns ``(new_value, unused, blocked)``.

    Mirrors ``behinstProto.step`` (c2runtime.js:22983-23010): every sub-position
    ``start + move*(i/steps)`` is probed, and a blocked sub-step rolls back to
    the previous free sub-position (``cancelStep === 1``). When nothing blocks,
    the position ends at the EXACT target ``start + move`` -- the loop's last
    assignment is ``i === steps``, i.e. ``prog === 1``.
    """
    if move == 0.0:
        return (x if axis == "x" else y, 0.0, False)

    px_per_step = c2spec.CUSTOM_MOVEMENT_PROPS[2]
    steps = c2spec.sub_step_count(move, px_per_step)
    last = x if axis == "x" else y
    for i in range(1, steps + 1):
        prog = i / steps
        if axis == "x":
            nx, ny = x + move * prog, y
        else:
            nx, ny = x, y + move * prog
        if _solids_at(nx, ny, platforms, arena_w, arena_h):
            # roll back one sub-step and stop (cancelStep === 1)
            return (last, 0.0, True)
        last = nx if axis == "x" else ny
    # Unblocked: the loop's final iteration sits exactly on the target.
    target = (x + move) if axis == "x" else (y + move)
    return (target, 0.0, False)


def _cos(deg: float) -> float:
    import math

    return math.cos(math.radians(deg))


def _sin(deg: float) -> float:
    import math

    return math.sin(math.radians(deg))
