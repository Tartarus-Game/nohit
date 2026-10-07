#!/usr/bin/env python3
"""Dumps every bone the rasterizer builds for sans_bonegap1, with local coords.

Live ground truth (absolute, arena floor y=378, left x=146):

    95-tall bones: abs y = 257, bbox y in [257, 352]
    20-tall bones: abs y = 366, bbox y in [366, 386]

The 20-tall bones are the ones actually hitting the heart: at the first damage
tick the heart sits at abs y=366.6 and overlaps a [366, 386] box. The heart at
REST is at abs y=377.9, which is *under* those bones -- so the model must model
them, and must not send the heart up into them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.parser import parse_csv_timeline  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"


def main() -> int:
    cmds = parse_csv_timeline(GAME / "sans_bonegap1.csv", fps=60)
    bones = [c for c in cmds if getattr(c, "cmd_type", "") in ("BoneV", "BoneH")]
    print(f"parsed BoneV/BoneH commands: {len(bones)}")
    print()
    print(f"{'t(s)':>7}{'frame':>7}  {'args'}")
    seen_heights: dict[str, int] = {}
    for c in bones[:40]:
        args = getattr(c, "raw_args", getattr(c, "args", []))
        h = args[2] if len(args) > 2 else "?"
        seen_heights[str(h)] = seen_heights.get(str(h), 0) + 1
        if len(bones) <= 40 or bones.index(c) < 12:
            print(f"{c.time_s:>7.3f}{c.frame:>7}  {args}")

    print()
    print("height histogram (position 2 of the args):")
    for h, n in sorted(seen_heights.items(), key=lambda kv: -kv[1]):
        print(f"   height={h:>5}  count={n}")

    print()
    print("raw CSV lines:")
    text = (GAME / "sans_bonegap1.csv").read_text(encoding="gbk", errors="replace")
    for line in text.splitlines():
        if "BoneV" in line or "BoneH" in line or "CombatZone" in line or "HeartTeleport" in line:
            print("   " + line.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
