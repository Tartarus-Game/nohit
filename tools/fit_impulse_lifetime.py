#!/usr/bin/env python3
"""Derives the jump's impulse lifetime from the isolated live measurement.

Isolated run (heart settled 40 ticks on the floor at abs y ~= 377.89, then UP
held for 24 engine ticks; three repeats gave apex 4.49 / 3.00 / 4.50 px):

    k=1  dy = -180.00   VPad.Up = 1  LastUp = 0   <- impulse lands
    k=2  dy = -179.26   VPad.Up = 1  LastUp = 1   <- pure gravity (0.74/tick)
    k=3  dy = -178.51   VPad.Up = 1  LastUp = 1
    k=4  dy =  -28.11   VPad.Up = 0  LastUp = 1   <- cutoff fires

So the impulse is NOT clamped on the frame it is applied: it survives two full
gravity steps (k=2, k=3) and is only clamped at k=4. In 60 Hz model frames that
is roughly one frame of full impulse, then the clamp.

This script computes the apex for each candidate "impulse survives N model
frames, then clamp to c" and reports which reproduces the measured 3.0-4.5 px,
so the constant is chosen from the measurement rather than guessed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine.dynamics import MODEL_FPS  # noqa: E402

G = 180.0 / (MODEL_FPS * MODEL_FPS)      # 0.05 px/frame^2
V_JUMP = 180.0 / MODEL_FPS               # 3.0 px/frame
CUTOFF = 30.0 / MODEL_FPS                # 0.5 px/frame
LIVE = (3.00, 4.49, 4.50)


def apex(impulse_frames: int, cutoff: float) -> float:
    vy = V_JUMP
    y = 0.0
    peak = 0.0
    for f in range(60):
        if f == impulse_frames:
            vy = min(vy, cutoff)
        y += vy
        vy -= G
        peak = max(peak, y)
    return peak


def main() -> int:
    print(f"MODEL_FPS={MODEL_FPS}  v_jump={V_JUMP:.2f}  g={G:.4f}  cutoff={CUTOFF:.2f}")
    print(f"live apex (3 isolated runs): {LIVE}  -> mean {sum(LIVE) / len(LIVE):.2f} px\n")
    print(f"{'impulse frames':>15}{'cutoff':>9}{'apex px':>10}   vs live mean")
    for imp in range(0, 5):
        for cut in (CUTOFF, 0.6, 0.7, 0.8):
            a = apex(imp, cut)
            mean = sum(LIVE) / len(LIVE)
            mark = "  <== within 1 px" if abs(a - mean) <= 1.0 else ""
            print(f"{imp:>15}{cut:>9.2f}{a:>10.2f}{mark}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
