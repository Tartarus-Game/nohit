#!/usr/bin/env python3
"""Diffs the authoritative attack scripts (repo_badtime/Files) against the
older compiled export (c2-sans-fight) and reports exactly which commands the
nohit pipeline must support for a faithful solve.

Output:
  * per-file identical / differs
  * command inventory used by the AUTHORITATIVE scripts
  * which of those the current parser+rasterizer handle
  * sample argument lines for the unhandled ones
"""

from __future__ import annotations

import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "repo_badtime" / "Files"
EXP = ROOT / "c2-sans-fight"

sys.path.insert(0, str(ROOT))

# Commands the rasterizer currently models (from nohit/baker/rasterizer.py).
HANDLED = {
    "combozoneresize", "combatzoneresize", "combatzoneresizeinstant",
    "heartteleport", "heartmode", "heartmaxfallspeed", "tlpause", "tlresume", "tlstop",
    "sansslam", "sansslamdamage",
    "bonev", "bonevrepeat", "boneh", "bonehrepeat", "bonestab",
    "platform", "platformrepeat",
    "sinebones",
    "gasterblaster",
    "endattack",
    # Non-geometric / presentational: intentionally ignored by the rasterizer.
    "sound", "sanshead", "sansbody", "sanstorso", "sansanimation", "sanssweat",
    "sanstext", "blackscreen", "sansx", "noeffects1", "noeffects2",
    "musicoff", "music", "sansendrepeat", "sansrepeat", "sansshake",
    "combatzonespeed", "combatzonetick", "damageplayer",
    # Timeline control flow (labels / jumps / arithmetic).
    "set", "add", "sub", "mul", "div", "mod", "floor", "sin", "cos", "rnd",
    "angle", "getheartpos", "jmpabs", "jmpz", "jmpnz", "jmpe", "jmpne",
    "jmpl", "jmpnl", "jmpg", "jmpng", "jmprel", "debug", "tlloadline",
    "tlplay", "tlpanic", "tlisrunning",
}


def load(path: pathlib.Path) -> list[list[str]]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        rows.append([c.strip() for c in line.split(",")])
    return rows


def main() -> int:
    print("=" * 78)
    print("Authoritative scripts: repo_badtime/Files  vs  export: c2-sans-fight")
    print("=" * 78)
    differing = []
    for csv in sorted(SRC.glob("sans_*.csv")):
        other = EXP / csv.name
        same = other.exists() and csv.read_bytes() == other.read_bytes()
        mark = "same" if same else "** DIFFERS **"
        if not same:
            size = other.stat().st_size if other.exists() else "missing"
            differing.append(csv.name)
            print(f"  {csv.name:<32} src={csv.stat().st_size:<7} export={size:<8} {mark}")
    print(f"\n  differing files: {differing or '(none)'}")

    usage: collections.Counter = collections.Counter()
    samples: dict[str, list[str]] = collections.defaultdict(list)
    for csv in sorted(SRC.glob("sans_*.csv")):
        for row in load(csv):
            if len(row) < 2 or not row[1]:
                continue
            cmd = row[1].lower()
            if cmd.startswith(":"):
                continue  # loop label
            usage[cmd] += 1
            if len(samples[cmd]) < 3:
                samples[cmd].append(f"{csv.name}:{','.join(row)}")

    print()
    print("=" * 78)
    print("Commands used by the AUTHORITATIVE scripts")
    print("=" * 78)
    unhandled = sorted(c for c in usage if c not in HANDLED)
    for c in sorted(usage):
        flag = "" if c in HANDLED else "   <== NOT MODELLED"
        print(f"  {c:<26} {usage[c]:<6}{flag}")

    print()
    print("=" * 78)
    print("NOT-MODELLED commands: samples")
    print("=" * 78)
    for c in unhandled:
        print(f"  --- {c} ({usage[c]} uses) ---")
        for s in samples[c]:
            print(f"      {s}")

    return 0 if not unhandled else 1


if __name__ == "__main__":
    sys.exit(main())
