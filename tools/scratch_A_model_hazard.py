"""scratch_A_model_hazard.py -- query model B_hazard at the live-measured positions.

Read-only measurement helper for VERIFY_A. Does NOT modify any project file.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nohit.baker.dilator import bake_cspace  # noqa: E402

GAME = ROOT / "c2-sans-fight"
WAVE = "sans_bonegap1"

ABS_X = [170, 260, 320, 396, 466]
LOCAL_X = [x - 146 for x in ABS_X]
LIVE_DANGER_PCT = {24: 19.5, 114: 15.1, 174: 14.7, 250: 15.9, 320: 11.8}


def runs_of(flags):
    """[start, end] inclusive runs of True."""
    out = []
    s = None
    for i, v in enumerate(flags):
        if v and s is None:
            s = i
        elif not v and s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(flags) - 1))
    return out


def main() -> int:
    bake = bake_cspace(GAME / f"{WAVE}.csv", T=500, auto_size=True,
                       soul_w=4, soul_h=4, physics_mode="c2")
    B = bake.B_hazard
    T, H, W = B.shape
    md = bake.metadata or {}
    AFR = int(md.get("attack_duration_frames") or 397)
    print("=" * 78)
    print(f"{WAVE}: B_hazard (T,H,W)={B.shape} density={B.mean():.5f} initial_state={bake.initial_state}")
    print(f"attack_duration_frames={AFR}  (model comparison horizon)")
    print("=" * 78)

    print(f"{'absX':>6} {'localX':>7} {'row0_%@AFR':>11} {'row0_%@500':>11} {'live%@floor':>12} {'row18_%@AFR':>12}")
    for lx in LOCAL_X:
        d0a = 100 * B[:AFR, 0, lx].mean()
        d0b = 100 * B[:, 0, lx].mean()
        d18 = 100 * B[:AFR, 18, lx].mean()
        print(f"{lx + 146:>6} {lx:>7} {d0a:>11.2f} {d0b:>11.2f} {LIVE_DANGER_PCT[lx]:>12.1f} {d18:>12.2f}")
    print("=" * 78)

    # exact danger schedule per x at floor row
    print("model danger intervals at ROW 0 (floor) over frames 0..AFR-1")
    for lx in LOCAL_X:
        f = B[:AFR, 0, lx]
        r = runs_of(f)
        print(f"  localX={lx:>3} absX={lx + 146:>3}: {len(r)} runs, total {int(f.sum())} frames "
              f"({100 * f.mean():.1f}%)")
        print(f"      {r}")
    print("=" * 78)

    # safe-band check at row 18 for every x
    print("row 18 (abs y=360) danger frames per x over full T:")
    for lx in LOCAL_X:
        print(f"  localX={lx:>3}: {int(B[:, 18, lx].sum())} dangerous frames out of {T}")
    # is row 18 safe for ALL x?
    print(f"row18 safe for all {W} columns over full T: {not B[:, 18, :].any()}")
    print(f"row16-22 safe for all columns over full T: {not B[:, 16:23, :].any()}")
    print(f"row0 (floor) ever dangerous anywhere: {bool(B[:, 0, :].any())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
