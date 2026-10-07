#!/usr/bin/env python3
"""Extracts the authoritative command handlers from the repo_badtime event
sheets: which sheet defines each On-function, its parameter count, and the raw
action list. Used to bring the nohit rasterizer in line with the real source
instead of the older compiled export.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHEETS = ROOT / "repo_badtime" / "Event sheets"

TARGETS = sys.argv[1:] or ["Angle", "GetHeartPos", "GasterBlaster", "RND", "SineBones", "DamagePlayer"]


def iter_event_blocks(root: ET.Element):
    for block in root.iter("event-block"):
        yield block


def handler_name(block: ET.Element) -> str | None:
    conds = block.find("conditions")
    if conds is None:
        return None
    for cond in conds.findall("condition"):
        if cond.get("name") != "On function":
            continue
        for param in cond.findall("param"):
            if param.get("id") == "0":
                return (param.text or "").strip().strip('"')
    return None


def describe_actions(block: ET.Element, indent: str = "      ") -> None:
    acts = block.find("actions")
    if acts is None:
        return
    for act in acts.findall("action"):
        aparams = []
        for param in act.findall("param"):
            aparams.append(f'{param.get("name")}={(param.text or "").strip()}')
        print(f"{indent}ACT[{act.get('type')}] {act.get('name')} :: {', '.join(aparams)}")


def describe_conditions(block: ET.Element, indent: str = "      ") -> None:
    conds = block.find("conditions")
    if conds is None:
        return
    for cond in conds.findall("condition"):
        cparams = []
        for param in cond.findall("param"):
            cparams.append(f'{param.get("name")}={(param.text or "").strip()}')
        print(f"{indent}COND[{cond.get('type')}] {cond.get('name')} :: {', '.join(cparams)}")


def main() -> int:
    for sheet in sorted(SHEETS.glob("*.xml")):
        try:
            tree = ET.parse(sheet)
        except ET.ParseError as exc:
            print(f"!! {sheet.name}: parse error {exc}")
            continue
        root = tree.getroot()
        for block in iter_event_blocks(root):
            name = handler_name(block)
            if not name:
                continue
            if name not in TARGETS:
                continue
            sid = block.get("sid")
            print("=" * 78)
            print(f"{name}   [sheet={sheet.name} sid={sid}]")
            print("=" * 78)
            describe_conditions(block)
            describe_actions(block)
            # One level of sub-events carries the real logic in this project.
            subs = block.find("sub-events")
            if subs is not None:
                for i, sub in enumerate(subs.findall("event-block")):
                    print(f"    -- sub-event {i} --")
                    describe_conditions(sub)
                    describe_actions(sub)
                    subs2 = sub.find("sub-events")
                    if subs2 is not None:
                        for j, sub2 in enumerate(subs2.findall("event-block")):
                            print(f"        -- sub-sub {j} --")
                            describe_conditions(sub2)
                            describe_actions(sub2)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
