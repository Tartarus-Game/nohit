#!/usr/bin/env python3
"""Instruments the c2 jump path to show where the impulse is being re-applied."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine import dynamics as D  # noqa: E402

KW = dict(physics_mode="c2", W=349, H=114, v_walk=150, v_jump_init=180)

# Re-implement the first two frames of the c2 branch with visibility into every
# intermediate value, mirroring dynamics.step_dynamics line by line.
v_scale = float(D.VY_SCALE)
dt_frames = 1.0 / 60.0
speed_frame = 150 / 60.0
jump_frame = 180 / 60.0 * v_scale

x, y, vy, kappa, tau = 0, 0, 0, 1, 0
print(f"v_scale={v_scale} jump_frame(scaled)={jump_frame} (physical {jump_frame/v_scale:.3f} px/f)")
print()

for i in range(4):
    uy = 1
    print(f"--- frame {i}: IN x={x} y={y} vy={vy} ({vy/v_scale:+.3f} px/f) kappa={kappa}")

    vy_frames = vy / v_scale
    print(f"    start vy_frames = {vy_frames:+.4f}")

    if kappa == 1 and uy == 1:
        vy_frames += jump_frame
        print(f"    + jump impulse   = {vy_frames:+.4f}   <-- applied because kappa==1")
    else:
        print("    (no impulse)")

    if uy == 0 and vy_frames > (30.0 / 60.0) * v_scale:
        vy_frames = (30.0 / 60.0) * v_scale
        print(f"    release cutoff   = {vy_frames:+.4f}")

    down_speed = -(vy_frames / v_scale) * 60.0
    g = D.gravity_for_down_speed(down_speed)
    g = D.GRAVITY_HOLD_FALLBACK if g is None else g
    vy_frames -= g * dt_frames * dt_frames
    print(f"    downSpeed={down_speed:+.1f} g={g:.0f} -> vy_frames={vy_frames:+.4f}")

    y_star = y + vy_frames
    surfaces = [0.0]
    adsorbed = [s for s in surfaces if y >= s and y_star <= s]
    print(f"    y_star={y_star:+.4f} adsorbed={adsorbed}")
    if adsorbed:
        y, vy, kappa = int(round(max(adsorbed))), 0, 1
        print("    -> LANDED (kappa=1)")
    else:
        y = max(0, min(113, int(round(y_star))))
        vy = int(round(vy_frames * v_scale))
        kappa = 0 if vy_frames > 0 else 2
        print(f"    -> airborne kappa={kappa}")
    print()

_ = KW
