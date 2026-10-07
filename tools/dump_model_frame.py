#!/usr/bin/env python3
"""Dumps the MODEL's own geometry at a given frame, in ABSOLUTE c2 coordinates.

Purpose: put the solver's baked hazard, its bone rectangles, and the plan's
trajectory next to the live engine's own bboxes at the same tick, so the
divergence is measured rather than inferred.

Usage:
  python tools/dump_model_frame.py --wave sans_bonegap1 --frame 103 --x 147.2 --y 13.7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.baker.rasterizer import RasterizerConfig, rasterize_timeline  # noqa: E402
from nohit.baker.parser import parse_csv_timeline  # noqa: E402
from nohit.engine.dynamics import MODEL_FPS  # noqa: E402

C2_DIR = ROOT / "c2-sans-fight"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", default="sans_bonegap1")
    ap.add_argument("--frame", type=int, default=103)
    ap.add_argument("--x", type=float, default=None, help="abs heart x")
    ap.add_argument("--y", type=float, default=None, help="abs heart y")
    ap.add_argument("--radius", type=float, default=40.0)
    ap.add_argument("--local", action="store_true", help="interpret --x/--y as local coords")
    args = ap.parse_args()

    csv_path = C2_DIR / (args.wave if args.wave.endswith(".csv") else args.wave + ".csv")
    bake = bake_cspace(csv_path, T=None, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2")
    meta = bake.metadata
    c2_left = meta["c2_left"]
    c2_floor = meta["c2_floor"]
    W, H = bake.B_hazard.shape[2], bake.B_hazard.shape[1]
    print(f"wave={csv_path.name} T={bake.T} arena W={W} H={H} c2_left={c2_left} c2_floor={c2_floor}")
    print(f"initial_state={bake.initial_state}  physics={meta['physics_mode']} soul={meta['soul_size']}")

    # ---- raw bone rectangles from the rasterizer's own bookkeeping ----------
    commands = parse_csv_timeline(csv_path, fps=int(MODEL_FPS))
    cfg = RasterizerConfig(T=bake.T, W=W, H=H, auto_size=True, FPS=int(MODEL_FPS))
    res = rasterize_timeline(commands, config=cfg, T=bake.T, W=W, H=H)
    print(f"raster O shape={res.O.shape}  initial_heart_pos={res.initial_heart_pos}")
    print(f"metadata: { {k: v for k, v in (res.metadata or {}).items() if k != 'platform_table'} }")

    f = args.frame
    if f >= res.O.shape[0]:
        print(f"frame {f} out of range (T={res.O.shape[0]})")
        return 1

    # rows of the raw obstacle tensor at frame f, converted to absolute coords
    occ = res.O[f]
    oy, ox = np.nonzero(occ)  # oy = row index (= y), ox = column index (= x)
    print(f"\n--- RAW OCCUPANCY frame {f}: {len(ox)} cells ---")
    if len(ox):
        # group into runs per y
        for y in sorted(set(oy.tolist())):
            row = np.nonzero(occ[y])[0]
            d = np.diff(np.pad(row, (1, 1)))
            starts = np.where(d == 1)[0]
            ends = np.where(d == -1)[0]
            runs = [(int(s), int(e - 1)) for s, e in zip(starts, ends)]
            print(f"  local_y={y:4d} abs_y={c2_floor - y:7.2f}  x-runs(local) {runs}  abs_x "
                  f"{[(round(c2_left + a, 2), round(c2_left + b, 2)) for a, b in runs]}")

    haz = bake.B_hazard[f]
    hy_idx, hx_idx = np.nonzero(haz)
    print(f"\n--- DILATED HAZARD frame {f}: {len(hx_idx)} cells ---")
    for y in sorted(set(hy_idx.tolist())):
        row = np.nonzero(haz[y])[0]
        d = np.diff(np.pad(row, (1, 1)))
        starts = np.where(d == 1)[0]
        ends = np.where(d == -1)[0]
        runs = [(int(s), int(e - 1)) for s, e in zip(starts, ends)]
        print(f"  local_y={y:4d} abs_y={c2_floor - y:7.2f}  abs_x "
              f"{[(round(c2_left + a, 2), round(c2_left + b, 2)) for a, b in runs]}")

    # ---- specific query point ----------------------------------------------
    if args.x is not None and args.y is not None:
        if args.local:
            lx, ly = args.x, args.y
            ax, ay = lx + c2_left, c2_floor - ly
        else:
            ax, ay = args.x, args.y
            lx, ly = ax - c2_left, c2_floor - ay
        # The engine's verdict at a real (float) heart position: the 4x4 hitbox is
        # the half-open box [ax-2, ax+2] x [ay-2, ay+2] and the hazard cell (cx,cy)
        # covers abs [c2_left+cx, c2_left+cx+1] x [c2_floor-cy-1, c2_floor-cy].
        print(f"\n--- QUERY abs=({ax}, {ay}) local=({lx}, {ly}) ---")
        cx = int(np.floor(lx))
        cy = int(np.floor(ly))
        print(f"  anchor cell local=({cx},{cy})  hazard[{cy}][{cx}] = {bool(haz[cy, cx])}")
        # Every cell whose abs rect the heart's 4x4 box touches
        touched = []
        for ccx in range(cx - 3, cx + 3):
            for ccy in range(cy - 3, cy + 3):
                if 0 <= ccy < H and 0 <= ccx < W and haz[ccy, ccx]:
                    # cell abs rect
                    cell_l, cell_r = c2_left + ccx, c2_left + ccx + 1
                    cell_b, cell_t = c2_floor - ccy - 1, c2_floor - ccy
                    if (ax + 2 > cell_l and ax - 2 < cell_r and ay + 2 > cell_b and ay - 2 < cell_t):
                        touched.append((ccx, ccy, round(cell_l, 2), round(cell_r, 2), round(cell_b, 2), round(cell_t, 2)))
        print(f"  hazard cells touched by the 4x4 hitbox at this position: {touched}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
