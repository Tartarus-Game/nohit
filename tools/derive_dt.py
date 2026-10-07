#!/usr/bin/env python3
"""Integrates the LIVE dy trace to recover the exact per-tick timestep.

The engine samples velocity every tick; if we know the gravity constant exactly
(180 px/s^2, read off the source and confirmed by the decay rate), the observed
per-tick velocity change directly gives dt:

    dv = G * dt   ->   dt = dv / G

then the observed per-tick POSITION change must equal v * dt for the same dt.
That closes the loop without guessing anything.
"""

from __future__ import annotations

# (tick, y, dy) transcribed from the live capture
LIVE = [
    (1, 377.955, -180.00),
    (2, None, -179.25),
    (3, None, -178.50),
    (4, None, -177.75),
    (5, None, -177.00),
    (6, None, -176.25),
    (7, 373.484, -175.48),
    (13, 369.144, -170.98),
    (19, 364.899, -166.46),
    (25, 360.801, -161.98),
]

G = 180.0  # px/s^2, from the authoritative ladder (segment 12.7)


def main() -> int:
    print("=== 1. per-tick velocity change -> dt ===")
    # consecutive full-tick samples: use ticks 1->2 style deltas via the 6-tick span
    dv6 = LIVE[6][2] - LIVE[0][2]      # -175.48 - (-180) over 6 ticks
    dt_impl = dv6 / (6 * G)
    print(f"  dy over 6 ticks = {dv6:+.2f} px/s")
    print(f"  dv per tick     = {-dv6 / 6:.4f} px/s")
    print(f"  dt = dv/G       = {dt_impl:.6f} s   (1/240={1/240:.6f}, 1/60={1/60:.6f})")

    print("\n=== 2. does position advance by v*dt with that dt? ===")
    for k in (6, 12, 18, 24):
        t0, y0, v0 = LIVE[0]
        t1 = [x for x in LIVE if x[0] == t0 + k]
        if not t1 or t1[0][1] is None:
            continue
        _, y1, _ = t1[0]
        observed = y0 - y1
        ticks = k
        # closed form: sum of (v0 + j*G*dt)*dt for j=0..ticks-1
        v = v0
        pred = 0.0
        for _ in range(ticks):
            pred += abs(v) * dt_impl
            v += G * dt_impl
        print(f"  {ticks:>2} ticks: observed dy_sum={observed:8.2f} px  predicted={pred:8.2f} px  "
              f"ratio={observed / pred:.4f}")

    print("\n=== 3. apex under this dt ===")
    v = 180.0
    y = 0.0
    peak = 0.0
    t = 0
    while v > 0:
        y += v * dt_impl
        v -= G * dt_impl
        t += 1
        peak = max(peak, y)
    print(f"  hold-forever apex = {peak:.2f} px after {t} ticks ({t * dt_impl:.3f} s)")
    print(f"  v0^2 / 2G closed form = {180 ** 2 / (2 * G):.2f} px")

    print("\n=== 4. same numbers expressed at 60 Hz ===")
    print(f"  dt = 1/60 -> per-tick dv = {G / 60:.4f} px/s per frame")
    print(f"  v0 = 180 px/s = {180 / 60:.3f} px/frame")
    print(f"  apex = {180 ** 2 / (2 * G):.1f} px, reached in {180 / G:.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
