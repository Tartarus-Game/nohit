#!/usr/bin/env python3
"""Aligns the model's bone positions with a LIVE snapshot, cell by cell.

LIVE snapshot (fresh page, sans_bonegap1, right after the round starts),
tick 40, h=95 group, absolute canvas x:

    21.49  141.49  249.51  261.49  369.51  381.49  489.51  609.51
    Δ :    120    108.02   11.98   108.02   11.98   108.02   120

Three distinct gaps mean TWO interleaved groups. Splitting by trailing motion
(the +3 group moves right, the -3 group moves left):

    right-moving: 21.49  141.49  261.49  381.49      (120 apart => x0 ≈ -98)
    left-moving : 249.51 369.51  489.51  609.51      (120 apart => x0 ≈ 369)

But the model is built from `BoneVRepeat,128,...` and `BoneVRepeat,503,...`, so
its anchors are 128 / 503. This script prints the model's live-equivalent
positions so the two can be compared directly instead of by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker import rasterizer as R  # noqa: E402
from nohit.baker.parser import parse_csv_timeline  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"
C2_LEFT = 146.0
LIVE_TICK = 40
FRAME = LIVE_TICK / 4.0          # 240 Hz engine -> 60 Hz model
C2_FLOOR = 378.0


def main() -> int:
    cmds = parse_csv_timeline(GAME / "sans_bonegap1.csv", fps=60)
    print("parsed BoneV commands (first 8):")
    for c in cmds:
        if c.cmd_type == "BoneV":
            p = c.params
            print(f"   frame={c.frame:>3}  x={p['x']:>8.1f}  y={p['y']:>6.1f}"
                  f"  h={p['height']:>5.1f}  dir={p['direction']}  speed={p['speed']:.0f}")
    print()

    # Reconstruct the rasterizer's own view of positions at FRAME (integer frame)
    fi = int(round(FRAME))
    res = R.rasterize_timeline(
        cmds, config=R.RasterizerConfig(T=397, auto_size=True, FPS=60), T=397
    )
    O = res.O
    print(f"model frame {fi}  (live tick {LIVE_TICK})")
    # h=95 lives in local y 26..120; probe row 30.  h=20 in y 0..11; probe row 2.
    for label, row in (("h=95", 30), ("h=20", 2)):
        cols = np.where(O[fi][row])[0]
        blocks = []
        if len(cols):
            s = cols[0]
            p = cols[0]
            for c in cols[1:]:
                if c != p + 1:
                    blocks.append((int(s), int(p)))
                    s = c
                p = c
            blocks.append((int(s), int(p)))
        abs_cols = [lo + C2_LEFT for lo, _ in blocks]
        print(f"  {label} local cols {blocks}")
        print(f"  {label} abs x     {abs_cols}")
        if len(abs_cols) > 1:
            print(f"  {label} abs Δ     {[round(abs_cols[i+1]-abs_cols[i],2) for i in range(len(abs_cols)-1)]}")
    print()
    print(f"LIVE at tick {LIVE_TICK} (h=95, abs x):")
    print("    21.49  141.49  249.51  261.49  369.51  381.49  489.51  609.51")
    print("    Δ: 120   108.02   11.98   108.02   11.98   108.02   120")
    print()
    print("=> the model's Δ pattern should reproduce 120 / small / 120 / small ...")
    print("   if both interleaved groups are present with the right phase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
