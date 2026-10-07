#!/usr/bin/env python3
"""Shows how Timeline.xml's `Running` flag gates the per-tick executor.

If the whole tick body sits under `Running = 1`, then no attack is running
whenever the timeline is stopped -- which means injected key input can never
reach the heart, and any "no damage" observed in that state is meaningless.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHEET = ROOT / "repo_badtime" / "Event sheets" / "Timeline.xml"


def fmt(elem: ET.Element) -> str:
    out = []
    for p in elem.findall("param"):
        t = (p.text or "").strip()
        if t:
            out.append(f'{p.get("name")}={t}')
    return ", ".join(out)


def walk(block: ET.Element, depth: int, out: list[str], max_depth: int = 6) -> None:
    if depth > max_depth:
        return
    ind = "  " * depth
    conds = block.find("conditions")
    acts = block.find("actions")
    cl = [f'[{c.get("type")}] {c.get("name")} {{{fmt(c)}}}'
          for c in (conds.findall("condition") if conds is not None else [])]
    al = [f'[{a.get("type")}] {a.get("name")} {{{fmt(a)}}}'
          for a in (acts.findall("action") if acts is not None else [])]
    if cl:
        out.append(f"{ind}IF " + " AND ".join(cl))
    if al:
        for a in al[:3]:
            out.append(f"{ind}   DO {a}")
        if len(al) > 3:
            out.append(f"{ind}   DO ... (+{len(al)-3} more)")
    subs = block.find("sub-events")
    if subs is not None:
        for v in subs.findall("variable"):
            out.append(f"{ind}  VAR {v.get('name')} = {v.text!r}")
        for sub in subs.findall("event-block"):
            walk(sub, depth + 1, out, max_depth)


def main() -> int:
    root = ET.parse(SHEET).getroot()
    out: list[str] = []
    for group in root.iter("event-group"):
        title = group.get("title") or ""
        out.append(f"\n######## group {title!r} ########")
        subs = group.find("sub-events")
        if subs is None:
            continue
        for v in subs.findall("variable"):
            out.append(f"  VAR {v.get('name')} = {v.text!r} static={v.get('static')}")
        for block in subs.findall("event-block"):
            walk(block, 1, out)

    text = "\n".join(out)
    # Only the top two levels matter for the guard question; print all but keep
    # it readable.
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
