#!/usr/bin/env python3
"""Quantifies how much of the authoritative attack scripts the current
literal-only rasterizer silently drops.

For every script this reports:
  * how many rows carry a control-flow / variable / RNG command
  * how many geometric commands have non-literal (variable) arguments
  * which of those would place geometry the rasterizer cannot resolve

Any row with a non-literal geometric argument is a row the solver currently
models WRONG (the rasterizer treats the literal text as 0), which is the
"motion model does not match the settlement model" failure mode.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "repo_badtime" / "Files"

CONTROL = {"set", "add", "sub", "mul", "div", "mod", "floor", "sin", "cos", "rnd",
           "angle", "getheartpos", "jmpabs", "jmpz", "jmpnz", "jmpe", "jmpne",
           "jmpl", "jmpnl", "jmpg", "jmpng", "jmprel", "debug", "tlloadline",
           "tlplay", "tlpanic", "tlisrunning", "tlpause", "tlresume", "tlstop"}

GEOMETRIC = {"bonev", "bonevrepeat", "boneh", "bonehrepeat", "bonestab",
             "platform", "platformrepeat", "sinebones", "gasterblaster",
             "heartteleport", "combatzoneresize", "combatzoneresizeinstant"}

NUMERIC = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$")
KEYWORDS = {"tlresume", "tlpause", "tlstop", "true", "false", "none", "-", ""}


def is_variable(token: str) -> bool:
    """True when the token is a runtime variable / computed expression rather
    than a numeric literal (or a non-numeric keyword the rasterizer ignores)."""
    t = token.strip()
    if t == "" or NUMERIC.match(t):
        return False
    if t.lower() in KEYWORDS:
        return False
    # `$name` is an explicit timeline variable; a bare identifier is a variable
    # reference too (Function.Param style names never appear in these scripts).
    return True


def main() -> int:
    header = (f"{'file':<30}{'rows':<7}{'ctrl':<7}{'geom':<7}{'geom-var':<10}{'geom-var-rows'}")
    print(header)
    print("-" * len(header))

    total_geom_var = 0
    worst: list[tuple[str, int]] = []
    samples: dict[str, list[str]] = {}

    for csv in sorted(SRC.glob("sans_*.csv")):
        rows = 0
        ctrl = 0
        geom = 0
        geom_var = 0
        for line in csv.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = [c.strip() for c in line.split(",")]
            if len(parts) < 2 or not parts[1]:
                continue
            rows += 1
            cmd = parts[1].lower()
            if cmd.startswith(":"):
                continue
            if cmd in CONTROL:
                ctrl += 1
            if cmd in GEOMETRIC:
                geom += 1
                args = parts[2:]
                if any(is_variable(a) for a in args if a.strip()):
                    geom_var += 1
                    if len(samples.get(csv.name, [])) < 3:
                        samples.setdefault(csv.name, []).append(
                            f"{cmd} :: {','.join(a for a in args if a.strip())}"
                        )
        total_geom_var += geom_var
        if geom_var:
            worst.append((csv.name, geom_var))
        print(f"{csv.name:<30}{rows:<7}{ctrl:<7}{geom:<7}{geom_var:<10}{'' if not geom_var else 'UNRESOLVABLE'}")

    print()
    print(f"total geometric rows with variable args (silently mis-modelled): {total_geom_var}")
    if worst:
        print("worst offenders:")
        for name, n in sorted(worst, key=lambda kv: -kv[1])[:10]:
            print(f"   {name:<30} {n}")
            for s in samples.get(name, [])[:2]:
                print(f"        {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
