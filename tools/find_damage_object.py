#!/usr/bin/env python3
"""Finds which object the damage routine actually tests for collision.

VERIFY_A measured that a pinned heart at (320, 360) takes damage, and that at that
position:
    t65 (the 4x4 "playerhitbox" sprite) bbox [318,358,322,362] -> 0 bone overlaps
    t55 (the heart sprite, 16x16)        bbox [312,352,328,368] -> overlaps bones

So the engine must be testing the heart sprite, not the 4x4 hitbox. This script
locates the collision test in the compiled event data so the model can use the
correct envelope instead of guessing.
"""

from __future__ import annotations

import re
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"


def main() -> int:
    data = (GAME / "data.js").read_text(encoding="utf-8", errors="ignore")

    # C2 stores object references in getObjectRefTable(); find which index maps
    # to which type name, then look for collision conditions referencing them.
    print("--- object reference table (name -> index) ---")
    ref = re.search(r"getObjectRefTable\s*=\s*function\s*\(\)\s*\{\s*return\s*\[(.*?)\];",
                    (GAME / "c2runtime.js").read_text(encoding="utf-8", errors="ignore"), re.S)
    if ref:
        entries = ref.group(1)
        for m in re.finditer(r'"(\w+)"', entries):
            pass
        names = re.findall(r'"(\w+)"', entries)
        for n in ("t55", "t65", "t31", "t14"):
            if n in names:
                print(f"    {n} -> index {names.index(n)}")
    print()

    # Look for the OnCollision-style conditions mentioning the heart/hitbox.
    print("--- occurrences of t65 / playerhitbox in data.js ---")
    for pat in ("t65", "playerhitbox", "playerheart"):
        hits = [m.start() for m in re.finditer(re.escape(pat), data)]
        print(f"  {pat}: {len(hits)} hit(s)")
    print()

    # The FVF variant has a known number of DamagePlayer paths; list them so we
    # can see which collision object each one uses.
    print("--- DamagePlayer call sites (Battle sheet) ---")
    battle = GAME.parent / "repo_badtime" / "Event sheets" / "Battle.xml"
    if battle.is_file():
        txt = battle.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"DamagePlayer", txt):
            s = max(0, m.start() - 900)
            ctx = txt[s:m.start() + 60]
            # find the nearest preceding object name
            objs = re.findall(r'name="Object"[^>]*>([^<]+)<', ctx)
            conds = re.findall(r'<condition[^>]*name="([^"]+)"[^>]*>(.{0,400}?)</condition>',
                               ctx, re.S)
            last_obj = objs[-1] if objs else "?"
            print(f"  @{m.start()}  preceding Object param = {last_obj!r}")
            for cn, body in conds[-2:]:
                body1 = " ".join(body.split())[:150]
                print(f"       cond {cn!r}: {body1}")
    else:
        print("  (Battle.xml not found)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
