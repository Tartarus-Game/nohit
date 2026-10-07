#!/usr/bin/env python3
"""Checks whether a solver plan satisfies the MODEL's own hazard constraint, and
where the model places the nearest bone relative to the heart.

Usage:
  python tools/check_plan_vs_model.py --plan tools/.plan_bonegap1.json
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
    ap.add_argument("--plan", default="tools/.plan_bonegap1.json")
    ap.add_argument("--soul", type=int, default=4)
    args = ap.parse_args()

    csv_path = C2_DIR / (args.wave if args.wave.endswith(".csv") else args.wave + ".csv")
    bake = bake_cspace(csv_path, T=None, auto_size=True, soul_w=args.soul, soul_h=args.soul, physics_mode="c2")
    haz = bake.B_hazard
    plan = json.loads((ROOT / args.plan).read_text(encoding="utf-8"))
    traj = plan["trajectory"]
    acts = plan["action_sequence"]
    T, H, W = haz.shape
    L = plan["arena"]["c2_left"]
    F = plan["arena"]["c2_floor"]
    print(f"wave={csv_path.name} T={T} plan T={len(traj)} arena {W}x{H} c2_left={L} c2_floor={F}")

    # The engine's damage test is "the soul's 4x4 box overlaps the bone's bbox",
    # i.e. a position is unsafe iff haz[y][x] is set for a cell the 4x4 box touches.
    # The rasterizer's anchor convention: heart top-left at local (x, y) -> cell.
    rows = []
    bad = []
    for f in range(min(T, len(traj))):
        x, y = int(traj[f][0]), int(traj[f][1])
        # cell touched by the 4x4 box anchored at (x, y): [x, x+4) x (y, y+4]
        touched = haz[f, max(0, y):y + 4, max(0, x):x + 4]
        hit = bool(touched.any())
        rows.append((f, x, y, hit))
        if hit:
            bad.append((f, x, y))
    print(f"\nplan frames checked: {len(rows)}   VIOLATIONS (model says unsafe): {len(bad)}")
    if bad:
        print("first 30 violations:", bad[:30])
    # Is x=174 at ground level safe for the whole run?
    print("\n--- reference: what the model says for STANDING STILL at x=174, y=0 ---")
    viol = [f for f in range(T) if haz[f, 0:4, 174:178].any()]
    print(f"  standing still: unsafe frames = {len(viol)}; first 20 = {viol[:20]}")
    # The action sequence's per-frame input cost
    ux = np.array([a[0] for a in acts])
    uy = np.array([a[1] for a in acts])
    nz = (ux != 0).astype(int) + (uy != 0).astype(int)
    print(f"\n--- plan input usage ---")
    print(f"  frames with any input : {int((nz>0).sum())} / {len(acts)}")
    print(f"  frames moving left    : {int((ux<0).sum())}  right: {int((ux>0).sum())}  jump: {int((uy>0).sum())}")
    print(f"  total |horizontal|    : {int(np.abs(ux).sum())}   total jump frames: {int((uy>0).sum())}")
    # where the left inputs are
    runs = []
    cur = None
    for i, v in enumerate(ux):
        if v != 0 and (cur is None or cur[2] != v):
            if cur:
                runs.append(cur)
            cur = [i, i, v]
        elif v != 0 and cur and cur[2] == v:
            cur[1] = i
        elif v == 0 and cur:
            runs.append(cur)
            cur = None
    if cur:
        runs.append(cur)
    print(f"  horizontal input runs (start,end,dir): {runs[:24]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
