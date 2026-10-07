#!/usr/bin/env python3
"""Compares the model's jump against the live measurement on equal terms.

Live measurement (compiled export, 240 Hz, holding UP for 40 ticks):
    tick 1 : dy 0 -> -180            single impulse (HEART_JUMP_STRENGTH)
    then   : dy += 180*dt             gravity 180 px/s^2
    tick 41: dy -151 -> -27           release cutoff (30 px/s)
    peak   : y fell from 377.955 to 354.551 -> RISE = 23.4 px

The 60 Hz model holds UP for 9 frames == 0.15 s, so the earlier comparison
(9 frames vs 40 ticks) was not like-for-like. This integrates the exact
continuous law at 240 Hz to match the experiment, then reports both.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine.dynamics import VY_SCALE, step_dynamics  # noqa: E402

V0 = 180.0        # jump impulse, px/s
G = 180.0         # gravity, px/s^2
CUTOFF = 30.0     # release cutoff, px/s
FLOOR = 0.0


def integrate(dt: float, hold_ticks: int, total: int) -> list[tuple[int, float, float]]:
    """Exact forward Euler of the authoritative law (matches the engine)."""
    y, dy = FLOOR, 0.0
    grounded = True
    out: list[tuple[int, float, float]] = []
    for i in range(total):
        if grounded and i < hold_ticks:
            dy += V0
            grounded = False
        if i >= hold_ticks and dy > CUTOFF:
            dy = CUTOFF
        dy -= G * dt
        if dy < -750.0:
            dy = -750.0
        y += dy * dt
        if y <= FLOOR and dy < 0:
            y, dy, grounded = FLOOR, 0.0, True
        out.append((i, y, dy))
    return out


def main() -> int:
    print("=== continuous law @240 Hz, hold 40 ticks (the live experiment) ===")
    a = integrate(1 / 240.0, 40, 140)
    peak_a = max(y for _, y, _ in a)
    at_a = [i for i, y, _ in a if y == peak_a][0]
    print(f"  rise = {peak_a:.2f} px at tick {at_a} ({at_a / 240:.3f} s)")
    print("  live = 23.40 px at tick 67 (0.279 s)")
    print(f"  delta = {peak_a - 23.4:+.2f} px")

    print("\n=== same law @60 Hz, hold 9 frames (same 0.15 s of input) ===")
    b = integrate(1 / 60.0, 9, 40)
    peak_b = max(y for _, y, _ in b)
    at_b = [i for i, y, _ in b if y == peak_b][0]
    print(f"  rise = {peak_b:.2f} px at frame {at_b} ({at_b / 60:.3f} s)")

    print("\n=== shipped 60 Hz stepper (nohit.engine.dynamics, c2 mode) ===")
    s = (0, 0, 0, 1, 0)
    ys = []
    for i in range(40):
        uy = 1 if i < 9 else 0
        s = step_dynamics(s, (0, uy), physics_mode="c2", W=349, H=114, v_walk=150, v_jump_init=180)
        ys.append((i, s[1], s[2] / VY_SCALE))
    peak_c = max(y for _, y, _ in ys)
    at_c = [i for i, y, _ in ys if y == peak_c][0]
    print(f"  rise = {peak_c:.2f} px at frame {at_c} ({at_c / 60:.3f} s)")
    print(f"  stepper vs continuous@60Hz delta = {peak_c - peak_b:+.2f} px")

    print("\n  the stepper rounds y to whole pixels each frame, so a small")
    print("  positive bias is expected; anything beyond ~1 px per frame means")
    print("  a real divergence.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
