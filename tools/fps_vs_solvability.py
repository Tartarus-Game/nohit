#!/usr/bin/env python3
"""Does the solver's step size (frame rate) decide solvability for bonegap1?

The heart needs to cross ~103 px of open space while bones sweep at 6 px/frame.
With a 5 px/frame stride (30 Hz) it gets ~20 samples across that gap; with
2.5 px/frame (60 Hz) it gets ~41. This test sweeps the stride and reports which
values find a route, to settle the 30 fps vs 60 fps question with data.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"
HEARTSPEED = 150.0   # px/s, authoritative
JUMP = 180.0         # px/s


def main() -> int:
    print("步长 = HEARTSPEED / fps  (权威 150 px/s)")
    print(f"{'fps':>5}{'步长(px/帧)':>13}{'重力(px/帧²)':>15}{'T':>6}{'deadlock':>10}{'at':>6}{'peak':>9}")
    print("-" * 66)

    for fps in (30, 60, 120):
        step = HEARTSPEED / fps
        g_frame = 180.0 / (fps * fps)
        T = int(6.6 * fps) + 1

        bake = bake_cspace(
            GAME / "sans_bonegap1.csv",
            T=T,
            auto_size=True,
            soul_w=4,
            soul_h=4,
            physics_mode="c2",
        )
        # Override the step/jump scaling the solver uses: metadata v_walk/v_jump
        # are px/s and dynamics divides by 60, so pass fps-scaled values to make
        # the effective stride HEARTSPEED/fps.
        bake.metadata["v_walk"] = HEARTSPEED * (60.0 / fps)
        bake.metadata["v_jump"] = JUMP * (60.0 / fps)

        try:
            sol = solve_lattice_dp(bake)
            print(f"{fps:>5}{step:>13.1f}{g_frame:>15.3f}{T:>6}"
                  f"{str(sol.is_deadlock):>10}{str(sol.deadlock_frame):>6}{sol.stats.peak_alive_states:>9}")
        except Exception as exc:  # noqa: BLE001
            print(f"{fps:>5}{step:>13.1f}{g_frame:>15.3f}{T:>6}   ERROR {type(exc).__name__}: {exc}")

    print()
    print("说明: 步长通过 metadata v_walk 注入, 使每帧位移 == HEARTSPEED/fps,")
    print("      与真机 150 px/s 的时间积分一致; T 按 6.6 秒脚本时长换算。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
