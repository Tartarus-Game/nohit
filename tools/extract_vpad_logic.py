#!/usr/bin/env python3
"""Finds the events that drive the VPad instance variables the cutoff depends on.

The release cutoff is
    WHEN  VPad.Up < VPad.LastUp   (Up < LastUp == "just released")
    THEN  Set speed dy = -HEART_JUMPHOLD_CUTOFF
so the jump's effective impulse depends entirely on how VPad.Up / VPad.LastUp are
maintained. Prints every event that touches them.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML = ROOT / "repo_badtime" / "Event sheets" / "Battle.xml"


def desc(n: ET.Element) -> str:
    parts = [f'{p.get("name")}={(p.text or "").strip()}' for p in n.findall("param")]
    t = n.get("name", "?")
    if n.get("behavior"):
        t += "[" + n.get("behavior") + "]"
    if n.get("type"):
        t += "(" + n.get("type") + ")"
    return t + (" " + ", ".join(parts) if parts else "")


def main() -> int:
    root = ET.parse(XML).getroot()
    pat = re.compile(r"VPad")
    hits = []
    for b in root.iter("event-block"):
        conds = [desc(c) for c in b.findall("./conditions/condition")]
        acts = [desc(a) for a in b.findall("./actions/action")]
        blob = " ".join(conds + acts)
        if pat.search(blob) and re.search(r"(Up|LastUp|Left|Right|Down|LastLeft|LastRight|LastDown)", blob):
            hits.append((conds, acts))

    print(f"events touching VPad key state: {len(hits)}\n")
    for i, (c, a) in enumerate(hits[:18], 1):
        print("-" * 74)
        print(f"#{i}")
        for x in c:
            print("  WHEN ", x)
        for x in a:
            print("  THEN ", x)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
