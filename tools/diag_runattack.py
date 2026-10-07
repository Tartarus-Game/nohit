#!/usr/bin/env python3
"""Diagnostic: why does the recursive handler walk miss RunAttack?"""

from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
p = ROOT / "repo_badtime" / "Event sheets" / "Battle.xml"
txt = p.read_text(encoding="utf-8")

print("raw 'RunAttack' occurrences:", txt.count("RunAttack"))
print("raw 'On function' occurrences:", txt.count('name="On function"'))

root = ET.parse(p).getroot()
blocks = list(root.iter("event-block"))
print("event-blocks (iter):", len(blocks))

onfn = []
for b in blocks:
    conds = b.find("conditions")
    if conds is None:
        continue
    for c in conds.findall("condition"):
        if c.get("name") == "On function":
            name = None
            for par in c.findall("param"):
                if par.get("id") == "0":
                    name = (par.text or "").strip().strip('"')
            onfn.append(name)

print("On-function conditions (iter):", len(onfn))
print("RunAttack present in that list:", "RunAttack" in onfn)

# Where does RunAttack live structurally?
for b in blocks:
    conds = b.find("conditions")
    if conds is None:
        continue
    for c in conds.findall("condition"):
        if c.get("name") == "On function":
            for par in c.findall("param"):
                if par.get("id") == "0" and (par.text or "").strip().strip('"') == "RunAttack":
                    # find the nearest ancestor event-group by walking up is not
                    # supported, so report the parent chain via a manual walk
                    print("found RunAttack block sid=", b.get("sid"))
                    print("  parent tag:", "<unknown - ET has no parent>")

# Manual structural walk from the root to see container tags
def walk(node, depth=0, path=""):
    if depth > 8:
        return
    tag = node.tag
    title = node.get("title") or node.get("name") or ""
    here = f"{path}/{tag}"
    if tag in ("event-group", "event-block", "sub-events", "events"):
        subs = node.find("sub-events")
        for i, child in enumerate(list(node)):
            walk(child, depth + 1, here)
        # also descend into <events>
        ev = node.find("events")
        if ev is not None:
            walk(ev, depth + 1, here)
    return

# Simpler: report all distinct container tag paths that contain an On function
def collect(node, chain):
    tag = node.tag
    if tag == "condition" and node.get("name") == "On function":
        for par in node.findall("param"):
            if par.get("id") == "0":
                nm = (par.text or "").strip().strip('"')
                if nm == "RunAttack":
                    print("RunAttack chain:", " > ".join(chain))
    for child in list(node):
        collect(child, chain + [child.tag if child.tag != "event-block" else "block"])

collect(root, [root.tag])
print()
print("distinct On-function names via iter:", sorted(set(n for n in onfn if n))[:60])
