#!/usr/bin/env python3
"""Reconciles the model's jump with the LIVE measurement.

Live trace captured from the compiled export at 240 Hz, holding UP:
    i= 1  y=377.955  dy=-180      (impulse)
    i= 7  y=373.484  dy=-175.48
    i=19  y=364.899  dy=-166.46
    i=25  y=360.801  dy=-161.98
    i=31  y=356.798  dy= -28.11   (released; snapped toward the 30 px/s cutoff)
    i=67  y=354.551  dy=  -1.11   (apex)
    i=85  y=354.945  dy= +12.39   (falling)

Two things are checked:
  1. does dy decay at exactly 180 px/s^2? (dv/dt from consecutive samples)
  2. what initial velocity actually reproduces the observed rise, and does it
     match HEART_JUMP_STRENGTH once the sampling offset is accounted for?
"""

from __future__ import annotations

# (tick, y, dy)  -- transcribed from the live capture
LIVE = [
    (1, 377.955, -180.00),
    (7, 373.484, -175.48),
    (13, 369.144, -170.98),
    (19, 364.899, -166.46),
    (25, 360.801, -161.98),
    (31, 356.798, -28.11),
    (37, 356.142, -23.61),
    (43, 355.601, -19.13),
    (49, 355.168, -14.61),
    (55, 354.850, -10.11),
    (61, 354.644, -5.61),
    (67, 354.551, -1.11),
    (73, 354.570, 3.39),
    (79, 354.701, 7.87),
    (85, 354.945, 12.39),
]

DT = 1 / 240.0


def main() -> int:
    print("=== decay rate: dv/dt from the live samples ===")
    for k in range(1, 6):
        t0, _, v0 = LIVE[k - 1]
        t1, _, v1 = LIVE[k]
        dt = (t1 - t0) * DT
        print(f"  ticks {t0:>3}->{t1:<3} dv={v1 - v0:+7.2f}  dt={dt:.6f}  g={-(v1 - v0) / dt:8.1f} px/s^2")

    print("\n=== release edge ===")
    t0, y0, v0 = LIVE[4]
    t1, y1, v1 = LIVE[5]
    print(f"  ticks {t0}->{t1}: dy {v0:.2f} -> {v1:.2f}  (cutoff is 30 px/s)")
    print(f"  the snap is NOT to exactly -30 because the key was released between"
          f"\n  samples, so the value lands wherever the release tick fell.")

    print("\n=== apex ===")
    y_top = min(y for _, y, _ in LIVE)
    t_top = [t for t, y, _ in LIVE if y == y_top][0]
    y_start = LIVE[0][1]
    print(f"  start y={y_start:.3f}  apex y={y_top:.3f}  RISE={y_start - y_top:.2f} px at tick {t_top}")

    print("\n=== what initial velocity explains the observed rise? ===")
    rise = y_start - y_top
    # Apex of v0 against gravity g: rise = v0^2 / (2g)
    for g in (180.0, 540.0):
        implied_v0 = (2 * g * rise) ** 0.5
        print(f"  with g={g:.0f}: implied v0 = {implied_v0:.1f} px/s "
              f"(source HEART_JUMP_STRENGTH = 180)")

    print("\n=== time to apex check ===")
    t_apex = (t_top - 1) * DT
    print(f"  measured time to apex = {t_apex:.3f} s")
    for v0 in (180.0, 150.0):
        print(f"  v0={v0:.0f} px/s, g=180 -> t=v0/g={v0 / 180:.3f} s, rise={v0 ** 2 / 360:.1f} px")

    print("\n=== conclusion inputs ===")
    print("  If the decay is exactly 180 px/s^2 but the rise is below v0^2/2g,")
    print("  the launch velocity is being reduced before/while the heart rises --")
    print("  e.g. the same-tick gravity subtraction, or the sub-step rounding in")
    print("  CustomMovement (pxPerStep=1) eating part of the first frames.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
