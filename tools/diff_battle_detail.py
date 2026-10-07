#!/usr/bin/env python3
"""Answers two questions definitively:

1. WHAT did ``repo_badtime`` remove relative to the author's ``repo_jcw87``
   (the four event-blocks that exist only in jcw87), with full context?

2. WHICH source does the shipped build (``c2-sans-fight/data.js``) match?

For (2) the comparison uses the instance-variable initialisation values and the
computed condition parameters that Construct 2 bakes into data.js as plain
numbers. Those are behavioural fingerprints: e.g. jcw87 tints the blue heart at
``23.53`` while repo_badtime uses ``25``, and jcw87 compares ``BBoxBottom-2``
with ``>`` while repo_badtime uses ``<``.
"""

from __future__ import annotations

import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
JCW = ROOT / "repo_jcw87" / "Event sheets" / "Battle.xml"
BAD = ROOT / "repo_badtime" / "Event sheets" / "Battle.xml"
DATA = ROOT / "c2-sans-fight" / "data.js"

ONLY_JCW = [
    "336622092866585",
    "346193478372130",
    "530186312537819",
    "742535640295667",
]

# Behavioural fingerprints: a value that differs between the two sources, and
# whose presence in data.js identifies which source the build came from.
FINGERPRINTS = [
    ("blue-heart tint component", "23.53", "25"),
    ("bowl (vertical-from-below) Y expr", "BBoxBottom + 8.05", "BBoxTop + 8.05"),
    ("tint red component", "7.84", "0"),
    ("tint green component", "66.27", "66"),
]


def fmt(elem: ET.Element) -> str:
    out = []
    for p in elem.findall("param"):
        t = (p.text or "").strip()
        if t:
            out.append(f'{p.get("name")}={t}')
    return ", ".join(out)


def blocks_of(path: pathlib.Path) -> dict[str, ET.Element]:
    root = ET.parse(path).getroot()
    return {b.get("sid"): b for b in root.iter("event-block") if b.get("sid")}


def render(block: ET.Element, depth: int = 0, out: list[str] | None = None) -> list[str]:
    out = out if out is not None else []
    ind = "  " * depth
    conds = block.find("conditions")
    acts = block.find("actions")
    cl = [f'[{c.get("type")}] {c.get("name")} {{{fmt(c)}}}'
          for c in (conds.findall("condition") if conds is not None else [])]
    al = [f'[{a.get("type")}] {a.get("name")} {{{fmt(a)}}}'
          for a in (acts.findall("action") if acts is not None else [])]
    if cl:
        out.append(f"{ind}IF " + " AND ".join(cl))
    for a in al:
        out.append(f"{ind}   DO {a}")
    subs = block.find("sub-events")
    if subs is not None:
        for v in subs.findall("variable"):
            out.append(f"{ind}  VAR {v.get('name')} = {v.text!r} static={v.get('static')}")
        for sub in subs.findall("event-block"):
            render(sub, depth + 1, out)
    return out


def main() -> int:
    jcw_blocks = blocks_of(JCW)
    bad_blocks = blocks_of(BAD)

    print("=" * 78)
    print("Blocks present ONLY in repo_jcw87 (removed by repo_badtime)")
    print("=" * 78)
    for sid in ONLY_JCW:
        b = jcw_blocks.get(sid)
        if b is None:
            print(f"  sid={sid}: not found")
            continue
        print(f"\n  --- sid={sid} ---")
        for line in render(b, 2):
            print(line)

    print()
    print("=" * 78)
    print("Which source does the shipped build match?")
    print("=" * 78)
    data = DATA.read_text(encoding="utf-8", errors="replace")
    for label, jcw_val, bad_val in FINGERPRINTS:
        # data.js stores numbers bare; expression text is compiled away, so only
        # numeric fingerprints are usable directly.
        jcw_hits = len(re.findall(rf"(?<![\d.]){re.escape(jcw_val)}(?![\d])", data))
        bad_hits = len(re.findall(rf"(?<![\d.]){re.escape(bad_val)}(?![\d])", data))
        if jcw_val == bad_val:
            continue
        if not jcw_val.replace(".", "").isdigit() or not bad_val.replace(".", "").isdigit():
            print(f"  {label:<34} (text expression, not checkable numerically)")
            continue
        verdict = "ambiguous"
        if jcw_hits and not bad_hits:
            verdict = "matches repo_jcw87"
        elif bad_hits and not jcw_hits:
            verdict = "matches repo_badtime"
        print(
            f"  {label:<34} jcw87={jcw_val!r} hits={jcw_hits:<4} "
            f"badtime={bad_val!r} hits={bad_hits:<4} -> {verdict}"
        )

    # Also report the raw numeric constants that differ, for completeness.
    print()
    print("  note: constants that appear elsewhere in data.js give false hits; the")
    print("        authoritative comparison is the side-by-side block diff.")

    # Report added/removed counts for the record.
    print()
    print("=" * 78)
    print("Summary")
    print("=" * 78)
    print(f"  blocks only in repo_jcw87 : {len(set(jcw_blocks) - set(bad_blocks))}")
    print(f"  blocks only in repo_badtime: {len(set(bad_blocks) - set(jcw_blocks))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
