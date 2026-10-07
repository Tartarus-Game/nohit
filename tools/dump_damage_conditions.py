#!/usr/bin/env python3
"""Prints the event-sheet conditions immediately preceding each DamagePlayer call.

The model dilates the hazard by the soul box (4x4, object `t65`, "playerhitbox").
VERIFY_A's live measurement says that is wrong: a heart pinned at abs (320, 360)
takes damage even though the 4x4 hitbox overlaps no bone, while the 16x16 heart
sprite bbox does overlap one.

This walks the ORIGINAL project's Battle.xml and dumps, for each DamagePlayer
call, every condition's Object parameter, so the collision primitive the engine
really uses is read straight from the source.
"""

from __future__ import annotations

import re
from pathlib import Path

BATTLE = Path(__file__).resolve().parent.parent / "repo_badtime" / "Event sheets" / "Battle.xml"


def cond_summary(body: str, attrs: str) -> str:
    name = re.search(r'name="([^"]*)"', attrs)
    obj = re.search(r'name="Object"\s*>([^<]*)<', body)
    iv = re.search(r'name="Instance variable"\s*>([^<]*)<', body)
    val = re.search(r'name="Value"\s*>([^<]*)<', body)
    parts = [f"cond={name.group(1) if name else '?'}"]
    if obj:
        parts.append(f"Object={obj.group(1)}")
    if iv:
        parts.append(f"IV={iv.group(1)}")
    if val:
        parts.append(f"Value={val.group(1)}")
    return "  ".join(parts)


def main() -> int:
    if not BATTLE.is_file():
        print(f"missing {BATTLE}")
        return 1
    text = BATTLE.read_text(encoding="utf-8", errors="replace")

    hits = [m.start() for m in re.finditer(r"DamagePlayer", text)]
    print(f"{len(hits)} DamagePlayer call site(s) in Battle.xml\n")
    for n, pos in enumerate(hits, 1):
        # Walk backwards to the enclosing event block
        start = text.rfind("<event ", 0, pos)
        if start < 0:
            start = max(0, pos - 3000)
        block = text[start:pos + 80]
        print(f"--- call #{n} @{pos} ---")
        for m in re.finditer(r"<condition([^>]*)>(.*?)</condition>", block, re.S):
            print("    " + cond_summary(m.group(2), m.group(1)))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
