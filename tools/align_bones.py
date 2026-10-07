#!/usr/bin/env python3
"""Prints the MODEL's bone x positions at given frames, for direct diffing
against the live dump.

Live dump (h=95 bones, absolute canvas x, from the running export):

    tick  50: 502.24  622.24  742.24          (spacing 120, moving -3/tick)
    tick 105: 460.99  580.99  700.99
    tick 200: 389.74  509.74  629.74  749.74

Model frames are tick/4 (240 Hz engine -> 60 Hz plan).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from nohit.baker import rasterizer as R  # noqa: E402
from nohit.baker.parser import parse_csv_timeline  # noqa: E402

C2_LEFT = 146.0
LIVE = {
    12: (502.24, 622.24, 742.24),      # tick 50
    26: (460.99, 580.99, 700.99),      # tick 105
    50: (389.74, 509.74, 629.74, 749.74),  # tick 200
}


def main() -> int:
    cmds = parse_csv_timeline(
        Path(__file__).resolve().parent.parent / "c2-sans-fight" / "sans_bonegap1.csv", fps=60
    )
    res = R.rasterize_timeline(
        cmds, config=R.RasterizerConfig(T=397, auto_size=True, FPS=60), T=397
    )
    O = res.O
    print(f"model arena {O.shape[2]}x{O.shape[1]}   c2_left={C2_LEFT}")
    print()
    print(f"{'frame':>6}{'tick':>6}  {'model bones (abs x)':<48}{'live bones (abs x)'}")
    for frame, live in LIVE.items():
        # h=95 bones live at local y 26..120; use row 30 to be safely inside
        cols = np.where(O[frame][30])[0]
        if not len(cols):
            model = []
        else:
            blocks = []
            s = cols[0]
            p = cols[0]
            for c in cols[1:]:
                if c != p + 1:
                    blocks.append((int(s), int(p)))
                    s = c
                p = c
            blocks.append((int(s), int(p)))
            model = [lo + C2_LEFT for lo, _ in blocks]
        print(f"{frame:>6}{frame * 4:>6}  {str(model):<48}{list(live)}")
    print()
    print("differences (model - live), pairing left to right:")
    for frame, live in LIVE.items():
        cols = np.where(O[frame][30])[0]
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
        model = [lo + C2_LEFT for lo, _ in blocks]
        if len(model) >= len(live):
            # align on the rightmost pair, which both dumps share
            for m, l in zip(model[-len(live):], live):
                print(f"  frame {frame:>3}: model {m:>7}  live {l:>7}  delta {m - l:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
