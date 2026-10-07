#!/usr/bin/env python3
"""Prints the gravity the c2 stepper actually applies while the heart rises."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine import dynamics as D  # noqa: E402

KW = dict(physics_mode="c2", W=349, H=114, v_walk=150, v_jump_init=180)
v_scale = float(D.VY_SCALE)
dt_frames = 1.0 / 60.0

# Reproduce the scalar c2 path but report the ladder decision each frame.
x, vy, kappa = 0, 0, 1
y = 0
for i in range(14):
    uy = 1
    vy_frames = vy / v_scale
    if kappa == 1 and uy == 1:
        vy_frames += 180 / 60.0
    if uy == 0 and vy_frames > 30 / 60.0:
        vy_frames = 30 / 60.0
    down_speed = -(vy_frames / v_scale) * 60.0
    g = D.gravity_for_down_speed(down_speed)
    hold = g is None
    g = D.GRAVITY_HOLD_FALLBACK if hold else g
    vy_frames -= g * dt_frames * dt_frames
    y_star = y + vy_frames
    adsorbed = [s for s in [0.0] if y >= s and y_star <= s]
    if adsorbed:
        y, vy, kappa = int(round(max(adsorbed))), 0, 1
    else:
        y = max(0, min(113, int(round(y_star))))
        vy = int(round(vy_frames * v_scale))
        kappa = 0 if vy_frames > 0 else 2
    print(f"i={i:>2} uy={uy} vy={vy_frames:+.4f} px/f  down={down_speed:+7.1f} "
          f"g={g:5.0f}{' (HOLD)' if hold else '       '}  y={y:>3} kappa={kappa}")

print()
print("expected while rising (g=180, v0=3.0 px/frame): apex = v0^2/(2*g_frame)")
g_frame = 180.0 * dt_frames * dt_frames
print(f"  g_frame = 180 * (1/60)^2 = {g_frame:.6f} px/frame^2")
print(f"  apex    = 3.0^2 / (2*{g_frame:.6f}) = {3.0 ** 2 / (2 * g_frame):.1f} px")
_ = x
