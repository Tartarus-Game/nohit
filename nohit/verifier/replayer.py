"""
nohit.verifier.replayer
~~~~~~~~~~~~~~~~~~~~~~~
Strict forward kinematic trajectory simulation and collision re-verification.
Enforces that witness action sequences pi* produced by the DP solver
strictly abide by physical dynamics and collision safety on every single frame.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple
import numpy as np

from nohit.common.constants import (
    DEFAULT_W,
    DEFAULT_H,
    SOUL_W,
    SOUL_H,
    V_WALK,
    V_JUMP_INIT,
    ACTIONS,
)
from nohit.common.types import (
    Action,
    BakeResult,
    PlatformInstance,
    VerificationResult,
)
from nohit.engine.dynamics import step_dynamics


def arena_bounds(
    physics_mode: str,
    W: int,
    H: int,
    soul_w: int = SOUL_W,
    soul_h: int = SOUL_H,
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Returns the legal inclusive ``((x_min, x_max), (y_min, y_max))`` anchor range.

    ``physics_mode`` is validated by the caller.
    """
    if physics_mode == "c2":
        # Construct 2 anchors the soul on its centre, so the raw pixel grid is
        # the legal domain and W - 1 / H - 1 are the last reachable anchors.
        return (0, W - 1), (0, H - 1)
    return (0, W - soul_w), (0, H - soul_h)


def replay_and_verify(
    bake_result: BakeResult,
    action_sequence: Sequence[Tuple[int, int] | Action],
) -> VerificationResult:
    """Simulates an action sequence forward in the exact discrete physical model.

    Parameters
    ----------
    bake_result : BakeResult
        Contains B_hazard, platform_table, initial_state, and metadata.
    action_sequence : Sequence[Tuple[int, int] | Action]
        Control actions of length T - 1 (or T).

    Returns
    -------
    VerificationResult
        passed (bool), collision_frames (List[int]), kinematic_errors (List[str]),
        simulated_trajectory (List[5D states]).
    """
    B_hazard = bake_result.B_hazard
    T, H, W = B_hazard.shape
    platform_table = bake_result.platform_table
    metadata = getattr(bake_result, "metadata", None) or {}
    slam_frames = set(metadata.get("slam_frames", []))

    actions: List[Tuple[int, int]] = []
    for act in action_sequence:
        if isinstance(act, Action):
            actions.append((act.ux, act.uy))
        else:
            actions.append((int(act[0]), int(act[1])))

    if len(actions) != T - 1 and len(actions) != T:
        return VerificationResult(
            passed=False,
            collision_frames=[],
            kinematic_errors=[f"Action sequence length {len(actions)} does not match T-1 ({T-1}) or T ({T})"],
            simulated_trajectory=[],
        )

    x0, y0 = int(bake_result.initial_state[0]), int(bake_result.initial_state[1])
    current_state = (x0, y0, 0, 1, 0)
    sim_trajectory: List[Tuple[int, int, int, int, int]] = [current_state]
    collision_frames: List[int] = []
    kinematic_errors: List[str] = []

    # Frame 0 Collision Check
    if B_hazard[0, y0, x0]:
        collision_frames.append(0)

    soul_w, soul_h = metadata.get("soul_size", (SOUL_W, SOUL_H))
    v_walk = metadata.get("v_walk", V_WALK)
    v_jump_init = metadata.get("v_jump", V_JUMP_INIT)
    physics_mode = metadata.get("physics_mode", "docs")
    if physics_mode not in ("docs", "c2"):
        return VerificationResult(
            passed=False,
            collision_frames=[],
            kinematic_errors=[f"Unknown physics_mode {physics_mode!r}; expected 'docs' or 'c2'"],
            simulated_trajectory=[],
        )
    (x_lo, x_hi), (y_lo, y_hi) = arena_bounds(physics_mode, W, H, soul_w, soul_h)
    B_blue = metadata.get("B_blue")
    B_orange = metadata.get("B_orange")

    for t in range(len(actions)):
        act = actions[t]
        if act not in ACTIONS:
            kinematic_errors.append(f"Frame {t}: Invalid action {act} not in alphabet U")

        is_slam = (t in slam_frames)
        plat_t = platform_table[t] if t < len(platform_table) else ()

        next_state = step_dynamics(
            current_state,
            act,
            platforms=plat_t,
            is_slam=is_slam,
            W=W,
            H=H,
            w=soul_w,
            h=soul_h,
            v_walk=v_walk,
            v_jump_init=v_jump_init,
            physics_mode=physics_mode,
        )
        sim_trajectory.append(next_state)
        nx, ny, nvy, nkappa, ntau = next_state

        # Check bounds against the physics-mode anchor domain
        if not (x_lo <= nx <= x_hi):
            kinematic_errors.append(f"Frame {t+1}: x={nx} out of bounds [{x_lo}, {x_hi}]")
        if not (y_lo <= ny <= y_hi):
            kinematic_errors.append(f"Frame {t+1}: y={ny} out of bounds [{y_lo}, {y_hi}]")

        # Check hazard collision
        is_hit = False
        if t + 1 < T:
            if B_hazard[t + 1, ny, nx]:
                is_hit = True
            elif B_blue is not None and t + 1 < len(B_blue):
                is_moving = (act[0] != 0) or (nvy != 0) or (nkappa == 0)
                if B_blue[t + 1, ny, nx] and is_moving:
                    is_hit = True
            elif B_orange is not None and t + 1 < len(B_orange):
                is_moving = (act[0] != 0) or (nvy != 0) or (nkappa == 0)
                if B_orange[t + 1, ny, nx] and not is_moving:
                    is_hit = True

        if is_hit:
            collision_frames.append(t + 1)

        current_state = next_state

    passed = (len(collision_frames) == 0 and len(kinematic_errors) == 0)
    return VerificationResult(
        passed=passed,
        collision_frames=collision_frames,
        kinematic_errors=kinematic_errors,
        simulated_trajectory=sim_trajectory,
    )


__all__ = [
    "replay_and_verify",
    "arena_bounds",
]
