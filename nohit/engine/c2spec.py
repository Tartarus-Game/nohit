"""
nohit.engine.c2spec
~~~~~~~~~~~~~~~~~~~
Machine-readable specification of the AUTHORITATIVE Construct 2 player physics.

Sources, in priority order (per the project owner: ``repo_badtime`` is the
authoritative source and ``c2-sans-fight`` is an older post-compiled export):

  * ``repo_badtime/Event sheets/Battle.xml``      (group ``PlayerMovement``)
  * ``repo_badtime/Event sheets/InputManagement.xml``
  * ``c2-sans-fight/c2runtime.js``                (the CustomMovement behaviour
    implementation the event sheet's ``Set speed`` calls land in)

Why this module exists
----------------------
``nohit/baker/rasterizer.py`` models the heart as "position += 5 px per frame,
immediately". The engine does something structurally different, and that is the
root of "the motion model and the settlement model disagree":

1. **Movement goes through the CustomMovement behaviour, never through absolute
   positioning.** The event sheet only calls ``Set speed(axis, v)`` with ``v``
   in **px per second**; the displacement happens in the behaviour's ``tick``.

       mx = dx * dt          # dt is wall-clock derived
       my = dy * dt
       stepMode 2 -> step(mx, 0, HORIZ_STEP_EVENT); cancelStep = 0
                     step(0, my, VERT_STEP_EVENT)

2. **A step is sub-divided and can be cancelled mid-way.** ``step()`` splits the
   move into ``round(hypot(x,y)/pxPerStep)`` sub-steps (at least 1), moving to
   ``start + delta*(i/steps)`` and firing the step event at EACH sub-position.
   If the event sheet reacts by setting ``cancelStep``:

       cancelStep = 1 -> roll back one sub-step and stop  (blocked contact)
       cancelStep = 2 -> stop at the current sub-position

   This per-sub-step contact loop is exactly what the event sheet uses to stop
   the heart against solids (Battle.xml blocks 7.1/7.2 and 8.1/8.2 set the axis
   speed to 0 and ``Stop stepping``). An "immediate 5 px hop" model cannot
   express it, and it changes which cells the heart can actually occupy.

3. **Gravity is ``Gravity * dt`` applied to velocity, with a 4-segment ladder**
   keyed on ``DownSpeed`` -- the velocity component along the heart's facing
   axis. The ladder is evaluated in document order, so the first match wins, and
   the (-120, -30] band uses 450 px/s^2. XML comparison 3 is <= and
   comparison 4 is >; reversing these produced an incorrect transcription.

4. **The per-frame order of operations is fixed**: solid probe -> speed
   assignment -> platform probe/snap -> horizontal step -> reset cancelStep ->
   vertical step. The sub-step contact handling means horizontal contact is
   resolved before the vertical move is even attempted.

5. **Landing is fractional.** The platform contact path writes
   ``Set Y = Platform1.BBoxTop - 8.05``; the rasterizer anchors the floor on an
   integer ``c2_floor``. The live export was measured resting at
   ``y = 377.9396`` (non-integer), confirming the fractional rule.

6. **Keyboard input is only read in practice / single-attack mode.** In the
   default ``SimulatorMode = MODE_NORMAL`` the heart is not player-controlled, so
   keyboard injection produces no motion at all -- a calibration that drives keys
   in normal mode measures nothing.

Measured facts from the running export (``c2-sans-fight``):
  * ``PlayerHeart`` sprite is **16 x 20** (not square); the colliding object is
    the separate 4 x 4 ``PlayerHitbox`` re-centred on it every tick.
  * ``CustomMovement`` properties on ``t55`` are ``[2, 1, 1]`` i.e.
    ``stepMode = 2`` (horizontal then vertical), ``pxPerStep = 1``.
  * The runtime ran at ``fps = 240`` with ``dt1`` around 0.0042, so ``dt`` is
    NOT 1/60 unless it is pinned (``rt.timescale = (1/60)/rt.dt1``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# ---------------------------------------------------------------------------
# Constants transcribed from the authoritative event sheets
# ---------------------------------------------------------------------------
FPS_NOMINAL: Final[int] = 60
"""Construct 2's default tick rate, used only to express px/s constants in the
px/frame unit the existing steppers work in. The real timestep is wall-clock
derived, so this is NOT the engine's actual ``dt``."""

HEARTSPEED: Final[float] = 150.0
"""``Set speed(axis, +-HEARTSPEED)`` for RED-mode movement, px/s.

The current ``docs``/``c2`` steppers use 5 px/frame (== 300 px/s at 60 Hz),
which is double the source value. Part of the motion-model gap.
"""

HEART_JUMP_STRENGTH: Final[float] = 180.0
"""Jump impulse: ``Set speed(axis, speed - component*180)``, px/s."""

HEART_JUMPHOLD_CUTOFF: Final[float] = 30.0
"""Clamp applied while the direction key is held: ``Set speed == -30`` px/s."""

MAX_FALL_SPEED_DEFAULT: Final[float] = 750.0
"""``MaxFallSpeed``, px/s. Per-attack override via ``HeartMaxFallSpeed``."""

PLATFORM_LAND_OFFSET: Final[float] = 8.05
"""``Set Y = Platform1.BBoxTop - 8.05`` on the vertical approach; the mirrored
``+ 8.05`` form is used from below. Fractional by construction."""

HEART_SPRITE_SIZE: Final[tuple[int, int]] = (16, 20)
"""Measured live: ``PlayerHeart.width x .height``."""

HITBOX_SIZE: Final[int] = 4
"""``PlayerHitbox`` is created 4x4 and re-centred on PlayerHeart every tick."""

CUSTOM_MOVEMENT_PROPS: Final[tuple[int, int, int]] = (2, 1, 1)
"""``t55.behavior_insts[0].properties`` measured live:
``stepMode = 2`` (horizontal then vertical), ``speed = 1``, ``pxPerStep = 1``."""


@dataclass(frozen=True, slots=True)
class GravitySegment:
    """One segment of the ``DownSpeed -> Gravity`` ladder.

    ``lower`` is EXCLUSIVE and ``upper`` INCLUSIVE, matching the source's
    ``DownSpeed > lower AND DownSpeed <= upper`` condition pairs. ``None`` means
    unbounded on that side.
    """

    lower: float | None
    upper: float | None
    gravity: float
    source_block: str


GRAVITY_LADDER: Final[tuple[GravitySegment, ...]] = (
    GravitySegment(15.0, 240.0, 540.0, "12.4 15<DownSpeed<240 (strict upper bound)"),
    GravitySegment(-30.0, 15.0, 180.0, "12.5 -30<DownSpeed<=15"),
    GravitySegment(-120.0, -30.0, 450.0, "12.6 -120<DownSpeed<=-30"),
    GravitySegment(None, -120.0, 180.0, "12.7 DownSpeed<=-120"),
)
"""Piecewise gravity, px/s^2.

The falling threshold is 15 px/s, corroborated by real-game velocity traces.
The remaining bounds are transcribed from Battle.xml with comparison IDs decoded.
"""

GRAVITY_HOLD_BAND: Final[tuple[float, float]] = (-120.0, -30.0)
"""Historical name for the (-120, -30] ascent band; gravity is 450."""

GRAVITY_INITIAL: Final[float] = 0.0
"""Initial sheet-local value before the movement event selects a segment."""


@dataclass(frozen=True, slots=True)
class FrameOrderStep:
    order: int
    name: str
    detail: str


FRAME_ORDER: Final[tuple[FrameOrderStep, ...]] = (
    FrameOrderStep(
        1,
        "solid_probe",
        "HeartCheckSolid(cos(angle)*0.2, sin(angle)*0.2) gates the gravity "
        "application (block 12.9): a solid ahead suppresses the whole gravity "
        "term for that tick.",
    ),
    FrameOrderStep(
        2,
        "speed_assignment",
        "HORIZONTAL: for RED, VPad.Left vs VPad.Right -> Set speed(1, "
        "+-HEARTSPEED) or 0 (blocks 11.2/11.3). VERTICAL: RED forces speed(2)=0; "
        "BLUE adds component*Gravity*dt and clamps to +-MaxFallSpeed (12.9).",
    ),
    FrameOrderStep(
        3,
        "platform_probe_and_snap",
        "Is overlapping at offset Platform1 (12.10/12.11). On contact the heart "
        "adopts the platform velocity AND Y is snapped to BBoxTop -+ 8.05.",
    ),
    FrameOrderStep(
        4,
        "horizontal_step",
        "CustomMovement stepMode 2: step(dx*dt, 0, HORIZ_STEP_EVENT). Sub-divided "
        "into round(|dx*dt|/pxPerStep) sub-steps; the event sheet may cancel.",
    ),
    FrameOrderStep(
        5,
        "reset_cancel_step",
        "cancelStep := 0 between the two axes (c2runtime.js:23029).",
    ),
    FrameOrderStep(
        6,
        "vertical_step",
        "step(0, dy*dt, VERT_STEP_EVENT), same sub-step contract.",
    ),
)


def gravity_for_down_speed(down_speed: float) -> float | None:
    """Effective gravity (px/s^2) for ``down_speed``.

    Uses the four non-overlapping bands in the actual movement event sheet.
    """
    if 15.0 < down_speed < 240.0:
        return 540.0
    if down_speed >= 240.0:
        return 0.0
    if -30.0 < down_speed <= 15.0:
        return 180.0
    if -120.0 < down_speed <= -30.0:
        return 450.0
    return 180.0


def sub_step_count(distance: float, px_per_step: int = 1) -> int:
    """``round(|distance| / pxPerStep)`` clamped to a minimum of 1.

    Mirrors ``behinstProto.step`` (c2runtime.js:22989-22991): a non-zero move is
    always taken in at least one sub-step, and the event sheet sees a collision
    trigger at every sub-position.
    """
    if distance == 0:
        return 0
    steps = round(abs(distance) / max(1, px_per_step))
    return max(1, steps)


__all__ = [
    "CUSTOM_MOVEMENT_PROPS",
    "FPS_NOMINAL",
    "FRAME_ORDER",
    "GRAVITY_HOLD_BAND",
    "GRAVITY_INITIAL",
    "GRAVITY_LADDER",
    "HEARTSPEED",
    "HEART_JUMPHOLD_CUTOFF",
    "HEART_JUMP_STRENGTH",
    "HEART_SPRITE_SIZE",
    "HITBOX_SIZE",
    "MAX_FALL_SPEED_DEFAULT",
    "PLATFORM_LAND_OFFSET",
    "FrameOrderStep",
    "GravitySegment",
    "gravity_for_down_speed",
    "sub_step_count",
]
