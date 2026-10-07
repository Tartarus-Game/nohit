#!/usr/bin/env python3
"""Counts how many of each repeat group survive culling at a given frame.

The model shows only TWO bone columns at frame 26 while the live engine shows
THREE (at abs 460.99 / 580.99 / 700.99). Each CSV line expands to 8 bones, so a
349-wide arena should contain three of them (spacing 120).

This prints, per group, the position of every one of its 8 repeats, whether the
culler keeps it, and whether it lands inside the arena -- so a culling bug is
distinguishable from a positioning bug at a glance.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.parser import parse_csv_timeline  # noqa: E402
from nohit.baker.parser import DIR_COS, DIR_SIN  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"
C2_LEFT = 146.0
FRAME = 26


def main() -> int:
    cmds = parse_csv_timeline(GAME / "sans_bonegap1.csv", fps=60)
    print(f"frame {FRAME} (tick {FRAME * 4})   c2_left={C2_LEFT}   arena W=349")
    print()
    print(f"{'line y':>7}{'h':>5}{'dir':>5}{'speed':>7}{'spawn':>7}"
          f"   {'repeat x0 (local)':<58}{'in arena'}")
    for cmd in cmds:
        if cmd.cmd_type != "BoneV":
            continue
        p = cmd.params
        if p.get("spacing") is not None:
            continue
        y = p.get("y", 0.0)
        h = p.get("height", 0.0)
        d = int(p.get("direction", 0))
        spd = p.get("speed", 0.0)
        # reconstruct the repeat set from the ORIGINAL command
        # (BoneV carries no spacing, so look up the parent line's args)
        if y not in (257.0, 366.0):
            continue
        break

    # Re-derive from the raw CSV directly so nothing is hidden by expansion
    text = (GAME / "sans_bonegap1.csv").read_text(encoding="gbk", errors="replace")
    lines = [ln for ln in text.splitlines() if "BoneVRepeat" in ln]
    for ln in lines:
        parts = ln.split(",")
        time_s = float(parts[0])
        args = parts[2:]
        x0, y0, h, d, spd, cnt, spacing = (float(args[0]), float(args[1]), float(args[2]),
                                           int(float(args[3])), float(args[4]),
                                           int(float(args[5])), float(args[6]))
        spawn = int(round(time_s * 60))
        cosv = DIR_COS.get(d, 0.0)
        sinv = DIR_SIN.get(d, 0.0)
        v_local = spd / 60.0
        vx = v_local * cosv          # local-space velocity used by the model
        age = FRAME - spawn
        print(f"{y0:>7.0f}{h:>5.0f}{d:>5}{spd:>7.0f}{spawn:>7}")
        ins = []
        for i in range(cnt):
            xi_local = (x0 - cosv * spacing * i) - C2_LEFT
            xi_now = xi_local + vx * age
            inside = (-1.0 <= xi_now <= 349.0)
            if inside:
                ins.append(round(xi_now + C2_LEFT, 2))
            print(f"       i={i}  x0_local={xi_local:>8.1f}  x@{FRAME}={xi_now:>9.2f}"
                  f"   abs={xi_now + C2_LEFT:>9.2f}   {'IN' if inside else 'out'}")
        print(f"       -> {len(ins)} in arena: {ins}")
        print()

    print("live at tick 104-105 (h=95): 460.99, 580.99, 700.99   -> 3 columns")
    print("live at tick 200     (h=95): 389.74, 509.74, 629.74, 749.74 -> 4 columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
