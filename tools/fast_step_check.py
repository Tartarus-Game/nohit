"""Scalar fast-path stepper for the A* planner, with an equivalence harness.

`step_dynamics_batch` costs ~0.7 ms per call on a 1-row input because of numpy
dispatch overhead, which dominates the A* loop (92k expansions -> 71 s). This
module re-derives the *same* c2 transition arithmetically, with no numpy, and
carries a self-check so the two can never silently diverge.

Usage:
  python tools/fast_step_check.py [n_random]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nohit.engine.dynamics import MODEL_FPS, VY_SCALE, step_dynamics_batch  # noqa: E402


def step_one_c2(
    x: int, y: int, vy: int, kappa: int, tau: int,
    ux: int, uy: int,
    W: int, H: int,
    v_walk: int = 150, v_jump_init: int = 180,
    platforms=(),
) -> tuple[int, int, int, int, int]:
    """Exactly mirrors `step_dynamics_batch`'s `physics_mode == "c2"` branch.

    Keep this in lock-step with dynamics.py:416-508. The harness below fails
    loudly if they ever disagree.
    """
    v_scale = float(VY_SCALE)
    dt_frames = 1.0 / MODEL_FPS
    speed_frame = v_walk / MODEL_FPS

    delta_x_plat = 0.0
    if platforms:
        on_ground = kappa == 1
        for plat in platforms:
            p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
            p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
            p_top = getattr(plat, "y_top", getattr(plat, "y_surf", 0.0))
            if on_ground and (x + 4 > p_min) and (x < p_max) and (abs(y - p_top) <= 1.0):
                delta_x_plat = plat.vx
                break

    raw_x = x + speed_frame * ux + delta_x_plat / v_scale
    next_x = int(round(raw_x))
    next_x = 0 if next_x < 0 else (W - 1 if next_x > W - 1 else next_x)

    vy_up = -vy / v_scale
    jump_frame = float(v_jump_init) / MODEL_FPS
    cutoff_frame_b = 30.0 / MODEL_FPS
    if kappa == 1 and uy == 1:
        vy_up = vy_up + jump_frame
    if uy == 0 and vy_up > cutoff_frame_b:
        vy_up = cutoff_frame_b

    down_speed = -vy_up * MODEL_FPS
    if down_speed > 240.0:
        g_px_s2 = 540.0
    elif -30.0 < down_speed <= 240.0:
        g_px_s2 = 180.0
    elif -120.0 < down_speed <= -30.0:
        g_px_s2 = 180.0  # GRAVITY_HOLD_FALLBACK in dynamics.py
    else:
        g_px_s2 = 180.0
    vy_up = vy_up - g_px_s2 * dt_frames * dt_frames
    if vy_up < -(750.0 / MODEL_FPS):
        vy_up = -(750.0 / MODEL_FPS)
    vy_frames = vy_up

    frac_in = tau / 10.0
    y_star = y + frac_in + vy_frames

    landed = (y >= 0.0) and (y_star <= 0.0)
    best_surf = 0.0 if landed else -1.0
    if platforms:
        for plat in platforms:
            p_min = getattr(plat, "x_min", getattr(plat, "x_left", 0.0))
            p_max = getattr(plat, "x_max", getattr(plat, "x_right", 0.0))
            p_top = float(getattr(plat, "y_top", getattr(plat, "y_surf", 0.0)))
            if (next_x >= p_min) and (next_x <= p_max) and (y >= p_top) and (y_star <= p_top):
                if p_top > best_surf:
                    best_surf = p_top
    landed = best_surf >= 0.0

    y_floor = float(np.floor(y_star))
    next_y = int(round(best_surf)) if landed else int(y_floor)
    next_y = 0 if next_y < 0 else (H - 1 if next_y > H - 1 else next_y)

    next_vy = 0 if landed else int(round(-vy_frames * v_scale))
    next_kappa = 1 if landed else 0
    frac_out = int(round((y_star - y_floor) * 10.0))
    next_tau = 0 if landed else (0 if frac_out < 0 else (9 if frac_out > 9 else frac_out))
    return next_x, next_y, next_vy, next_kappa, next_tau


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    rng = np.random.default_rng(12345)
    W, H = 349, 114
    mismatches = 0
    checked = 0
    for _ in range(n):
        x = int(rng.integers(0, W))
        y = int(rng.integers(0, H))
        vy = int(rng.integers(-512, 512))
        kappa = int(rng.integers(0, 2))
        tau = int(rng.integers(0, 10))
        ux = int(rng.integers(-1, 2))
        uy = int(rng.integers(-1, 2))
        s = np.array([[x, y, vy, kappa, tau]], dtype=np.int32)
        ref = step_dynamics_batch(s, ux, uy, W=W, H=H, w=4, h=4,
                                  v_walk=150, v_jump_init=180, physics_mode="c2")[0]
        got = step_one_c2(x, y, vy, kappa, tau, ux, uy, W, H, 150, 180)
        checked += 1
        if tuple(int(v) for v in ref) != tuple(got):
            mismatches += 1
            if mismatches <= 8:
                print(f"  MISMATCH state=({x},{y},{vy},{kappa},{tau}) u=({ux},{uy})")
                print(f"    batch={tuple(int(v) for v in ref)}  scalar={tuple(got)}")
    print(f"checked {checked} random transitions, mismatches = {mismatches}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
