#!/usr/bin/env python3
"""Verifies the 32-bit packed key round-trips exactly for both physics models.

Also reports WHICH field mismatches if it does not, so a layout regression is
immediately attributable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine import state as S  # noqa: E402

print(f"layout: X={S._X_BITS} Y=8 VY={S.VY_KEY_BITS} KAPPA=1 TAU={S._TAU_BITS} "
      f"-> {S._TAU_SHIFT + S._TAU_BITS} bits")
print(f"vy field [-{S.VY_KEY_BIAS}, {S.VY_KEY_MASK - S.VY_KEY_BIAS}]")
print()

cases = {
    "docs": dict(vys=range(-12, 9), kappas=(0, 1), taus=(0, 1, 7, 15)),
    # kappa is a SINGLE BIT in the layout: only 0 (airborne) and 1 (resting)
    # are representable, and the steppers only ever produce those two.
    # vy range == [-12.5, +3.0] px/frame * dynamics.VY_SCALE.
    "c2": dict(vys=range(-500, 121, 5), kappas=(0, 1), taus=(0,)),
}

for name, cfg in cases.items():
    xs, ys, vs, ks, ts = [], [], [], [], []
    for x in range(0, 349, 41):
        for y in range(0, 200, 23):
            for vy in cfg["vys"]:
                for k in cfg["kappas"]:
                    for tau in cfg["taus"]:
                        xs.append(x); ys.append(y); vs.append(vy); ks.append(k); ts.append(tau)
    arr = np.column_stack([xs, ys, vs, ks, ts]).astype(np.int32)
    pk = S.pack_states_array(arr)
    back = S.unpack_states_to_array(pk)

    fields = ["x", "y", "vy", "kappa", "tau"]
    bad = [f for i, f in enumerate(fields) if not np.array_equal(back[:, i], arr[:, i])]
    cells = len(set(zip(xs, ys, vs, ks, ts)))
    print(f"{name:>5}: states={len(arr):>7} unique_cells={cells:>7} distinct_keys={len(set(pk.tolist())):>7}")
    print(f"       mismatched fields: {bad or 'none'}")

    if "vy" in bad:
        i = int(np.argmax(back[:, 2] != arr[:, 2]))
        print(f"       first vy mismatch: in={arr[i, 2]} out={back[i, 2]}  (x={arr[i,0]} y={arr[i,1]} k={arr[i,3]} tau={arr[i,4]})")
    if "tau" in bad:
        i = int(np.argmax(back[:, 4] != arr[:, 4]))
        print(f"       first tau mismatch: in={arr[i, 4]} out={back[i, 4]} (mask allows 0..{(1 << S._TAU_BITS) - 1})")
    if "kappa" in bad:
        i = int(np.argmax(back[:, 3] != arr[:, 3]))
        print(f"       first kappa mismatch: in={arr[i, 3]} out={back[i, 3]} (only 0/1 representable)")
    print()

# scalar/vector agreement
print("scalar vs vector:")
ok = True
for st in [(174, 2, 120, 0, 3), (174, 2, -500, 1, 15), (96, 0, 0, 1, 0), (348, 113, -500, 0, 1)]:
    v = int(S.pack_states_array(np.array([st], dtype=np.int32))[0])
    sc = S.pack_state(*st)
    same = v == sc and S.unpack_state(sc) == st
    ok &= same
    print(f"  {st} -> key={sc} -> {S.unpack_state(sc)}  {'OK' if same else 'MISMATCH'}")
print(f"all OK: {ok}")
