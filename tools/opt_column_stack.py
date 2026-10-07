#!/usr/bin/env python3
"""Drops the per-frame np.column_stack allocation in step_dynamics_batch.

Profiling the open-arena benchmark (T=150, peak ~13k states) at 30 Hz showed
np.column_stack at 78 ms and the five astype calls at 107 ms of a ~1 s solve,
all from rebuilding the returned state array every frame. Writing into a
preallocated int32 buffer instead removes the alloc plus 5 temporaries.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DYN = ROOT / "nohit" / "engine" / "dynamics.py"

text = DYN.read_text(encoding="utf-8")

old = """        return np.column_stack([next_x, next_y, next_vy, next_kappa, next_tau]).astype(np.int32)"""

new = """        # Write straight into one int32 buffer instead of np.column_stack +
        # .astype, which allocated a new array plus 5 temporaries every frame
        # (~180 ms of a 1 s open-arena solve at 30 Hz).
        out = np.empty((N, 5), dtype=np.int32)
        out[:, 0] = next_x
        out[:, 1] = next_y
        out[:, 2] = next_vy
        out[:, 3] = next_kappa
        out[:, 4] = next_tau
        return out"""

count = text.count(old)
text = text.replace(old, new)
DYN.write_text(text, encoding="utf-8")
print(f"replaced {count} occurrence(s)")
