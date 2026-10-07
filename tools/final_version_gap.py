#!/usr/bin/env python3
"""Final version-gap determination.

Compares the Timeline executor handler sets between the two source repos and
checks, precisely, which of those handler names the compiled build contains.
"""

from __future__ import annotations

import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "c2-sans-fight" / "data.js"


def handler_names(sheet: pathlib.Path) -> set[str]:
    root = ET.parse(sheet).getroot()
    out: set[str] = set()
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
                        out.add(nm)
    return out


def main() -> int:
    tl_a = handler_names(ROOT / "repo_jcw87" / "Event sheets" / "Timeline.xml")
    tl_b = handler_names(ROOT / "repo_badtime" / "Event sheets" / "Timeline.xml")

    print("=" * 78)
    print("Timeline executor handlers")
    print("=" * 78)
    print(f"  repo_jcw87   : {len(tl_a)}")
    print(f"  repo_badtime : {len(tl_b)}")
    print(f"  identical    : {tl_a == tl_b}")
    if tl_a - tl_b:
        print(f"  only jcw87   : {sorted(tl_a - tl_b)}")
    if tl_b - tl_a:
        print(f"  only badtime : {sorted(tl_b - tl_a)}")

    data = DATA.read_text(encoding="utf-8", errors="replace")

    print()
    print("=" * 78)
    print("Which Timeline handlers does the compiled build contain?")
    print("=" * 78)
    print("  (a bare substring hit is a strong signal for these distinct names;")
    print("   a quoted hit is definitive for the JSON-string form C2 emits)")
    print()
    missing: list[str] = []
    for name in sorted(tl_b | tl_a):
        bare = len(re.findall(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", data))
        quoted = data.count(f'"{name}"')
        flag = "OK " if bare else "MISSING"
        if not bare:
            missing.append(name)
        print(f"  {flag} {name:<16} bare={bare:<4} quoted={quoted}")

    print()
    print(f"handlers absent from the build: {missing or '(none)'}")

    # How often do the authoritative scripts use each missing handler?
    print()
    print("=" * 78)
    print("Usage of any missing handler in the authoritative attack scripts")
    print("=" * 78)
    for name in missing:
        total = 0
        files: dict[str, int] = {}
        for csv in sorted((ROOT / "repo_badtime" / "Files").glob("sans_*.csv")):
            try:
                text = csv.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            n = len(re.findall(rf",\s*{re.escape(name)}\s*,", text, re.IGNORECASE))
            if n:
                files[csv.name] = n
                total += n
        print(f"  {name}: {total} uses  {files if files else ''}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
