#!/usr/bin/env python3
"""Extracts the heart's per-tick movement logic from Battle.xml as a tree.

Prints the events that govern the blue heart's velocity, so the model's step can
be checked against the source rather than inferred:

  * the jump impulse (function HeartJump)     -- Set speed ... - dir*HEART_JUMP_STRENGTH
  * the gravity application                    -- Set speed ... + dir*Gravity*dt
  * the release cutoff                         -- Set speed ... = ±HEART_JUMPHOLD_CUTOFF

Each event is printed as: conditions (with params) then actions.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML = ROOT / "repo_badtime" / "Event sheets" / "Battle.xml"


def describe(node: ET.Element) -> str:
    kind = node.get("name", "?")
    typ = node.get("type", "")
    beh = node.get("behavior", "")
    parts = []
    for p in node.findall("param"):
        parts.append(f'{p.get("name")}={ (p.text or "").strip() }')
    tag = f"{kind}"
    if beh:
        tag += f"[{beh}]"
    if typ:
        tag += f"({typ})"
    if parts:
        tag += " " + ", ".join(parts)
    return tag


def main() -> int:
    tree = ET.parse(XML)
    root = tree.getroot()

    blocks = root.iter("event-block")
    hits: list[tuple[str, list[str], list[str]]] = []
    for b in blocks:
        conds = [describe(c) for c in b.findall("./conditions/condition")]
        acts = [describe(a) for a in b.findall("./actions/action")]
        blob = " ".join(conds + acts)
        if not re.search(r"HEART_JUMP_STRENGTH|Gravity|HEART_JUMPHOLD_CUTOFF", blob):
            continue
        fn = ""
        for c in conds:
            m = re.search(r'Name="([^"]+)"', c)
            if m:
                fn = m.group(1)
        hits.append((fn, conds, acts))

    print(f"events mentioning jump/gravity/cutoff: {len(hits)}\n")
    for i, (fn, conds, acts) in enumerate(hits, 1):
        print("=" * 78)
        print(f"#{i}  function = {fn or '(none)'}")
        print("  WHEN:")
        for c in conds:
            print(f"    - {c}")
        print("  THEN:")
        for a in acts:
            print(f"    * {a}")
        print()

    # constants
    print("=" * 78)
    print("constants:")
    for v in root.iter("variable"):
        n = v.get("name", "")
        if n in ("HEART_JUMP_STRENGTH", "HEART_JUMPHOLD_CUTOFF", "HeartSpeed", "MaxFallSpeed", "Gravity"):
            print(f"  {n} = {(v.text or '').strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
