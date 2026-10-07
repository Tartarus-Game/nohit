#!/usr/bin/env python3
"""One-shot patch: widen the packed vy field to 11 bits and shrink tau to 3.

Rationale: the 10-bit vy field forced VY_SCALE = 16, which quantised the
0.05 px/frame^2 gravity step up to 0.0625 (+25%). That made the planner's jump
peak 21 px against the engine's measured 72 px. 11 bits allows VY_SCALE = 128
(gravity step quantised to 0.046875, -6%).
"""

from __future__ import annotations

import pathlib

PATH = pathlib.Path(__file__).resolve().parent.parent / "nohit" / "engine" / "state.py"
text = PATH.read_text(encoding="utf-8")

subs = [
    ("VY_KEY_BITS: int = 10", "VY_KEY_BITS: int = 11"),
    ("VY_KEY_BIAS: int = 200", "VY_KEY_BIAS: int = 1600"),
    (
        "((int(tau_val) & 0x0F) << _TAU_SHIFT)",
        "((int(tau_val) & ((1 << _TAU_BITS) - 1)) << _TAU_SHIFT)",
    ),
    ("tau = (p >> _TAU_SHIFT) & 0x0F", "tau = (p >> _TAU_SHIFT) & ((1 << _TAU_BITS) - 1)"),
    (
        "((tau.astype(np.uint32) & np.uint32(0x0F)) << np.uint32(_TAU_SHIFT))",
        "((tau.astype(np.uint32) & np.uint32((1 << _TAU_BITS) - 1)) << np.uint32(_TAU_SHIFT))",
    ),
    (
        "tau = ((p >> np.uint32(_TAU_SHIFT)) & np.uint32(0x0F)).astype(np.int32)",
        "tau = ((p >> np.uint32(_TAU_SHIFT)) & np.uint32((1 << _TAU_BITS) - 1)).astype(np.int32)",
    ),
]

for old, new in subs:
    if old not in text:
        print(f"  !! not found: {old[:60]}")
    text = text.replace(old, new)

PATH.write_text(text, encoding="utf-8")
print("patched", PATH)
