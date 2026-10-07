#!/usr/bin/env python3
"""Prints the ground-band hazard / safe corridor and overlays the solver's plan.

Answers "is the plan actually satisfying the model's own constraint, and what
does the model think is dangerous near the floor?".

Usage:
  python tools/dump_corridor.py --wave sans_bonegap1 --y 2 --f0 0 --f1 200 --step 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nohit.baker.dilator import bake_cspace  # noqa: E402

C2_DIR = ROOT / "c2-sans-fight"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", default="sans_bonegap1")
    ap.add_argument("--y", type=int, default=2, help="local y band (the heart's floor row)")
    ap.add_argument("--f0", type=int, default=0)
    ap.add_argument("--f1", type=int, default=200)
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--plan", default="tools/.plan_bonegap1.json")
    args = ap.parse_args()

    csv_path = C2_DIR / (args.wave if args.wave.endswith(".csv") else args.wave + ".csv")
    bake = bake_cspace(csv_path, T=None, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2")
    haz = bake.B_hazard
    T, H, W = haz.shape
    plan_path = ROOT / args.plan
    traj = json.loads(plan_path.read_text(encoding="utf-8"))["trajectory"] if plan_path.is_file() else None

    y = args.y
    print(f"wave={csv_path.name} T={T} W={W} H={H}  band y={y}")
    print("legend: '#'=hazard(hitbox would overlap a bone)  '.'=safe   'H'=plan position")
    print("        columns are local x, printed every column")
    hdr = "frame " + "".join(str((x // 10) % 10) if x % 10 == 0 else " " for x in range(W))
    print(hdr)
    for f in range(args.f0, min(args.f1, T), args.step):
        row = haz[f, y]
        chars = ["#" if v else "." for v in row]
        if traj and f < len(traj):
            px, py = traj[f][0], traj[f][1]
            if 0 <= px < W:
                chars[px] = "H" if py == y else "h"
        print(f"{f:5d} " + "".join(chars))
        # how many safe cells on this row
    print()
    # Safe-cell count on the band per frame (a quick "corridor width" signal)
    counts = [(f, int((~haz[f, y]).sum())) for f in range(0, min(T, args.f1), max(1, args.step * 5))]
    print("frame -> safe cells on band:", ", ".join(f"{f}:{c}" for f, c in counts[:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
