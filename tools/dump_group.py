#!/usr/bin/env python3
"""Prints the authoritative PlayerMovement (and PlayerDamage) event-group of
repo_badtime/Battle.xml in document order, WITH sheet ordering numbers, so the
per-frame sequence of horizontal movement / gravity / landing / collision can be
reproduced exactly instead of guessed.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHEETS = ROOT / "repo_badtime" / "Event sheets"


def fmt(elem: ET.Element) -> str:
    out = []
    for p in elem.findall("param"):
        txt = (p.text or "").strip()
        if txt:
            out.append(f'{p.get("name")}={txt}')
    return ", ".join(out)


def blocks(node: ET.Element):
    subs = node.find("sub-events")
    if subs is None:
        return []
    return subs.findall("event-block")


def render(block: ET.Element, path: list[int], out: list[str], depth: int = 0) -> None:
    ind = "  " * depth
    idx = ".".join(str(p) for p in path)
    conds = block.find("conditions")
    cl = []
    if conds is not None:
        for c in conds.findall("condition"):
            dis = " (DISABLED)" if c.get("disabled") == "1" else ""
            cl.append(f'[{c.get("type")}] {c.get("name")}{dis} {{{fmt(c)}}}')
    acts = block.find("actions")
    al = []
    if acts is not None:
        for a in acts.findall("action"):
            al.append(f'[{a.get("type")}] {a.get("name")} {{{fmt(a)}}}')

    if cl:
        out.append(f"{ind}{idx} IF " + (" AND ".join(cl)))
    if al:
        for a in al:
            out.append(f"{ind}{' ' * (len(idx) + 3)}DO {a}")
    if not cl and not al:
        out.append(f"{ind}{idx} (container)")

    subs = block.find("sub-events")
    if subs is not None:
        # local variables first
        for v in subs.findall("variable"):
            out.append(f"{ind}  {idx}.v VAR {v.get('name')} = {v.text!r} static={v.get('static')}")
        for i, sub in enumerate(subs.findall("event-block")):
            render(sub, path + [i], out, depth + 1)


def main() -> int:
    want = sys.argv[1:] or ["PlayerMovement", "PlayerDamage"]
    tree = ET.parse(SHEETS / "Battle.xml")
    root = tree.getroot()
    for group in root.iter("event-group"):
        title = group.get("title") or ""
        if title not in want:
            continue
        print("=" * 78)
        print(f"event-group {title!r}")
        print("=" * 78)
        out: list[str] = []
        for i, block in enumerate(blocks(group)):
            render(block, [i], out, 0)
        print("\n".join(out))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
