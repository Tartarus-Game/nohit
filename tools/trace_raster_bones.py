#!/usr/bin/env python3
"""Instrument the rasterizer's bone construction for sans_bonegap1.

Checks whether the 20-tall bones (abs y=366, bbox [366,386]) end up in the
hazard tensor, and where. The heart at REST sits at abs y=377.9 -- i.e. INSIDE
those boxes -- yet the heart only takes damage once it leaves the floor, so the
model's treatment of them is the thing under test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker import rasterizer as R  # noqa: E402
from nohit.baker.parser import parse_csv_timeline  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"
C2_LEFT, C2_FLOOR = 146.0, 378.0

orig_init = R._ActiveBone.__init__


def spy_init(self, *a, **kw):  # noqa: ANN001
    orig_init(self, *a, **kw)
    SPY.append(
        dict(x=self.x, y=self.y, w=self.width, h=self.height,
             vx=self.vx, vy=self.vy, color=self.color, spawn=self.spawn_frame)
    )


SPY: list[dict] = []
R._ActiveBone.__init__ = spy_init

cmds = parse_csv_timeline(GAME / "sans_bonegap1.csv", fps=60)
cfg = R.RasterizerConfig(T=397, auto_size=True, FPS=60)
res = R.rasterize_timeline(cmds, config=cfg, T=397)

R._ActiveBone.__init__ = orig_init

print(f"_ActiveBone instances built: {len(SPY)}")
if SPY:
    print()
    print(f"{'x':>8}{'y':>6}{'w':>6}{'h':>6}{'vx':>8}{'vy':>6}{'color':>6}{'spawn':>7}")
    for b in SPY[:34]:
        print(f"{b['x']:>8}{b['y']:>6}{str(b['w']):>6}{str(b['h']):>6}"
              f"{str(b['vx']):>8}{str(b['vy']):>6}{str(b['color']):>6}{str(b['spawn']):>7}")

    hs = {}
    for b in SPY:
        hs[b["h"]] = hs.get(b["h"], 0) + 1
    print("\nheight histogram of built bones:", hs)

print()
print("hazard tensor:")
B = res.O
for t in (12, 20, 40, 53, 60, 88, 92):
    if t >= B.shape[0]:
        continue
    row = B[t]
    cols = np.where(row.any(axis=0))[0]
    if not len(cols):
        print(f"  t={t:>4}: (empty)")
        continue
    blocks = []
    s = cols[0]; p = cols[0]
    for c in cols[1:]:
        if c != p + 1:
            blocks.append((int(s), int(p))); s = c
        p = c
    blocks.append((int(s), int(p)))
    # vertical extent of each block
    info = []
    for lo, hi in blocks[:6]:
        sub = row[:, lo:hi + 1]
        rws = np.where(sub.any(axis=1))[0]
        info.append(f"x[{lo},{hi}] y[{int(rws.min())},{int(rws.max())}]")
    print(f"  t={t:>4}: {len(blocks)} blocks -> {info}")
