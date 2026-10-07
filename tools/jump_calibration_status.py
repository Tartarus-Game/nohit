#!/usr/bin/env python3
"""SUMMARY OF THE JUMP CALIBRATION PROBLEM (for the next round).

Everything below was measured on the compiled export with real DOM key events
(`window.dispatchEvent(new KeyboardEvent("keydown", {keyCode:38}))`), reading
the heart's `y` and `CustomMovement.dy` every engine tick at rt.fps = 240.

MEASUREMENT 1 -- hold UP for 24 engine ticks
    tick  2: y = 377.156  dy = -179.26   VPad.Up = 1
    tick  4: y = 375.653  dy =  -28.07   VPad.Up = 0     <-- cutoff already fired
    apex   : 4.49 px above the floor (377.894)
    VPad.Up stayed 1 for only ~2 ticks out of the 24 held.

MEASUREMENT 2 -- hold UP for 40 engine ticks (earlier capture)
    dy decayed -180 -> -161.98 across ticks 1..25, i.e. PURE GRAVITY, no clamp
    cutoff fired at tick ~31
    apex   : 23.40 px

These two are inconsistent under any single-parameter model:

  * if the cutoff fires ~1 tick after the impulse (M1), the apex is ~2.5-4.5 px
  * if it fires ~31 ticks later (M2), the apex is ~23 px
  * the ratio of hold lengths is 40/24 = 1.67, but the ratio of apexes is 5.2

So the engine's "key held" semantics are NOT a simple function of how long the
test held the key down. The likely cause is `VPad`: it only registers a press for
a tick or two regardless of the underlying key state, and it can re-arm during a
long hold. That means the impulse/cutoff interleaving depends on VPad's internal
timing, which has not been characterised yet.

WHAT THE MODEL NEEDS
    A per-tick function of (key state, prior VPad state) -> (impulse?, cutoff?)
    reproducing BOTH apexes. The next measurement should drive the engine with an
    explicit press pattern and record, per tick:
        - VPad.Up, VPad.LastUp          (the actual edge detector state)
        - heart.y, CustomMovement.dy
    for a sweep of press durations (1, 2, 3, 4, 6, 8, 12, 16, 24, 40 ticks), so
    the impulse/cutoff sequence can be read off directly instead of inferred.

Until then the model keeps the source-faithful behaviour (impulse on the landing
frame, cutoff on release), which reproduces M2's shape but overshoots short holds.
"""

from __future__ import annotations

MEASUREMENTS = [
    dict(hold_ticks=24, apex_px=4.49, clamp_at_tick=4, note="cutoff fires ~1 tick after the impulse"),
    dict(hold_ticks=40, apex_px=23.40, clamp_at_tick=31, note="pure gravity for ~30 ticks"),
]

NEXT_SWEEP = [1, 2, 3, 4, 6, 8, 12, 16, 24, 40]


def main() -> int:
    print(__doc__)
    print("=" * 70)
    print("recorded measurements:")
    for m in MEASUREMENTS:
        print(f"  hold {m['hold_ticks']:>3} ticks -> apex {m['apex_px']:>6.2f} px "
              f"(clamp at tick {m['clamp_at_tick']:>3})  {m['note']}")
    print()
    print("hold-length ratio  : ", MEASUREMENTS[1]["hold_ticks"] / MEASUREMENTS[0]["hold_ticks"])
    print("apex ratio         : ", MEASUREMENTS[1]["apex_px"] / MEASUREMENTS[0]["apex_px"])
    print()
    print("press durations to sweep next:", NEXT_SWEEP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
