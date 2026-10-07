#!/usr/bin/env python3
"""Dumps the menu-input event blocks so the correct injection point is known.

The main menu and the attack list may read input via `VPad` polling OR via
`Keyboard On key pressed` triggers; a polled keyMap write only satisfies the
former, which is why synthetic DOM key events and keyMap writes can behave
differently.
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
        t = (p.text or "").strip()
        if t:
            out.append(f'{p.get("name")}={t}')
    return ", ".join(out)


def walk(block: ET.Element, depth: int, out: list[str], max_depth: int = 8) -> None:
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
    for a in al[:4]:
        out.append(f"{ind}   DO {a}")
    subs = block.find("sub-events")
    if subs is not None:
        for v in subs.findall("variable"):
            out.append(f"{ind}  VAR {v.get('name')} = {v.text!r}")
        for sub in subs.findall("event-block"):
            walk(sub, depth + 1, out, max_depth)


def main() -> int:
    for sheet_name in ("MainMenu.xml", "Battle.xml", "Menus.xml"):
        path = SHEETS / sheet_name
        if not path.exists():
            continue
        root = ET.parse(path).getroot()
        out: list[str] = []
        for block in root.iter("event-block"):
            conds = block.find("conditions")
            if conds is None:
                continue
            text = " ".join(f'{c.get("name")} {fmt(c)}' for c in conds.findall("condition"))
            # Only input-related blocks.
            if not any(k in text for k in ("Key", "VPad", "Touch", "Confirm", "MenuState")):
                continue
            walk(block, 0, out, max_depth=5)
        if out:
            print("=" * 78)
            print(f"{sheet_name}: input-related blocks")
            print("=" * 78)
            print("\n".join(out[:200]))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
