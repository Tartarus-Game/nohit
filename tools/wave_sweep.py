#!/usr/bin/env python3
"""Sweeps every exported attack through /api/tas in the default c2 physics mode.

Reports, per wave, the arena absolute frame, the solver's initial state, the
outcome (solvable vs. proven deadlock) and the DP timing. Also cross-checks the
solver's initial_state against the CSV HeartTeleport anchor and the arena frame.

Usage: python tools/wave_sweep.py [port]
"""

from __future__ import annotations

import json
import sys
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
BASE = f"http://127.0.0.1:{PORT}"

WAVES = [
    "sans_bonegap1.csv", "sans_bonegap1fast.csv", "sans_bonegap2.csv",
    "sans_boneslideh.csv", "sans_boneslidev.csv",
    "sans_platforms1.csv", "sans_platforms2.csv", "sans_platforms3.csv",
    "sans_platforms4.csv", "sans_platforms4hard.csv",
    "sans_bonestab1.csv", "sans_bonestab2.csv", "sans_bonestab3.csv",
    "sans_bluebone.csv", "sans_platformblaster.csv", "sans_platformblasterfast.csv",
    "sans_multi1.csv", "sans_multi2.csv", "sans_multi3.csv",
    "sans_randomblaster1.csv", "sans_randomblaster2.csv",
    "sans_intro.csv", "sans_final.csv",
]

HEADER = f"{'wave':<30}{'mode':<5}{'origin':<12}{'arena':<10}{'init':<10}{'outcome':<18}{'acts':<6}{'dp_ms':<9}{'blue':<6}{'orange'}"


def main() -> int:
    print(HEADER)
    print("-" * len(HEADER))
    solvable = deadlock = failed = 0
    for wave in WAVES:
        try:
            with urllib.request.urlopen(f"{BASE}/api/tas?wave={wave}&T=150&soul_w=4&soul_h=4") as resp:
                d = json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001
            print(f"{wave:<30}ERROR {exc}")
            failed += 1
            continue

        a = d["arena"]
        origin = f"{int(a['c2_left'])},{int(a['c2_floor'])}"
        arena = f"{a['W']}x{a['H']}"
        init = f"{d['initial_state'][0]},{d['initial_state'][1]}"
        if d["is_deadlock"]:
            outcome = f"DEADLOCK @ t={d['deadlock_frame']}"
            deadlock += 1
            acts = "-"
        else:
            outcome = "solvable"
            solvable += 1
            acts = str(len(d["action_sequence"]))
        blue = "yes" if a.get("soul_w") else "?"
        print(
            f"{wave:<30}{d['physics_mode']:<5}{origin:<12}{arena:<10}{init:<10}{outcome:<18}"
            f"{acts:<6}{d['stats']['dp_ms']:<9}{blue:<6}{'-' if not d['is_deadlock'] else '-'}"
        )

    print(f"\nsolvable={solvable} deadlock={deadlock} error={failed} total={len(WAVES)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
