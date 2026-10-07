#!/usr/bin/env python3
"""Structural diff of Battle.xml between repo_jcw87 (author's repo) and
repo_badtime (the newer copy), plus a map of which compiled build matches which
source.

Compares per event-block (keyed by sid) the normalised condition/action text, so
insertions, deletions and edits are all visible without the noise of XML
formatting.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
A = ROOT / "repo_jcw87" / "Event sheets" / "Battle.xml"
B = ROOT / "repo_badtime" / "Event sheets" / "Battle.xml"


def norm(elem: ET.Element) -> str:
    params = []
    for p in elem.findall("param"):
        params.append(f'{p.get("name")}={(p.text or "").strip()}')
    return f'[{elem.get("type")}] {elem.get("name")} {{' + ", ".join(params) + "}"


def block_signature(block: ET.Element) -> tuple[str, str, str]:
    conds = block.find("conditions")
    acts = block.find("actions")
    c = " AND ".join(norm(x) for x in (conds.findall("condition") if conds is not None else []))
    a = " | ".join(norm(x) for x in (acts.findall("action") if acts is not None else []))
    return (block.get("sid") or "?", c, a)


def indexed(path: pathlib.Path) -> dict[str, tuple[str, str, str]]:
    root = ET.parse(path).getroot()
    out: dict[str, tuple[str, str, str]] = {}
    for block in root.iter("event-block"):
        sid, c, a = block_signature(block)
        out[sid] = (c, a, "")
    return out


def handler_of_block(block: ET.Element) -> str | None:
    conds = block.find("conditions")
    if conds is None:
        return None
    for cond in conds.findall("condition"):
        if cond.get("name") == "On function":
            for par in cond.findall("param"):
                if par.get("id") == "0":
                    return (par.text or "").strip().strip('"')
    return None


def handler_map(path: pathlib.Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    m: dict[str, str] = {}
    for block in root.iter("event-block"):
        sid = block.get("sid")
        h = handler_of_block(block)
        if sid and h:
            m[sid] = h
    return m


def main() -> int:
    a, b = indexed(A), indexed(B)
    ha, hb = handler_map(A), handler_map(B)

    print("=" * 78)
    print("Battle.xml block-level diff  (repo_jcw87 -> repo_badtime)")
    print("=" * 78)
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    print(f"  blocks only in repo_jcw87   : {len(only_a)}")
    print(f"  blocks only in repo_badtime : {len(only_b)}")

    changed = [sid for sid in sorted(set(a) & set(b)) if a[sid] != b[sid]]
    print(f"  blocks present in both but EDITED: {len(changed)}")

    if only_b:
        print()
        print("  --- blocks added in repo_badtime ---")
        for sid in only_b:
            h = hb.get(sid, "(no handler)")
            print(f"    sid={sid}  handler={h}")
            c, act, _ = b[sid]
            if c:
                print(f"      IF {c}")
            print(f"      DO {act}")

    if only_a:
        print()
        print("  --- blocks removed in repo_badtime ---")
        for sid in only_a:
            print(f"    sid={sid}  handler={ha.get(sid, '(no handler)')}")

    if changed:
        print()
        print("  --- edited blocks ---")
        for sid in changed:
            h = ha.get(sid) or hb.get(sid) or "(no handler)"
            print(f"    sid={sid}  handler={h}")
            print(f"      jcw87   : IF {a[sid][0]}")
            print(f"                DO {a[sid][1]}")
            print(f"      badtime : IF {b[sid][0]}")
            print(f"                DO {b[sid][1]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
