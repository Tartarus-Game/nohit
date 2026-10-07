#!/usr/bin/env python3
"""VERIFY_B scratch: recompute spawn-x table straight from the CSV + source formula.

Source formula (authoritative), Battle.xml sid=2005883927831399 / BoneVRepeat:

    X = StartX - cos(Direction*90)*Spacing*loopindex     (loopindex = 0 .. Count-1)

Then BoneV does Set X = int(Function.Param(0)).

This script does NOT import nohit; it re-derives everything from the raw CSV so
the arithmetic is independent of the model under test.
"""

from __future__ import annotations

import math
from pathlib import Path

CSV = Path(__file__).resolve().parent.parent / "c2-sans-fight" / "sans_bonegap1.csv"


def c2_num(x: float) -> int:
    """Construct 2 int() = truncation toward zero (ExpValue.set_int)."""
    return math.trunc(x)


def main() -> int:
    text = CSV.read_text(encoding="gbk", errors="replace")
    print(f"decoded {CSV.name} as GBK, {len(text.splitlines())} lines")
    print()

    rows = [ln for ln in text.splitlines() if "BoneVRepeat" in ln]
    for ln in rows:
        parts = ln.split(",")
        t_s = float(parts[0])
        cmd = parts[1]
        a = parts[2:]
        start_x = float(a[0])
        start_y = float(a[1])
        height = float(a[2])
        direction = int(float(a[3]))
        speed = float(a[4])
        count = int(float(a[5]))
        spacing = float(a[6])

        cosv = math.cos(math.radians(direction * 90))
        sinv = math.sin(math.radians(direction * 90))

        print(f"CSV line: {ln}")
        print(f"  t={t_s}s cmd={cmd} start_x={start_x} start_y={start_y} height={height}")
        print(f"  direction={direction} speed={speed}px/s count={count} spacing={spacing}")
        print(f"  cos(dir*90)={cosv!r}  sin(dir*90)={sinv!r}")

        xs, ys = [], []
        for i in range(count):
            xf = start_x - cosv * spacing * i
            yf = start_y - sinv * spacing * i
            xs.append(c2_num(xf))
            ys.append(c2_num(yf))
        print(f"  spawn X (SOURCE, minus): {xs}")
        print(f"  spawn Y                 : {sorted(set(ys))}")
        print(f"  spawn X (if PLUS       ): "
              f"{[c2_num(start_x + cosv * spacing * i) for i in range(count)]}")
        print(f"  delta(minus -> plus)    : "
              f"{[c2_num(start_x + cosv*spacing*i) - c2_num(start_x - cosv*spacing*i) for i in range(count)]}")
        # culled / on-screen subset for a 349-wide arena anchored at 146
        arena_lo, arena_hi = 146.0, 146.0 + 349.0
        vis = [x for x in xs if arena_lo <= x <= arena_hi]
        print(f"  of those, inside absolute arena [{arena_lo:.0f},{arena_hi:.0f}] "
              f"at spawn instant: {vis}  ({len(vis)} bones)")
        print()

    print("== BoneV int() check: the Set X argument is int(Function.Param(0)) ==")
    print("   truncation toward zero: int(-0.5) =", c2_num(-0.5),
          " int(-112.0) =", c2_num(-112.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
