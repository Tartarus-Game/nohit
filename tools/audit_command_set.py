#!/usr/bin/env python3
"""Audits the authoritative Timeline executor command set (repo_badtime source)
against what the nohit parser/rasterizer actually implements, and reports which
command names appear in the source attack scripts but are unhandled.
"""

from __future__ import annotations

import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "repo_badtime"
EXPORT = ROOT / "c2-sans-fight"

TIMELINE = SRC / "Event sheets" / "Timeline.xml"
BATTLE = SRC / "Event sheets" / "Battle.xml"


def on_function_names(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.findall(
        r'<condition id="0" name="On function"[^>]*>\s*<param id="0" name="Name">&quot;([^&]+)&quot;</param>',
        text,
    )


def command_usage(folder: pathlib.Path) -> collections.Counter:
    usage: collections.Counter = collections.Counter()
    for csv in sorted(folder.glob("sans_*.csv")):
        for line in csv.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = [x.strip() for x in line.split(",")]
            if len(parts) > 1 and parts[1]:
                usage[parts[1].lower()] += 1
    return usage


def main() -> int:
    tl_names = sorted(set(on_function_names(TIMELINE)))
    battle_names = sorted(set(on_function_names(BATTLE)))

    print("=" * 78)
    print("Timeline.xml 'On function' handlers (authoritative executor command set)")
    print("=" * 78)
    print(f"  ({len(tl_names)} distinct)")
    for n in tl_names:
        print("   ", n)

    print()
    print("=" * 78)
    print("Battle.xml 'On function' handlers")
    print("=" * 78)
    print(f"  ({len(battle_names)} distinct)")
    for n in battle_names:
        print("   ", n)

    src_usage = command_usage(SRC / "Files")
    exp_usage = command_usage(EXPORT)

    print()
    print("=" * 78)
    print("Command usage across sans_*.csv")
    print("=" * 78)
    only_src = sorted(set(src_usage) - set(exp_usage))
    only_exp = sorted(set(exp_usage) - set(src_usage))
    print(f"  source-only commands: {only_src}")
    print(f"  export-only commands: {only_exp}")

    handlers = {n.lower() for n in tl_names} | {n.lower() for n in battle_names}
    # Commands tagged in the CSV are matched case-insensitively by C2.
    unhandled = sorted(c for c in set(src_usage) | set(exp_usage) if c not in handlers and c not in {"", "endattack"})
    print()
    print("Commands present in CSVs but with NO matching On-function handler:")
    for c in unhandled:
        print(f"    {c:<28} src={src_usage.get(c, 0):<6} export={exp_usage.get(c, 0)}")
    if not unhandled:
        print("    (none)")

    print()
    print("=" * 78)
    print("Per-command counts (source vs export)")
    print("=" * 78)
    allc = sorted(set(src_usage) | set(exp_usage))
    for c in allc:
        flag = "   <-- DIFFERS" if src_usage.get(c, 0) != exp_usage.get(c, 0) else ""
        print(f"  {c:<28} src={src_usage.get(c, 0):<6} export={exp_usage.get(c, 0):<6}{flag}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
