#!/usr/bin/env python3
"""Validates the baked hazard tensor against the engine's damage predicate.

The engine's test is: the soul's 4x4 box (centred on PlayerHeart.x/y) overlaps the
bone's AABB. For a bone occupying local cells [bx0, bx1) x [by0, by1) - which is
how the rasterizer stores it - a soul at cell (x, y) is therefore hit iff

    [x-2, x+2) intersects [bx0, bx1)   AND   [y-2, y+2) intersects [by0, by1)

This recomputes B_hazard directly from the rasterizer's own occupancy tensor and
compares. Any cell where the two disagree is a real modelling error, and the
DIRECTION matters: an under-marked cell is a hit the plan will walk into.

Usage:
  python tools/validate_hazard.py --wave sans_bonegap1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.baker.parser import parse_csv_timeline  # noqa: E402
from nohit.baker.rasterizer import RasterizerConfig, rasterize_timeline  # noqa: E402
from nohit.engine.dynamics import MODEL_FPS  # noqa: E402

C2_DIR = ROOT / "c2-sans-fight"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", default="sans_bonegap1")
    ap.add_argument("--soul", type=int, default=4)
    ap.add_argument("--frames", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    csv_path = C2_DIR / (args.wave if args.wave.endswith(".csv") else args.wave + ".csv")
    bake = bake_cspace(csv_path, T=None, auto_size=True, soul_w=args.soul, soul_h=args.soul,
                       physics_mode="c2")
    haz = bake.B_hazard
    T, H, W = haz.shape
    meta = bake.metadata
    print(f"wave={csv_path.name} T={T} arena {W}x{H} c2_left={meta['c2_left']} c2_floor={meta['c2_floor']}")

    cmds = parse_csv_timeline(csv_path, fps=int(MODEL_FPS))
    cfg = RasterizerConfig(T=T, W=W, H=H, auto_size=True, FPS=int(MODEL_FPS))
    res = rasterize_timeline(cmds, config=cfg, T=T, W=W, H=H)
    occ = res.O
    print(f"raw occupancy: {int(occ.sum())} cells over {T} frames")

    half = args.soul // 2
    n_frames = T if args.frames <= 0 else min(args.frames, T)
    under = np.zeros((n_frames,), dtype=np.int64)
    over = np.zeros((n_frames,), dtype=np.int64)
    first_under = None

    for t in range(n_frames):
        # exact predicate on the integer cell grid, derived from the SAME
        # occupancy the rasterizer produced
        obst = occ[t]
        ys, xs = np.nonzero(obst)
        exact = np.zeros((H, W), dtype=bool)
        for by, bx in zip(ys.tolist(), xs.tolist()):
            x0 = max(0, bx - half)
            x1 = min(W, bx + half)          # box [x-half, x+half) hits bone cell bx
            y0 = max(0, by - half)
            y1 = min(H, by + half)
            exact[y0:y1, x0:x1] = True
        diff_u = exact & ~haz[t]
        diff_o = haz[t] & ~exact
        under[t] = int(diff_u.sum())
        over[t] = int(diff_o.sum())
        if diff_u.any() and first_under is None:
            uy, ux = np.nonzero(diff_u)
            first_under = (t, int(ux[0]), int(uy[0]), int(diff_u.sum()))

    tot_u = int(under.sum())
    tot_o = int(over.sum())
    print(f"\ncells the MODEL MISSES (engine would hit, model says safe): {tot_u}")
    print(f"cells the MODEL ADDS  (model says dangerous, engine is safe)  : {tot_o}")
    print(f"frames with any MISS: {int((under > 0).sum())} / {n_frames}")
    if first_under is not None:
        t, ux, uy, n = first_under
        print(f"first MISS at frame {t} local=({ux},{uy}) abs=({meta['c2_left']+ux}, {meta['c2_floor']-uy}) "
              f"({n} cells that frame)")
        print("  occupancy window (rows y-3..y+3, cols x-3..x+3), '#'=bone cell:")
        for yy in range(max(0, uy - 3), min(H, uy + 4)):
            row = "".join("#" if occ[t, yy, xx] else "." for xx in range(max(0, ux - 3), min(W, ux + 4)))
            print(f"    y={yy:3d} {row}")
        print("  MODEL hazard window at the same place:")
        for yy in range(max(0, uy - 3), min(H, uy + 4)):
            row = "".join("#" if haz[t, yy, xx] else "." for xx in range(max(0, ux - 3), min(W, ux + 4)))
            print(f"    y={yy:3d} {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
