#!/usr/bin/env python3
"""Finds the heart's sprite dimensions in the compiled C2 export.

VERIFY_A measured that the LIVE engine damages on the heart's full sprite
bounding box, not the 4x4 soul box:

    at (320, 360):
        soul/damage object t65 bbox [318,358,322,362]  -> overlaps 0 bones
        heart sprite      bbox [312,352,328,368]       -> overlaps the 20-high bones

If that 16x20 sprite box is what actually triggers damage, the model's hazard
dilation (soul_w=4, soul_h=4) is optimistic by 12 px vertically -- exactly in the
band a planner would try to park in.

This locates the authoritative width/height for the heart type so the correct
envelope can be baked instead of guessed.
"""

from __future__ import annotations

import re
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"


def main() -> int:
    data = (GAME / "data.js").read_text(encoding="utf-8", errors="ignore")

    # C2 world records: ["t55", ...] with width/height fields early in the list.
    for name in ("t55", "t65", "t31"):
        hits = [m.start() for m in re.finditer(r'"' + name + r'"', data)]
        print(f"--- {name}: {len(hits)} occurrence(s) in data.js")
        for pos in hits[:3]:
            snippet = data[pos:pos + 240].replace("\n", " ")
            print(f"    @{pos}: {snippet}")
        print()

    # Also look for the object-type declaration with explicit width/height
    print("--- searching for object-type entries ---")
    for m in re.finditer(r'\{[^{}]*"width"\s*:\s*(\d+)[^{}]*"height"\s*:\s*(\d+)', data):
        pass

    # The .caproj lists display sizes; search for heart-related names
    for pat in ("HeartSoul", "Heart", "BoneV"):
        idx = data.find(pat)
        if idx >= 0:
            print(f"  '{pat}' @{idx}: "
                  f"{data[max(0, idx - 120):idx + 200]!r}".replace("\n", " ")[:320])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
