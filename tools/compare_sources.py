#!/usr/bin/env python3
"""Correctly compares the two source repos' On-function handler inventories.

The earlier audit used a regex that missed handlers nested under the ``<events>``
wrapper, which produced a bogus "5 missing handlers" list. This walks the parsed
XML properly and reports the true difference between:
  * repo_jcw87  -- the original author's repository
  * repo_badtime -- the copy the project has been treating as authoritative
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPOS = {"jcw87": ROOT / "repo_jcw87", "badtime": ROOT / "repo_badtime"}
DATA_JS = ROOT / "c2-sans-fight" / "data.js"


def on_function_names(sheet: pathlib.Path) -> list[str]:
    root = ET.parse(sheet).getroot()
    names: list[str] = []
    for block in root.iter("event-block"):
        conds = block.find("conditions")
        if conds is None:
            continue
        for cond in conds.findall("condition"):
            if cond.get("name") != "On function":
                continue
            for par in cond.findall("param"):
                if par.get("id") == "0":
                    nm = (par.text or "").strip().strip('"')
                    if nm:
                        names.append(nm)
    return names


def inventory(repo: pathlib.Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sheet in sorted((repo / "Event sheets").glob("*.xml")):
        for nm in on_function_names(sheet):
            counts[nm] = counts.get(nm, 0) + 1
    return counts


def main() -> int:
    inv = {k: inventory(v) for k, v in REPOS.items()}
    for k, v in inv.items():
        print(f"{k}: {len(v)} distinct On-function handlers across all sheets")

    jcw, bad = set(inv["jcw87"]), set(inv["badtime"])
    print()
    print("=" * 78)
    print("Handler set differences between the two source repos")
    print("=" * 78)
    print(f"  only in repo_jcw87 : {sorted(jcw - bad) or '(none)'}")
    print(f"  only in repo_badtime: {sorted(bad - jcw) or '(none)'}")

    print()
    print("=" * 78)
    print("Handlers whose occurrence count differs")
    print("=" * 78)
    diffs = False
    for name in sorted(jcw | bad):
        a, b = inv["jcw87"].get(name, 0), inv["badtime"].get(name, 0)
        if a != b:
            diffs = True
            print(f"  {name:<26} jcw87={a:<4} badtime={b}")
    if not diffs:
        print("  (none)")

    # Which handlers does the compiled export actually implement?
    print()
    print("=" * 78)
    print("Compiled export (c2-sans-fight/data.js) coverage")
    print("=" * 78)
    data = DATA_JS.read_text(encoding="utf-8", errors="replace")
    all_names = sorted(jcw | bad)
    absent = [n for n in all_names if n not in data]
    print(f"  {len(all_names) - len(absent)}/{len(all_names)} handler names present in the build")
    print(f"  ABSENT: {absent or '(none)'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
