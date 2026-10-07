#!/usr/bin/env python3
"""Dumps every damage-dealing event block in Battle.xml for a given source repo.

Answers the question "what actually damages the player in this build" -- the
settlement model the solver must reproduce -- including the conditions that gate
each DamagePlayer call.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent


def fmt(elem: ET.Element) -> str:
    out = []
    for p in elem.findall("param"):
        t = (p.text or "").strip()
        if t:
            out.append(f'{p.get("name")}={t}')
    return ", ".join(out)


def acts_of(block: ET.Element) -> list[str]:
    acts = block.find("actions")
    if acts is None:
        return []
    return [f'[{a.get("type")}] {a.get("name")} {{{fmt(a)}}}' for a in acts.findall("action")]


def conds_of(block: ET.Element) -> list[str]:
    conds = block.find("conditions")
    if conds is None:
        return []
    return [f'[{c.get("type")}] {c.get("name")} {{{fmt(c)}}}' for c in conds.findall("condition")]


def calls_damage(block: ET.Element) -> bool:
    return any("DamagePlayer" in a for a in acts_of(block))


def report(repo: pathlib.Path) -> None:
    sheet = repo / "Event sheets" / "Battle.xml"
    if not sheet.exists():
        print(f"  (missing {sheet})")
        return
    root = ET.parse(sheet).getroot()
    blocks = list(root.iter("event-block"))

    direct = [b for b in blocks if calls_damage(b)]
    print(f"  blocks calling DamagePlayer directly: {len(direct)}")
    for b in direct:
        print(f"\n    sid={b.get('sid')}")
        for c in conds_of(b):
            print(f"      IF {c}")
        for a in acts_of(b):
            print(f"      DO {a}")

    # Blocks that subtract HP directly (the non-function damage path).
    hp_sub = []
    for b in blocks:
        for a in acts_of(b):
            if "[System] Subtract from" in a and "HP" in a:
                hp_sub.append((b, a))
    print(f"\n  blocks subtracting HP directly: {len(hp_sub)}")
    for b, a in hp_sub:
        print(f"    sid={b.get('sid')}  IF " + " AND ".join(conds_of(b)))
        print(f"        DO {a}")


def main() -> int:
    repos = sys.argv[1:] or ["repo_jcw87", "repo_badtime"]
    for name in repos:
        print("=" * 78)
        print(f"{name} :: Battle.xml damage model")
        print("=" * 78)
        report(ROOT / name)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
