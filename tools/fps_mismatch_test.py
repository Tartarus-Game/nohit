#!/usr/bin/env python3
"""Isolates WHY 60 Hz failed while 30 Hz succeeded.

Three different rates are in play and they were never checked against each other:

  1. the attack script timeline -- authored at 30 Hz (`constants.FPS`), since the
     parser does `frame = round(clock * 30)` and the CSV timestamps are multiples
     of 1/30 s (0.2 s -> frame 6)
  2. the hazard tensor -- built by the rasterizer at `RasterizerConfig.FPS`,
     also 30 Hz, indexed by timeline frame
  3. the dynamics step -- this is the only one that was 60 Hz

The solver indexes the tensor as `B_hazard[t + 1]`, i.e. it assumes ONE model
step == ONE tensor frame. That held only while the model was at 30 Hz. At 60 Hz
the model advanced two steps per tensor frame, so it walked the danger sequence
at half speed and skipped every other hazard frame -- a mismatch bug, not a
precision effect.

This test bakes the tensor at the SAME rate as the model for both 30 and 60 Hz.
If 60 Hz then behaves like 30 Hz, the failure was the mismatch. If 60 Hz is
still worse, the model step itself is at fault.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.baker.rasterizer import RasterizerConfig, rasterize_timeline  # noqa: E402
from nohit.baker.parser import parse_csv_timeline  # noqa: E402
from nohit.common.types import BakeResult  # noqa: E402
from nohit.engine.solver import solve_lattice_dp  # noqa: E402

GAME = Path(__file__).resolve().parent.parent / "c2-sans-fight"


def bake_at(csv: Path, fps: int, T: int) -> BakeResult:
    """Bake with the timeline, the tensor AND the step all at `fps`."""
    cmds = parse_csv_timeline(csv, fps=fps)
    cfg = RasterizerConfig(T=T, W=0, H=0, auto_size=True, FPS=fps)
    res = rasterize_timeline(cmds, config=cfg, T=T)
    meta = dict(res.metadata)
    # dynamics divides v_walk by MODEL_FPS, so scale it to keep the real
    # 150 px/s stride at this fps.
    meta["v_walk"] = 150.0 * (30.0 / fps) * (fps / 30.0) * (30.0 / 30.0)
    meta["v_walk"] = 150.0
    meta["v_jump"] = 180.0
    meta["physics_mode"] = "c2"
    meta["soul_size"] = (4, 4)
    return BakeResult(
        B_hazard=res.O,
        platform_table=res.platform_table,
        initial_state=res.initial_heart_pos,
        metadata=meta,
    )


def main() -> int:
    import nohit.engine.dynamics as D

    wave = GAME / "sans_bonegap1.csv"
    saved = D.MODEL_FPS

    print(f"{'模型fps':>8}{'张量fps':>9}{'T':>6}{'deadlock':>10}{'at':>6}{'peak':>9}")
    print("-" * 50)

    for model_fps in (30, 60):
        D.MODEL_FPS = model_fps
        for tensor_fps in (30, 60):
            T = int(6.6 * model_fps) + 1
            bake = bake_at(wave, tensor_fps, T)
            try:
                sol = solve_lattice_dp(bake)
                print(f"{model_fps:>8}{tensor_fps:>9}{T:>6}{str(sol.is_deadlock):>10}"
                      f"{str(sol.deadlock_frame):>6}{sol.stats.peak_alive_states:>9}")
            except Exception as exc:  # noqa: BLE001
                print(f"{model_fps:>8}{tensor_fps:>9}{T:>6}   ERROR {type(exc).__name__}: {exc}")

    D.MODEL_FPS = saved
    print()
    print("解读: 若 (model=60, tensor=60) 与 (model=30, tensor=30) 结论一致,")
    print("      则之前 60 Hz 的失败是『模型步长与危险张量频率不一致』造成的,")
    print("      而不是 60 Hz 精度更高或更低。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
