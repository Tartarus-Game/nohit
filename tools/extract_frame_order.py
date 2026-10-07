#!/usr/bin/env python3
"""Extracts the authoritative per-frame ORDER OF OPERATIONS for PlayerHeart.

Dumps the movement / gravity / landing event blocks from the source event sheet
in document order (which IS Construct 2's execution order within a sheet), so
the Python stepper can be re-ordered to match the real engine exactly instead of
using an assumed "horizontal then vertical" or "vertical then horizontal" order.
"""

from __future__ import annotations

import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHEETS = ROOT / "repo_badtime" / "Event sheets"

INTERESTING_ACTION = re.compile(
    r"(heart|heartmode|PlayerHeart|CustomMovement|position|Solid|Gravity|"
    r"FallSpeed|Jump|Slam|Conveyor|Platform|Move|Speed)",
    re.IGNORECASE,
)
INTERESTING_COND = re.compile(
    r"(Heart|CustomMovement|Solid|Function|Overlap|Compare|Tick|Layout|Pick)",
    re.IGNORECASE,
)


def fmt_params(elem: ET.Element) -> str:
    out = []
    for p in elem.findall("param"):
        txt = (p.text or "").strip()
        if txt:
            out.append(f'{p.get("name")}={txt}')
    return ", ".join(out)


def walk(block: ET.Element, depth: int, counter: list[int], limit_depth: int = 6) -> None:
    if depth > limit_depth:
        return
    ind = "  " * depth
    conds = block.find("conditions")
    cond_txt = []
    if conds is not None:
        for c in conds.findall("condition"):
            cond_txt.append(f'[{c.get("type")}] {c.get("name")} {fmt_params(c)}'.strip())
    acts = block.find("actions")
    act_txt = []
    if acts is not None:
        for a in acts.findall("action"):
            act_txt.append(f'[{a.get("type")}] {a.get("name")} {fmt_params(a)}'.strip())

    joined = " ".join(cond_txt + act_txt)
    if INTERESTING_COND.search(joined) or INTERESTING_ACTION.search(joined):
        counter[0] += 1
        print(f"{ind}#{counter[0]} COND: " + ("; ".join(cond_txt) if cond_txt else "(none)"))
        for a in act_txt:
            print(f"{ind}    ACT: {a}")

    subs = block.find("sub-events")
    if subs is not None:
        for sub in subs.findall("event-block"):
            walk(sub, depth + 1, counter, limit_depth)


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "Battle.xml"
    sheet = SHEETS / target
    tree = ET.parse(sheet)
    root = tree.getroot()
    print("=" * 78)
    print(f"{target}: PlayerHeart movement / landing order of operations")
    print("=" * 78)
    counter = [0]
    for group in root.iter("event-group"):
        title = group.get("title") or ""
        if not re.search(r"(Movement|Player|Heart|Damage|Collision|Battle|Solid)", title, re.I):
            continue
        print(f"\n######## event-group: {title!r} ########")
        subs = group.find("sub-events")
        if subs is None:
            continue
        for block in subs.findall("event-block"):
            walk(block, 1, counter)
    print(f"\n({counter[0]} relevant blocks printed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
