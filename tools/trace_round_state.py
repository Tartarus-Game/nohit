#!/usr/bin/env python3
"""Traces how a SINGLE-attack deep-link round starts: where HP/MaxHP are set and
what actually arms the heart, so the round can be started deterministically.

Prints, in document order, every block that writes HP / MaxHP / KR / HeartMode /
StartAttack / ResetVars, plus the EventBlock that runs when the deep-link
condition matches.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHEETS = ROOT / "repo_badtime" / "Event sheets"

WATCH = ("HP", "MaxHP", "KR", "HeartMode", "ResetVars", "StartAttack", "SingleAttack",
         "SimulatorMode", "EndAttack", "RunAttack", "MenuState", "NextAttack")


def fmt(elem: ET.Element) -> str:
    out = []
    for p in elem.findall("param"):
        t = (p.text or "").strip()
        if t:
            out.append(f'{p.get("name")}={t}')
    return ", ".join(out)


def direct_text(node: ET.Element) -> str:
    r = []
    for par in node.findall("param"):
        r.append((par.text or "").strip())
    return " ".join(r)


def walk(block: ET.Element, chain: str, rows: list, depth: int = 0, maxd: int = 3) -> None:
    if depth > maxd:
        return
    conds = block.find("conditions")
    cl = [f'[{c.get("type")}] {c.get("name")} {{{fmt(c)}}}' for c in (conds.findall("condition") if conds is not None else [])]
    acts = block.find("actions")
    al = []
    for a in (acts.findall("action") if acts is not None else []):
        txt = fmt(a)
        if any(w in txt for w in WATCH):
            al.append(f'[{a.get("type")}] {a.get("name")} {{{txt}}}')
    if cl and al:
        rows.append((chain, " AND ".join(cl), al))
    subs = block.find("sub-events")
    if subs is not None:
        for sub in subs.findall("event-block"):
            walk(sub, chain, rows, depth + 1, maxd)


def main() -> int:
    for name in ("Battle.xml", "MainMenu.xml", "Globals.xml", "Menus.xml"):
        path = SHEETS / name
        if not path.exists():
            continue
        root = ET.parse(path).getroot()
        rows: list = []
        for group in root.iter("event-group"):
            title = group.get("title") or ""
            for block in group.iter("event-block"):
                walk(block, title, rows, 0, 3)
        if not rows:
            continue
        print("=" * 78)
        print(f"{name}  ({len(rows)} blocks touching round state)")
        print("=" * 78)
        for title, cond, acts in rows:
            print(f"\n[{title}] IF {cond}")
            for a in acts[:6]:
                print(f"     DO {a}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
