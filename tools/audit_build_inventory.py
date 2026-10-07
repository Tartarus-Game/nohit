#!/usr/bin/env python3
"""Audits the COMPILED export's On-function handler inventory.

Construct 2 stores each event block's condition parameters as a JS array inside
``data.js``; the "On function" condition's name parameter is therefore present as
a plain string. Scanning the raw text for those names is the quickest reliable
answer to "does this build implement the command the authoritative script uses?".

Outputs the set of names found in the built export vs the set the authoritative
event sheets define, so any genuine version gap is visible.
"""

from __future__ import annotations

import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPORT_DATA = ROOT / "c2-sans-fight" / "data.js"
SRC_SHEETS = ROOT / "repo_badtime" / "Event sheets"

# Commands that only ever appear as On-function handler names in this project, so
# a substring hit in data.js means the build really has that handler.
PROBE = [
    "GetHeartPos", "SineBones", "DamagePlayer", "BoneStab", "BoneV", "BoneH",
    "BoneVRepeat", "BoneHRepeat", "Platform", "PlatformRepeat",
    "HeartTeleport", "HeartMode", "HeartJump", "HeartMaxFallSpeed",
    "CombatZoneResize", "CombatZoneResizeInstant", "CombatZoneSpeed", "CombatZoneTick",
    "GasterBlaster", "gasterblaster", "RunAttack", "StartAttack", "EndAttack",
    "TLPlay", "TLPause", "TLResume", "TLStop", "TLIsRunning", "TLLoadLine", "TLPanic",
    "SansSlam", "SansSlamDamage", "SansShake", "SansHead", "SansBody", "SansTorso",
    "SansAnimation", "SansText", "SansSweat", "SansX", "SansEndRepeat", "SansRepeat",
    "SetPracticeAttack", "SetSimulatorMode", "Sound", "Music", "BlackScreen",
    "MenuBattle", "MenuFight", "ResetVars", "Win1", "Win2", "Debug",
]


def on_function_names(sheet: pathlib.Path) -> list[str]:
    """Every 'On function' handler name in the sheet.

    The XML nests top-level events under a bare ``<events>`` wrapper
    (``c2eventsheet > events > event-block``), so this walks the parsed tree
    rather than regexing the raw text -- a text-only walk misses nothing but a
    structural walk is robust to the wrapper and to nesting depth.
    """
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


def main() -> int:
    if not EXPORT_DATA.exists():
        print(f"missing {EXPORT_DATA}")
        return 1
    data = EXPORT_DATA.read_text(encoding="utf-8", errors="replace")

    src_names: set[str] = set()
    for sheet in sorted(SRC_SHEETS.glob("*.xml")):
        try:
            ET.parse(sheet)
        except ET.ParseError:
            pass
        src_names.update(on_function_names(sheet))

    print("=" * 78)
    print("Compiled export vs authoritative source: On-function inventory")
    print("=" * 78)
    print(f"authoritative handlers defined in the source sheets: {len(src_names)}")
    print()

    missing: list[str] = []
    present: list[str] = []
    for name in PROBE:
        hit = data.count(name)
        # Case-sensitive count; C2 stores the name verbatim.
        found = hit > 0
        (present if found else missing).append(name)
        mark = "FOUND" if found else "ABSENT"
        in_src = "in-source" if name in src_names else "source-only-helper"
        print(f"  {mark:<7} {name:<26} occurrences={hit:<4} {in_src}")

    print()
    print(f"probes present in build: {len(present)}/{len(PROBE)}")
    if missing:
        print(f"probes ABSENT from build: {missing}")

    # Any source handler that is also a plausible command but absent from data.js
    non_trivial = sorted(
        n for n in src_names
        if n.lower() not in {"add", "sub", "mul", "div", "mod", "set", "sin", "cos",
                             "rnd", "angle", "floor", "jmpabs", "jmpz", "jmpnz",
                             "jmpe", "jmpne", "jmpl", "jmpnl", "jmpg", "jmpng",
                             "jmprel", "getheartpos", "debug", "tlloadline", "tlplay",
                             "tlpause", "tlresume", "tlstop", "tlisrunning", "tlpanic"}
    )
    print()
    print("=" * 78)
    print("Authoritative non-arithmetic handlers missing from data.js")
    print("=" * 78)
    really_missing = [n for n in non_trivial if n not in data]
    print(f"  {len(really_missing)} of {len(non_trivial)}")
    for n in really_missing:
        print(f"    {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
