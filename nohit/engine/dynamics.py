"""
nohit.engine.dynamics
~~~~~~~~~~~~~~~~~~~~~
5D Forward Discrete Physical Dynamics & Hybrid Jump Physics Stepper.
Implements:
- Feature 10 (HORIZONTAL_DYNAMICS): Walking speed v_walk & platform convection.
- Feature 11 (PIECEWISE_GRAVITY): Jump initiation impulse & piecewise gravity g(uy, tau, vy).
- Feature 12 (INELASTIC_LANDING): Floor & one-way platform surface adsorption.
- Feature 13 (SANS_SLAM_OPERATOR): Exogenous SansSlam phase space collapse operator R_slam.
"""

from __future__ import annotations

from typing import Sequence, Tuple, Union
import numpy as np

from nohit.common.constants import (
    ACTIONS,
    DEFAULT_W,
    DEFAULT_H,
    SOUL_W,
    SOUL_H,
    V_WALK,
    V_JUMP_INIT,
    V_MIN,
    V_MAX,
    G_ASCEND,
    G_DESCEND,
    TAU_MAX,
)
from nohit.engine.c2spec import (
    HEARTSPEED,
    gravity_for_down_speed as _gravity_for_down_speed,
)
from nohit.common.types import Action, ALL_ACTIONS, PlatformInstance, State

# ---------------------------------------------------------------------------
# C2 normalisation constants
# ---------------------------------------------------------------------------
VY_SCALE: int = 40
"""The 5D state stores `vy` as an int, but authoritative gravity steps are only
~0.05 px/frame^2 (180 px/s^2 / 3600). The scale sets how accurately that step
survives integer rounding:

    scale 32  -> 0.05 lands on 1.6 cells -> rounds to 2 cells = 0.0625 (25% err)
    scale 16  -> 0.05 lands on 0.8 cells -> rounds to 1 cell  = 0.0625 (25% err)
    scale 8   -> 0.05 lands on 0.4 cells -> rounds to 0       (gravity lost)

At scale 32 the upward jump reached only 72 px instead of the correct 90 px.
The quantisation floor is set by the packed key: the 10-bit vy field must hold
the whole reachable range [-MaxFallSpeed/60, jump impulse/60] =
[-12.5, +3.0] px/frame, i.e. a span of 15.5, so `VY_SCALE` cannot exceed
about 16 without overflowing the field (see `state.VY_KEY_BIAS`).

This is a genuine precision ceiling of the integer 5D state. A follow-up should
carry vy as a float or sub-pixel fixed point so gravity integrates exactly; the
current accuracy is adequate for whole-pixel hazard planning but biases long
jumps slightly short.

MUST stay in sync with `state.VY_KEY_BIAS`."""

MODEL_FPS: int = 60
"""The model's tick rate. The solver, the stepper and the extracted action
sequence all live at this rate; `tas_runner.js` converts it to engine ticks via
`rt.fps / PLAN_FPS`.

This MUST equal the hazard tensor's rate: the solver indexes the tensor as
`B_hazard[t + 1]`, i.e. one model step consumes exactly one tensor frame. A
mismatch makes the model walk the danger sequence at the wrong speed (that bug
once looked like "60 Hz is unsolvable"). `bake_cspace` now bakes the tensor at
this same rate."""

GRAVITY_HOLD_FALLBACK: float = 450.0
"""Compatibility constant for the (-120, -30] ascent band."""


def gravity_for_down_speed(down_speed: float) -> float | None:
    """Delegates to :mod:`nohit.engine.c2spec` (single source of truth)."""
    return _gravity_for_down_speed(down_speed)


def step_dynamics(
    state: Union[Tuple[int, int, int, int, int], State],
    action: Union[Tuple[int, int], Action],
    platforms: Sequence[PlatformInstance] | None = None,
    is_slam: bool = False,
    W: int = DEFAULT_W,
    H: int = DEFAULT_H,
    w: int = SOUL_W,
    h: int = SOUL_H,
    v_walk: int = V_WALK,
    v_jump_init: int = V_JUMP_INIT,
    physics_mode: str = "docs",
) -> Tuple[int, int, int, int, int]:
    """Computes exact forward discrete physics step f(s, u) or R_slam(f(s, u)).

    Parameters:
      state: 5D micro-state tuple (x, y, vy, kappa, tau) or State instance.
      action: Discrete control action (ux, uy) or Action instance.
      platforms: Sequence of PlatformInstance active on current frame t.
      is_slam: Whether an exogenous SansSlam event occurs on frame t.
      W, H: Arena bounds (default: 200, 160).
      w, h: Soul hitbox dimensions (default: 8, 8).
      v_walk: Horizontal walk displacement (default: 3 px/frame).
      v_jump_init: Initial upward jump impulse velocity (default: 8 px/frame).
      physics_mode: "docs" for discrete benchmark, "c2" for Construct 2 in-game engine.

    Returns:
      Next 5D micro-state tuple (next_x, next_y, next_vy, next_kappa, next_tau).
    """
    x, y, vy, kappa, tau = state
    ux, uy = action
    plat_list = platforms if platforms is not None else ()

    if physics_mode == "c2":
        # ------------------------------------------------------------------
        # Authoritative Construct 2 branch, normalised to a 60 Hz tick.
        #
        # The engine integrates in px-per-SECOND (`dx`, `dy`) and displaces by
        # `dx * dt` (c2runtime.js behinstProto.tick). Sampling at 60 Hz means
        # dt = 1/60, so every source constant converts by dividing by 60 per
        # frame (or 3600 for px/s^2). This is frame-rate independent in the
        # steady state: at 240 Hz the engine simply takes four smaller steps of
        # the same total distance, which the live measurement confirmed
        # (cm.dx = 150 -> 0.5994 px/tick at dt = 0.0042 == 150*dt).
        #
        # The previous constants were exactly 2x too large: HEARTSPEED is
        # 150 px/s (= 2.5 px/frame), not 5 px/frame.
        #
        # `vy` in the state carries an INTENTIONALLY SCALED representation
        # (px/frame * VY_SCALE) because the gravity deltas are ~0.05 px/frame^2
        # and would be lost to integer rounding otherwise.
        # ------------------------------------------------------------------
        v_scale = VY_SCALE
        dt_frames = 1.0 / MODEL_FPS
        speed_frame = v_walk / MODEL_FPS      # 150 px/s -> 2.5 px/frame at 60 Hz

        delta_x_plat = 0.0
        if kappa == 1 and plat_list:
            for plat in plat_list:
                p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
                p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
                p_top = getattr(plat, "y_top", getattr(plat, "y_surf", 0.0))
                if (x + w > p_min) and (x < p_max) and (abs(y - p_top) <= 1.0):
                    delta_x_plat = plat.vx / v_scale
                    break

        raw_x = x + speed_frame * ux + delta_x_plat
        next_x = max(0, min(W - 1, int(round(raw_x))))

        if is_slam:
            return (next_x, 0, 0, 1, 0)

        vy_frames = vy / v_scale           # px/frame (signed, + = upward)

        # ---- BLUE heart jump: hold to rise, release to drop --------------
        # The mechanic, stated by the designer and confirmed verbatim in
        # Battle.xml / InputManagement.xml:
        #
        #   * HOLD to climb   : while VPad.Up == 1 the engine keeps setting
        #                       dy = -HEARTSPEED (150 px/s), so the longer you
        #                       hold the higher you go.
        #   * RELEASE to fall : on the keyup edge it clamps dy to
        #                       -HEART_JUMPHOLD_CUTOFF (30 px/s), so the heart
        #                       starts coming down immediately.
        #   * NO AIR JUMP     : HeartJump fires only on the keydown EDGE
        #                       (VPad.Up > VPad.LastUp), so it can only start
        #                       from the ground.
        #   * FINITE CEILING  : the piecewise gravity ladder plus MaxFallSpeed
        #                       bound the height.
        #
        # Source rules, in order:
        #   WHEN VPad.Up > VPad.LastUp  THEN HeartJump  -> dy -= sin(angle)*180
        #   WHEN VPad.Up == 1           THEN dy = -HEARTSPEED
        #   WHEN VPad.Up < VPad.LastUp  THEN dy = -HEART_JUMPHOLD_CUTOFF
        #
        # The previous revision applied the impulse and then clamped it to the
        # cutoff on the same frame, which deleted the "hold to climb" rule
        # entirely and capped every jump at a ~2 px twitch.
        # ---- coordinate frames --------------------------------------------
        # Construct 2 (and the exported engine) uses SCREEN coordinates: origin
        # top-left, **y growing downward** -- c2runtime.js CollisionPoly_
        # .update_bbox assigns bboxTop to the SMALLER y and bboxBottom to the
        # larger. Live proof: the arena floor is `c2_floor = 378` while the
        # resting heart sits at y = 377.9, so a LARGER absolute y is LOWER.
        #
        # The model's local arena uses the opposite (mathematical) convention:
        #   y = 0 on the floor, larger y = higher, and the hazard tensor is
        #   indexed in that frame.
        #
        # Two frames therefore coexist, and the ONLY place they meet is the
        # state's `vy` field, which follows the engine (its CustomMovement.dy):
        #     vy < 0 rising,  vy > 0 falling
        # Everything inside this function works in LOCAL terms with `vy_up`
        # (+ = rising). Conflating the two is what previously drove the heart
        # into the floor on a jump -- see the sign trap noted below.
        vy_up = -vy / v_scale              # engine dy -> local (+ = rising)

        jump_frame = v_jump_init / MODEL_FPS     # +3.0 px/frame upward
        cutoff_frame = 30.0 / MODEL_FPS          # release clamps the climb to +0.5

        # 1. keydown edge (kappa == 1 == resting, so no air jumps).
        if kappa == 1 and uy == 1:
            vy_up += jump_frame

        # NO per-frame "held" re-assertion: the impulse persists and decays under
        # gravity, so a longer hold climbs higher. Live dy while UP is held:
        # tick 1 -180.00, tick 2 -179.24, ..., tick 15 -165.74 (monotone).

        # 2. released: clamp the climb so the heart falls immediately.
        if uy == 0 and vy_up > cutoff_frame:
            vy_up = cutoff_frame

        # ---- piecewise gravity ladder -------------------------------------
        # The ladder is defined on the engine's DownSpeed = dy (positive when
        # falling), so convert local -> engine for the lookup, then subtract the
        # resulting acceleration (gravity always pulls the heart down).
        down_speed = -vy_up * MODEL_FPS
        g_px_s2 = gravity_for_down_speed(down_speed)
        if g_px_s2 is None:
            # Hold band (-120, -30]: no ladder block matches, so Gravity keeps
            # the value it had. The 5D state has no such slot yet, so reuse a
            # representative ladder value (documented limitation).
            g_px_s2 = GRAVITY_HOLD_FALLBACK
        g_frame = g_px_s2 * dt_frames * dt_frames

        vy_up -= g_frame
        # terminal velocity: MaxFallSpeed = 750 px/s -> 12.5 px/frame downward.
        max_fall_frame = 750.0 / MODEL_FPS
        if vy_up < -max_fall_frame:
            vy_up = -max_fall_frame
        vy_frames = vy_up                  # local alias used by the landing code

        # Sub-pixel carry: `tau` is unused in the c2 branch, so it holds the
        # fractional part of y as round(frac * 10). Without this a 0.45 px/frame
        # hop rounds back to the same pixel every frame and vanishes.
        frac_in = tau / 10.0
        y_next_star = y + frac_in + vy_frames

        # ---- landing ------------------------------------------------------
        surfaces = [0.0]
        if plat_list:
            for plat in plat_list:
                p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
                p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
                p_top = getattr(plat, "y_top", getattr(plat, "y_surf", 0.0))
                if (next_x >= p_min) and (next_x <= p_max):
                    surfaces.append(float(p_top))

        adsorbed = [s for s in surfaces if y >= s and y_next_star <= s]
        if adsorbed:
            y_surf_max = max(adsorbed)
            next_y = int(round(y_surf_max))
            next_vy = 0
            next_kappa = 1
            next_tau = 0          # back on a surface: residual is absorbed
        else:
            next_y = max(0, min(H - 1, int(np.floor(y_next_star))))
            # carry the sub-pixel remainder in tau (0..9)
            next_tau = int(round((y_next_star - np.floor(y_next_star)) * 10.0))
            if next_tau > 9:
                next_tau = 9
            # Store in the ENGINE's sign (state.vy == CustomMovement.dy), which
            # is the negation of the local `vy_up`. Forgetting this flips every
            # airborne frame's velocity on the next read and produces a heart
            # that alternates between 2 px and the floor forever.
            next_vy = int(round(-vy_up * v_scale))
            # kappa is a SINGLE BIT in the packed key (0 = airborne, 1 = resting),
            # so it cannot carry a third "falling" value -- encoding 2 collided
            # with 0 and merged distinct states. Re-triggering is prevented
            # instead by kappa becoming 0 on the very tick the impulse fires, so
            # the gate `kappa == 1 and uy == 1` holds only while still resting.
            next_kappa = 0

        return (next_x, next_y, next_vy, next_kappa, next_tau)

    # -------------------------------------------------------------------------
    # 1. Feature 10: Horizontal Dynamics & Platform Convection
    # -------------------------------------------------------------------------
    delta_x_plat = 0.0
    if kappa == 1 and plat_list:
        for plat in plat_list:
            p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
            p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
            p_top = getattr(plat, "y_top", getattr(plat, "y_surf", 0.0))
            # Soul stands on platform top surface within horizontal interval
            if (x + w > p_min) and (x < p_max) and (abs(y - p_top) <= 1.0):
                delta_x_plat = plat.vx
                break

    raw_x = x + v_walk * ux + delta_x_plat
    next_x = max(0, min(W - w, int(round(raw_x))))

    # -------------------------------------------------------------------------
    # 2. Feature 13: Exogenous SansSlam Reset Operator
    # -------------------------------------------------------------------------
    if is_slam:
        return (next_x, 0, 0, 1, 0)

    # -------------------------------------------------------------------------
    # 3. Feature 11: Piecewise Gravity & Jump Dynamics
    # -------------------------------------------------------------------------
    if kappa == 1 and uy == 1:
        # Ground jump impulse initiation
        v_next_star = v_jump_init
        tau_next = 1
    else:
        # Piecewise gravity in air or grounded release
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

    # -------------------------------------------------------------------------
    # 4. Feature 12: Inelastic Surface Landing & Adsorption
    # -------------------------------------------------------------------------
    surfaces = [0.0]  # Floor y = 0
    if plat_list:
        for plat in plat_list:
            p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
            p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
            p_top = getattr(plat, "y_top", getattr(plat, "y_surf", 0.0))
            if (next_x + w > p_min) and (next_x < p_max):
                surfaces.append(float(p_top))

    # Inelastic collision condition: y >= y_surf and y_next_star <= y_surf
    adsorbed = [s for s in surfaces if y >= s and y_next_star <= s]

    if adsorbed:
        y_surf_max = max(adsorbed)
        next_y = int(round(y_surf_max))
        next_vy = 0
        next_kappa = 1
        next_tau = 0
    else:
        # Free airborne motion with ceiling clamping
        next_y = max(0, min(H - h, y_next_star))
        next_vy = v_next_star
        next_kappa = 0
        next_tau = tau_next

    return (next_x, next_y, next_vy, next_kappa, next_tau)


def step_dynamics_batch(
    states: np.ndarray,
    ux: Union[int, np.ndarray],
    uy: Union[int, np.ndarray],
    platforms: Sequence[PlatformInstance] | None = None,
    is_slam: bool = False,
    W: int = DEFAULT_W,
    H: int = DEFAULT_H,
    w: int = SOUL_W,
    h: int = SOUL_H,
    v_walk: int = V_WALK,
    v_jump_init: int = V_JUMP_INIT,
    physics_mode: str = "docs",
) -> np.ndarray:
    """Vectorized forward dynamics stepper over an array of states (N, 5).

    Supports either scalar control inputs (ux, uy) or vectorized control arrays (N,).
    Returns an (N, 5) int32 array of next states.
    """
    states = np.asarray(states)
    if states.ndim == 1:
        states = states.reshape(1, -1)
    N = states.shape[0]
    if N == 0:
        return np.empty((0, 5), dtype=np.int32)

    x = states[:, 0]
    y = states[:, 1]
    vy = states[:, 2]
    kappa = states[:, 3]
    tau = states[:, 4]

    # Handle control inputs
    if isinstance(ux, np.ndarray) and ux.ndim > 0:
        arr_ux = ux.astype(np.float64)
    else:
        arr_ux = float(ux)

    if isinstance(uy, np.ndarray) and uy.ndim > 0:
        arr_uy = uy.astype(np.int32)
    else:
        arr_uy = int(uy)

    # 1. Platform convection
    delta_x_plat = np.zeros(N, dtype=np.float64)
    plat_list = platforms if platforms is not None else ()
    if plat_list:
        on_ground = (kappa == 1)
        for plat in plat_list:
            p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
            p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
            p_top = getattr(plat, "y_top", getattr(plat, "y_surf", 0.0))
            mask = on_ground & (x + w > p_min) & (x < p_max) & (np.abs(y - p_top) <= 1.0) & (delta_x_plat == 0.0)
            delta_x_plat[mask] = plat.vx

    if physics_mode == "c2":
        # Mirrors the scalar c2 branch exactly; see its comment block for the
        # 60 Hz normalisation rationale and the jump-impulse semantics.
        v_scale = float(VY_SCALE)
        dt_frames = 1.0 / MODEL_FPS
        speed_frame = v_walk / MODEL_FPS    # 150 px/s -> 2.5 px/frame at 60 Hz

        raw_x = x.astype(np.float64) + speed_frame * arr_ux + delta_x_plat / v_scale
        next_x = np.clip(np.round(raw_x).astype(np.int32), 0, W - 1)

        if is_slam:
            out = np.zeros((N, 5), dtype=np.int32)
            out[:, 0] = next_x
            out[:, 3] = 1
            return out

        # State `vy` follows the ENGINE (CustomMovement.dy): negative = rising.
        # Internally we work in LOCAL terms with `vy_up` (+ = rising), then flip
        # back at the storage boundary. See the scalar branch for the full
        # derivation of the two coordinate frames.
        vy_up = -vy.astype(np.float64) / v_scale

        # Jump impulse on the keydown edge; `kappa` is 1 only while resting,
        # which enforces "no air jumps". The impulse persists and decays under
        # gravity (it is NOT clamped on the frame it is applied), so holding
        # longer climbs higher.
        jump_frame = float(v_jump_init) / MODEL_FPS
        cutoff_frame_b = 30.0 / MODEL_FPS
        jumped = (kappa == 1) & (arr_uy == 1)
        vy_up = np.where(jumped, vy_up + jump_frame, vy_up)

        # Release: clamp the climb so the heart starts falling immediately.
        vy_up = np.where((arr_uy == 0) & (vy_up > cutoff_frame_b),
                         cutoff_frame_b, vy_up)

        # Piecewise gravity ladder, selected on the engine's DownSpeed = dy
        # (positive when falling). Gravity always pulls DOWN, so it is
        # subtracted from the local upward velocity.
        down_speed = -vy_up * MODEL_FPS
        g_px_s2 = np.select(
            [(down_speed > 15.0) & (down_speed < 240.0),
             (down_speed > -30.0) & (down_speed <= 15.0),
             (down_speed > -120.0) & (down_speed <= -30.0),
             down_speed <= -120.0],
            [540.0, 180.0, 450.0, 180.0],
            default=0.0,
        )
        g_frame = g_px_s2 * dt_frames * dt_frames
        vy_up = vy_up - g_frame
        vy_up = np.maximum(-(750.0 / MODEL_FPS), vy_up)
        vy_frames = vy_up

        # Sub-pixel carry (batch): `tau` is unused in the c2 branch, so it holds
        # the fractional part of y as round(frac * 10). Without this a
        # 0.45 px/frame hop rounds back to the same pixel every frame and
        # vanishes, which loses the ~4 px jump some levels require.
        frac_in = tau.astype(np.float64) / 10.0
        y_star = y.astype(np.float64) + frac_in + vy_frames

        floor_land = (y >= 0.0) & (y_star <= 0.0)
        best_surf = np.full(N, -1.0, dtype=np.float64)
        best_surf[floor_land] = 0.0

        if plat_list:
            for plat in plat_list:
                p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
                p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
                p_top = float(getattr(plat, "y_top", getattr(plat, "y_surf", 0.0)))
                p_mask = (next_x >= p_min) & (next_x <= p_max) & (y >= p_top) & (y_star <= p_top)
                best_surf = np.where(p_mask & (p_top > best_surf), p_top, best_surf)

        landed = best_surf >= 0.0
        y_floor = np.floor(y_star)
        next_y = np.where(
            landed,
            np.round(best_surf).astype(np.int32),
            np.clip(y_floor.astype(np.int32), 0, H - 1),
        )
        # Store in the ENGINE's sign (state.vy == CustomMovement.dy), i.e. the
        # negation of the local upward velocity -- see the scalar branch.
        next_vy = np.where(landed, 0, np.round(-vy_frames * v_scale)).astype(np.int32)
        # kappa is 1 bit: 1 = resting, 0 = airborne (no third state, see the
        # scalar branch comment).
        next_kappa = np.where(landed, 1, 0).astype(np.int32)
        # Airborne states carry the sub-pixel remainder of y in tau (0..9);
        # landing absorbs it.
        frac_out = np.round((y_star - y_floor) * 10.0).astype(np.int32)
        next_tau = np.where(landed, 0, np.clip(frac_out, 0, 9)).astype(np.int32)

        # Write straight into one int32 buffer instead of np.column_stack plus
        # .astype, which allocated a fresh array and 5 temporaries every frame
        # (measured ~180 ms of a ~1 s open-arena solve at 30 Hz).
        out = np.empty((N, 5), dtype=np.int32)
        out[:, 0] = next_x
        out[:, 1] = next_y
        out[:, 2] = next_vy
        out[:, 3] = next_kappa
        out[:, 4] = next_tau
        return out

    raw_x = x.astype(np.float64) + v_walk * arr_ux + delta_x_plat
    next_x = np.clip(np.round(raw_x).astype(np.int32), 0, W - w)

    # 2. SansSlam
    if is_slam:
        out = np.zeros((N, 5), dtype=np.int32)
        out[:, 0] = next_x
        out[:, 3] = 1
        return out

    # 3. Vertical dynamics
    ground_jump_mask = (kappa == 1) & (arr_uy == 1)
    is_ascend = (arr_uy == 1) & (tau < TAU_MAX) & (vy > 0)
    g = np.where(is_ascend, G_ASCEND, G_DESCEND)
    v_grav = np.clip(vy - g, V_MIN, V_MAX)
    tau_inc = np.where((kappa == 0) & (arr_uy == 1) & (tau < TAU_MAX), tau + 1, TAU_MAX)

    v_star = np.where(ground_jump_mask, v_jump_init, v_grav)
    tau_next = np.where(ground_jump_mask, 1, tau_inc)
    y_star = y + v_star

    # 4. Inelastic landing detection
    floor_land = (y >= 0.0) & (y_star <= 0.0)
    best_surf = np.full(N, -1.0, dtype=np.float64)
    best_surf[floor_land] = 0.0

    if plat_list:
        for plat in plat_list:
            p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
            p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
            p_top = float(getattr(plat, "y_top", getattr(plat, "y_surf", 0.0)))
            p_mask = (next_x + w > p_min) & (next_x < p_max) & (y >= p_top) & (y_star <= p_top)
            best_surf = np.where(p_mask & (p_top > best_surf), p_top, best_surf)

    landed = best_surf >= 0.0
    next_y = np.where(landed, np.round(best_surf).astype(np.int32), np.clip(y_star, 0, H - h))
    next_vy = np.where(landed, 0, v_star).astype(np.int32)
    next_kappa = np.where(landed, 1, 0).astype(np.int32)
    next_tau = np.where(landed, 0, tau_next).astype(np.int32)

    return np.column_stack([next_x, next_y, next_vy, next_kappa, next_tau]).astype(np.int32)


__all__ = [
    "step_dynamics",
    "step_dynamics_batch",
    "Action",
    "ALL_ACTIONS",
]
