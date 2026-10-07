#!/usr/bin/env python3
"""Dumps the authoritative StartAttack / attack-loading chain so a specific
attack can be launched without the (missing-in-this-build) practice-menu UI.

Prints Battle.xml's StartAttack, RunAttack, and any AttackLoader handlers that
decide which CSV is fetched, in document order.
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


def blocks(node):
    subs = node.find("sub-events")
    return subs.findall("event-block") if subs is not None else []


def render(block, path, out, depth=0, limit=4):
    if depth > limit:
        return
    ind = "  " * depth
    idx = ".".join(map(str, path))
    conds = block.find("conditions")
    cl = [f'[{c.get("type")}] {c.get("name")} {{{fmt(c)}}}' for c in (conds.findall("condition") if conds is not None else [])]
    acts = block.find("actions")
    al = [f'[{a.get("type")}] {a.get("name")} {{{fmt(a)}}}' for a in (acts.findall("action") if acts is not None else [])]
    if cl:
        out.append(f"{ind}{idx} IF " + " AND ".join(cl))
    for a in al:
        out.append(f"{ind}     DO {a}")
    subs = block.find("sub-events")
    if subs is not None:
        for v in subs.findall("variable"):
            out.append(f"{ind}  {idx}.v VAR {v.get('name')} = {v.text!r} static={v.get('static')}")
        for i, sub in enumerate(subs.findall("event-block")):
            render(sub, path + [i], out, depth + 1, limit)


def handler_of(block):
    conds = block.find("conditions")
    if conds is None:
        return None
    for c in conds.findall("condition"):
        if c.get("name") == "On function":
            for p in c.findall("param"):
                if p.get("id") == "0":
                    return (p.text or "").strip().strip('"')
    return None


def iter_blocks(node):
    """Yields every event-block in the subtree, in document order."""
    subs = node.find("sub-events")
    if subs is None:
        return
    for block in subs.findall("event-block"):
        yield block
        yield from iter_blocks(block)


def main() -> int:
    wants = set(sys.argv[1:] or ["StartAttack", "RunAttack", "AttackLoadFinished", "MenuCustomRun", "MenuCustomSelect"])
    for sheet_name in ("Battle.xml", "AttackLoader.xml"):
        sheet = SHEETS / sheet_name
        if not sheet.exists():
            continue
        root = ET.parse(sheet).getroot()
        print("=" * 78)
        print(sheet_name)
        print("=" * 78)
        found = 0
        for group in root.iter("event-group"):
            title = group.get("title") or ""
            for i, block in enumerate(iter_blocks(group)):
                name = handler_of(block)
                if name not in wants:
                    continue
                found += 1
                print(f"\n######## {sheet_name} :: group {title!r} :: On function {name!r} ########")
                out: list[str] = []
                render(block, [i], out)
                print("\n".join(out))
        if found == 0:
            print("  (no matching handlers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
